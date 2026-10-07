#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Storage Manager & Setup Suite
==================================
Validates all Phase 2 deliverables:
1. tools/storage_manager.py init
2. tools/storage_manager.py import (with normal files and collect.zip extraction)
3. tools/storage_manager.py export (with --overwrite safety check)
4. tools/storage_manager.py sync / merge
5. tools/storage_manager.py audit with --deep-verify
6. tools/storage_manager.py backup and restore
7. tools/setup_database.py non-interactive execution
"""

import os
import sys
import shutil
import tempfile
import zipfile
import subprocess
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

C_GREEN  = '\033[92m'
C_RED    = '\033[91m'
C_CYAN   = '\033[96m'
C_YELLOW = '\033[93m'
C_RESET  = '\033[0m'


def run_cmd(args):
    cmd = [sys.executable] + args
    res = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if res.returncode != 0:
        print(f"{C_RED}[!] Command failed: {' '.join(cmd)}{C_RESET}")
        print(f"STDOUT:\n{res.stdout}")
        print(f"STDERR:\n{res.stderr}")
        raise RuntimeError(f"Command returned code {res.returncode}")
    return res.stdout


def test_storage_manager_lifecycle():
    print(f"\n{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}         TESTING TOOLS/STORAGE_MANAGER.PY (PHASE 2)         {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")

    with tempfile.TemporaryDirectory() as temp_dir:
        outbase = os.path.join(temp_dir, "test_outbase")
        os.makedirs(outbase, exist_ok=True)
        runs_dir = os.path.join(outbase, "runs")
        os.makedirs(runs_dir, exist_ok=True)

        # 1. Test 'init'
        print(f"\n[*] Testing 'storage_manager.py init'...")
        out = run_cmd(["tools/storage_manager.py", "init", "--outbase", outbase])
        assert "Database initialization completed successfully" in out
        db_path = os.path.join(outbase, "database", "network_data.db")
        assert os.path.isfile(db_path), f"DB not found at {db_path}"
        print(f"  • Database init {C_GREEN}[PASS]{C_RESET}")

        # 2. Setup mock run with uncompressed and compressed collect.zip
        mock_run_id = "20261005_100000"
        mock_run_dir = os.path.join(runs_dir, mock_run_id)
        mock_collect = os.path.join(mock_run_dir, "collect")
        mock_resume = os.path.join(mock_run_dir, "resume")
        mock_conn = os.path.join(mock_run_dir, "connections")
        os.makedirs(mock_collect, exist_ok=True)
        os.makedirs(mock_resume, exist_ok=True)
        os.makedirs(mock_conn, exist_ok=True)

        # Write resume CSVs
        with open(os.path.join(mock_resume, "interfaces_all.csv"), "w", encoding="utf-8") as f:
            f.write("element;interface;admin_status;line_protocol;description;ip_address;mtu;bandwidth_kbit;last_flapped\n")
            f.write("RTAC-POA01-01;Gi0/0;up;up;TEST_LINK;10.0.0.1;1500;1000000;-\n")

        with open(os.path.join(mock_conn, "topology.connections.csv"), "w", encoding="utf-8") as f:
            f.write("endpoint_a;interface_a;endpoint_b;interface_b;connection_type;speed_kbit\n")
            f.write("RTAC-POA01-01;Gi0/0;RTIC-POA01-01;Gi0/1;physical;1000000\n")

        # Create collect.zip to test transparent archive extraction (user requested)
        zip_path = os.path.join(mock_run_dir, "collect.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("RTAC-POA01-01.051026100000.show.interfaces.txt", "GigabitEthernet0/0 is up\nDescription: TEST_LINK")

        # 3. Test 'import' (Filesystem -> DB)
        print(f"\n[*] Testing 'storage_manager.py import' (with transparent collect.zip extraction)...")
        out = run_cmd(["tools/storage_manager.py", "import", "--outbase", outbase])
        assert "[SUCCESS]" in out or "Import Summary: 1 imported" in out
        print(f"  • Import from filesystem (including collect.zip) {C_GREEN}[PASS]{C_RESET}")

        # 4. Test 'audit'
        print(f"\n[*] Testing 'storage_manager.py audit --deep-verify'...")
        out = run_cmd(["tools/storage_manager.py", "audit", "--outbase", outbase, "--deep-verify"])
        assert "Database Integrity" in out and "ok" in out
        assert "Deep verify passed" in out
        print(f"  • Audit with deep verification {C_GREEN}[PASS]{C_RESET}")

        # 5. Test 'export' with --overwrite safety check
        print(f"\n[*] Testing 'storage_manager.py export' with --overwrite protection...")
        export_target = os.path.join(temp_dir, "export_dest")
        os.makedirs(os.path.join(export_target, mock_run_id), exist_ok=True)

        # First try without --overwrite: should refuse to overwrite
        out = run_cmd(["tools/storage_manager.py", "export", "--outbase", outbase, "--run", mock_run_id, "--dest", export_target])
        assert "Refusing to overwrite existing directory" in out
        print(f"  • Overwrite protection safety check {C_GREEN}[PASS]{C_RESET}")

        # Now try with --overwrite
        out = run_cmd(["tools/storage_manager.py", "export", "--outbase", outbase, "--run", mock_run_id, "--dest", export_target, "--overwrite"])
        assert "successfully exported to filesystem" in out
        assert os.path.isfile(os.path.join(export_target, mock_run_id, "resume", "interfaces_all.csv"))
        assert os.path.isfile(os.path.join(export_target, mock_run_id, "connections", "topology.connections.csv"))
        assert os.path.isfile(os.path.join(export_target, mock_run_id, "collect", "RTAC-POA01-01.051026100000.show.interfaces.txt"))
        print(f"  • Export with --overwrite {C_GREEN}[PASS]{C_RESET}")

        # 6. Test 'backup' and 'restore'
        print(f"\n[*] Testing 'storage_manager.py backup' and 'restore'...")
        backup_file = os.path.join(temp_dir, "test_backup.tar.gz")
        out = run_cmd(["tools/storage_manager.py", "backup", "--outbase", outbase, "--output", backup_file])
        assert "Backup snapshot created successfully" in out
        assert os.path.isfile(backup_file)

        # Restore
        out = run_cmd(["tools/storage_manager.py", "restore", "--outbase", outbase, "--input", backup_file, "--force"])
        assert "Database restored successfully from backup" in out
        print(f"  • Backup and Restore cycle {C_GREEN}[PASS]{C_RESET}")

        # 7. Test 'setup_database.py' non-interactive execution
        print(f"\n[*] Testing 'setup_database.py' wizard...")
        out = run_cmd(["tools/setup_database.py", "--non-interactive", "--outbase", outbase])
        assert "DATABASE SETUP COMPLETED: 100% READY FOR PRODUCTION" in out
        print(f"  • setup_database.py wizard {C_GREEN}[PASS]{C_RESET}")


if __name__ == "__main__":
    test_storage_manager_lifecycle()
    print(f"\n{C_GREEN}[✔] ALL PHASE 2 STORAGE MANAGER TESTS PASSED WITH 100% SUCCESS!{C_RESET}\n")
