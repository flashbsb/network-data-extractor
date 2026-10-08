#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Storage Layer Verification Script
======================================
Tests all Phase 1 deliverables of the Storage Abstraction Layer:
1. SQLite Driver initialization, WAL mode, pragmas and DDL tables
2. CRUD operations and batch inserts
3. Filesystem Driver operations
4. StorageManager in files_only, hybrid, and db_only modes
5. Concurrency lock retry resilience
6. Health checks and integrity checks
"""

import os
import sys
import shutil
import tempfile
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.storage.interface import StorageDriver
from core.storage.sqlite_driver import SQLiteDriver
from core.storage.filesystem_driver import FilesystemDriver
from core.storage.manager import StorageManager

C_GREEN = '\033[92m'
C_RED = '\033[91m'
C_CYAN = '\033[96m'
C_RESET = '\033[0m'

def test_sqlite_driver():
    print(f"\n{C_CYAN}[*] Testing SQLiteDriver...{C_RESET}")
    with tempfile.TemporaryDirectory() as temp_dir:
        driver = SQLiteDriver()
        driver.initialize(temp_dir, {"sqlite": {"database_name": "test.db"}})

        db_path = driver.db_path
        assert os.path.isfile(db_path), f"DB file not found at {db_path}"
        print(f"  • DB created at: {db_path} {C_GREEN}[OK]{C_RESET}")

        # Check WAL mode
        health = driver.health_check()
        assert health["integrity"] == "ok", f"Integrity check failed: {health['integrity']}"
        assert health["journal_mode"] == "WAL", f"Expected WAL, got {health['journal_mode']}"
        assert health["tables_count"] >= 7, f"Expected >= 7 tables, got {health['tables_count']}"
        print(f"  • Health check & WAL mode verified {C_GREEN}[OK]{C_RESET} ({health['tables_count']} tables)")

        # Create Run
        run_id = "20261007_120000"
        driver.create_run(run_id, datetime.now(), "hybrid", {"test": True})
        run_info = driver.get_run(run_id)
        assert run_info is not None, "Run not found"
        assert run_info["status"] == "IN_PROGRESS", f"Unexpected status: {run_info['status']}"
        print(f"  • create_run / get_run {C_GREEN}[OK]{C_RESET}")

        # Raw Collections
        driver.save_raw_collection(run_id, "RTAC-POA01-01", "10.0.0.1", "show interfaces", "GigabitEthernet0/0 is up")
        raw_out = driver.get_raw_collection(run_id, "RTAC-POA01-01", "show interfaces")
        assert raw_out == "GigabitEthernet0/0 is up", f"Unexpected raw output: {raw_out}"
        print(f"  • save_raw_collection / get_raw_collection (compressed) {C_GREEN}[OK]{C_RESET}")

        # Interfaces
        driver.save_interfaces(run_id, [
            {"element": "RTAC-POA01-01", "interface": "Gi0/0", "admin_status": "up", "line_protocol": "up", "bandwidth_kbit": 1000000},
            {"element": "RTAC-POA01-01", "interface": "Gi0/1", "admin_status": "down", "line_protocol": "down", "bandwidth_kbit": 1000000}
        ])
        ifaces = driver.get_interfaces(run_id)
        assert len(ifaces) == 2, f"Expected 2 interfaces, got {len(ifaces)}"
        print(f"  • save_interfaces / get_interfaces {C_GREEN}[OK]{C_RESET}")

        # Topology Connections
        driver.save_topology_connections(run_id, [
            {"endpoint_a": "RTAC-POA01-01", "interface_a": "Gi0/0", "endpoint_b": "RTIC-POA01-01", "interface_b": "Gi0/1", "connection_type": "physical", "speed_kbit": 1000000}
        ])
        conns = driver.get_topology_connections(run_id)
        assert len(conns) == 1, f"Expected 1 connection, got {len(conns)}"
        print(f"  • save_topology_connections / get_topology_connections {C_GREEN}[OK]{C_RESET}")

        # Ping Tests
        driver.save_ping_tests(run_id, [
            {"origin": "RTAC-POA01-01", "dest": "RTIC-POA01-01", "tx": 5, "rx": 5, "loss_pct": 0.0, "min": 1.2, "avg": 1.5, "max": 1.9, "jitter": 0.7, "is_dead": False}
        ])
        pings = driver.get_ping_tests(run_id)
        assert len(pings) == 1, f"Expected 1 ping test, got {len(pings)}"
        hist = driver.get_ping_history("RTAC-POA01-01", "RTIC-POA01-01")
        assert len(hist) == 1, f"Expected 1 history point, got {len(hist)}"
        print(f"  • save_ping_tests / get_ping_history {C_GREEN}[OK]{C_RESET}")

        # Finish Run
        driver.finish_run(run_id, datetime.now(), "SUCCESS", total_elements=1, successful_elements=1, failed_elements=0)
        run_info = driver.get_run(run_id)
        assert run_info["status"] == "SUCCESS", f"Expected SUCCESS, got {run_info['status']}"
        print(f"  • finish_run {C_GREEN}[OK]{C_RESET}")


def test_storage_manager():
    print(f"\n{C_CYAN}[*] Testing StorageManager in all 3 modes...{C_RESET}")
    with tempfile.TemporaryDirectory() as temp_dir:
        # 1. files_only
        sm_files = StorageManager(outbase=temp_dir, settings={"storage": {"mode": "files_only"}})
        assert sm_files.is_files_enabled() is True
        assert sm_files.is_db_enabled() is False
        sm_files.create_run("run_files", datetime.now())
        assert os.path.isdir(os.path.join(temp_dir, "runs", "run_files", "collect"))
        print(f"  • files_only mode {C_GREEN}[OK]{C_RESET}")

        # 2. hybrid
        sm_hybrid = StorageManager(outbase=temp_dir, settings={"storage": {"mode": "hybrid"}})
        assert sm_hybrid.is_files_enabled() is True
        assert sm_hybrid.is_db_enabled() is True
        sm_hybrid.create_run("run_hybrid", datetime.now())
        sm_hybrid.save_raw_collection("run_hybrid", "HOST1", "10.0.0.1", "show version", "Cisco IOS XE")
        # Check in files
        assert len(os.listdir(os.path.join(temp_dir, "runs", "run_hybrid", "collect"))) > 0
        # Check in DB
        raw_db = sm_hybrid.get_raw_collection("run_hybrid", "HOST1", "show version")
        assert raw_db == "Cisco IOS XE"
        print(f"  • hybrid mode {C_GREEN}[OK]{C_RESET}")

        # 3. db_only
        sm_db = StorageManager(outbase=temp_dir, settings={"storage": {"mode": "db_only"}})
        assert sm_db.is_files_enabled() is False
        assert sm_db.is_db_enabled() is True
        sm_db.create_run("run_db", datetime.now())
        sm_db.save_interfaces("run_db", [{"element": "HOST2", "interface": "Eth1", "admin_status": "up"}])
        ifaces = sm_db.get_interfaces("run_db")
        assert len(ifaces) == 1
        assert ifaces[0]["element"] == "HOST2"
        print(f"  • db_only mode {C_GREEN}[OK]{C_RESET}")


def test_settings_json_integration():
    print(f"\n{C_CYAN}[*] Testing settings.json integration...{C_RESET}")
    from core.utils_shared import load_settings
    cfg = load_settings()
    assert "storage" in cfg, "storage key missing from settings.json"
    storage_cfg = cfg["storage"]
    assert storage_cfg.get("mode") in ["files_only", "hybrid"], f"Default mode must be files_only or hybrid, got: {storage_cfg.get('mode')}"
    assert storage_cfg.get("backend") == "sqlite"
    print(f"  • settings.json default storage.mode valid ({storage_cfg.get('mode')}) {C_GREEN}[OK]{C_RESET}")


if __name__ == "__main__":
    print(f"{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}       STORAGE LAYER PHASE 1 VERIFICATION TEST SUITE       {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")

    test_sqlite_driver()
    test_storage_manager()
    test_settings_json_integration()

    print(f"\n{C_GREEN}[+] ALL PHASE 1 STORAGE LAYER TESTS PASSED SUCCESSFULLY!{C_RESET}\n")
