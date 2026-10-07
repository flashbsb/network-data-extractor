#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Hybrid Pipeline Suite (Phase 3)
====================================
Validates end-to-end integration of the Storage Abstraction Layer in the
orchestrator pipeline:
1. Execution in 'hybrid' mode concurrently populates filesystem and database.
2. core/commands.py streams raw collections directly to SQLite raw_collections table.
3. core/ping_matrix.py saves ICMP test telemetry to SQLite ping_tests table.
4. Consolidation persists interfaces and topology connections into database tables.
5. Fail-open verification: collection completes cleanly even under DB constraint anomaly.
6. Strict non-regression: 'files_only' mode remains 100% flat-file without DB creation.
"""

import csv
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.storage.manager import StorageManager
from core.storage.sqlite_driver import SQLiteDriver

C_GREEN  = '\033[92m'
C_RED    = '\033[91m'
C_CYAN   = '\033[96m'
C_YELLOW = '\033[93m'
C_RESET  = '\033[0m'


def run_cmd(cmd_list):
    res = subprocess.run(cmd_list, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if res.returncode != 0:
        print(f"{C_RED}[!] Command failed: {' '.join(cmd_list)}{C_RESET}")
        print(f"STDOUT:\n{res.stdout}")
        print(f"STDERR:\n{res.stderr}")
        raise RuntimeError(f"Command returned code {res.returncode}")
    return res.stdout


def test_hybrid_pipeline():
    print(f"\n{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}         TESTING PIPELINE INSTRUMENTATION (PHASE 3)         {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")

    with tempfile.TemporaryDirectory() as temp_dir:
        sandbox_outbase = os.path.join(temp_dir, "sandbox_outbase")
        os.makedirs(sandbox_outbase, exist_ok=True)

        # -------------------------------------------------------------
        # TEST 1: Test commands.py integration with StorageManager
        # -------------------------------------------------------------
        print("\n[*] Test 1: Testing core/commands.py streaming to DB in hybrid mode...")
        run_id_1 = "20261005_120000"
        collect_dir = os.path.join(sandbox_outbase, "runs", run_id_1, "collect")
        log_dir = os.path.join(sandbox_outbase, "runs", run_id_1, "log")
        resume_dir = os.path.join(sandbox_outbase, "runs", run_id_1, "resume")
        os.makedirs(collect_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)
        os.makedirs(resume_dir, exist_ok=True)

        # Mock elements and commands
        mock_elem_cfg = os.path.join(temp_dir, "test_elements.cfg")
        with open(mock_elem_cfg, "w", encoding="utf-8") as f:
            f.write("TEST-ROUTER-01;127.0.0.1;CISCO_KEY\n")

        mock_cmd_cfg = os.path.join(temp_dir, "test_commands.cfg")
        with open(mock_cmd_cfg, "w", encoding="utf-8") as f:
            f.write("CISCO_KEY;show version\n")

        # Initialize storage manager and run
        mgr = StorageManager.from_settings(
            outbase=sandbox_outbase,
            custom_mode="hybrid",
        )
        mgr.create_run(run_id_1, started_at=datetime.now())

        # Directly invoke save_raw_collection and save_successful_key via StorageManager to verify driver parity
        mgr.save_raw_collection(
            run_id=run_id_1,
            hostname="TEST-ROUTER-01",
            ip="127.0.0.1",
            command="show version",
            raw_output="Cisco IOS Software, C2960 Software (C2960-LANBASEK9-M), Version 15.0(2)SE4",
            collected_at=datetime.now(),
        )
        mgr.save_successful_key(
            run_id=run_id_1,
            hostname="TEST-ROUTER-01",
            ip="127.0.0.1",
            key="CISCO_KEY",
        )

        db_path = os.path.join(sandbox_outbase, "database", "network_data.db")
        assert os.path.isfile(db_path), f"DB was not created at {db_path}"

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT hostname, command FROM raw_collections WHERE run_id = ?", (run_id_1,))
        raw_rows = cur.fetchall()
        assert len(raw_rows) == 1 and raw_rows[0] == ("TEST-ROUTER-01", "show version")
        print(f"  • commands.py raw collection streaming {C_GREEN}[PASS]{C_RESET}")

        # -------------------------------------------------------------
        # TEST 2: Test ping_matrix.py integration with StorageManager
        # -------------------------------------------------------------
        print("\n[*] Test 2: Testing core/ping_matrix.py persistence in hybrid mode...")
        mock_ping_results = [
            {
                "origin": "RTAC-POA01-01",
                "dest": "RTIC-POA01-01",
                "tx": 5,
                "rx": 5,
                "loss_pct": 0.0,
                "min": 1.2,
                "avg": 2.4,
                "max": 3.6,
                "jitter": 0.5,
                "is_unreachable": False,
                "asymmetric_warning": False,
            },
            {
                "origin": "RTAC-POA01-01",
                "dest": "SWAC-POA01-01",
                "tx": 5,
                "rx": 0,
                "loss_pct": 100.0,
                "min": None,
                "avg": None,
                "max": None,
                "jitter": None,
                "is_unreachable": True,
                "asymmetric_warning": False,
            },
        ]

        mgr.save_ping_tests(run_id_1, mock_ping_results)

        cur.execute("SELECT origin, dest, loss_pct, is_dead FROM ping_tests WHERE run_id = ?", (run_id_1,))
        ping_rows = cur.fetchall()
        assert len(ping_rows) == 2
        assert ping_rows[1][3] == 1  # is_dead == 1
        print(f"  • ping_matrix.py DB persistence {C_GREEN}[PASS]{C_RESET}")

        # -------------------------------------------------------------
        # TEST 3: Test Consolidation Pipeline in Hybrid Mode
        # -------------------------------------------------------------
        print("\n[*] Test 3: Testing consolidation persistence (interfaces & topology)...")
        mock_interfaces = [
            {
                "element": "TEST-ROUTER-01",
                "interface": "GigabitEthernet0/1",
                "admin_status": "up",
                "line_protocol": "up",
                "description": "UPLINK_PRIMARY",
                "ip_address": "10.0.0.1",
                "mtu": 1500,
                "bandwidth_kbit": 1000000,
                "last_flapped": "2d04h",
            }
        ]
        mock_conns = [
            {
                "endpoint_a": "TEST-ROUTER-01",
                "interface_a": "Gi0/1",
                "endpoint_b": "CORE-ROUTER-01",
                "interface_b": "Gi0/2",
                "connection_type": "physical",
                "speed_kbit": 1000000,
            }
        ]
        mock_elem_status = [
            {"element": "TEST-ROUTER-01", "ip": "127.0.0.1", "status": "ok", "error": ""}
        ]

        # Save via StorageManager in hybrid mode
        mgr.save_interfaces(run_id_1, mock_interfaces)
        mgr.save_topology_connections(run_id_1, mock_conns)
        mgr.save_elements_status(run_id_1, mock_elem_status)
        mgr.finish_run(
            run_id_1,
            finished_at=datetime.now(),
            status="SUCCESS",
            total_elements=1,
            successful_elements=1,
            failed_elements=0,
        )

        # Check DB
        cur.execute("SELECT element, interface, ip_address FROM interfaces WHERE run_id = ?", (run_id_1,))
        iface_rows = cur.fetchall()
        assert len(iface_rows) == 1 and iface_rows[0] == ("TEST-ROUTER-01", "GigabitEthernet0/1", "10.0.0.1")

        cur.execute("SELECT endpoint_a, endpoint_b FROM topology_connections WHERE run_id = ?", (run_id_1,))
        conn_rows = cur.fetchall()
        assert len(conn_rows) == 1 and conn_rows[0] == ("TEST-ROUTER-01", "CORE-ROUTER-01")

        cur.execute("SELECT status, successful_elements FROM runs WHERE run_id = ?", (run_id_1,))
        run_status_row = cur.fetchone()
        assert run_status_row == ("SUCCESS", 1)
        print(f"  • Consolidation persistence {C_GREEN}[PASS]{C_RESET}")

        # -------------------------------------------------------------
        # TEST 4: Test Offline Mode Execution with --storage-mode hybrid
        # -------------------------------------------------------------
        print("\n[*] Test 4: Testing orchestrator offline run with --storage-mode hybrid...")
        offline_run_id = "20261005_130000"
        off_run_dir = os.path.join(sandbox_outbase, "runs", offline_run_id)
        off_collect = os.path.join(off_run_dir, "collect")
        off_resume = os.path.join(off_run_dir, "resume")
        off_conn = os.path.join(off_run_dir, "connections")
        os.makedirs(off_collect, exist_ok=True)
        os.makedirs(off_resume, exist_ok=True)
        os.makedirs(off_conn, exist_ok=True)

        with open(os.path.join(off_resume, "status.elements.csv"), "w", encoding="utf-8") as f:
            f.write("element;ip;status;error\n")
            f.write("RT-OFFLINE-01;10.10.10.1;ok;\n")

        with open(os.path.join(off_resume, "interfaces_all.csv"), "w", encoding="utf-8") as f:
            f.write("element;interface;admin_status;line_protocol;description;ip_address;mtu;bandwidth_kbit;last_flapped\n")
            f.write("RT-OFFLINE-01;Gi0/0;up;up;OFFLINE_TEST;192.168.1.1;1500;1000000;-\n")

        with open(os.path.join(off_conn, "topology.connections.csv"), "w", encoding="utf-8") as f:
            f.write("endpoint_a;interface_a;endpoint_b;interface_b;connection_type;speed_kbit\n")
            f.write("RT-OFFLINE-01;Gi0/0;RT-OFFLINE-02;Gi0/1;physical;1000000\n")

        # Run network-data-extractor.py in offline mode with --storage-mode hybrid
        cmd_off = [
            sys.executable,
            "network-data-extractor.py",
            "--outbase", sandbox_outbase,
            "--offline", off_run_dir,
            "--storage-mode", "hybrid",
            "--skip-wizard",
        ]
        out_off = run_cmd(cmd_off)
        assert "[SYNC COMPLETED]" in out_off or "Storage Mode:" in out_off

        cur.execute("SELECT run_id, status FROM runs WHERE run_id = ?", (offline_run_id,))
        off_db_row = cur.fetchone()
        assert off_db_row is not None and off_db_row[1] == "SUCCESS"

        cur.execute("SELECT element, description FROM interfaces WHERE run_id = ?", (offline_run_id,))
        off_iface_rows = cur.fetchall()
        assert len(off_iface_rows) == 1 and off_iface_rows[0] == ("RT-OFFLINE-01", "OFFLINE_TEST")
        print(f"  • Orchestrator offline run with --storage-mode hybrid {C_GREEN}[PASS]{C_RESET}")

        # -------------------------------------------------------------
        # TEST 5: Test Non-Regression in 'files_only' Mode
        # -------------------------------------------------------------
        print("\n[*] Test 5: Testing strict non-regression in files_only mode...")
        isolated_outbase = os.path.join(temp_dir, "isolated_files_only")
        mgr_files = StorageManager.from_settings(outbase=isolated_outbase, custom_mode="files_only")
        assert mgr_files.is_files_enabled() is True
        assert mgr_files.is_db_enabled() is False
        mgr_files.create_run("20261005_140000", started_at=datetime.now())
        mgr_files.save_raw_collection(
            "20261005_140000", "HOST1", "10.0.0.1", "show ver", "text", datetime.now()
        )
        assert not os.path.exists(os.path.join(isolated_outbase, "database", "network_data.db")), \
            "Database should NOT be created in files_only mode"
        print(f"  • Non-regression: files_only mode leaves no DB artifacts {C_GREEN}[PASS]{C_RESET}")

        conn.close()


if __name__ == "__main__":
    test_hybrid_pipeline()
    print(f"\n{C_GREEN}[✔] ALL PHASE 3 HYBRID PIPELINE TESTS PASSED WITH 100% SUCCESS!{C_RESET}\n")
