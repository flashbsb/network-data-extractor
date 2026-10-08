#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Network Data Extractor - Web Server & REST API Integration Test Suite
Validates embedded HTTP server, session cookie auth, CSRF enforcement,
Path-Traversal guards, and REST endpoints.
"""

import os
import sys
import json
import time
import shutil
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import http.client
from typing import Dict, Any, Optional

# Ensure repo root is on path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core.web_server import NDXWebServer


class TestWebServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="ndx_web_test_")
        cls.outbase = os.path.join(cls.test_dir, "outbase")
        os.makedirs(os.path.join(cls.outbase, "runs", "20261008_120000", "resume"), exist_ok=True)
        os.makedirs(os.path.join(cls.outbase, "runs", "20261008_120000", "connections"), exist_ok=True)

        # Mock status elements CSV
        status_csv = os.path.join(cls.outbase, "runs", "20261008_120000", "resume", "status.elements.csv")
        with open(status_csv, "w", encoding="utf-8") as f:
            f.write("element;status;error\nRT-CORE-01;ok;\nRT-EDGE-02;ok;\nSW-DIST-01;failed;Timeout\n")

        # Mock ping matrix JSON
        ping_json = os.path.join(cls.outbase, "runs", "20261008_120000", "resume", "ping_matrix_list.json")
        with open(ping_json, "w", encoding="utf-8") as f:
            json.dump({
                "metadata": {"total_pings": 10, "network_health": {"healthy": 8, "warning": 1, "critical": 0, "dead": 1}},
                "node_stats": {"RT-CORE-01": {"avg_global_latency": 12.5}}
            }, f)

        # Mock cron log
        with open(os.path.join(cls.outbase, "cron_execution.log"), "w", encoding="utf-8") as f:
            f.write("[INFO] [2026-10-08 12:00:00] Iniciando execucao da cron\n[INFO] [2026-10-08 12:05:00] Execucao concluida com sucesso.\n")

        cls.users_file = os.path.join(cls.test_dir, "users.json")
        cls.port = 18099
        cls.host = "127.0.0.1"

        cls.server = NDXWebServer(outbase=cls.outbase, host=cls.host, port=cls.port, users_file=cls.users_file)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)  # Allow socket to bind

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir)

    def _request(self, method: str, path: str, body: Any = None, headers: Dict[str, str] = None):
        url = f"http://{self.host}:{self.port}{path}"
        req_headers = {"User-Agent": "NDX-Test-Runner"}
        if headers:
            req_headers.update(headers)

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                status = resp.status
                resp_headers = dict(resp.info())
                resp_body = resp.read().decode("utf-8")
                try:
                    payload = json.loads(resp_body)
                except Exception:
                    payload = resp_body
                return status, payload, resp_headers
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            try:
                err_payload = json.loads(err_body)
            except Exception:
                err_payload = err_body
            return e.code, err_payload, dict(e.headers)

    def test_01_unauthenticated_access_denied(self):
        """Protected endpoints must return 401 when no token is provided."""
        status, payload, _ = self._request("GET", "/api/v1/summary")
        self.assertEqual(status, 401)
        self.assertTrue(payload.get("error"))

    def test_02_successful_login_and_cookie_generation(self):
        """Verifies logging in yields session token, HttpOnly cookie, and CSRF token."""
        status, payload, headers = self._request("POST", "/api/v1/auth/login", {"username": "admin", "password": "admin"})
        self.assertEqual(status, 200)
        self.assertTrue(payload.get("success"))
        self.assertIn("csrf_token", payload)
        self.assertIn("Set-Cookie", headers)
        self.assertIn("ndx_session=", headers["Set-Cookie"])

    def test_03_authenticated_flow_and_summary(self):
        """Verifies full authenticated workflow with session token."""
        # 1. Login
        _, login_res, headers = self._request("POST", "/api/v1/auth/login", {"username": "admin", "password": "admin"})
        cookie = headers["Set-Cookie"].split(";")[0]
        csrf = login_res["csrf_token"]
        auth_headers = {"Cookie": cookie, "X-CSRF-Token": csrf}

        # 2. Get Current Profile
        st_me, me_res, _ = self._request("GET", "/api/v1/auth/me", headers=auth_headers)
        self.assertEqual(st_me, 200)
        self.assertEqual(me_res["username"], "admin")
        self.assertEqual(me_res["role"], "SuperAdmin")

        # 3. Get System Summary
        st_sum, sum_res, _ = self._request("GET", "/api/v1/summary", headers=auth_headers)
        self.assertEqual(st_sum, 200)
        self.assertEqual(sum_res["total_runs"], 1)
        self.assertEqual(sum_res["cron"]["status"], "HEALTHY")

        # 4. Get Runs List
        st_runs, runs_res, _ = self._request("GET", "/api/v1/runs", headers=auth_headers)
        self.assertEqual(st_runs, 200)
        self.assertEqual(len(runs_res["runs"]), 1)
        self.assertEqual(runs_res["runs"][0]["id"], "20261008_120000")

        # 5. Get Run Telemetry Summary
        st_rsum, rsum_res, _ = self._request("GET", "/api/v1/runs/20261008_120000/summary", headers=auth_headers)
        self.assertEqual(st_rsum, 200)
        self.assertEqual(rsum_res["elements_health"]["counts"]["ok"], 2)
        self.assertEqual(rsum_res["elements_health"]["counts"]["failed"], 1)
        self.assertEqual(rsum_res["ping_health"]["healthy"], 8)

    def test_04_csrf_enforcement_on_mutations(self):
        """Verifies mutating requests fail without valid CSRF header."""
        _, login_res, headers = self._request("POST", "/api/v1/auth/login", {"username": "admin", "password": "admin"})
        cookie = headers["Set-Cookie"].split(";")[0]

        # POST without CSRF
        st_nocsrf, _, _ = self._request("POST", "/api/v1/users", {"username": "attacker", "password": "123"}, headers={"Cookie": cookie})
        self.assertEqual(st_nocsrf, 403)

    def test_05_path_traversal_prevention(self):
        """Ensures path traversal attempts are safely rejected."""
        _, login_res, headers = self._request("POST", "/api/v1/auth/login", {"username": "admin", "password": "admin"})
        cookie = headers["Set-Cookie"].split(";")[0]
        auth_headers = {"Cookie": cookie}

        # Attempt to read outside config dir
        st_trav, _, _ = self._request("GET", "/api/v1/configs/../../etc/passwd", headers=auth_headers)
        self.assertIn(st_trav, (400, 403, 404))

    def test_06_config_json_syntax_validation(self):
        """Ensures saving broken JSON is rejected before writing."""
        _, login_res, headers = self._request("POST", "/api/v1/auth/login", {"username": "admin", "password": "admin"})
        cookie = headers["Set-Cookie"].split(";")[0]
        csrf = login_res["csrf_token"]
        auth_headers = {"Cookie": cookie, "X-CSRF-Token": csrf}

        # Attempt to save invalid JSON
        st_bad, bad_res, _ = self._request("PUT", "/api/v1/configs/network.json", {"content": "{ broken json ..."}, headers=auth_headers)
        self.assertEqual(st_bad, 400)
        self.assertIn("Invalid JSON", bad_res["message"])


if __name__ == "__main__":
    print("=" * 60)
    print("        WEB SERVER & REST API INTEGRATION SUITE              ")
    print("=" * 60)
    unittest.main(verbosity=2)
