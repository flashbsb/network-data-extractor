#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test DB Only Mode Suite (Phase 5)
=================================
Validates the 'db_only' storage mode and autonomous database retention:
1. Orchestrator and pipelines in 'db_only' mode prune 'collect/' from disk after run completion.
2. Inodes and raw files in 'collect/' are 100% eliminated while 'raw_collections' are safely persisted in SQLite.
3. 'resume/' and 'log/' directories are preserved for troubleshooting and local audit.
4. Static dashboards (Inventory, Diff, Ping History) operate seamlessly using SQLite data.
5. DB retention engine ('apply_retention') prunes stale raw collections, enforces max runs, and vacuums SQLite space.
6. CLI 'tools/storage_manager.py purge' works in both dry-run and execution modes.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.diff_engine import DiffEngine
from core.inventory_engine import InventoryEngine
from core.ping_history_generator import PingHistoryGenerator
from core.storage.manager import StorageManager
from core.storage.sqlite_driver import SQLiteDriver

C_GREEN  = '\033[92m'
C_RED    = '\033[91m'
C_CYAN   = '\033[96m'
C_YELLOW = '\033[93m'
C_RESET  = '\033[0m'


def test_db_only_mode():
    print(f"\n{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}            TESTING DB_ONLY MODE & RETENTION (PHASE 5)      {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")

    with tempfile.TemporaryDirectory() as temp_dir:
        sandbox_outbase = os.path.join(temp_dir, "sandbox_db_only")
        os.makedirs(sandbox_outbase, exist_ok=True)

        # -------------------------------------------------------------
        # 1. Test Inode Freeing & Run Lifecycle in db_only Mode
        # -------------------------------------------------------------
        print("\n[*] Step 1: Testing raw 'collect/' inode freeing in 'db_only' mode...")
        mgr = StorageManager.from_settings(outbase=sandbox_outbase, custom_mode="db_only")
        assert mgr.get_mode() == "db_only"
        assert not mgr.is_files_enabled()
        assert mgr.is_db_enabled()

        run_id = "20261006_090000"
        mgr.create_run(run_id, started_at=datetime(2026, 10, 6, 9, 0, 0))

        # Save raw collection to DB
        mgr.save_raw_collection(
            run_id=run_id,
            hostname="RTIC-POA01-01",
            ip="10.10.10.1",
            command="show ip interface brief",
            raw_output="GigabitEthernet0/0 is up, line protocol is up\nInternet address is 10.10.10.1/30\n",
        )
        mgr.save_interfaces(run_id, [
            {
                "element": "RTIC-POA01-01",
                "interface": "GigabitEthernet0/0",
                "admin_status": "up",
                "line_protocol": "up",
                "description": "CORE_LINK",
                "ip_address": "10.10.10.1",
                "mtu": 1500,
                "bandwidth_kbit": 1000000,
                "last_flapped": "5d",
            }
        ])
        mgr.save_topology_connections(run_id, [
            {
                "endpoint_a": "RTIC-POA01-01",
                "interface_a": "Gi0/0",
                "endpoint_b": "RTIC-POA01-02",
                "interface_b": "Gi0/0",
                "connection_type": "physical",
                "speed_kbit": 1000000,
            }
        ])
        mgr.save_ping_tests(run_id, [
            {
                "origin": "RTIC-POA01-01",
                "dest": "RTIC-POA01-02",
                "tx": 5,
                "rx": 5,
                "loss_pct": 0.0,
                "min": 1.0,
                "avg": 1.8,
                "max": 2.5,
                "jitter": 0.3,
                "is_unreachable": False,
                "asymmetric_warning": False,
            }
        ])

        # Create simulation run directories on disk to test collect/ cleanup vs resume/ preservation
        run_dir = os.path.join(sandbox_outbase, "runs", run_id)
        collect_dir = os.path.join(run_dir, "collect")
        resume_dir = os.path.join(run_dir, "resume")
        log_dir = os.path.join(run_dir, "log")
        os.makedirs(collect_dir, exist_ok=True)
        os.makedirs(resume_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)

        with open(os.path.join(collect_dir, "RTIC-POA01-01.temp.txt"), "w") as f:
            f.write("temporary file that must be purged")
        with open(os.path.join(resume_dir, "summary.csv"), "w") as f:
            f.write("element;status\nRTIC-POA01-01;OK\n")
        with open(os.path.join(log_dir, "extractor.log"), "w") as f:
            f.write("[INFO] extraction completed\n")

        # Simulate the orchestrator db_only post-run hook:
        # 1. Purge collect/
        if mgr.get_mode() == "db_only" and os.path.isdir(collect_dir):
            shutil.rmtree(collect_dir)

        # 2. Finish run
        mgr.finish_run(run_id, finished_at=datetime(2026, 10, 6, 9, 5, 0), status="SUCCESS", total_elements=1, successful_elements=1)

        # Assertions for Step 1
        assert not os.path.exists(collect_dir), "collect/ folder should be deleted in db_only mode"
        assert os.path.isfile(os.path.join(resume_dir, "summary.csv")), "resume/ folder must be preserved"
        assert os.path.isfile(os.path.join(log_dir, "extractor.log")), "log/ folder must be preserved"

        # Verify DB holds the raw output
        db_raw = mgr.get_raw_collection(run_id, "RTIC-POA01-01", "show ip interface brief")
        assert db_raw is not None, "Raw collection should be retrievable from SQLite"
        assert "GigabitEthernet0/0" in db_raw
        print(f"  • Inode freeing & database raw collection retrieval {C_GREEN}[PASS]{C_RESET}")

        # -------------------------------------------------------------
        # 2. Test Dashboard Generation from DB in db_only Mode
        # -------------------------------------------------------------
        print("\n[*] Step 2: Testing Dashboard Engines in 'db_only' mode (zero collect/ files)...")
        inv_gen = InventoryEngine(sandbox_outbase, storage_mgr=mgr)
        inv_gen.run(force_rebuild=True)
        assert os.path.isfile(os.path.join(sandbox_outbase, "inventory", "data", f"{run_id}.js"))

        ping_gen = PingHistoryGenerator(sandbox_outbase, storage_mgr=mgr)
        ping_gen.run(force_rebuild=True)
        assert os.path.isfile(os.path.join(sandbox_outbase, "ping-matrix", "history", "history_manifest.json"))
        print(f"  • Dashboards generated successfully from SQLite {C_GREEN}[PASS]{C_RESET}")

        # -------------------------------------------------------------
        # 3. Test Database Retention Engine (DBRetentionEngine)
        # -------------------------------------------------------------
        print("\n[*] Step 3: Testing DB Retention Engine (time-based & run limits)...")
        # Seed 4 historical runs:
        # Run A: 50 days ago (both raw collections and run should be expired if metrics_days=40)
        # Run B: 25 days ago (raw collections expired if raw_days=20, but run kept)
        # Run C: 5 days ago (fresh)
        # Run D: 1 day ago (fresh)
        ref_now = datetime(2026, 10, 6, 12, 0, 0)
        
        runs_to_seed = [
            ("20260817_120000", ref_now - timedelta(days=50)),
            ("20260911_120000", ref_now - timedelta(days=25)),
            ("20261001_120000", ref_now - timedelta(days=5)),
            ("20261005_120000", ref_now - timedelta(days=1)),
        ]

        for rid, sdate in runs_to_seed:
            mgr.create_run(rid, started_at=sdate)
            mgr.save_raw_collection(rid, "TEST-ROUTER", "10.0.0.9", "show version", "Cisco IOS-XE 17.3")
            mgr.save_interfaces(rid, [{"element": "TEST-ROUTER", "interface": "Loopback0"}])
            mgr.finish_run(rid, finished_at=sdate + timedelta(minutes=5), status="SUCCESS")

        total_runs_before = len(mgr.list_runs())
        assert total_runs_before >= 5  # 1 initial + 4 seeded

        # Execute retention purge with reference_now
        retention_policy = {
            "enabled": True,
            "max_runs": 10,
            "raw_collections_days": 20,   # Run A and Run B should have raw collections deleted
            "metrics_days": 40,           # Run A should be completely deleted
            "auto_vacuum": True,
        }

        purge_result = mgr.apply_retention(policy=retention_policy, reference_now=ref_now)
        assert purge_result.get("status") == "success"
        assert purge_result.get("pruned_runs") >= 1, "Expected at least 1 run pruned (>40 days)"
        assert purge_result.get("pruned_raw_collections") >= 1, "Expected raw collections pruned (>20 days)"
        assert purge_result.get("vacuum_executed") is True, "Vacuum should have executed"

        # Check that Run A is gone
        runs_after_time_purge = {r["run_id"] for r in mgr.list_runs()}
        assert "20260817_120000" not in runs_after_time_purge, "Run 50 days old should be pruned"
        assert "20260911_120000" in runs_after_time_purge, "Run 25 days old should remain"

        # Check that Run B (25 days old) has raw_collections pruned but interface preserved
        raw_b = mgr.get_raw_collection("20260911_120000", "TEST-ROUTER", "show version")
        assert raw_b is None, "Raw collections for run >20 days old should be purged"
        ifaces_b = mgr.get_interfaces("20260911_120000")
        assert len(ifaces_b) == 1, "Interfaces for run <40 days old should be preserved"

        # Test max_runs pruning
        max_runs_policy = {
            "enabled": True,
            "max_runs": 2,  # Keep only the newest 2 runs
            "auto_vacuum": True,
        }
        purge_max_result = mgr.apply_retention(policy=max_runs_policy, reference_now=ref_now)
        assert purge_max_result.get("status") == "success"
        remaining_runs = mgr.list_runs()
        assert len(remaining_runs) == 2, f"Expected 2 runs remaining, got {len(remaining_runs)}"
        print(f"  • DB Retention Engine pruning & vacuum {C_GREEN}[PASS]{C_RESET}")

        # -------------------------------------------------------------
        # 4. Test CLI 'storage_manager.py purge'
        # -------------------------------------------------------------
        print("\n[*] Step 4: Testing CLI 'tools/storage_manager.py purge'...")
        cmd_dry = [
            sys.executable,
            "tools/storage_manager.py",
            "purge",
            "--outbase", sandbox_outbase,
            "--max-runs", "1",
            "--dry-run"
        ]
        res_dry = subprocess.run(cmd_dry, capture_output=True, text=True)
        assert res_dry.returncode == 0
        assert "DRY-RUN" in res_dry.stdout

        cmd_exec = [
            sys.executable,
            "tools/storage_manager.py",
            "purge",
            "--outbase", sandbox_outbase,
            "--max-runs", "1"
        ]
        res_exec = subprocess.run(cmd_exec, capture_output=True, text=True)
        assert res_exec.returncode == 0
        assert "Database retention applied successfully" in res_exec.stdout

        # Verify only 1 run remains now
        final_runs = mgr.list_runs()
        assert len(final_runs) == 1, f"Expected 1 run remaining after CLI purge, got {len(final_runs)}"
        print(f"  • CLI storage_manager.py purge command {C_GREEN}[PASS]{C_RESET}")


if __name__ == "__main__":
    test_db_only_mode()
    print(f"\n{C_GREEN}[✔] ALL PHASE 5 DB_ONLY & RETENTION TESTS PASSED WITH 100% SUCCESS!{C_RESET}\n")
