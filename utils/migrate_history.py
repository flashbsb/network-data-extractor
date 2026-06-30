#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
              NETWORK HISTORY MIGRATION UTILITY             
============================================================
 Migrates legacy scattered run folders to the unified
 runs/YYYYMMDD_HHMMSS/ structure and rebuilds all indexes.
"""

import os
import sys
import glob
import shutil
import argparse
import subprocess

# ANSI Colors
C_GREEN  = '\033[92m'
C_RED    = '\033[91m'
C_CYAN   = '\033[96m'
C_YELLOW = '\033[93m'
C_RESET  = '\033[0m'

def safe_move_and_merge(src, dst):
    """Safely moves files and folders from src to dst, merging directories if dst already exists."""
    if not os.path.exists(src):
        return
    
    if not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            shutil.move(src, dst)
        except Exception as e:
            print(f"  {C_RED}[!] Error moving {src} -> {dst}: {e}{C_RESET}")
        return

    # If both exist and are directories, merge contents recursively
    if os.path.isdir(src) and os.path.isdir(dst):
        for item in os.listdir(src):
            s_item = os.path.join(src, item)
            d_item = os.path.join(dst, item)
            if os.path.isdir(s_item):
                safe_move_and_merge(s_item, d_item)
            else:
                try:
                    if os.path.exists(d_item):
                        if os.path.isdir(d_item):
                            shutil.rmtree(d_item)
                        else:
                            os.remove(d_item)
                    shutil.move(s_item, d_item)
                except Exception as e:
                    print(f"  {C_RED}[!] Error moving file {s_item} -> {d_item}: {e}{C_RESET}")
        
        # Clean up empty source directory
        try:
            if not os.listdir(src):
                os.rmdir(src)
        except Exception:
            pass

def main():
    parser = argparse.ArgumentParser(description="Migrate legacy network-data-extractor history to unified runs/ structure.")
    parser.add_argument("--outbase", required=True, help="Path to the output base directory (e.g. ../d-network-data-extractor/infos/bb)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate execution without moving any files.")
    args = parser.parse_args()

    outbase = os.path.abspath(args.outbase)
    if not os.path.isdir(outbase):
        print(f"{C_RED}[!] Error: outbase directory does not exist: {outbase}{C_RESET}")
        sys.exit(1)

    print(f"\n{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}           NETWORK DATA HISTORY MIGRATION TOOL              {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")
    print(f"[*] Base directory: {outbase}")
    if args.dry_run:
        print(f"[*] {C_YELLOW}Mode: DRY-RUN (Simulation only){C_RESET}")

    runs_dir = os.path.join(outbase, "runs")
    ping_matrix_dir = os.path.join(outbase, "ping-matrix")
    topology_dir = os.path.join(outbase, "topology")

    # 1. Scan for unique timestamps YYYYMMDD_HHMMSS
    timestamps = set()
    
    # Check directly under outbase
    for path in glob.glob(os.path.join(outbase, "20*_*")):
        if os.path.isdir(path) and os.path.basename(path) != "runs":
            timestamps.add(os.path.basename(path))
            
    # Check under ping-matrix
    if os.path.isdir(ping_matrix_dir):
        for path in glob.glob(os.path.join(ping_matrix_dir, "20*_*")):
            if os.path.isdir(path):
                timestamps.add(os.path.basename(path))
                
    # Check under topology
    if os.path.isdir(topology_dir):
        for path in glob.glob(os.path.join(topology_dir, "20*_*")):
            if os.path.isdir(path):
                timestamps.add(os.path.basename(path))

    sorted_ts = sorted(list(timestamps))
    if not sorted_ts:
        print(f"{C_GREEN}[+] No timestamped directories found to migrate.{C_RESET}")
        sys.exit(0)

    print(f"[*] Found {len(sorted_ts)} unique runs to process.")

    # 2. Process each timestamp
    for ts in sorted_ts:
        print(f"\n---> {C_CYAN}Processing Run: {ts}{C_RESET}")
        dst_run_dir = os.path.join(runs_dir, ts)
        
        # Determine source paths
        src_root = os.path.join(outbase, ts)
        src_ping = os.path.join(ping_matrix_dir, ts)
        src_topo = os.path.join(topology_dir, ts)

        # Move root run folder
        if os.path.exists(src_root):
            print(f"  [+] Move base: {src_root} -> {dst_run_dir}")
            if not args.dry_run:
                safe_move_and_merge(src_root, dst_run_dir)
        else:
            if not args.dry_run:
                os.makedirs(dst_run_dir, exist_ok=True)

        # Move ping-matrix data
        if os.path.exists(src_ping):
            dst_ping = os.path.join(dst_run_dir, "ping-matrix")
            print(f"  [+] Move ping: {src_ping} -> {dst_ping}")
            if not args.dry_run:
                safe_move_and_merge(src_ping, dst_ping)

        # Move topology data
        if os.path.exists(src_topo):
            dst_topo = os.path.join(dst_run_dir, "topology")
            print(f"  [+] Move topo: {src_topo} -> {dst_topo}")
            if not args.dry_run:
                safe_move_and_merge(src_topo, dst_topo)

    # 3. Rebuild dashboards and indexes
    if not args.dry_run:
        print(f"\n{C_CYAN}============================================================{C_RESET}")
        print(f"[*] Rebuilding all portals and indices for {outbase}...")
        print(f"{C_CYAN}============================================================{C_RESET}")
        
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        main_orchestrator = os.path.join(script_dir, "network-data-extractor.py")
        
        if os.path.isfile(main_orchestrator):
            cmd = [sys.executable, main_orchestrator, "--rebuild-index", "--outbase", outbase]
            print(f"[*] Running command: {' '.join(cmd)}")
            try:
                rc = subprocess.run(cmd)
                if rc.returncode == 0:
                    print(f"\n{C_GREEN}[+] Rebuild successfully finished!{C_RESET}")
                else:
                    print(f"\n{C_RED}[!] Rebuild failed with return code {rc.returncode}.{C_RESET}")
            except Exception as e:
                print(f"\n{C_RED}[!] Error executing rebuild: {e}{C_RESET}")
        else:
            print(f"\n{C_RED}[!] Error: network-data-extractor.py not found at {main_orchestrator}{C_RESET}")

    print(f"\n{C_GREEN}Migration process finished!{C_RESET}\n")

if __name__ == "__main__":
    main()
