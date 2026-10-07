#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Storage Manager Tool (NDX Data Lifecycle Management)
=====================================================
Multi-purpose tool for Network Data Extractor data management:
- init    : Setup database schema, connection check, and element seeding
- import  : Ingest filesystem runs into database (transparently extracts .zip/.tar.gz)
- export  : Export database runs back into standard filesystem hierarchy (protected with --overwrite)
- sync    : Bidirectional merge with configurable conflict strategies
- audit   : Deep consistency validation, row count cross-checks, and integrity audits
- backup  : Create compressed transactional backup snapshots of SQLite database
- restore : Safely restore database from backup with pre-check
"""

import argparse
import csv
import glob
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.storage.interface import StorageDriver
from core.storage.sqlite_driver import SQLiteDriver
from core.storage.filesystem_driver import FilesystemDriver
from core.storage.manager import StorageManager
from core.utils_shared import load_settings

# Terminal Colors
C_GREEN  = '\033[92m'
C_RED    = '\033[91m'
C_CYAN   = '\033[96m'
C_YELLOW = '\033[93m'
C_BOLD   = '\033[1m'
C_RESET  = '\033[0m'


def get_default_outbase() -> str:
    cfg = load_settings()
    return cfg.get("extractor", {}).get("output_base_dir", "infos")


def resolve_driver(outbase: str, db_path: Optional[str] = None) -> SQLiteDriver:
    cfg = load_settings()
    driver = SQLiteDriver(db_path=db_path)
    driver.initialize(outbase, cfg.get("storage", {}))
    return driver


# ============================================================================
# SUBCOMMAND: INIT
# ============================================================================
def handle_init(args):
    print(f"\n{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}         NETWORK DATA EXTRACTOR - DATABASE SETUP & INIT     {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")

    outbase = os.path.abspath(args.outbase)
    print(f"[*] Target Outbase       : {outbase}")
    driver = resolve_driver(outbase, args.db_path)
    print(f"[*] Target Database Path : {driver.db_path}")

    health = driver.health_check()
    print(f"  • Journal Mode         : {health['journal_mode']} {C_GREEN}[OK]{C_RESET}")
    print(f"  • Database Integrity   : {health['integrity']} {C_GREEN}[OK]{C_RESET}")
    print(f"  • Active Tables        : {health['tables_count']} tables provisioned {C_GREEN}[OK]{C_RESET}")

    # Seed Elements if requested
    elements_file = args.elements or "config/elements.cfg"
    seeded_count = 0
    if os.path.isfile(elements_file):
        print(f"[*] Seeding elements from: {elements_file}...")
        elements = []
        with open(elements_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(";")
                if len(parts) >= 2:
                    hostname = parts[0].strip()
                    ip = parts[1].strip()
                    cmd_key = parts[2].strip() if len(parts) >= 3 else ""
                    elements.append((hostname, ip, cmd_key))

        if elements and not args.dry_run:
            conn = driver._get_connection()
            with conn:
                conn.executemany(
                    """
                    INSERT INTO elements (hostname, ip, cmd_key, status, updated_at)
                    VALUES (?, ?, ?, 'ok', CURRENT_TIMESTAMP)
                    ON CONFLICT(hostname) DO UPDATE SET
                        ip = excluded.ip,
                        cmd_key = excluded.cmd_key,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    elements,
                )
            seeded_count = len(elements)
            print(f"  • Successfully seeded : {C_GREEN}{seeded_count}{C_RESET} network elements.")
        elif args.dry_run:
            print(f"  • [DRY-RUN] Would seed: {len(elements)} elements.")
    else:
        print(f"  • {C_YELLOW}Notice:{C_RESET} Elements file not found at {elements_file} (skipping seed).")

    print(f"\n{C_GREEN}[+] Database initialization completed successfully!{C_RESET}")
    print(f"[*] Database file is ready for production at: {driver.db_path}\n")


# ============================================================================
# SUBCOMMAND: IMPORT (Filesystem -> DB with transparent zip extraction)
# ============================================================================
def extract_raw_files_from_dir(collect_dir: str) -> List[Tuple[str, str, str, str, datetime]]:
    """Reads raw .txt files directly or unzips collect.zip / collect.tar.gz transparently."""
    results = []

    # 1. Uncompressed txt files
    txt_files = glob.glob(os.path.join(collect_dir, "*.txt"))
    for tf in txt_files:
        fname = os.path.basename(tf)
        parts = fname.split(".")
        if len(parts) >= 3:
            hostname = parts[0]
            ts_str = parts[1]
            cmd = ".".join(parts[2:-1]).replace(".", " ")
            try:
                dt = datetime.strptime(ts_str, "%d%m%y%H%M%S")
            except Exception:
                dt = datetime.now()
            try:
                with open(tf, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                results.append((hostname, "", cmd, content, dt))
            except Exception as e:
                print(f"      {C_RED}[!] Error reading {fname}: {e}{C_RESET}")

    # 2. Check for collect.zip archive (if collect/ had been compressed)
    zip_candidates = [
        os.path.join(collect_dir, "collect.zip"),
        os.path.join(os.path.dirname(collect_dir), "collect.zip"),
    ]
    for zpath in zip_candidates:
        if os.path.isfile(zpath):
            try:
                with zipfile.ZipFile(zpath, "r") as zf:
                    for name in zf.namelist():
                        if name.endswith(".txt"):
                            base_name = os.path.basename(name)
                            parts = base_name.split(".")
                            if len(parts) >= 3:
                                hostname = parts[0]
                                ts_str = parts[1]
                                cmd = ".".join(parts[2:-1]).replace(".", " ")
                                try:
                                    dt = datetime.strptime(ts_str, "%d%m%y%H%M%S")
                                except Exception:
                                    dt = datetime.now()
                                content = zf.read(name).decode("utf-8", errors="replace")
                                results.append((hostname, "", cmd, content, dt))
            except Exception as e:
                print(f"      {C_RED}[!] Error extracting {zpath}: {e}{C_RESET}")

    # 3. Check for collect.tar.gz archive
    tar_candidates = [
        os.path.join(collect_dir, "collect.tar.gz"),
        os.path.join(os.path.dirname(collect_dir), "collect.tar.gz"),
    ]
    for tpath in tar_candidates:
        if os.path.isfile(tpath):
            try:
                with tarfile.open(tpath, "r:*") as tf:
                    for member in tf.getmembers():
                        if member.name.endswith(".txt"):
                            base_name = os.path.basename(member.name)
                            parts = base_name.split(".")
                            if len(parts) >= 3:
                                hostname = parts[0]
                                ts_str = parts[1]
                                cmd = ".".join(parts[2:-1]).replace(".", " ")
                                try:
                                    dt = datetime.strptime(ts_str, "%d%m%y%H%M%S")
                                except Exception:
                                    dt = datetime.now()
                                fobj = tf.extractfile(member)
                                if fobj:
                                    content = fobj.read().decode("utf-8", errors="replace")
                                    results.append((hostname, "", cmd, content, dt))
            except Exception as e:
                print(f"      {C_RED}[!] Error extracting {tpath}: {e}{C_RESET}")

    return results


def handle_import(args):
    print(f"\n{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}         STORAGE MANAGER: IMPORT (Filesystem -> DB)         {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")

    outbase = os.path.abspath(args.outbase)
    source_dir = os.path.abspath(args.source) if args.source else os.path.join(outbase, "runs")
    driver = resolve_driver(outbase, args.db_path)

    if args.dry_run:
        print(f"[*] {C_YELLOW}Running in DRY-RUN mode (No changes will be written to DB){C_RESET}")

    print(f"[*] Source runs directory: {source_dir}")
    print(f"[*] Destination Database  : {driver.db_path}")

    if not os.path.isdir(source_dir):
        print(f"{C_RED}[!] Error: Source directory does not exist: {source_dir}{C_RESET}")
        return

    # Find run directories
    all_runs = sorted(glob.glob(os.path.join(source_dir, "20*_*")))
    selected_runs = []

    for rpath in all_runs:
        rid = os.path.basename(rpath)
        if args.run and rid != args.run:
            continue
        if args.since and rid[:8] < args.since.replace("-", ""):
            continue
        if args.until and rid[:8] > args.until.replace("-", ""):
            continue
        selected_runs.append((rid, rpath))

    print(f"[*] Found {len(selected_runs)} run(s) matching criteria.\n")

    imported_runs = 0
    skipped_runs = 0

    for rid, rpath in selected_runs:
        print(f"  • Processing run: {C_BOLD}{rid}{C_RESET} ... ", end="", flush=True)

        # Check if run already exists in DB
        existing_run = driver.get_run(rid)
        if existing_run and not args.force:
            print(f"{C_YELLOW}[SKIP - Already in DB]{C_RESET}")
            skipped_runs += 1
            continue

        try:
            rdate = datetime.strptime(rid, "%Y%m%d_%H%M%S")
        except Exception:
            rdate = datetime.now()

        collect_dir = os.path.join(rpath, "collect")
        resume_dir = os.path.join(rpath, "resume")
        conn_dir = os.path.join(rpath, "connections")
        ping_dir = os.path.join(rpath, "ping-matrix", "resume")

        # Extract Raw Output Files (supports .txt, .zip, .tar.gz)
        raw_items = extract_raw_files_from_dir(collect_dir)

        # Load Interfaces
        interfaces = []
        ifaces_json = os.path.join(resume_dir, "interfaces_all.json")
        ifaces_csv = os.path.join(resume_dir, "interfaces_all.csv")
        if os.path.isfile(ifaces_json):
            try:
                with open(ifaces_json, "r", encoding="utf-8") as f:
                    interfaces = json.load(f)
            except Exception:
                pass
        elif os.path.isfile(ifaces_csv):
            try:
                with open(ifaces_csv, "r", encoding="utf-8") as f:
                    interfaces = list(csv.DictReader(f, delimiter=";"))
            except Exception:
                pass

        # Load Topology Connections
        connections = []
        conn_csv = os.path.join(conn_dir, "topology.connections.csv")
        if os.path.isfile(conn_csv):
            try:
                with open(conn_csv, "r", encoding="utf-8") as f:
                    connections = list(csv.DictReader(f, delimiter=";"))
            except Exception:
                pass

        # Load Ping Tests
        ping_tests = []
        pjson = os.path.join(ping_dir, "ping_matrix_list.json")
        if not os.path.isfile(pjson):
            pjson = os.path.join(resume_dir, "ping_matrix_list.json")
        if os.path.isfile(pjson):
            try:
                with open(pjson, "r", encoding="utf-8") as f:
                    pdata = json.load(f)
                    ping_tests = pdata.get("data", [])
            except Exception:
                pass

        # Determine status: PARTIAL if critical pieces are missing
        is_partial = False
        missing_parts = []
        if not raw_items:
            missing_parts.append("raw_collect")
        if not interfaces:
            missing_parts.append("interfaces")
        if missing_parts:
            is_partial = True

        run_status = "PARTIAL" if is_partial else "SUCCESS"

        if args.dry_run:
            print(f"{C_GREEN}[DRY-RUN OK]{C_RESET} ({len(raw_items)} raw, {len(interfaces)} ifaces, {len(connections)} conns, {len(ping_tests)} pings)")
            imported_runs += 1
            continue

        # Ingest to DB inside a transaction
        conn = driver._get_connection()
        with conn:
            driver.create_run(rid, rdate, "import", {"source_path": rpath, "missing": missing_parts})

            for host, ip, cmd, text, dt in raw_items:
                driver.save_raw_collection(rid, host, ip, cmd, text, dt)

            if interfaces:
                driver.save_interfaces(rid, interfaces)

            if connections:
                driver.save_topology_connections(rid, connections)

            if ping_tests:
                driver.save_ping_tests(rid, ping_tests)

            driver.finish_run(
                rid,
                finished_at=datetime.now(),
                status=run_status,
                total_elements=len(set(i.get("element", "") for i in interfaces)),
                successful_elements=len(set(i.get("element", "") for i in interfaces)),
                failed_elements=0,
            )

        status_color = C_YELLOW if is_partial else C_GREEN
        print(f"{status_color}[{run_status}]{C_RESET} (Ingested: {len(raw_items)} raw, {len(interfaces)} ifaces, {len(connections)} conns)")
        imported_runs += 1

    print(f"\n{C_CYAN}------------------------------------------------------------{C_RESET}")
    print(f"[*] Import Summary: {C_GREEN}{imported_runs}{C_RESET} imported, {C_YELLOW}{skipped_runs}{C_RESET} skipped.")
    print(f"{C_CYAN}============================================================{C_RESET}\n")


# ============================================================================
# SUBCOMMAND: EXPORT (DB -> Filesystem with --overwrite protection)
# ============================================================================
def handle_export(args):
    print(f"\n{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}         STORAGE MANAGER: EXPORT (DB -> Filesystem)         {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")

    outbase = os.path.abspath(args.outbase)
    dest_dir = os.path.abspath(args.dest) if args.dest else os.path.join(outbase, "runs")
    driver = resolve_driver(outbase, args.db_path)

    if not args.run:
        print(f"{C_RED}[!] Error: --run <run_id> is required for export.{C_RESET}")
        return

    run_info = driver.get_run(args.run)
    if not run_info:
        print(f"{C_RED}[!] Error: Run '{args.run}' not found in database.{C_RESET}")
        return

    target_run_dir = os.path.join(dest_dir, args.run)

    # Protect against accidental overwrite by default
    if os.path.isdir(target_run_dir) and not args.overwrite:
        print(f"{C_RED}[!] Refusing to overwrite existing directory:{C_RESET} {target_run_dir}")
        print(f"    {C_YELLOW}Use --overwrite to force replacing existing files.{C_RESET}")
        return

    print(f"[*] Exporting Run : {C_BOLD}{args.run}{C_RESET}")
    print(f"[*] Destination   : {target_run_dir}")

    if args.dry_run:
        print(f"[*] {C_YELLOW}[DRY-RUN] Would export files to {target_run_dir}{C_RESET}")
        return

    fs_driver = FilesystemDriver(outbase=outbase, runs_dir=dest_dir)
    fs_driver.initialize(outbase, {})
    fs_driver.create_run(args.run, datetime.now(), "export")

    # 1. Export Interfaces
    interfaces = driver.get_interfaces(args.run)
    if interfaces:
        fs_driver.save_interfaces(args.run, interfaces)
        print(f"  • Exported {C_GREEN}{len(interfaces)}{C_RESET} interfaces to resume/interfaces_all.csv and .json")

    # 2. Export Topology Connections
    connections = driver.get_topology_connections(args.run)
    if connections:
        fs_driver.save_topology_connections(args.run, connections)
        print(f"  • Exported {C_GREEN}{len(connections)}{C_RESET} connections to connections/topology.connections.csv")

    # 3. Export Ping Tests
    pings = driver.get_ping_tests(args.run)
    if pings:
        fs_driver.save_ping_tests(args.run, pings)
        print(f"  • Exported {C_GREEN}{len(pings)}{C_RESET} ping tests to ping-matrix/resume/ping_matrix_list.csv")

    # 4. Export Raw Collections
    conn = driver._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT hostname, ip, command, collected_at FROM raw_collections WHERE run_id = ?", (args.run,))
    raw_meta = cursor.fetchall()

    for row in raw_meta:
        h, ip, cmd, cat = row["hostname"], row["ip"], row["command"], row["collected_at"]
        text = driver.get_raw_collection(args.run, h, cmd)
        if text:
            try:
                dt = datetime.strptime(cat, "%Y-%m-%d %H:%M:%S")
            except Exception:
                dt = datetime.now()
            fs_driver.save_raw_collection(args.run, h, ip, cmd, text, dt)

    if raw_meta:
        print(f"  • Exported {C_GREEN}{len(raw_meta)}{C_RESET} raw collection files to collect/*.txt")

    print(f"\n{C_GREEN}[+] Run {args.run} successfully exported to filesystem!{C_RESET}\n")


# ============================================================================
# SUBCOMMAND: SYNC / MERGE
# ============================================================================
def handle_sync(args):
    print(f"\n{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}         STORAGE MANAGER: SYNC & BIDIRECTIONAL MERGE        {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")

    outbase = os.path.abspath(args.outbase)
    strategy = args.conflict_strategy or "newest-wins"
    print(f"[*] Conflict Strategy : {C_BOLD}{strategy}{C_RESET}")

    driver = resolve_driver(outbase, args.db_path)
    runs_dir = os.path.join(outbase, "runs")

    db_runs = {r["run_id"]: r for r in driver.list_runs()}
    fs_runs = set(os.path.basename(p) for p in glob.glob(os.path.join(runs_dir, "20*_*")))

    missing_in_db = fs_runs - set(db_runs.keys())
    missing_in_fs = set(db_runs.keys()) - fs_runs
    in_both = fs_runs & set(db_runs.keys())

    print(f"[*] Runs in Filesystem : {len(fs_runs)}")
    print(f"[*] Runs in Database   : {len(db_runs)}")
    print(f"[*] Missing in DB      : {C_YELLOW}{len(missing_in_db)}{C_RESET}")
    print(f"[*] Missing in Files   : {C_CYAN}{len(missing_in_fs)}{C_RESET}")
    print(f"[*] Present in Both    : {C_GREEN}{len(in_both)}{C_RESET}")

    if args.dry_run:
        print(f"\n{C_YELLOW}[DRY-RUN] Simulation completed. No changes made.{C_RESET}\n")
        return

    # Ingest missing to DB
    if missing_in_db:
        print(f"\n[*] Ingesting {len(missing_in_db)} run(s) from Filesystem into Database...")
        for rid in sorted(missing_in_db):
            rpath = os.path.join(runs_dir, rid)
            args.run = rid
            args.source = runs_dir
            args.force = False
            handle_import(args)

    # Export missing to FS
    if missing_in_fs:
        print(f"\n[*] Exporting {len(missing_in_fs)} run(s) from Database into Filesystem...")
        for rid in sorted(missing_in_fs):
            args.run = rid
            args.dest = runs_dir
            args.overwrite = True
            handle_export(args)

    print(f"\n{C_GREEN}[+] Bidirectional sync completed successfully!{C_RESET}\n")


# ============================================================================
# SUBCOMMAND: AUDIT
# ============================================================================
def handle_audit(args):
    print(f"\n{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}         STORAGE MANAGER: INTEGRITY & CONSISTENCY AUDIT     {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")

    outbase = os.path.abspath(args.outbase)
    driver = resolve_driver(outbase, args.db_path)
    health = driver.health_check()

    print(f"[*] SQLite Path         : {health['database_path']}")
    print(f"[*] Database Integrity  : {C_GREEN if health['integrity'] == 'ok' else C_RED}{health['integrity']}{C_RESET}")
    print(f"[*] Database Size       : {health['size_mb']} MB ({health['size_bytes']} bytes)")
    print(f"[*] Table Statistics:")
    for tbl, count in health["row_counts"].items():
        print(f"    • {tbl:22s}: {count:>8} rows")

    if args.deep_verify:
        print(f"\n[*] Running deep SHA-256 hash checks on raw collections...")
        conn = driver._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, output_hash, raw_output, is_compressed FROM raw_collections LIMIT 500;")
        corrupted = 0
        total_checked = 0
        for r in cursor.fetchall():
            total_checked += 1
            data = r["raw_output"]
            if r["is_compressed"]:
                import zlib
                data = zlib.decompress(data)
            h = hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()
            if h != r["output_hash"]:
                corrupted += 1

        if corrupted == 0:
            print(f"  • Deep verify passed {C_GREEN}[OK]{C_RESET} ({total_checked} sample blobs verified)")
        else:
            print(f"  • {C_RED}[FAIL]{C_RESET} {corrupted} corrupted records detected!")

    print(f"\n{C_GREEN}[+] Audit completed successfully.{C_RESET}\n")


# ============================================================================
# SUBCOMMAND: BACKUP / RESTORE
# ============================================================================
def handle_backup(args):
    print(f"\n{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}         STORAGE MANAGER: DATABASE BACKUP SNAPSHOT          {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")

    outbase = os.path.abspath(args.outbase)
    driver = resolve_driver(outbase, args.db_path)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = args.output or os.path.join(outbase, "backups", f"backup_ndx_db_{timestamp}.tar.gz")
    os.makedirs(os.path.dirname(backup_file), exist_ok=True)

    print(f"[*] Database Source : {driver.db_path}")
    print(f"[*] Target Snapshot : {backup_file}")

    # Use SQLite VACUUM INTO or sqlite3.backup API for 100% online transactional backup
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        tmp_db_path = tmp_db.name

    try:
        conn = driver._get_connection()
        bck_conn = sqlite3.connect(tmp_db_path)
        with bck_conn:
            conn.backup(bck_conn)
        bck_conn.close()

        # Compress to tar.gz
        with tarfile.open(backup_file, "w:gz") as tar:
            tar.add(tmp_db_path, arcname=os.path.basename(driver.db_path))

        size_mb = round(os.path.getsize(backup_file) / (1024 * 1024), 2)
        print(f"\n{C_GREEN}[+] Backup snapshot created successfully!{C_RESET} ({size_mb} MB)")
        print(f"[*] Snapshot Path: {backup_file}\n")
    finally:
        if os.path.exists(tmp_db_path):
            os.remove(tmp_db_path)


def handle_restore(args):
    print(f"\n{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}         STORAGE MANAGER: DATABASE RESTORE FROM BACKUP      {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")

    if not args.input or not os.path.isfile(args.input):
        print(f"{C_RED}[!] Error: Valid backup archive path is required (--input).{C_RESET}")
        return

    outbase = os.path.abspath(args.outbase)
    driver = resolve_driver(outbase, args.db_path)

    print(f"[*] Backup Archive  : {args.input}")
    print(f"[*] Target Database : {driver.db_path}")

    if not args.force:
        confirm = input(f"{C_YELLOW}WARNING: This will replace the database at {driver.db_path}. Proceed? [y/N]: {C_RESET}")
        if confirm.lower() not in ("y", "yes"):
            print("Restore aborted by user.")
            return

    with tempfile.TemporaryDirectory() as tmp_dir:
        with tarfile.open(args.input, "r:gz") as tar:
            tar.extractall(path=tmp_dir)

        extracted_files = glob.glob(os.path.join(tmp_dir, "*.db"))
        if not extracted_files:
            print(f"{C_RED}[!] Error: No .db file found inside backup archive.{C_RESET}")
            return

        src_db = extracted_files[0]
        shutil.copy2(src_db, driver.db_path)
        os.chmod(driver.db_path, 0o600)

    print(f"\n{C_GREEN}[+] Database restored successfully from backup!{C_RESET}\n")


# ============================================================================
# MAIN CLI ENTRYPOINT
# ============================================================================
def main():
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("--outbase", default=get_default_outbase(), help="Base output directory")
    common_parser.add_argument("--db-path", default=None, help="Explicit path to SQLite database")
    common_parser.add_argument("--dry-run", action="store_true", help="Simulate execution without modifications")

    parser = argparse.ArgumentParser(
        description="Network Data Extractor Storage Management CLI",
        formatter_class=argparse.RawTextHelpFormatter,
        parents=[common_parser],
    )

    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommands")

    # init
    p_init = subparsers.add_parser("init", parents=[common_parser], help="Initialize database, schema, and seed elements")
    p_init.add_argument("--elements", help="Path to elements.cfg to seed (optional)")

    # import
    p_import = subparsers.add_parser("import", parents=[common_parser], help="Import filesystem runs into database")
    p_import.add_argument("--source", help="Source runs directory (defaults to outbase/runs)")
    p_import.add_argument("--run", help="Import only a specific run_id (e.g. 20261005_120000)")
    p_import.add_argument("--since", help="Filter runs starting from YYYY-MM-DD")
    p_import.add_argument("--until", help="Filter runs up to YYYY-MM-DD")
    p_import.add_argument("--force", action="store_true", help="Re-import runs even if already in DB")

    # export
    p_export = subparsers.add_parser("export", parents=[common_parser], help="Export database run to filesystem")
    p_export.add_argument("--run", required=True, help="Run ID to export")
    p_export.add_argument("--dest", help="Destination runs directory (defaults to outbase/runs)")
    p_export.add_argument("--overwrite", action="store_true", help="Overwrite existing files in destination")

    # sync
    p_sync = subparsers.add_parser("sync", parents=[common_parser], help="Bidirectional sync and merge between files and DB")
    p_sync.add_argument(
        "--conflict-strategy",
        choices=["db-wins", "files-wins", "newest-wins", "skip", "abort"],
        default="newest-wins",
        help="Strategy to resolve conflicting runs",
    )

    # audit
    p_audit = subparsers.add_parser("audit", parents=[common_parser], help="Verify database integrity and row statistics")
    p_audit.add_argument("--deep-verify", action="store_true", help="Verify blob checksums against output hashes")

    # backup
    p_backup = subparsers.add_parser("backup", parents=[common_parser], help="Create a compressed transactional backup")
    p_backup.add_argument("--output", help="Output path for backup archive")

    # restore
    p_restore = subparsers.add_parser("restore", parents=[common_parser], help="Restore database from backup archive")
    p_restore.add_argument("--input", required=True, help="Backup archive file path")
    p_restore.add_argument("--force", action="store_true", help="Skip interactive confirmation")

    args = parser.parse_args()

    cmd_map = {
        "init": handle_init,
        "import": handle_import,
        "export": handle_export,
        "sync": handle_sync,
        "audit": handle_audit,
        "backup": handle_backup,
        "restore": handle_restore,
    }

    cmd_map[args.command](args)


if __name__ == "__main__":
    main()
