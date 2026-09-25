#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Network Data Extractor - Ping History Sanitization & Purge Tool
Safely cleans legacy out-of-scope link history files (e.g. SWAC/SWAG)
based on the active routing matrix rules in settings.json.
Generates an uncorrupted compressed tar.gz backup before deletion.
"""

import os
import sys
import json
import tarfile
import argparse
from datetime import datetime

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.ping_matrix import is_pair_allowed
from core.ping_history_generator import PingHistoryGenerator

C_GREEN  = '\033[92m'
C_RED    = '\033[91m'
C_CYAN   = '\033[96m'
C_YELLOW = '\033[93m'
C_RESET  = '\033[0m'

def load_settings(settings_path):
    if not os.path.isfile(settings_path):
        print(f"{C_RED}[!] Settings file not found: {settings_path}{C_RESET}")
        sys.exit(1)
    with open(settings_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def scan_history_links(links_dir, json_config):
    if not os.path.isdir(links_dir):
        print(f"{C_RED}[!] Links directory not found: {links_dir}{C_RESET}")
        sys.exit(1)

    all_files = os.listdir(links_dir)
    keep_files = []
    purge_files = []
    total_purge_bytes = 0
    total_keep_bytes = 0

    for fname in all_files:
        fpath = os.path.join(links_dir, fname)
        if not os.path.isfile(fpath):
            continue
        
        if not (fname.endswith('.json') or fname.endswith('.js')):
            continue

        base = fname[:-5] if fname.endswith('.json') else fname[:-3]
        parts = base.split('_')
        if len(parts) != 2:
            # Malformed filename, flag for purge
            purge_files.append(fname)
            total_purge_bytes += os.path.getsize(fpath)
            continue

        origin, dest = parts[0], parts[1]
        if is_pair_allowed(origin, dest, json_config):
            keep_files.append(fname)
            total_keep_bytes += os.path.getsize(fpath)
        else:
            purge_files.append(fname)
            total_purge_bytes += os.path.getsize(fpath)

    return keep_files, purge_files, total_keep_bytes, total_purge_bytes

def create_backup_archive(links_dir, purge_files, backup_path):
    print(f"{C_CYAN}[*] Creating safety backup archive at: {backup_path}...{C_RESET}")
    os.makedirs(os.path.dirname(os.path.abspath(backup_path)), exist_ok=True)
    
    # Try fast system tar via filelist first
    import tempfile
    import subprocess
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as tf:
            for fname in purge_files:
                tf.write(f"{fname}\n")
            tmp_list_path = tf.name

        cmd = ["tar", "-czf", os.path.abspath(backup_path), "-C", links_dir, "-T", tmp_list_path]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.remove(tmp_list_path)
        if res.returncode == 0:
            archive_size_mb = os.path.getsize(backup_path) / (1024 * 1024)
            print(f"{C_GREEN}[+] Backup archive successfully created via fast tar ({archive_size_mb:.2f} MB){C_RESET}")
            return
    except Exception as e:
        print(f"{C_YELLOW}[!] Fast tar fallback: {e}{C_RESET}")

    # Fallback to Python tarfile
    with tarfile.open(backup_path, "w:gz") as tar:
        for i, fname in enumerate(purge_files, start=1):
            fpath = os.path.join(links_dir, fname)
            tar.add(fpath, arcname=fname)
            if i % 10000 == 0 or i == len(purge_files):
                print(f"    Archived {i}/{len(purge_files)} files...")

    archive_size_mb = os.path.getsize(backup_path) / (1024 * 1024)
    print(f"{C_GREEN}[+] Backup archive successfully created ({archive_size_mb:.2f} MB){C_RESET}")

def main():
    parser = argparse.ArgumentParser(description="Sanitize legacy/out-of-scope link history files.")
    parser.add_argument("--history-dir", default="infos/ping-matrix/history",
                        help="Path to ping-matrix/history directory")
    parser.add_argument("--settings", default="config/settings.json",
                        help="Path to settings.json containing matrix_rules")
    parser.add_argument("--backup-dir", default=None,
                        help="Directory to store safety backup archives (default: <history-dir>/../backups)")
    parser.add_argument("--backup-only", action="store_true", default=False,
                        help="Generate the backup archive without deleting files")
    parser.add_argument("--apply", action="store_true", default=False,
                        help="Perform actual deletion (default is dry-run mode)")
    args = parser.parse_args()

    args.history_dir = os.path.abspath(args.history_dir)
    links_dir = os.path.join(args.history_dir, "links")
    backup_dir = args.backup_dir or os.path.abspath(os.path.join(args.history_dir, "..", "backups"))
    json_config = load_settings(args.settings)

    mode_str = "LIVE APPLY" if args.apply else ("BACKUP ONLY" if args.backup_only else "DRY-RUN (SIMULATION)")

    print(f"{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}       PING MATRIX HISTORY SANITIZATION & RETENTION         {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")
    print(f"History directory: {args.history_dir}")
    print(f"Settings path:     {args.settings}")
    print(f"Mode:              {mode_str}\n")

    print("[*] Scanning and classifying link history files...")
    keep_files, purge_files, keep_bytes, purge_bytes = scan_history_links(links_dir, json_config)

    total_files = len(keep_files) + len(purge_files)
    print("\n" + "=" * 60)
    print(f"Total history files scanned : {total_files:,}")
    print(f"{C_GREEN}Active Backbone links (KEEP)  : {len(keep_files):,} files ({(len(keep_files)/total_files)*100:.1f}%) [{keep_bytes/(1024*1024):.2f} MB]{C_RESET}")
    print(f"{C_YELLOW}Out-of-scope links (PURGE)   : {len(purge_files):,} files ({(len(purge_files)/total_files)*100:.1f}%) [{purge_bytes/(1024*1024):.2f} MB]{C_RESET}")
    print("=" * 60 + "\n")

    if not args.apply and not args.backup_only:
        print(f"{C_YELLOW}[!] Dry-run completed. No files were removed and no backup was written.{C_RESET}")
        print(f"To create backup without deleting: {C_GREEN}--backup-only{C_RESET}")
        print(f"To execute the backup and purge:  {C_GREEN}--apply{C_RESET}\n")
        return

    # Backup creation
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"backup_pre_purge_history_links_{timestamp}.tar.gz")
    create_backup_archive(links_dir, purge_files, backup_file)

    if args.backup_only:
        print(f"\n{C_GREEN}[+] Backup-only completed safely. No files were deleted.{C_RESET}")
        print(f"To execute the actual purge, rerun with: {C_GREEN}--apply{C_RESET}\n")
        return

    # Remove files safely
    print(f"\n{C_CYAN}[*] Purging {len(purge_files):,} out-of-scope files from {links_dir}...{C_RESET}")
    deleted_count = 0
    for fname in purge_files:
        fpath = os.path.join(links_dir, fname)
        try:
            os.remove(fpath)
            deleted_count += 1
            if deleted_count % 10000 == 0 or deleted_count == len(purge_files):
                print(f"    Purged {deleted_count}/{len(purge_files)} files...")
        except Exception as e:
            print(f"{C_RED}[!] Error removing {fname}: {e}{C_RESET}")

    print(f"{C_GREEN}[+] Purge completed. Deleted {deleted_count:,} obsolete files.{C_RESET}")

    # Recompute rankings and manifest
    print(f"\n{C_CYAN}[*] Recomputing clean rankings and updating manifest...{C_RESET}")
    outbase = os.path.dirname(os.path.dirname(os.path.abspath(args.history_dir)))
    generator = PingHistoryGenerator(outbase=outbase)
    generator.recompute_rankings_and_write()

    print(f"\n{C_GREEN}[+] All operations completed successfully! History database is now 100% clean.{C_RESET}\n")

if __name__ == "__main__":
    main()
