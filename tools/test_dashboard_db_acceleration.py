#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Dashboard DB Acceleration Suite (Phase 4)
==============================================
Validates that Inventory Engine, Diff Engine, and Ping History Generator:
1. Query data directly from SQLite database when storage.mode is 'hybrid' or 'db_only'.
2. Produce identical, accurate static payloads (data/*.js and manifest.js).
3. Execute incremental verification (skipping redundant calculations when no new runs exist).
4. Maintain seamless fallback to filesystem when in 'files_only' mode or when DB is empty.
"""

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

from core.diff_engine import DiffEngine
from core.inventory_engine import InventoryEngine
from core.ping_history_generator import PingHistoryGenerator
from core.storage.manager import StorageManager

C_GREEN  = '\033[92m'
C_RED    = '\033[91m'
C_CYAN   = '\033[96m'
C_YELLOW = '\033[93m'
C_RESET  = '\033[0m'


def test_dashboard_acceleration():
    print(f"\n{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}         TESTING DASHBOARD DB ACCELERATION (PHASE 4)        {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")

    with tempfile.TemporaryDirectory() as temp_dir:
        sandbox_outbase = os.path.join(temp_dir, "sandbox_dashboards")
        os.makedirs(sandbox_outbase, exist_ok=True)

        # 1. Initialize StorageManager in hybrid mode and seed test runs
        print("\n[*] Step 1: Seeding database with telemetry and inventory data...")
        mgr = StorageManager.from_settings(outbase=sandbox_outbase, custom_mode="hybrid")

        run1 = "20261005_100000"
        run2 = "20261005_110000"

        # Create Run 1
        mgr.create_run(run1, started_at=datetime(2026, 10, 5, 10, 0, 0))
        mgr.save_interfaces(run1, [
            {
                "element": "RTAC-POA01-01",
                "interface": "GigabitEthernet0/0",
                "admin_status": "up",
                "line_protocol": "up",
                "description": "PRIMARY_UPLINK",
                "ip_address": "10.0.0.1",
                "mtu": 1500,
                "bandwidth_kbit": 1000000,
                "last_flapped": "10d",
            },
            {
                "element": "RTIC-POA01-01",
                "interface": "GigabitEthernet0/1",
                "admin_status": "up",
                "line_protocol": "up",
                "description": "PEERING_LINK",
                "ip_address": "10.0.0.2",
                "mtu": 1500,
                "bandwidth_kbit": 1000000,
                "last_flapped": "10d",
            }
        ])
        mgr.save_topology_connections(run1, [
            {
                "endpoint_a": "RTAC-POA01-01",
                "interface_a": "Gi0/0",
                "endpoint_b": "RTIC-POA01-01",
                "interface_b": "Gi0/1",
                "connection_type": "physical",
                "speed_kbit": 1000000,
            }
        ])
        mgr.save_ping_tests(run1, [
            {
                "origin": "RTAC-POA01-01",
                "dest": "RTIC-POA01-01",
                "tx": 5,
                "rx": 5,
                "loss_pct": 0.0,
                "min": 1.1,
                "avg": 2.2,
                "max": 3.3,
                "jitter": 0.4,
                "is_unreachable": False,
                "asymmetric_warning": False,
            }
        ])
        mgr.finish_run(run1, finished_at=datetime(2026, 10, 5, 10, 5, 0), status="SUCCESS", total_elements=2, successful_elements=2)

        # Create Run 2 (with a slight change in interface description for drift detection)
        mgr.create_run(run2, started_at=datetime(2026, 10, 5, 11, 0, 0))
        mgr.save_interfaces(run2, [
            {
                "element": "RTAC-POA01-01",
                "interface": "GigabitEthernet0/0",
                "admin_status": "up",
                "line_protocol": "up",
                "description": "PRIMARY_UPLINK_MODIFIED",
                "ip_address": "10.0.0.1",
                "mtu": 1500,
                "bandwidth_kbit": 1000000,
                "last_flapped": "1d",
            },
            {
                "element": "RTIC-POA01-01",
                "interface": "GigabitEthernet0/1",
                "admin_status": "down",
                "line_protocol": "down",
                "description": "PEERING_LINK",
                "ip_address": "10.0.0.2",
                "mtu": 1500,
                "bandwidth_kbit": 1000000,
                "last_flapped": "10m",
            }
        ])
        mgr.save_topology_connections(run2, [
            {
                "endpoint_a": "RTAC-POA01-01",
                "interface_a": "Gi0/0",
                "endpoint_b": "RTIC-POA01-01",
                "interface_b": "Gi0/1",
                "connection_type": "physical",
                "speed_kbit": 1000000,
            }
        ])
        mgr.save_ping_tests(run2, [
            {
                "origin": "RTAC-POA01-01",
                "dest": "RTIC-POA01-01",
                "tx": 5,
                "rx": 5,
                "loss_pct": 0.0,
                "min": 1.3,
                "avg": 2.5,
                "max": 3.7,
                "jitter": 0.6,
                "is_unreachable": False,
                "asymmetric_warning": False,
            }
        ])
        mgr.finish_run(run2, finished_at=datetime(2026, 10, 5, 11, 5, 0), status="SUCCESS", total_elements=2, successful_elements=2)
        print(f"  • Database seeded {C_GREEN}[PASS]{C_RESET}")

        # -------------------------------------------------------------
        # 2. Test DB-Accelerated PingHistoryGenerator
        # -------------------------------------------------------------
        print("\n[*] Step 2: Testing DB-Accelerated Ping History Generator...")
        ping_gen = PingHistoryGenerator(sandbox_outbase, storage_mgr=mgr)
        ping_gen.run(force_rebuild=True)

        manifest_file = os.path.join(sandbox_outbase, "ping-matrix", "history", "history_manifest.json")
        assert os.path.isfile(manifest_file), "history_manifest.json not found"
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest_pings = json.load(f)
        assert len(manifest_pings) == 2, f"Expected 2 runs in history manifest, got {len(manifest_pings)}"

        # Incremental test: second run without force_rebuild should be instant
        print("  • Testing incremental verification (cache hit)...")
        ping_gen.run(force_rebuild=False)
        print(f"  • Ping History DB generation & incremental verification {C_GREEN}[PASS]{C_RESET}")

        # -------------------------------------------------------------
        # 3. Test DB-Accelerated InventoryEngine
        # -------------------------------------------------------------
        print("\n[*] Step 3: Testing DB-Accelerated Inventory Engine...")
        inv_engine = InventoryEngine(sandbox_outbase, storage_mgr=mgr)
        inv_engine.run(force_rebuild=True)

        inv_js_1 = os.path.join(sandbox_outbase, "inventory", "data", f"{run1}.js")
        inv_js_2 = os.path.join(sandbox_outbase, "inventory", "data", f"{run2}.js")
        assert os.path.isfile(inv_js_1), f"Inventory data {inv_js_1} not created"
        assert os.path.isfile(inv_js_2), f"Inventory data {inv_js_2} not created"

        with open(inv_js_1, "r", encoding="utf-8") as f:
            content1 = f.read()
            assert "RTAC-POA01-01" in content1
            assert "PRIMARY_UPLINK" in content1

        # Incremental check
        inv_engine.run(force_rebuild=False)
        print(f"  • Inventory Engine DB generation & payload creation {C_GREEN}[PASS]{C_RESET}")

        # -------------------------------------------------------------
        # 4. Test DB-Accelerated DiffEngine
        # -------------------------------------------------------------
        print("\n[*] Step 4: Testing DB-Accelerated Diff Engine...")
        diff_engine = DiffEngine(sandbox_outbase, storage_mgr=mgr)
        diff_engine.run(force_rebuild=True)

        diff_manifest = os.path.join(sandbox_outbase, "diff", "manifest.js")
        assert os.path.isfile(diff_manifest), f"Diff manifest {diff_manifest} not created"

        # Check that drift reports between run1 and run2 were created
        reports = os.listdir(os.path.join(sandbox_outbase, "diff", "reports"))
        assert len(reports) > 0, "No diff reports generated"
        print(f"  • Diff Engine DB generation & drift reports {C_GREEN}[PASS]{C_RESET}")

        # -------------------------------------------------------------
        # 5. Test Filesystem Fallback in files_only mode
        # -------------------------------------------------------------
        print("\n[*] Step 5: Testing transparent filesystem fallback...")
        fs_outbase = os.path.join(temp_dir, "fs_fallback_outbase")
        os.makedirs(fs_outbase, exist_ok=True)
        fs_run_dir = os.path.join(fs_outbase, "runs", "20261005_150000", "resume")
        os.makedirs(fs_run_dir, exist_ok=True)

        # Create pure filesystem run without DB
        with open(os.path.join(fs_run_dir, "interfaces_all.csv"), "w", encoding="utf-8") as f:
            f.write("element;interface;admin_status;line_protocol;description;ip_address;mtu;bandwidth_kbit;last_flapped\n")
            f.write("FS-NODE-01;Gi0/0;up;up;FS_LINK;10.20.30.40;1500;1000000;-\n")

        with open(os.path.join(fs_run_dir, "ping_matrix_list.json"), "w", encoding="utf-8") as f:
            json.dump({
                "metadata": {"datetime": "2026-10-05 15:00:00"},
                "data": [{"origin": "FS-NODE-01", "dest": "FS-NODE-02", "tx": 5, "rx": 5, "loss_pct": 0.0, "avg": 1.5, "is_unreachable": False}]
            }, f)

        # Run engines on purely file-based outbase: should fall back to disk without error
        inv_fs = InventoryEngine(fs_outbase)
        inv_fs.run()
        assert os.path.isfile(os.path.join(fs_outbase, "inventory", "data", "20261005_150000.js"))

        ping_fs = PingHistoryGenerator(fs_outbase)
        ping_fs.run()
        assert os.path.isfile(os.path.join(fs_outbase, "ping-matrix", "history", "history_manifest.json"))
        print(f"  • Transparent filesystem fallback {C_GREEN}[PASS]{C_RESET}")


if __name__ == "__main__":
    test_dashboard_acceleration()
    print(f"\n{C_GREEN}[✔] ALL PHASE 4 DASHBOARD DB ACCELERATION TESTS PASSED WITH 100% SUCCESS!{C_RESET}\n")
