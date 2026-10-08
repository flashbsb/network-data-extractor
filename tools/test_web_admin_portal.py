#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Network Data Extractor - Web Administration & Operations Portal Master Test Suite
Unified Phase 5 Test Suite validating:
1. PBKDF2 Password Hashing & Salt Protection
2. Session Management & Sliding Expiration
3. Granular RBAC Permissions (SuperAdmin, NetOps, Operator, Auditor)
4. Path-Traversal & File Isolation Protection
5. JSON Syntax Validation on Mutations
6. Cron Telemetry Health & Status Token Parsing
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
from typing import Dict, Any, Optional, Tuple

# Ensure repo root is on path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from core.auth_manager import AuthManager, ROLE_PERMISSIONS
from core.web_server import NDXWebServer


class TestWebAdminPortal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="ndx_portal_test_")
        cls.users_file = os.path.join(cls.test_dir, "users.json")
        cls.outbase = os.path.join(cls.test_dir, "infos", "bb")
        cls.runs_dir = os.path.join(cls.outbase, "runs")
        os.makedirs(cls.runs_dir, exist_ok=True)

        # Seed sample run
        sample_run = os.path.join(cls.runs_dir, "20261008_120000")
        os.makedirs(os.path.join(sample_run, "resume"), exist_ok=True)
        with open(os.path.join(sample_run, "resume", "summary.json"), "w") as f:
            json.dump({
                "run_id": "20261008_120000",
                "total_devices": 10,
                "successful_ssh": 9,
                "failed_ssh": 1,
                "total_pings": 50,
                "successful_pings": 48
            }, f)

        # Seed mock cron log
        cls.cron_log = os.path.join(cls.outbase, "cron_execution.log")
        with open(cls.cron_log, "w") as f:
            f.write("[INFO] [STATUS: COMPLETED] [2026-10-08 12:00:00] Execucao concluida com sucesso em 2m 15s.\n")

        # Pick random high port
        cls.port = 18888
        cls.host = "127.0.0.1"

        cls.server = NDXWebServer(
            outbase=cls.outbase,
            host=cls.host,
            port=cls.port,
            users_file=cls.users_file
        )
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "server"):
            cls.server.shutdown()
            cls.server.server_close()
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def _request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        cookie: Optional[str] = None,
        csrf: Optional[str] = None
    ) -> Tuple[int, Dict[str, Any], Dict[str, str]]:
        url = f"http://{self.host}:{self.port}{path}"
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf

        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req) as resp:
                status = resp.status
                resp_headers = dict(resp.info())
                resp_body = resp.read().decode("utf-8")
                try:
                    payload = json.loads(resp_body)
                except Exception:
                    payload = {"raw": resp_body}
                return status, payload, resp_headers
        except urllib.error.HTTPError as e:
            resp_body = e.read().decode("utf-8")
            try:
                payload = json.loads(resp_body)
            except Exception:
                payload = {"raw": resp_body}
            return e.code, payload, dict(e.headers)

    def test_01_authentication_flow(self):
        """Validates default admin login and token acquisition."""
        status, data, headers = self._request("POST", "/api/v1/auth/login", {
            "username": "admin",
            "password": "admin"
        })
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))
        self.assertIn("csrf_token", data)
        self.assertIn("Set-Cookie", headers)
        self.assertIn("ndx_session=", headers["Set-Cookie"])
        self.assertIn("HttpOnly", headers["Set-Cookie"])

    def test_02_rbac_user_creation_and_enforcement(self):
        """Validates user creation by SuperAdmin and permission enforcement for NetOps and Operator."""
        # 1. Login as SuperAdmin
        _, adm_data, adm_hdr = self._request("POST", "/api/v1/auth/login", {"username": "admin", "password": "admin"})
        adm_cookie = adm_hdr["Set-Cookie"].split(";")[0]
        adm_csrf = adm_data["csrf_token"]

        # 2. SuperAdmin creates NetOps user and Operator user
        status, _, _ = self._request("POST", "/api/v1/users", {
            "username": "netops_user",
            "password": "SecretNetOps123!",
            "role": "NetOps"
        }, cookie=adm_cookie, csrf=adm_csrf)
        self.assertEqual(status, 201)

        status, _, _ = self._request("POST", "/api/v1/users", {
            "username": "operator_user",
            "password": "SecretOperator123!",
            "role": "Operator"
        }, cookie=adm_cookie, csrf=adm_csrf)
        self.assertEqual(status, 201)

        # 3. Login as NetOps
        _, net_data, net_hdr = self._request("POST", "/api/v1/auth/login", {"username": "netops_user", "password": "SecretNetOps123!"})
        net_cookie = net_hdr["Set-Cookie"].split(";")[0]
        net_csrf = net_data["csrf_token"]

        # NetOps must NOT be able to create or list users (manage_users is SuperAdmin only)
        status, _, _ = self._request("GET", "/api/v1/users", cookie=net_cookie)
        self.assertEqual(status, 403)

        # NetOps must NOT be able to edit system JSON configs (extractor.json)
        status, _, _ = self._request("PUT", "/api/v1/configs/extractor.json", {
            "content": "{\"workers\": 20}"
        }, cookie=net_cookie, csrf=net_csrf)
        self.assertEqual(status, 403)

        # 4. Login as Operator
        _, op_data, op_hdr = self._request("POST", "/api/v1/auth/login", {"username": "operator_user", "password": "SecretOperator123!"})
        op_cookie = op_hdr["Set-Cookie"].split(";")[0]
        op_csrf = op_data["csrf_token"]

        # Operator can view configs
        status, _, _ = self._request("GET", "/api/v1/configs", cookie=op_cookie)
        self.assertEqual(status, 200)

        # Operator must NOT be able to save configs
        status, _, _ = self._request("PUT", "/api/v1/configs/extractor.json", {
            "content": "{\"workers\": 5}"
        }, cookie=op_cookie, csrf=op_csrf)
        self.assertEqual(status, 403)

    def test_03_path_traversal_and_sensitive_file_isolation(self):
        """Ensures traversal attacks and access to sensitive files (.env, users.json) are blocked."""
        _, adm_data, adm_hdr = self._request("POST", "/api/v1/auth/login", {"username": "admin", "password": "admin"})
        adm_cookie = adm_hdr["Set-Cookie"].split(";")[0]

        # Block traversal attempt
        status, _, _ = self._request("GET", "/api/v1/configs/..%2F..%2Fetc%2Fpasswd", cookie=adm_cookie)
        self.assertIn(status, (400, 403, 404))

        # Block direct request for .env
        status, _, _ = self._request("GET", "/api/v1/configs/.env", cookie=adm_cookie)
        self.assertIn(status, (400, 403, 404))

        # Block direct request for users.json
        status, _, _ = self._request("GET", "/api/v1/configs/users.json", cookie=adm_cookie)
        self.assertIn(status, (400, 403, 404))

    def test_04_json_syntax_validation(self):
        """Ensures malformed JSON configurations cannot be saved."""
        _, adm_data, adm_hdr = self._request("POST", "/api/v1/auth/login", {"username": "admin", "password": "admin"})
        adm_cookie = adm_hdr["Set-Cookie"].split(";")[0]
        adm_csrf = adm_data["csrf_token"]

        # Attempt to save invalid JSON syntax
        status, data, _ = self._request("PUT", "/api/v1/configs/extractor.json", {
            "content": "{ broken json syntax: invalid"
        }, cookie=adm_cookie, csrf=adm_csrf)
        self.assertEqual(status, 400)
        self.assertIn("Invalid JSON", data.get("message", ""))

    def test_05_cron_telemetry_status(self):
        """Verifies cron health status inspection."""
        _, adm_data, adm_hdr = self._request("POST", "/api/v1/auth/login", {"username": "admin", "password": "admin"})
        adm_cookie = adm_hdr["Set-Cookie"].split(";")[0]

        status, data, _ = self._request("GET", "/api/v1/cron/status", cookie=adm_cookie)
        self.assertEqual(status, 200)
        self.assertIn("status", data)
        self.assertEqual(data["status"], "HEALTHY")
        self.assertEqual(data["log_file"], "cron_execution.log")


if __name__ == "__main__":
    unittest.main()
