#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automated Test Suite: Modular Configuration Architecture (Phase 1)
==================================================================
Validates:
1. JSON syntax and integrity of all modular config files in config/
2. Schema structure, presence of required sections and new configurable hooks
3. Deep-merge behavior and precedence logic in core.utils_shared:load_settings
4. Backward compatibility with monolithic settings.json and omitted files
5. Live integration verification of loaded settings dictionary
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.utils_shared import deep_merge, load_settings

C_GREEN  = '\033[92m'
C_RED    = '\033[91m'
C_CYAN   = '\033[96m'
C_YELLOW = '\033[93m'
C_RESET  = '\033[0m'


def test_json_syntax():
    print(f"\n{C_CYAN}[*] Test 1: JSON Syntax & File Integrity...{C_RESET}")
    config_dir = REPO_ROOT / "config"
    expected_files = [
        "extractor.json",
        "ssh.json",
        "network.json",
        "ping.json",
        "storage.json",
        "settings.json"
    ]
    
    for filename in expected_files:
        filepath = config_dir / filename
        assert filepath.is_file(), f"Expected config file not found: {filepath}"
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert isinstance(data, dict), f"{filename} root must be a JSON object"
            print(f"  • {filename:20s}: Valid JSON ({len(data)} top-level sections) {C_GREEN}[PASS]{C_RESET}")
        except Exception as e:
            print(f"  • {filename:20s}: {C_RED}INVALID JSON: {e}{C_RESET}")
            raise


def test_schema_keys():
    print(f"\n{C_CYAN}[*] Test 2: Modular Schema & Domain Key Verification...{C_RESET}")
    config_dir = REPO_ROOT / "config"

    # 1. extractor.json
    with open(config_dir / "extractor.json", "r", encoding="utf-8") as f:
        ext_cfg = json.load(f)
    assert "extractor" in ext_cfg, "extractor.json missing 'extractor' section"
    assert "discovery" in ext_cfg, "extractor.json missing 'discovery' section"
    assert "threads" in ext_cfg["extractor"], "Missing extractor.threads"
    assert "preferred_management_subnets" in ext_cfg["discovery"]
    print(f"  • extractor.json schema verified {C_GREEN}[PASS]{C_RESET}")

    # 2. ssh.json
    with open(config_dir / "ssh.json", "r", encoding="utf-8") as f:
        ssh_cfg = json.load(f)
    assert "ssh" in ssh_cfg, "ssh.json missing 'ssh' section"
    assert "pager_markers" in ssh_cfg["ssh"], "Missing ssh.pager_markers hook"
    assert "prompt_regex" in ssh_cfg["ssh"], "Missing ssh.prompt_regex hook"
    assert "command_timeout" in ssh_cfg["ssh"]
    print(f"  • ssh.json schema & new hooks (pager_markers, prompt_regex) verified {C_GREEN}[PASS]{C_RESET}")

    # 3. network.json
    with open(config_dir / "network.json", "r", encoding="utf-8") as f:
        net_cfg = json.load(f)
    assert "routing_hierarchy" in net_cfg, "network.json missing 'routing_hierarchy'"
    assert "tier_metadata" in net_cfg, "network.json missing 'tier_metadata'"
    assert "topology" in net_cfg, "network.json missing 'topology'"
    assert "site_regex" in net_cfg["topology"], "Missing topology.site_regex hook"
    assert "interface_speed_inference" in net_cfg, "Missing 'interface_speed_inference' mapping"
    assert "transceiver_speed_map" in net_cfg, "Missing 'transceiver_speed_map' mapping"
    print(f"  • network.json schema & optic/site regex hooks verified {C_GREEN}[PASS]{C_RESET}")

    # 4. ping.json
    with open(config_dir / "ping.json", "r", encoding="utf-8") as f:
        ping_cfg = json.load(f)
    assert "ping_matrix" in ping_cfg, "ping.json missing 'ping_matrix'"
    assert "ping_history" in ping_cfg, "ping.json missing 'ping_history'"
    assert "canvas_sla_thresholds" in ping_cfg, "Missing 'canvas_sla_thresholds' hook"
    assert "anomaly_detection" in ping_cfg, "Missing 'anomaly_detection' hook"
    assert "matrix_rules" in ping_cfg["ping_matrix"]
    print(f"  • ping.json schema & SLA canvas thresholds verified {C_GREEN}[PASS]{C_RESET}")

    # 5. storage.json
    with open(config_dir / "storage.json", "r", encoding="utf-8") as f:
        stor_cfg = json.load(f)
    assert "storage" in stor_cfg, "storage.json missing 'storage'"
    assert "retention" in stor_cfg, "storage.json missing 'retention'"
    assert "compression" in stor_cfg, "storage.json missing 'compression'"
    assert stor_cfg["storage"]["mode"] in ["files_only", "db_only", "hybrid"]
    print(f"  • storage.json schema verified {C_GREEN}[PASS]{C_RESET}")


def test_deep_merge_sandbox():
    print(f"\n{C_CYAN}[*] Test 3: Sandbox Deep-Merge Precedence Logic...{C_RESET}")
    with tempfile.TemporaryDirectory() as sandbox:
        cfg_path = Path(sandbox)
        
        # Write base settings.json
        base_data = {
            "ssh": {
                "timeout": 10,
                "delay_between_commands": 5,
                "nested": {"level1": "original_base", "untouched": "keep_me"}
            },
            "extractor": {
                "threads": 8
            }
        }
        with open(cfg_path / "settings.json", "w", encoding="utf-8") as f:
            json.dump(base_data, f)

        # Write modular ssh.json that overrides timeout and nested.level1
        mod_ssh = {
            "ssh": {
                "timeout": 30,
                "nested": {"level1": "overridden_by_mod"},
                "new_key": "added_value"
            }
        }
        with open(cfg_path / "ssh.json", "w", encoding="utf-8") as f:
            json.dump(mod_ssh, f)

        merged = load_settings(custom_path=str(cfg_path))

        assert merged["ssh"]["timeout"] == 30, f"Expected 30, got {merged['ssh']['timeout']}"
        assert merged["ssh"]["delay_between_commands"] == 5, "Base setting delay_between_commands lost"
        assert merged["ssh"]["nested"]["level1"] == "overridden_by_mod", "Nested deep-merge failed"
        assert merged["ssh"]["nested"]["untouched"] == "keep_me", "Nested sibling untouched lost"
        assert merged["ssh"]["new_key"] == "added_value", "Modular added key missing"
        assert merged["extractor"]["threads"] == 8, "Sibling base section extractor lost"
        
        print(f"  • Deep-merge override and preservation logic verified {C_GREEN}[PASS]{C_RESET}")


def test_backward_compatibility():
    print(f"\n{C_CYAN}[*] Test 4: Backward Compatibility Edge-Cases...{C_RESET}")
    # Case A: Only settings.json exists (Legacy mode)
    with tempfile.TemporaryDirectory() as sandbox_a:
        with open(Path(sandbox_a) / "settings.json", "w", encoding="utf-8") as f:
            json.dump({"legacy_mode": True, "value": 123}, f)
        res_a = load_settings(custom_path=str(sandbox_a))
        assert res_a.get("legacy_mode") is True
        assert res_a.get("value") == 123
        print(f"  • Case A (Settings.json exclusively) supported {C_GREEN}[PASS]{C_RESET}")

    # Case B: Only modular files exist (No settings.json)
    with tempfile.TemporaryDirectory() as sandbox_b:
        with open(Path(sandbox_b) / "extractor.json", "w", encoding="utf-8") as f:
            json.dump({"extractor": {"threads": 15}}, f)
        with open(Path(sandbox_b) / "ssh.json", "w", encoding="utf-8") as f:
            json.dump({"ssh": {"timeout": 45}}, f)
        res_b = load_settings(custom_path=str(sandbox_b))
        assert res_b["extractor"]["threads"] == 15
        assert res_b["ssh"]["timeout"] == 45
        print(f"  • Case B (Modular files exclusively without settings.json) supported {C_GREEN}[PASS]{C_RESET}")

    # Case C: Explicit custom file path passed via CLI
    with tempfile.TemporaryDirectory() as sandbox_c:
        custom_file = Path(sandbox_c) / "my_custom_override.json"
        with open(custom_file, "w", encoding="utf-8") as f:
            json.dump({"custom_run": True}, f)
        res_c = load_settings(custom_path=str(custom_file))
        assert res_c.get("custom_run") is True
        print(f"  • Case C (Direct custom file path) supported {C_GREEN}[PASS]{C_RESET}")


def test_live_repository_settings():
    print(f"\n{C_CYAN}[*] Test 5: Live Repository Settings Integration...{C_RESET}")
    live_config = load_settings()
    
    required_sections = [
        "extractor",
        "ssh",
        "topology",
        "discovery",
        "ping_matrix",
        "ping_history",
        "routing_hierarchy",
        "tier_metadata",
        "canvas_sla_thresholds",
        "storage",
        "retention",
        "compression"
    ]
    
    for sec in required_sections:
        assert sec in live_config, f"Live config missing essential section: '{sec}'"
        print(f"  • Live section '{sec:23s}': {C_GREEN}[FOUND & MERGED]{C_RESET}")

    # Assert new hooks are accessible directly through standard load_settings()
    assert live_config["ssh"]["prompt_regex"] == "[A-Za-z0-9_\\-\\.\\:\\/]+[#>\\$]\\s*$"
    assert live_config["topology"]["site_regex"] == "[-_.]?([A-Za-z]{3,4}\\d{2,3})[-_.]?"
    assert live_config["canvas_sla_thresholds"]["rtt_warning_ms"] == 35.0
    assert live_config["anomaly_detection"]["std_dev_multiplier"] == 3.0
    print(f"\n  • Live integration verified: all modular hooks active and resolved {C_GREEN}[PASS]{C_RESET}")


if __name__ == "__main__":
    print(f"{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}    MODULAR CONFIGURATION ARCHITECTURE VERIFICATION SUITE   {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")

    test_json_syntax()
    test_schema_keys()
    test_deep_merge_sandbox()
    test_backward_compatibility()
    test_live_repository_settings()

    print(f"\n{C_GREEN}============================================================{C_RESET}")
    print(f"{C_GREEN}[+] ALL MODULAR CONFIG SUITE TESTS COMPLETED SUCCESSFULLY!  {C_RESET}")
    print(f"{C_GREEN}============================================================{C_RESET}\n")
