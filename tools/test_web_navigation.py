#!/usr/bin/env python3
"""
Web Navigation & GitHub Pages Compatibility Tester
===================================================
Automated test suite that audits the demo/ web portal:
1. Relative Path Compliance: Ensures no root-relative URLs (e.g. '/inventory/index.html')
   exist in HTML/JS, which would break on GitHub Pages sub-paths ('/<repo>/').
2. End-to-End HTTP Navigation: Launches a local HTTP server and verifies that all
   portals, dashboards, manifests, chart scripts, and draw.io files return HTTP 200 OK.
"""

import os
import re
import sys
import time
import socket
import urllib.request
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# Terminal Colors
C_GREEN = '\033[92m'
C_YELLOW = '\033[93m'
C_RED = '\033[91m'
C_CYAN = '\033[96m'
C_BOLD = '\033[1m'
C_RESET = '\033[0m'

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = REPO_ROOT / "demo"

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def audit_relative_paths(demo_dir: Path):
    """Audits HTML and JS files to ensure they don't contain breaking root-relative links."""
    print(f"\n{C_CYAN}[*] Step 1: Auditing Link Relative Path Compliance for GitHub Pages...{C_RESET}")
    
    # Regex to catch root-relative links like href="/something" or src="/something" (excluding // external protocol)
    root_rel_pattern = re.compile(r"""(?:href|src)\s*=\s*["']/(?!/)([^"']+)["']""", re.IGNORECASE)
    
    violations = []
    scanned_count = 0

    for root, _, files in os.walk(demo_dir):
        for f in files:
            if not f.endswith((".html", ".js")):
                continue
            scanned_count += 1
            f_path = Path(root) / f
            try:
                content = f_path.read_text(encoding="utf-8", errors="ignore")
                matches = root_rel_pattern.findall(content)
                if matches:
                    violations.append((f_path.relative_to(demo_dir), matches[:3]))
            except Exception:
                continue

    if violations:
        print(f"{C_RED}[!] FAILED: Found root-relative URLs that will break on GitHub Pages:{C_RESET}")
        for path, bad_urls in violations:
            print(f"    - {path}: {bad_urls}")
        return False

    print(f"{C_GREEN}[+] PASS: Scanned {scanned_count} web files. All links and asset references use relative paths.{C_RESET}")
    return True

class QuietHTTPHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress routine GET logs
        pass

def run_http_server(port, root_dir, stop_event):
    class CustomServer(HTTPServer):
        allow_reuse_address = True

    def handler_factory(*args, **kwargs):
        return QuietHTTPHandler(*args, directory=str(root_dir), **kwargs)

    server = CustomServer(('127.0.0.1', port), handler_factory)
    while not stop_event.is_set():
        server.handle_request()
    server.server_close()

def audit_http_endpoints(port: int, demo_dir: Path):
    """Tests critical navigation endpoints against a live local HTTP server."""
    print(f"\n{C_CYAN}[*] Step 2: Testing Live HTTP Endpoints (Port {port})...{C_RESET}")
    
    base_url = f"http://127.0.0.1:{port}"
    
    # Find latest run
    run_dirs = sorted((demo_dir / "runs").glob("20*_*"))
    latest_run = run_dirs[-1].name if run_dirs else ""

    endpoints_to_test = [
        # Portals
        ("/", "Root Master Portal (index.html)"),
        ("/inventory/index.html", "Inventory Dashboard"),
        ("/inventory/manifest.js", "Inventory Manifest"),
        ("/diff/index.html", "Diff / Drift Dashboard"),
        ("/diff/manifest.js", "Diff Manifest"),
        ("/ping-matrix/index.html", "Ping Matrix Master Index"),
        ("/ping-matrix/history.html", "Ping History Chart.js Portal"),
        ("/ping-matrix/path.html", "Ping Route Path Portal"),
        ("/ping-matrix/chart.js", "Chart.js Vendor Library"),
        ("/ping-matrix/history/history_manifest.js", "Ping History Manifest"),
        ("/ping-matrix/history/history_rankings.js", "Ping History Rankings"),
        ("/topology/index.html", "Topology Navigation Hub"),
        ("/topology/manifest.js", "Topology Manifest"),
        ("/topology/viewer.html", "Draw.io Embedded Viewer"),
        ("/topology/viewer-static.min.js", "Offline Draw.io Vendor Engine"),
    ]

    if latest_run:
        endpoints_to_test.extend([
            (f"/runs/{latest_run}/topology/topology.connections.SUM_geografico.drawio", "Geographic Topology Diagram"),
            (f"/runs/{latest_run}/topology/topology.connections.SUM_circular.drawio", "Circular Topology Diagram"),
            (f"/runs/{latest_run}/topology/topology.connections.SUM_organico.drawio", "Organic Topology Diagram"),
            (f"/runs/{latest_run}/ping-matrix/resume/ping_matrix_list.json", "Ping Matrix JSON Telemetry"),
            (f"/runs/{latest_run}/ping-matrix/resume/ping_matrix_dashboard.html", "Individual Ping Dashboard HTML"),
            (f"/runs/{latest_run}/resume/interfaces_all.json", "Run Interfaces Table JSON"),
            (f"/runs/{latest_run}/connections/topology.connections.SUM.csv", "Run Connection SUM CSV"),
        ])

    passed_count = 0
    failed_count = 0

    for path, desc in endpoints_to_test:
        url = f"{base_url}{path}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Demo-QA-Bot/1.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = resp.status
                length = len(resp.read())
                if status == 200 and length > 0:
                    print(f"  • {C_GREEN}200 OK{C_RESET} ({length:7d} bytes) : {desc} [{path}]")
                    passed_count += 1
                else:
                    print(f"  • {C_RED}FAILED ({status}){C_RESET} : {desc} [{path}]")
                    failed_count += 1
        except Exception as e:
            print(f"  • {C_RED}ERROR{C_RESET} : {desc} [{path}] -> {e}")
            failed_count += 1

    print(f"\n{C_BOLD}HTTP Navigation Results: {passed_count} Passed, {failed_count} Failed.{C_RESET}")
    return failed_count == 0

def main():
    print(f"{C_BOLD}{C_CYAN}============================================================{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}       DEMO WEB PORTAL QA & GITHUB PAGES AUDITOR            {C_RESET}")
    print(f"{C_BOLD}{C_CYAN}============================================================{C_RESET}")
    print(f"Target Directory: {DEMO_DIR}")

    if not DEMO_DIR.is_dir():
        print(f"{C_RED}[!] Error: demo/ directory does not exist. Run Phase 3 first.{C_RESET}")
        sys.exit(1)

    # 1. Audit relative paths
    paths_ok = audit_relative_paths(DEMO_DIR)

    # 2. Launch ephemeral HTTP server and test endpoints
    port = find_free_port()
    stop_event = threading.Event()
    server_thread = threading.Thread(target=run_http_server, args=(port, DEMO_DIR, stop_event), daemon=True)
    server_thread.start()
    time.sleep(0.5)

    try:
        http_ok = audit_http_endpoints(port, DEMO_DIR)
    finally:
        stop_event.set()
        # Ping server to unblock handle_request loop
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
        except Exception:
            pass
        server_thread.join(timeout=2)

    print(f"\n{C_BOLD}{C_CYAN}------------------------------------------------------------{C_RESET}")
    if paths_ok and http_ok:
        print(f"{C_BOLD}{C_GREEN}[✔] QA VALIDATION PASSED: DEMO PORTAL IS 100% HEALTHY & COMPATIBLE WITH GITHUB PAGES!{C_RESET}\n")
        sys.exit(0)
    else:
        print(f"{C_BOLD}{C_RED}[✘] QA VALIDATION FAILED: BUGS OR BROKEN ENDPOINTS DETECTED.{C_RESET}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
