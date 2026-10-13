#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit and Integration Tests for Systemic Failure Circuit Breaker (Fail-Fast Engine).
Validates failure classification, consecutive tracking, threshold tripping,
JSON marker generation, CLI bypass flags, and downstream suppression.
"""

import unittest
import os
import sys
import json
import tempfile
import shutil
import subprocess

# Ensure repo root is on sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.utils_shared import is_auth_failure, is_network_unreachable, load_settings
from core.web_server import NDXWebServer


class TestFailureClassification(unittest.TestCase):
    """Tests the failure classification functions for SSH and Network errors."""

    def test_auth_failure_detection(self):
        # Paramiko-like exception types or simulated Exception
        class DummyAuthException(Exception):
            pass

        self.assertTrue(is_auth_failure(Exception("Authentication failed.")))
        self.assertTrue(is_auth_failure(Exception("Permission denied (publickey,password).")))
        self.assertTrue(is_auth_failure(Exception("TACACS+ Auth Fail for user operator")))
        self.assertTrue(is_auth_failure(Exception("Bad authentication response")))

        # Non-auth failures
        self.assertFalse(is_auth_failure(Exception("Connection timed out")))
        self.assertFalse(is_auth_failure(Exception("Connection refused")))
        self.assertFalse(is_auth_failure(Exception("Name or service not known")))

    def test_network_unreachable_detection(self):
        self.assertTrue(is_network_unreachable(Exception("Network is unreachable")))
        self.assertTrue(is_network_unreachable(Exception("No route to host")))
        self.assertTrue(is_network_unreachable(Exception("Host is unreachable")))

        err_101 = OSError(101, "Network is unreachable")
        err_101.errno = 101
        self.assertTrue(is_network_unreachable(err_101))

        err_113 = OSError(113, "No route to host")
        err_113.errno = 113
        self.assertTrue(is_network_unreachable(err_113))

        # Non-network-unreachable errors
        self.assertFalse(is_network_unreachable(Exception("Authentication failed")))
        self.assertFalse(is_network_unreachable(Exception("Syntax error in command")))


class TestCommandsCircuitBreaker(unittest.TestCase):
    """Tests core/commands.py Circuit Breaker execution, tripping, and bypass."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="ndx_test_cb_")
        self.outdir = os.path.join(self.test_dir, "collect")
        self.resumedir = os.path.join(self.test_dir, "resume")
        self.logdir = os.path.join(self.test_dir, "log")
        os.makedirs(self.outdir, exist_ok=True)
        os.makedirs(self.resumedir, exist_ok=True)
        os.makedirs(self.logdir, exist_ok=True)

        # Create elements with 15 dummy hosts (all invalid IPs to trigger failures)
        self.elements_file = os.path.join(self.test_dir, "elements.cfg")
        with open(self.elements_file, "w", encoding="utf-8") as f:
            for i in range(1, 16):
                f.write(f"ROUTER-{i:02d};192.0.2.{i};cisco\n")

        # Create commands file
        self.commands_file = os.path.join(self.test_dir, "commands.cfg")
        with open(self.commands_file, "w", encoding="utf-8") as f:
            f.write("cisco;show version\n")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_commands_circuit_breaker_tripping_auth(self):
        """
        Runs commands.py with mock environment where SSH authentication immediately fails.
        Should trip at 10 consecutive failures and exit with returncode 101.
        """
        script_path = os.path.join(REPO_ROOT, "core", "commands.py")

        # Create a mock wrapper script or inject mock paramiko to simulate 10 consecutive auth failures
        mock_runner = os.path.join(self.test_dir, "mock_commands.py")
        mock_code = f"""import sys
import os

# Mock paramiko connect to raise AuthenticationException
import paramiko
def mock_connect(*args, **kwargs):
    raise paramiko.AuthenticationException("Mocked Authentication failed")

paramiko.SSHClient.connect = mock_connect

# Now run original commands.py
sys.path.insert(0, {repr(REPO_ROOT)})
import core.commands
core.commands.main()
"""
        with open(mock_runner, "w", encoding="utf-8") as f:
            f.write(mock_code)

        cmd = [
            sys.executable,
            mock_runner,
            "--outdir", self.outdir,
            "--resumedir", self.resumedir,
            "--logdir", self.logdir,
            "--elements", self.elements_file,
            "--commands", self.commands_file,
            "--threads", "1",
            "--no-randomize"
        ]

        env = os.environ.copy()
        env["NDX_SSH_USER"] = "testuser"
        env["NDX_SSH_PASS"] = "badpass"

        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)

        # Must exit with 101
        self.assertEqual(proc.returncode, 101, f"Expected returncode 101, got {proc.returncode}. Output:\n{proc.stdout}\n{proc.stderr}")

        # SYSTEMIC_FAILURE.json must exist in outdir and resumedir
        sf_out = os.path.join(self.outdir, "SYSTEMIC_FAILURE.json")
        self.assertTrue(os.path.isfile(sf_out), "SYSTEMIC_FAILURE.json not created in outdir")

        with open(sf_out, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertTrue(data.get("circuit_breaker_tripped"))
        self.assertEqual(data.get("failure_type"), "AUTHENTICATION_EXPIRED")
        self.assertEqual(data.get("consecutive_failures"), 10)
        self.assertEqual(data.get("threshold"), 10)

    def test_commands_circuit_breaker_bypass_flag(self):
        """
        When --ignore-circuit-breaker is passed, all 15 elements should be attempted
        instead of fast-aborting at 10.
        """
        mock_runner = os.path.join(self.test_dir, "mock_commands_bypass.py")
        mock_code = f"""import sys
import os

import paramiko
def mock_connect(*args, **kwargs):
    raise paramiko.AuthenticationException("Mocked Authentication failed")

paramiko.SSHClient.connect = mock_connect

sys.path.insert(0, {repr(REPO_ROOT)})
import core.commands
core.commands.main()
"""
        with open(mock_runner, "w", encoding="utf-8") as f:
            f.write(mock_code)

        cmd = [
            sys.executable,
            mock_runner,
            "--outdir", self.outdir,
            "--resumedir", self.resumedir,
            "--logdir", self.logdir,
            "--elements", self.elements_file,
            "--commands", self.commands_file,
            "--threads", "1",
            "--no-randomize",
            "--ignore-circuit-breaker"
        ]

        env = os.environ.copy()
        env["NDX_SSH_USER"] = "testuser"
        env["NDX_SSH_PASS"] = "badpass"

        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)

        # Without circuit breaker, empty collection exits with 100
        self.assertEqual(proc.returncode, 100)
        # SYSTEMIC_FAILURE.json should NOT be written
        self.assertFalse(os.path.isfile(os.path.join(self.outdir, "SYSTEMIC_FAILURE.json")))


class TestPingMatrixCircuitBreaker(unittest.TestCase):
    """Tests core/ping_matrix.py Circuit Breaker execution and tripping."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="ndx_test_ping_cb_")
        self.collect_dir = os.path.join(self.test_dir, "collect")
        self.resume_dir = os.path.join(self.test_dir, "resume")
        self.log_dir = os.path.join(self.test_dir, "log")
        os.makedirs(self.collect_dir, exist_ok=True)
        os.makedirs(self.resume_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)

        self.elements_file = os.path.join(self.test_dir, "elements.cfg")
        with open(self.elements_file, "w", encoding="utf-8") as f:
            for i in range(1, 15):
                f.write(f"ROUTER-{i:02d};192.0.2.{i};cisco\n")

        self.ping_cmds = os.path.join(self.test_dir, "commands.icmp.cfg")
        with open(self.ping_cmds, "w", encoding="utf-8") as f:
            f.write("cisco;ping {ip}\n")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_ping_matrix_circuit_breaker_tripping(self):
        mock_runner = os.path.join(self.test_dir, "mock_ping.py")
        mock_code = f"""import sys
import os

import paramiko
def mock_connect(*args, **kwargs):
    raise paramiko.AuthenticationException("Ping Auth expired")

paramiko.SSHClient.connect = mock_connect

sys.path.insert(0, {repr(REPO_ROOT)})
import core.ping_matrix
core.ping_matrix.main()
"""
        with open(mock_runner, "w", encoding="utf-8") as f:
            f.write(mock_code)

        cmd = [
            sys.executable,
            mock_runner,
            "--collect_dir", self.collect_dir,
            "--resume_dir", self.resume_dir,
            "--logdir", self.log_dir,
            "--elements_cfg", self.elements_file,
            "--ping_commands", self.ping_cmds,
        ]

        env = os.environ.copy()
        env["NDX_SSH_USER"] = "testuser"
        env["NDX_SSH_PASS"] = "badpass"

        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)

        self.assertEqual(proc.returncode, 101, f"Expected 101, got {proc.returncode}.\n{proc.stdout}\n{proc.stderr}")
        sf_file = os.path.join(self.collect_dir, "SYSTEMIC_FAILURE.json")
        self.assertTrue(os.path.isfile(sf_file))

        with open(sf_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self.assertTrue(payload["circuit_breaker_tripped"])
        self.assertEqual(payload["failure_type"], "AUTHENTICATION_EXPIRED")


class TestWebServerCircuitBreakerAwareness(unittest.TestCase):
    """Tests Web Server / Admin Portal awareness of SYSTEMIC_FAILURE."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="ndx_test_web_cb_")
        self.runs_dir = os.path.join(self.test_dir, "runs")
        os.makedirs(self.runs_dir, exist_ok=True)

        # Create one normal run
        normal_run = os.path.join(self.runs_dir, "20261010_100000")
        os.makedirs(os.path.join(normal_run, "resume"), exist_ok=True)
        with open(os.path.join(normal_run, "resume", "status.elements.csv"), "w", encoding="utf-8") as f:
            f.write("element;status;error\nNODE-A;ok;-\nNODE-B;ok;-\n")

        # Create one aborted run
        aborted_run = os.path.join(self.runs_dir, "20261012_090005")
        os.makedirs(os.path.join(aborted_run, "resume"), exist_ok=True)
        with open(os.path.join(aborted_run, "SYSTEMIC_FAILURE.json"), "w", encoding="utf-8") as f:
            json.dump({
                "circuit_breaker_tripped": True,
                "failure_type": "AUTHENTICATION_EXPIRED",
                "diagnosis": "10 consecutive authentication failures detected with 0 successes.",
                "timestamp": "2026-10-12 09:00:15",
                "consecutive_failures": 10,
                "threshold": 10
            }, f, indent=4)

        with open(os.path.join(aborted_run, "resume", "status.elements.csv"), "w", encoding="utf-8") as f:
            f.write("element;status;error\nNODE-A;failed;Authentication failed\nNODE-B;failed;Authentication failed\n")

        self.server = NDXWebServer(outbase=self.test_dir, host="127.0.0.1", port=0)

    def tearDown(self):
        self.server.server_close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_list_runs_identifies_aborted_run(self):
        runs = self.server.list_runs()
        self.assertEqual(len(runs), 2)

        aborted_entry = next((r for r in runs if r["id"] == "20261012_090005"), None)
        self.assertIsNotNone(aborted_entry)
        self.assertTrue(aborted_entry.get("is_aborted"))
        self.assertIsNotNone(aborted_entry.get("abort_info"))
        self.assertEqual(aborted_entry["abort_info"]["failure_type"], "AUTHENTICATION_EXPIRED")

        normal_entry = next((r for r in runs if r["id"] == "20261010_100000"), None)
        self.assertIsNotNone(normal_entry)
        self.assertFalse(normal_entry.get("is_aborted"))

    def test_get_run_summary_includes_abort_metadata(self):
        summary = self.server.get_run_summary("20261012_090005")
        self.assertIsNotNone(summary)
        self.assertTrue(summary.get("is_aborted"))
        self.assertEqual(summary["abort_info"]["consecutive_failures"], 10)

    def test_analytics_excludes_aborted_runs_from_chronic_failures(self):
        analytics = self.server.get_element_reliability_analytics()
        # Aborted run 20261012_090005 must NOT count towards failures of NODE-A or NODE-B
        elements = analytics.get("elements", [])
        node_a = next((e for e in elements if e["element"] == "NODE-A"), None)
        if node_a:
            # NODE-A should have 1 attempt (from 20261010_100000) and 1 success, 0 failure
            self.assertEqual(node_a["failure_count"], 0)


if __name__ == '__main__':
    unittest.main()
