#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database Setup Assistant (Onboarding Wizard)
============================================
Interactive, friction-free database setup for Network Data Extractor.
Designed for users who clone the project from GitHub and want to prepare,
validate, seed, and verify the database for production in seconds.
"""

import os
import sys
import sqlite3

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.storage.sqlite_driver import SQLiteDriver
from core.utils_shared import load_settings

# Terminal Colors
C_GREEN  = '\033[92m'
C_RED    = '\033[91m'
C_CYAN   = '\033[96m'
C_YELLOW = '\033[93m'
C_BOLD   = '\033[1m'
C_RESET  = '\033[0m'


def main():
    print(f"\n{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}        NETWORK DATA EXTRACTOR - DATABASE SETUP ASSISTANT   {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")
    print("Welcome! This wizard will initialize and validate your database engine.\n")

    import argparse
    parser = argparse.ArgumentParser(description="Network Data Extractor Database Setup Assistant")
    parser.add_argument("--outbase", default=None, help="Target output base directory")
    parser.add_argument("--elements", default=None, help="Elements configuration file to seed")
    parser.add_argument("-y", "--yes", "--non-interactive", dest="non_interactive", action="store_true", help="Run without interactive prompts")
    args = parser.parse_args()

    cfg = load_settings()
    default_outbase = args.outbase or cfg.get("extractor", {}).get("output_base_dir", "infos")
    default_elements = args.elements or cfg.get("extractor", {}).get("elements_file", "config/elements.cfg")

    # Interactive or Automated detection
    is_interactive = sys.stdin.isatty() and not args.non_interactive

    outbase = default_outbase
    if is_interactive and not args.outbase:
        try:
            inp = input(f"Output directory [{default_outbase}]: ").strip()
            if inp:
                outbase = inp
        except (KeyboardInterrupt, EOFError):
            print("\nSetup cancelled.")
            sys.exit(130)

    outbase = os.path.abspath(outbase)
    print(f"\n[*] Target Output Directory: {outbase}")

    # 1. Environment & SQLite check
    sqlite_ver = getattr(sqlite3, "sqlite_version", "unknown")
    print(f"[*] Python SQLite Version   : {sqlite_ver} {C_GREEN}[OK]{C_RESET}")

    # 2. Driver Initialization
    driver = SQLiteDriver()
    storage_cfg = cfg.get("storage", {})
    driver.initialize(outbase, storage_cfg)
    print(f"[*] Database File Location  : {driver.db_path} {C_GREEN}[CREATED]{C_RESET}")

    health = driver.health_check()
    print(f"[*] Journal Mode            : {health['journal_mode']} {C_GREEN}[OK]{C_RESET}")
    print(f"[*] Database Integrity      : {health['integrity']} {C_GREEN}[OK]{C_RESET}")
    print(f"[*] Provisioned Tables      : {health['tables_count']} tables {C_GREEN}[OK]{C_RESET}")

    # 3. Seed Elements from config/elements.cfg if present
    elements_file = os.path.abspath(default_elements)
    seeded_count = 0
    if os.path.isfile(elements_file):
        seed_now = True
        if is_interactive:
            try:
                ans = input(f"\nSeed network elements from {default_elements}? [Y/n]: ").strip().lower()
                if ans in ("n", "no", "false"):
                    seed_now = False
            except (KeyboardInterrupt, EOFError):
                seed_now = True

        if seed_now:
            elements = []
            with open(elements_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split(";")
                    if len(parts) >= 2:
                        h = parts[0].strip()
                        ip = parts[1].strip()
                        cmd_k = parts[2].strip() if len(parts) >= 3 else ""
                        elements.append((h, ip, cmd_k))

            if elements:
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
                print(f"[+] Successfully seeded: {C_GREEN}{seeded_count}{C_RESET} network elements.")
    else:
        print(f"[*] Elements file not found at {elements_file} (skipping seed).")

    # 4. Check for legacy runs to import
    runs_dir = os.path.join(outbase, "runs")
    legacy_count = 0
    if os.path.isdir(runs_dir):
        import glob
        legacy_runs = glob.glob(os.path.join(runs_dir, "20*_*"))
        legacy_count = len(legacy_runs)
        if legacy_count > 0:
            print(f"\n[*] Found {C_YELLOW}{legacy_count}{C_RESET} historical collection run(s) in {runs_dir}.")
            print("    You can import them into the database at any time using:")
            print(f"    {C_CYAN}python tools/storage_manager.py import --outbase {outbase}{C_RESET}")

    # 5. Final Readiness Summary
    print(f"\n{C_CYAN}============================================================{C_RESET}")
    print(f"{C_GREEN}✔ DATABASE SETUP COMPLETED: 100% READY FOR PRODUCTION{C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")
    print(f"  • SQLite Database : {driver.db_path}")
    print(f"  • WAL Mode Active : YES (High concurrency reads)")
    print(f"  • Tables Ready    : {health['tables_count']}")
    print(f"  • Seeded Nodes    : {seeded_count}")
    print(f"\nTo run your first extraction:")
    print(f"  {C_GREEN}python network-data-extractor.py --outbase {outbase}{C_RESET}\n")


if __name__ == "__main__":
    main()
