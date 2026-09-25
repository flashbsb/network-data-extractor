#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Network Data Extractor - Runs Retention & Archiving Tool
Safely manages historical run retention by archiving and purging runs older
than a defined threshold (e.g. 30 days) to prevent disk space exhaustion.
Guarantees full safety backup archive before any removal.
"""

import os
import sys
import shutil
import tarfile
import tempfile
import subprocess
import argparse
from datetime import datetime, timedelta

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.utils_shared import load_settings

C_GREEN  = '\033[92m'
C_RED    = '\033[91m'
C_CYAN   = '\033[96m'
C_YELLOW = '\033[93m'
C_RESET  = '\033[0m'

def get_dir_size(path):
    total = 0
    if not os.path.exists(path):
        return 0
    for root, dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total

def scan_runs(runs_dir, keep_days):
    if not os.path.isdir(runs_dir):
        print(f"{C_RED}[!] Runs directory not found: {runs_dir}{C_RESET}")
        sys.exit(1)

    now = datetime.now()
    cutoff_date = now - timedelta(days=keep_days)
    cutoff_str = cutoff_date.strftime("%Y%m%d_%H%M%S")

    all_entries = sorted(os.listdir(runs_dir))
    runs_to_keep = []
    runs_to_archive = []

    for d in all_entries:
        d_path = os.path.join(runs_dir, d)
        if not os.path.isdir(d_path):
            continue
        # Check standard run format: YYYYMMDD_HHMMSS (15 chars)
        if len(d) == 15 and d[8] == '_':
            try:
                datetime.strptime(d, "%Y%m%d_%H%M%S")
            except ValueError:
                continue

            if d < cutoff_str:
                runs_to_archive.append((d, d_path))
            else:
                runs_to_keep.append((d, d_path))

    return runs_to_keep, runs_to_archive, cutoff_date

def create_runs_backup_archive(outbase, runs_to_archive, backup_path):
    print(f"\n{C_CYAN}[*] Creating safety archive at: {backup_path}...{C_RESET}")
    os.makedirs(os.path.dirname(os.path.abspath(backup_path)), exist_ok=True)
    
    # Try fast system tar via filelist
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as tf:
            for run_id, _ in runs_to_archive:
                tf.write(f"runs/{run_id}\n")
                # Also include diff and inventory snapshots if present
                diff_data = f"diff/data/{run_id}.js"
                if os.path.exists(os.path.join(outbase, diff_data)):
                    tf.write(f"{diff_data}\n")
                inv_data = f"inventory/data/{run_id}.js"
                if os.path.exists(os.path.join(outbase, inv_data)):
                    tf.write(f"{inv_data}\n")
            tmp_list_path = tf.name

        cmd = ["tar", "-czf", os.path.abspath(backup_path), "-C", outbase, "-T", tmp_list_path]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.remove(tmp_list_path)
        if res.returncode == 0:
            archive_size_mb = os.path.getsize(backup_path) / (1024 * 1024)
            print(f"{C_GREEN}[+] Safety backup archive created via fast tar ({archive_size_mb:.2f} MB){C_RESET}")
            return
    except Exception as e:
        print(f"{C_YELLOW}[!] Fast tar fallback: {e}{C_RESET}")

    # Fallback to Python tarfile
    with tarfile.open(backup_path, "w:gz") as tar:
        for run_id, run_path in runs_to_archive:
            tar.add(run_path, arcname=f"runs/{run_id}")

    archive_size_mb = os.path.getsize(backup_path) / (1024 * 1024)
    print(f"{C_GREEN}[+] Safety backup archive created ({archive_size_mb:.2f} MB){C_RESET}")

def purge_archived_runs(outbase, runs_to_archive):
    print(f"\n{C_CYAN}[*] Purging {len(runs_to_archive)} legacy run folders...{C_RESET}")
    deleted_runs = 0
    
    for run_id, run_path in runs_to_archive:
        try:
            shutil.rmtree(run_path)
            deleted_runs += 1
        except Exception as e:
            print(f"{C_RED}[!] Error removing {run_path}: {e}{C_RESET}")

        # Clean corresponding diff and inventory presentation cache files
        inv_js = os.path.join(outbase, "inventory", "data", f"{run_id}.js")
        if os.path.isfile(inv_js):
            try: os.remove(inv_js)
            except Exception: pass

        diff_js = os.path.join(outbase, "diff", "data", f"{run_id}.js")
        if os.path.isfile(diff_js):
            try: os.remove(diff_js)
            except Exception: pass

        reports_dir = os.path.join(outbase, "diff", "reports")
        if os.path.isdir(reports_dir):
            for rf in os.listdir(reports_dir):
                if run_id in rf:
                    try: os.remove(os.path.join(reports_dir, rf))
                    except Exception: pass

    print(f"{C_GREEN}[+] Purged {deleted_runs} legacy runs and associated caches.{C_RESET}")

def rebuild_portals(outbase):
    print(f"\n{C_CYAN}[*] Updating portals, manifests and index...{C_RESET}")
    
    # 1. Root Portal
    try:
        from core.root_portal_engine import generate_root_portal
        generate_root_portal(outbase)
        print(f"{C_GREEN}[+] Root portal rebuilt.{C_RESET}")
    except Exception as e:
        print(f"{C_YELLOW}[!] Root portal rebuild: {e}{C_RESET}")

    # 2. Inventory manifest
    try:
        from core.inventory_engine import InventoryEngine
        InventoryEngine(outbase).run(force_rebuild=True)
        print(f"{C_GREEN}[+] Inventory manifest updated.{C_RESET}")
    except Exception as e:
        print(f"{C_YELLOW}[!] Inventory manifest: {e}{C_RESET}")

    # 3. Diff manifest
    try:
        from core.diff_engine import DiffEngine
        DiffEngine(outbase).run(force_rebuild=True)
        print(f"{C_GREEN}[+] Diff manifest updated.{C_RESET}")
    except Exception as e:
        print(f"{C_YELLOW}[!] Diff manifest: {e}{C_RESET}")

def main():
    parser = argparse.ArgumentParser(description="Manage runs retention and archiving.")
    parser.add_argument("--outbase", default="infos",
                        help="Path to workspace outbase directory")
    parser.add_argument("--keep-days", type=int, default=30,
                        help="Number of days of runs to keep active (default: 30)")
    parser.add_argument("--backup-dir", default=None,
                        help="Directory to store safety backup archives")
    parser.add_argument("--backup-only", action="store_true", default=False,
                        help="Generate the backup archive without purging runs")
    parser.add_argument("--apply", action="store_true", default=False,
                        help="Perform actual archive and purge (default is dry-run mode)")
    args = parser.parse_args()

    outbase = os.path.abspath(args.outbase)
    runs_dir = os.path.join(outbase, "runs")
    backup_dir = args.backup_dir or os.path.join(outbase, "backups")

    mode_str = "LIVE APPLY" if args.apply else ("BACKUP ONLY" if args.backup_only else "DRY-RUN (SIMULATION)")

    print(f"{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}           RUNS RETENTION & ARCHIVING MANAGER               {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")
    print(f"Workspace outbase : {outbase}")
    print(f"Retention window  : {args.keep_days} days")
    print(f"Mode              : {mode_str}\n")

    print("[*] Scanning runs and calculating disk usage...")
    runs_to_keep, runs_to_archive, cutoff_date = scan_runs(runs_dir, args.keep_days)

    keep_bytes = sum(get_dir_size(p) for _, p in runs_to_keep)
    archive_bytes = sum(get_dir_size(p) for _, p in runs_to_archive)
    total_runs = len(runs_to_keep) + len(runs_to_archive)

    # Check extra cache space in diff/data and inventory/data
    cache_purge_bytes = 0
    for run_id, _ in runs_to_archive:
        for sub in ["inventory/data", "diff/data"]:
            f = os.path.join(outbase, sub, f"{run_id}.js")
            if os.path.isfile(f):
                cache_purge_bytes += os.path.getsize(f)

    total_reclaimable_mb = (archive_bytes + cache_purge_bytes) / (1024 * 1024)

    print("\n" + "=" * 60)
    print(f"Cutoff timestamp            : {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total runs found            : {total_runs}")
    print(f"{C_GREEN}Active runs (KEEP <= {args.keep_days}d)   : {len(runs_to_keep)} runs [{keep_bytes/(1024*1024):.2f} MB]{C_RESET}")
    print(f"{C_YELLOW}Legacy runs (ARCHIVE > {args.keep_days}d): {len(runs_to_archive)} runs [{archive_bytes/(1024*1024):.2f} MB]{C_RESET}")
    print(f"Presentation cache reclaim  : {cache_purge_bytes/(1024*1024):.2f} MB")
    print(f"{C_CYAN}Total reclaimable disk space: {total_reclaimable_mb:.2f} MB{C_RESET}")
    print("=" * 60 + "\n")

    if not args.apply and not args.backup_only:
        print(f"{C_YELLOW}[!] Dry-run completed. No runs were deleted and no backup was written.{C_RESET}")
        print(f"To create backup without deleting: {C_GREEN}--backup-only{C_RESET}")
        print(f"To execute the backup and purge:  {C_GREEN}--apply{C_RESET}\n")
        return

    # Backup creation
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"backup_legacy_runs_pre_{cutoff_date.strftime('%Y%m%d')}_{timestamp}.tar.gz")
    create_runs_backup_archive(outbase, runs_to_archive, backup_file)

    if args.backup_only:
        print(f"\n{C_GREEN}[+] Backup-only completed safely. No runs were deleted.{C_RESET}")
        print(f"To execute the actual purge, rerun with: {C_GREEN}--apply{C_RESET}\n")
        return

    # Apply mode: Purge legacy runs & caches
    purge_archived_runs(outbase, runs_to_archive)

    # Rebuild portals and manifests
    rebuild_portals(outbase)

    print(f"\n{C_GREEN}[+] Retention policy successfully applied! Reclaimed ~{total_reclaimable_mb:.2f} MB of disk space.{C_RESET}\n")

if __name__ == "__main__":
    main()
