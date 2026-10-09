#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Network Data Extractor - Embedded Zero-Dependency Web Server & REST API Engine
Extends standard library http.server with multi-threading, REST dispatcher,
session cookies, CSRF protection, strict Path-Traversal guards, and live telemetry.
"""

import os
import re
import csv
import json
import time
import shutil
import urllib.parse
from http import HTTPStatus
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from core.auth_manager import AuthManager, ROLE_PERMISSIONS


class NDXRequestHandler(BaseHTTPRequestHandler):
    """
    Multi-threaded HTTP request handler supporting static dashboard assets
    and authenticated REST API endpoints with RBAC enforcement.
    """
    server_version = "NDX-Portal/1.92.0"

    def log_message(self, format: str, *args: Any) -> None:
        """Custom concise logging format."""
        # Suppress noisy health-check logs if needed
        pass

    # --------------------------------------------------------------------------
    # PROTOCOL HELPERS & PARSERS
    # --------------------------------------------------------------------------

    def _parse_cookies(self) -> Dict[str, str]:
        """Extracts cookie dictionary from Cookie header."""
        cookie_header = self.headers.get("Cookie", "")
        cookies = {}
        for item in cookie_header.split(";"):
            if "=" in item:
                k, v = item.strip().split("=", 1)
                cookies[k.strip()] = v.strip()
        return cookies

    def _get_session_token(self) -> Optional[str]:
        """Extracts session token from Cookie or Authorization header."""
        # Check Cookie first
        cookies = self._parse_cookies()
        if "ndx_session" in cookies:
            return cookies["ndx_session"]

        # Check Authorization header (Bearer token)
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()

        return None

    def _get_authenticated_user(self) -> Optional[Dict[str, Any]]:
        """Validates session token and returns active session dict."""
        token = self._get_session_token()
        if not token:
            return None
        return self.server.auth_mgr.validate_session(token)

    def _validate_csrf(self, session: Dict[str, Any]) -> bool:
        """Validates X-CSRF-Token header against current session."""
        csrf_header = self.headers.get("X-CSRF-Token", "")
        if not csrf_header:
            return False
        return self.server.auth_mgr.validate_csrf(session["session_token"], csrf_header)

    def _read_json_body(self) -> Optional[Dict[str, Any]]:
        """Reads and parses JSON body from request."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                return {}
            raw_body = self.rfile.read(content_length).decode("utf-8")
            return json.loads(raw_body)
        except Exception:
            return None

    def send_json(self, status_code: int, payload: Any, headers: Optional[Dict[str, str]] = None) -> None:
        """Sends a JSON response with status code and headers."""
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, status_code: int, message: str) -> None:
        """Sends a standardized JSON error response."""
        self.send_json(status_code, {"error": True, "message": message})

    def send_static_file(self, file_path: str, content_type: Optional[str] = None) -> None:
        """Streams a static file to the client with caching headers."""
        if not os.path.isfile(file_path):
            self.send_error_json(HTTPStatus.NOT_FOUND, "File not found")
            return

        if not content_type:
            ext = os.path.splitext(file_path)[1].lower()
            mime_map = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".json": "application/json; charset=utf-8",
                ".csv": "text/csv; charset=utf-8",
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".ico": "image/x-icon",
                ".drawio": "application/xml; charset=utf-8",
            }
            content_type = mime_map.get(ext, "application/octet-stream")

        file_size = os.path.getsize(file_path)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_size))
        # Short cache for static dashboard assets
        self.send_header("Cache-Control", "max-age=60")
        self.end_headers()

        with open(file_path, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    # --------------------------------------------------------------------------
    # CORS & OPTIONS HANDLER
    # --------------------------------------------------------------------------

    def do_OPTIONS(self) -> None:
        """Handles pre-flight CORS requests gracefully."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-CSRF-Token")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    # --------------------------------------------------------------------------
    # GET REQUEST DISPATCHER
    # --------------------------------------------------------------------------

    def do_GET(self) -> None:
        """Dispatches GET requests to REST API or static file handler."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. REST API Routing
        if path.startswith("/api/v1/"):
            self._handle_api_get(path, query)
            return

        # 2. Static File Serving
        self._handle_static_get(path)

    def _handle_api_get(self, path: str, query: Dict[str, List[str]]) -> None:
        """Handles API GET endpoints."""
        # Unauthenticated endpoints
        if path == "/api/v1/auth/status":
            sess = self._get_authenticated_user()
            self.send_json(HTTPStatus.OK, {
                "authenticated": bool(sess),
                "user": {"username": sess["username"], "role": sess["role"]} if sess else None
            })
            return

        # Protected endpoints require valid session
        sess = self._get_authenticated_user()
        if not sess:
            self.send_error_json(HTTPStatus.UNAUTHORIZED, "Authentication required")
            return

        user_role = sess["role"]
        auth_mgr = self.server.auth_mgr

        # GET /api/v1/auth/me
        if path == "/api/v1/auth/me":
            user_info = auth_mgr.get_user(sess["username"]) or {}
            self.send_json(HTTPStatus.OK, {
                "username": sess["username"],
                "role": user_role,
                "csrf_token": sess.get("csrf_token", ""),
                "permissions": list(ROLE_PERMISSIONS.get(user_role, set())),
                "description": user_info.get("description", ""),
                "is_default_password": sess.get("is_default_password", False)
            })
            return

        # GET /api/v1/summary
        if path == "/api/v1/summary":
            if not auth_mgr.has_permission(user_role, "view_metrics"):
                self.send_error_json(HTTPStatus.FORBIDDEN, "Permission denied")
                return
            summary = self.server.get_system_summary()
            self.send_json(HTTPStatus.OK, summary)
            return

        # GET /api/v1/runs
        if path == "/api/v1/runs":
            if not auth_mgr.has_permission(user_role, "view_metrics"):
                self.send_error_json(HTTPStatus.FORBIDDEN, "Permission denied")
                return
            runs = self.server.list_runs()
            self.send_json(HTTPStatus.OK, {"runs": runs})
            return

        # GET /api/v1/runs/{run_id}/summary
        m_run = re.match(r"^/api/v1/runs/([^/]+)/summary$", path)
        if m_run:
            if not auth_mgr.has_permission(user_role, "view_metrics"):
                self.send_error_json(HTTPStatus.FORBIDDEN, "Permission denied")
                return
            run_id = m_run.group(1)
            details = self.server.get_run_summary(run_id)
            if not details:
                self.send_error_json(HTTPStatus.NOT_FOUND, f"Run '{run_id}' not found")
                return
            self.send_json(HTTPStatus.OK, details)
            return

        # GET /api/v1/cron/status
        if path == "/api/v1/cron/status":
            if not auth_mgr.has_permission(user_role, "view_metrics"):
                self.send_error_json(HTTPStatus.FORBIDDEN, "Permission denied")
                return
            cron_stat = self.server.get_cron_status()
            self.send_json(HTTPStatus.OK, cron_stat)
            return

        # GET /api/v1/configs
        if path == "/api/v1/configs":
            if not (auth_mgr.has_permission(user_role, "view_json") or auth_mgr.has_permission(user_role, "view_cfg")):
                self.send_error_json(HTTPStatus.FORBIDDEN, "Permission denied")
                return
            configs = self.server.list_manageable_configs(user_role)
            self.send_json(HTTPStatus.OK, {"configs": configs})
            return

        # GET /api/v1/configs/{filename}
        m_cfg = re.match(r"^/api/v1/configs/([^/]+)$", path)
        if m_cfg:
            filename = m_cfg.group(1)
            is_json = filename.endswith(".json")
            perm_needed = "view_json" if is_json else "view_cfg"
            if not auth_mgr.has_permission(user_role, perm_needed):
                self.send_error_json(HTTPStatus.FORBIDDEN, "Permission denied for this configuration type")
                return
            content, err = self.server.read_config_file(filename)
            if err:
                self.send_error_json(HTTPStatus.NOT_FOUND, err)
                return
            self.send_json(HTTPStatus.OK, {
                "filename": filename,
                "content": content,
                "is_json": is_json,
                "can_edit": auth_mgr.has_permission(user_role, "edit_json" if is_json else "edit_cfg")
            })
            return

        # GET /api/v1/users
        if path == "/api/v1/users":
            if not auth_mgr.has_permission(user_role, "manage_users"):
                self.send_error_json(HTTPStatus.FORBIDDEN, "SuperAdmin permission required")
                return
            users = auth_mgr.list_users()
            self.send_json(HTTPStatus.OK, {"users": users, "roles": list(ROLE_PERMISSIONS.keys())})
            return

        # GET /api/v1/reports/download/{run_id}/{type}
        m_rep = re.match(r"^/api/v1/reports/download/([^/]+)/([^/]+)$", path)
        if m_rep:
            if not auth_mgr.has_permission(user_role, "export_reports"):
                self.send_error_json(HTTPStatus.FORBIDDEN, "Permission denied")
                return
            run_id, rep_type = m_rep.group(1), m_rep.group(2)
            f_path, fname = self.server.resolve_report_file(run_id, rep_type)
            if not f_path or not os.path.isfile(f_path):
                self.send_error_json(HTTPStatus.NOT_FOUND, "Report file not found")
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/csv; charset=utf-8" if fname.endswith(".csv") else "application/json")
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
            self.send_header("Content-Length", str(os.path.getsize(f_path)))
            self.end_headers()
            with open(f_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
            return

        self.send_error_json(HTTPStatus.NOT_FOUND, "Endpoint not found")

    # --------------------------------------------------------------------------
    # POST REQUEST DISPATCHER
    # --------------------------------------------------------------------------

    def do_POST(self) -> None:
        """Dispatches POST requests (login, logout, user creation)."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json_body() or {}

        # POST /api/v1/auth/login
        if path == "/api/v1/auth/login":
            username = str(body.get("username", "")).strip()
            password = str(body.get("password", ""))
            sess = self.server.auth_mgr.authenticate(username, password)
            if not sess:
                self.send_error_json(HTTPStatus.UNAUTHORIZED, "Invalid username or password")
                return

            # Set HttpOnly Cookie + return CSRF token
            cookie_val = f"ndx_session={sess['session_token']}; Path=/; HttpOnly; SameSite=Lax; Max-Age={AuthManager.SESSION_TTL_SECONDS}"
            self.send_json(
                HTTPStatus.OK,
                {
                    "success": True,
                    "username": sess["username"],
                    "role": sess["role"],
                    "csrf_token": sess["csrf_token"],
                    "is_default_password": sess.get("is_default_password", False),
                    "expires_at": sess["expires_at"]
                },
                headers={"Set-Cookie": cookie_val}
            )
            return

        # POST /api/v1/auth/logout
        if path == "/api/v1/auth/logout":
            token = self._get_session_token()
            if token:
                self.server.auth_mgr.revoke_session(token)
            clear_cookie = "ndx_session=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly"
            self.send_json(HTTPStatus.OK, {"success": True, "message": "Logged out"}, headers={"Set-Cookie": clear_cookie})
            return

        # All mutating actions require active session and CSRF validation
        sess = self._get_authenticated_user()
        if not sess:
            self.send_error_json(HTTPStatus.UNAUTHORIZED, "Authentication required")
            return

        if not self._validate_csrf(sess):
            self.send_error_json(HTTPStatus.FORBIDDEN, "Invalid or missing CSRF token")
            return

        user_role = sess["role"]
        auth_mgr = self.server.auth_mgr

        # POST /api/v1/users (Create User)
        if path == "/api/v1/users":
            if not auth_mgr.has_permission(user_role, "manage_users"):
                self.send_error_json(HTTPStatus.FORBIDDEN, "SuperAdmin permission required")
                return
            uname = str(body.get("username", "")).strip()
            pwd = str(body.get("password", ""))
            role = str(body.get("role", "Operator"))
            desc = str(body.get("description", ""))
            ok, msg = auth_mgr.create_user(uname, pwd, role=role, description=desc)
            if not ok:
                self.send_error_json(HTTPStatus.BAD_REQUEST, msg)
                return
            self.send_json(HTTPStatus.CREATED, {"success": True, "message": msg})
            return

        self.send_error_json(HTTPStatus.NOT_FOUND, "Endpoint not found")

    # --------------------------------------------------------------------------
    # PUT REQUEST DISPATCHER (CONFIG & USER UPDATES)
    # --------------------------------------------------------------------------

    def do_PUT(self) -> None:
        """Dispatches PUT requests (config save, password change)."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json_body() or {}

        sess = self._get_authenticated_user()
        if not sess:
            self.send_error_json(HTTPStatus.UNAUTHORIZED, "Authentication required")
            return

        if not self._validate_csrf(sess):
            self.send_error_json(HTTPStatus.FORBIDDEN, "Invalid or missing CSRF token")
            return

        user_role = sess["role"]
        auth_mgr = self.server.auth_mgr

        # PUT /api/v1/configs/{filename}
        m_cfg = re.match(r"^/api/v1/configs/([^/]+)$", path)
        if m_cfg:
            filename = m_cfg.group(1)
            is_json = filename.endswith(".json")
            content = body.get("content", "")

            # Role validation
            if is_json:
                if filename in ("network.json",):
                    if not (auth_mgr.has_permission(user_role, "edit_json") or auth_mgr.has_permission(user_role, "edit_json_network")):
                        self.send_error_json(HTTPStatus.FORBIDDEN, "Permission denied to edit network JSON")
                        return
                else:
                    if not auth_mgr.has_permission(user_role, "edit_json"):
                        self.send_error_json(HTTPStatus.FORBIDDEN, "Permission denied to edit system JSON")
                        return
            else:
                if not auth_mgr.has_permission(user_role, "edit_cfg"):
                    self.send_error_json(HTTPStatus.FORBIDDEN, "Permission denied to edit configuration (.cfg) files")
                    return

            ok, msg = self.server.write_config_file(filename, content)
            if not ok:
                self.send_error_json(HTTPStatus.BAD_REQUEST, msg)
                return
            self.send_json(HTTPStatus.OK, {"success": True, "message": msg})
            return

        # PUT /api/v1/users/{username}/password
        m_pwd = re.match(r"^/api/v1/users/([^/]+)/password$", path)
        if m_pwd:
            target_user = m_pwd.group(1)
            # Only self or SuperAdmin can change password
            if sess["username"] != target_user and not auth_mgr.has_permission(user_role, "manage_users"):
                self.send_error_json(HTTPStatus.FORBIDDEN, "Permission denied")
                return
            new_pass = body.get("new_password", "")
            ok, msg = auth_mgr.update_password(target_user, new_pass)
            if not ok:
                self.send_error_json(HTTPStatus.BAD_REQUEST, msg)
                return
            if sess["username"] == target_user:
                sess["is_default_password"] = (new_pass == "admin")
            self.send_json(HTTPStatus.OK, {
                "success": True,
                "message": msg,
                "is_default_password": sess.get("is_default_password", False)
            })
            return

        self.send_error_json(HTTPStatus.NOT_FOUND, "Endpoint not found")

    # --------------------------------------------------------------------------
    # DELETE REQUEST DISPATCHER
    # --------------------------------------------------------------------------

    def do_DELETE(self) -> None:
        """Dispatches DELETE requests (user deletion)."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        sess = self._get_authenticated_user()
        if not sess:
            self.send_error_json(HTTPStatus.UNAUTHORIZED, "Authentication required")
            return

        if not self._validate_csrf(sess):
            self.send_error_json(HTTPStatus.FORBIDDEN, "Invalid or missing CSRF token")
            return

        user_role = sess["role"]
        auth_mgr = self.server.auth_mgr

        # DELETE /api/v1/users/{username}
        m_usr = re.match(r"^/api/v1/users/([^/]+)$", path)
        if m_usr:
            target_user = m_usr.group(1)
            if not auth_mgr.has_permission(user_role, "manage_users"):
                self.send_error_json(HTTPStatus.FORBIDDEN, "SuperAdmin permission required")
                return
            ok, msg = auth_mgr.delete_user(target_user)
            if not ok:
                self.send_error_json(HTTPStatus.BAD_REQUEST, msg)
                return
            self.send_json(HTTPStatus.OK, {"success": True, "message": msg})
            return

        self.send_error_json(HTTPStatus.NOT_FOUND, "Endpoint not found")

    # --------------------------------------------------------------------------
    # STATIC FILE HANDLER
    # --------------------------------------------------------------------------

    def _handle_static_get(self, path: str) -> None:
        """Safely serves static portal and dashboard files with traversal guards."""
        clean_path = path.lstrip("/")
        if not clean_path or clean_path == "/":
            clean_path = "index.html"

        # Check if requesting admin portal asset
        if clean_path.startswith("admin/") or clean_path == "admin":
            admin_rel = clean_path[6:] if clean_path.startswith("admin/") else "index.html"
            if not admin_rel:
                admin_rel = "index.html"
            admin_base = Path(self.server.repo_dir) / "web" / "admin"
            target_file = (admin_base / admin_rel).resolve()
            if str(target_file).startswith(str(admin_base)) and target_file.is_file():
                self.send_static_file(str(target_file))
                return

        # Check in outbase directory (where dashboards, runs, and indexes reside)
        outbase_path = Path(self.server.outbase).resolve()
        target_file = (outbase_path / clean_path).resolve()

        # Strict Path-Traversal Guard
        if not str(target_file).startswith(str(outbase_path)):
            self.send_error_json(HTTPStatus.FORBIDDEN, "Access denied")
            return

        if target_file.is_file():
            self.send_static_file(str(target_file))
            return

        # Fallback to repo root for assets (e.g., demo/ or web/)
        repo_path = Path(self.server.repo_dir).resolve()
        repo_target = (repo_path / clean_path).resolve()
        if str(repo_target).startswith(str(repo_path)) and repo_target.is_file():
            self.send_static_file(str(repo_target))
            return

        self.send_error_json(HTTPStatus.NOT_FOUND, f"Resource not found: {path}")


# ------------------------------------------------------------------------------
# EMBEDDED WEB SERVER CLASS
# ------------------------------------------------------------------------------

class NDXWebServer(ThreadingHTTPServer):
    """
    Zero-dependency Threading HTTP Server hosting the management portal
    and telemetry aggregation backend.
    """

    def __init__(
        self,
        outbase: str,
        host: str = "127.0.0.1",
        port: int = 8080,
        users_file: Optional[str] = None
    ):
        self.outbase = os.path.abspath(outbase)
        self.repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.auth_mgr = AuthManager(users_file=users_file)
        
        super().__init__((host, port), NDXRequestHandler)

    # --------------------------------------------------------------------------
    # TELEMETRY & RUN SUMMARY HELPERS
    # --------------------------------------------------------------------------

    def get_system_summary(self) -> Dict[str, Any]:
        """Compiles global executive health and storage metrics."""
        runs = self.list_runs()
        runs_dir = os.path.join(self.outbase, "runs")
        
        # Calculate disk storage size
        disk_bytes = 0
        if os.path.isdir(runs_dir):
            for root, _, files in os.walk(runs_dir):
                for f in files:
                    try:
                        disk_bytes += os.path.getsize(os.path.join(root, f))
                    except Exception:
                        pass

        # Check SQLite db
        db_path = os.path.join(self.outbase, "database", "storage.db")
        db_bytes = os.path.getsize(db_path) if os.path.isfile(db_path) else 0

        # Unique nodes across recent runs
        unique_nodes = set()
        latest_run = runs[0] if runs else None
        oldest_run = runs[-1] if runs else None

        if latest_run:
            details = self.get_run_summary(latest_run["id"])
            if details and "elements" in details:
                unique_nodes.update([e["element"] for e in details["elements"]])

        return {
            "total_runs": len(runs),
            "latest_run": latest_run,
            "oldest_run": oldest_run,
            "active_elements_count": len(unique_nodes),
            "storage": {
                "disk_bytes": disk_bytes,
                "disk_mb": round(disk_bytes / (1024 * 1024), 2),
                "database_bytes": db_bytes,
                "database_mb": round(db_bytes / (1024 * 1024), 2),
                "total_mb": round((disk_bytes + db_bytes) / (1024 * 1024), 2)
            },
            "cron": self.get_cron_status()
        }

    def list_runs(self) -> List[Dict[str, Any]]:
        """Scans and lists all snapshot runs ordered descending by date."""
        runs_dir = os.path.join(self.outbase, "runs")
        if not os.path.isdir(runs_dir):
            return []

        entries = []
        for name in sorted(os.listdir(runs_dir), reverse=True):
            r_path = os.path.join(runs_dir, name)
            if not os.path.isdir(r_path) or not re.match(r"^\d{8}_\d{6}$", name):
                continue

            # Format readable timestamp: YYYY-MM-DD HH:MM:SS
            try:
                date_part, time_part = name.split("_")
                formatted_date = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:]}"
            except Exception:
                formatted_date = name

            # Quick status inspection
            status_file = os.path.join(r_path, "resume", "status.elements.csv")
            node_cnt = 0
            if os.path.isfile(status_file):
                try:
                    with open(status_file, "r", encoding="utf-8", errors="ignore") as f:
                        node_cnt = sum(1 for _ in csv.DictReader(f, delimiter=";"))
                except Exception:
                    pass

            has_ping = (
                os.path.isfile(os.path.join(r_path, "ping-matrix", "resume", "ping_matrix_list.json"))
                or os.path.isfile(os.path.join(r_path, "resume", "ping_matrix_list.json"))
            )
            entries.append({
                "id": name,
                "formatted_date": formatted_date,
                "node_count": node_cnt,
                "has_ping": has_ping,
                "has_topology": os.path.isfile(os.path.join(r_path, "connections", "topology.connections.SUM.csv"))
            })

        return entries

    def get_run_summary(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Deep telemetry extractor for a specific collection snapshot."""
        run_dir = os.path.join(self.outbase, "runs", run_id)
        if not os.path.isdir(run_dir):
            return None

        resume_dir = os.path.join(run_dir, "resume")
        status_file = os.path.join(resume_dir, "status.elements.csv")

        # Discover ping_matrix_list.json in ping-matrix subfolder or resume
        ping_file = os.path.join(run_dir, "ping-matrix", "resume", "ping_matrix_list.json")
        if not os.path.isfile(ping_file):
            ping_file = os.path.join(resume_dir, "ping_matrix_list.json")

        interfaces_file = os.path.join(resume_dir, "interfaces_all.csv")
        conn_file = os.path.join(run_dir, "connections", "topology.connections.SUM.csv")
        lldp_file = os.path.join(resume_dir, "lldp_mismatch_report.csv")

        # 1. Element SSH Connection Health
        elements_list = []
        status_counts = {"ok": 0, "failed": 0, "timeout": 0, "auth_fail": 0}
        if os.path.isfile(status_file):
            try:
                with open(status_file, "r", encoding="utf-8", errors="ignore") as f:
                    for row in csv.DictReader(f, delimiter=";"):
                        el = (row.get("element") or row.get("element_name") or "").strip()
                        st = row.get("status", "ok").strip().lower()
                        # OK elements must NOT show working_key or platform profile as error
                        raw_err = (row.get("error") or row.get("details") or "").strip()
                        err = raw_err if st != "ok" and raw_err != "-" else ""
                        if el:
                            elements_list.append({"element": el, "status": st, "error": err})
                            if st == "ok":
                                status_counts["ok"] += 1
                            else:
                                status_counts["failed"] += 1
                                if "auth" in str(err).lower():
                                    status_counts["auth_fail"] += 1
                                elif "time" in str(err).lower():
                                    status_counts["timeout"] += 1
            except Exception:
                pass

        # Enrich failed elements with exact diagnostics from commands.log if error is missing
        failed_with_no_diag = [e for e in elements_list if e["status"] != "ok" and not e["error"]]
        if failed_with_no_diag:
            commands_log_text = ""
            direct_log = os.path.join(run_dir, "log", "commands.log")
            if os.path.isfile(direct_log):
                try:
                    with open(direct_log, "r", encoding="utf-8", errors="ignore") as f:
                        commands_log_text = f.read()
                except Exception:
                    pass
            elif os.path.isfile(os.path.join(run_dir, "log.zip")):
                try:
                    import zipfile
                    with zipfile.ZipFile(os.path.join(run_dir, "log.zip")) as z:
                        if "commands.log" in z.namelist():
                            with z.open("commands.log") as f:
                                commands_log_text = f.read().decode("utf-8", errors="ignore")
                except Exception:
                    pass

            if commands_log_text:
                failed_lookup = {e["element"]: e for e in failed_with_no_diag}
                for match in re.finditer(r"Connection/Execution failed for ([^\s]+) at [^\s]+ with key '[^']+': (.*)", commands_log_text):
                    h = match.group(1).strip()
                    err_msg = match.group(2).strip()
                    if h in failed_lookup and not failed_lookup[h]["error"]:
                        failed_lookup[h]["error"] = err_msg
                        if "time" in err_msg.lower():
                            status_counts["timeout"] += 1
                        elif "auth" in err_msg.lower():
                            status_counts["auth_fail"] += 1

        # Resilient fallback: If status.elements.csv has empty element column, recover from filtered_elements.cfg
        if not elements_list:
            filtered_cfg = os.path.join(run_dir, "filtered_elements.cfg")
            if not os.path.isfile(filtered_cfg):
                filtered_cfg = os.path.join(run_dir, "ping-matrix", "filtered_elements.cfg")
            if os.path.isfile(filtered_cfg):
                try:
                    with open(filtered_cfg, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#"):
                                el = line.split(";")[0].strip()
                                elements_list.append({"element": el, "status": "ok", "error": ""})
                                status_counts["ok"] += 1
                except Exception:
                    pass

        # 2. Ping Telemetry Health
        ping_summary = {"total": 0, "healthy": 0, "warning": 0, "critical": 0, "dead": 0, "avg_latency_ms": 0.0}
        if os.path.isfile(ping_file):
            try:
                with open(ping_file, "r", encoding="utf-8", errors="ignore") as f:
                    p_data = json.load(f)
                    meta = p_data.get("metadata", {})
                    health = meta.get("network_health", {})
                    ping_summary["total"] = health.get("total_links", meta.get("total_pings", meta.get("total_tests", 0)))
                    ping_summary["healthy"] = health.get("healthy", 0)
                    ping_summary["warning"] = health.get("warning", 0)
                    ping_summary["critical"] = health.get("critical", 0)
                    ping_summary["dead"] = health.get("dead", 0)

                    # Compute global latency from metadata.node_stats or root node_stats
                    node_stats = meta.get("node_stats") or p_data.get("node_stats", {})
                    lats = [
                        s.get("avg_global_latency", 0)
                        for s in node_stats.values()
                        if isinstance(s, dict) and s.get("avg_global_latency", -1) > 0
                    ]
                    if lats:
                        ping_summary["avg_latency_ms"] = round(sum(lats) / len(lats), 2)
            except Exception:
                pass

        # 3. Interfaces & Topology stats
        interface_count = 0
        int_up = 0
        if os.path.isfile(interfaces_file):
            try:
                with open(interfaces_file, "r", encoding="utf-8", errors="ignore") as f:
                    for r in csv.DictReader(f, delimiter=";"):
                        interface_count += 1
                        if r.get("admin_status", "").lower() == "up":
                            int_up += 1
            except Exception:
                pass

        links_count = 0
        if os.path.isfile(conn_file):
            try:
                with open(conn_file, "r", encoding="utf-8", errors="ignore") as f:
                    links_count = sum(1 for _ in csv.DictReader(f, delimiter=";"))
            except Exception:
                pass

        lldp_mismatches = 0
        if os.path.isfile(lldp_file):
            try:
                with open(lldp_file, "r", encoding="utf-8", errors="ignore") as f:
                    lldp_mismatches = sum(1 for _ in csv.DictReader(f, delimiter=";"))
            except Exception:
                pass

        return {
            "run_id": run_id,
            "elements_health": {
                "total": len(elements_list),
                "counts": status_counts,
                "elements": elements_list
            },
            "ping_health": ping_summary,
            "topology_health": {
                "total_interfaces": interface_count,
                "interfaces_up": int_up,
                "interfaces_down": interface_count - int_up,
                "total_links": links_count,
                "lldp_mismatches": lldp_mismatches
            },
            "has_dashboards": {
                "inventory": os.path.isfile(os.path.join(self.outbase, "inventory", "index.html")),
                "diff": os.path.isfile(os.path.join(self.outbase, "diff", "index.html")),
                "topology": os.path.isfile(os.path.join(self.outbase, "topology", "index.html")),
                "ping_matrix": os.path.isfile(os.path.join(self.outbase, "ping-matrix", "index.html"))
            }
        }

    def get_cron_status(self) -> Dict[str, Any]:
        """Inspects cron execution log and evaluates scheduling health."""
        # Check potential cron log locations
        log_candidates = [
            os.path.join(self.outbase, "cron_execution.log"),
            os.path.join(os.path.dirname(self.outbase), "cron_execution.log"),
            os.path.join(os.path.dirname(os.path.dirname(self.outbase)), "cron_execution.log"),
            os.path.join(self.repo_dir, "cron_execution.log")
        ]

        log_file = None
        for cand in log_candidates:
            if os.path.isfile(cand):
                log_file = cand
                break

        if not log_file:
            return {
                "status": "UNKNOWN",
                "message": "Cron execution log not found",
                "last_run_timestamp": None,
                "hours_since_last_run": None,
                "is_delayed": False,
                "last_lines": []
            }

        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            last_lines = [l.strip() for l in lines[-15:] if l.strip()]

            # Search for timestamps like [YYYY-MM-DD HH:MM:SS]
            last_ts = None
            for l in reversed(lines):
                m = re.search(r"\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]", l)
                if m:
                    last_ts = m.group(1)
                    break

            hours_ago = None
            is_delayed = False
            if last_ts:
                try:
                    t_struct = time.strptime(last_ts, "%Y-%m-%d %H:%M:%S")
                    t_epoch = time.mktime(t_struct)
                    hours_ago = round((time.time() - t_epoch) / 3600, 1)
                    # Semi-weekly schedule: > 96 hours (4 days) signals a delayed cron
                    is_delayed = bool(hours_ago > 96.0)
                except Exception:
                    pass

            # Check structured tokens in last 30 lines
            recent_text = "\n".join(lines[-30:]) if lines else ""
            has_failed = bool("[STATUS: FAILED]" in recent_text or "[ERRO]" in recent_text or "Traceback" in recent_text)
            is_running = bool("[STATUS: STARTING]" in recent_text and "[STATUS: COMPLETED]" not in recent_text and not has_failed)

            if has_failed:
                status_text = "ERROR"
            elif is_running:
                status_text = "RUNNING"
            elif is_delayed:
                status_text = "DELAYED"
            else:
                status_text = "HEALTHY"

            return {
                "status": status_text,
                "log_file": os.path.basename(log_file),
                "last_run_timestamp": last_ts,
                "hours_since_last_run": hours_ago,
                "is_delayed": is_delayed,
                "last_lines": last_lines
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "message": str(e),
                "is_delayed": False,
                "last_lines": []
            }

    # --------------------------------------------------------------------------
    # CONFIGURATION FILE DISPATCHER
    # --------------------------------------------------------------------------

    def list_manageable_configs(self, role: str) -> List[Dict[str, Any]]:
        """Lists files permitted for viewing/editing based on user role."""
        configs = []
        cfg_dir = os.path.join(self.repo_dir, "config")
        external_cfg_dirs = [
            os.path.join(os.path.dirname(self.outbase), "config"),
            os.path.join(os.path.dirname(os.path.dirname(self.outbase)), "config"),
        ]

        # 1. JSON Configuration Files
        json_files = ["extractor.json", "ssh.json", "network.json", "ping.json", "storage.json", "settings.json"]
        seen_jsons = set()
        for jf in json_files:
            fp = os.path.join(cfg_dir, jf)
            if not os.path.isfile(fp):
                for ed in external_cfg_dirs:
                    cand = os.path.join(ed, jf)
                    if os.path.isfile(cand):
                        fp = cand
                        break
            if os.path.isfile(fp) and jf not in seen_jsons:
                seen_jsons.add(jf)
                can_edit = (role == "SuperAdmin") or (role == "NetOps" and jf == "network.json")
                configs.append({
                    "filename": jf,
                    "type": "json",
                    "description": f"Domain configuration ({jf})",
                    "size_bytes": os.path.getsize(fp),
                    "can_edit": can_edit
                })

        # 2. CFG Command/Element Files (Look in outbase parent config and local config/)
        candidate_cfg_dirs = external_cfg_dirs + [cfg_dir]
        seen_cfgs = set()
        for cdir in candidate_cfg_dirs:
            if not os.path.isdir(cdir):
                continue
            for fname in sorted(os.listdir(cdir)):
                if fname.endswith(".cfg") and fname not in seen_cfgs:
                    # Sensitive elements.cfg can be viewed if role allows
                    seen_cfgs.add(fname)
                    fp = os.path.join(cdir, fname)
                    can_edit = (role in ("SuperAdmin", "NetOps"))
                    configs.append({
                        "filename": fname,
                        "type": "cfg",
                        "description": f"Network macro / elements configuration ({fname})",
                        "size_bytes": os.path.getsize(fp),
                        "can_edit": can_edit
                    })

        return configs

    def _resolve_config_path(self, filename: str) -> Optional[Path]:
        """Safely maps a config filename to its verified Path without traversal."""
        clean_name = os.path.basename(filename)
        if clean_name != filename or ".." in filename:
            return None

        # Strict extension and file protection: never expose .env, passwords, or arbitrary files
        if clean_name in (".env", "users.json") or clean_name.startswith("."):
            return None
        if not (clean_name.endswith(".json") or clean_name.endswith(".cfg")):
            return None

        # Check external production config/ first (if running against production outbase)
        p3 = (Path(self.outbase).parent.parent / "config" / clean_name).resolve()
        if p3.is_file():
            return p3

        p2 = (Path(self.outbase).parent / "config" / clean_name).resolve()
        if p2.is_file():
            return p2

        # Check standard repo config/
        p1 = (Path(self.repo_dir) / "config" / clean_name).resolve()
        if p1.is_file():
            return p1

        return None

    def read_config_file(self, filename: str) -> Tuple[Optional[str], Optional[str]]:
        """Reads configuration file content safely."""
        p = self._resolve_config_path(filename)
        if not p or not p.is_file():
            return None, f"Configuration file '{filename}' not found"

        try:
            with open(p, "r", encoding="utf-8") as f:
                return f.read(), None
        except Exception as e:
            return None, f"Failed to read file: {e}"

    def write_config_file(self, filename: str, content: str) -> Tuple[bool, str]:
        """Validates syntax and writes configuration file atomically."""
        p = self._resolve_config_path(filename)
        if not p:
            return False, f"Configuration file '{filename}' not found or restricted"

        # If it is JSON, validate syntax before saving
        if filename.endswith(".json"):
            try:
                parsed = json.loads(content)
                # Pretty re-format JSON cleanly
                content = json.dumps(parsed, indent=2) + "\n"
            except Exception as ex:
                return False, f"Invalid JSON syntax: {ex}"

        try:
            tmp_file = f"{p}.tmp.{int(time.time())}"
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_file, p)
            return True, f"File '{filename}' updated successfully"
        except Exception as e:
            return False, f"Failed to save file: {e}"

    def resolve_report_file(self, run_id: str, rep_type: str) -> Tuple[Optional[str], Optional[str]]:
        """Maps download report request to physical file path."""
        run_dir = os.path.join(self.outbase, "runs", run_id)
        if not os.path.isdir(run_dir):
            return None, None

        if rep_type == "status_elements":
            return os.path.join(run_dir, "resume", "status.elements.csv"), f"status_elements_{run_id}.csv"
        elif rep_type == "interfaces":
            return os.path.join(run_dir, "resume", "interfaces_all.csv"), f"interfaces_{run_id}.csv"
        elif rep_type == "ping_matrix":
            return os.path.join(run_dir, "resume", "ping_matrix_list.json"), f"ping_matrix_{run_id}.json"
        elif rep_type == "lldp_mismatch":
            return os.path.join(run_dir, "resume", "lldp_mismatch_report.csv"), f"lldp_mismatch_{run_id}.csv"

        return None, None
