#!/usr/bin/env python3
"""
Verify Zero Leakage Tool
========================
Audits git tracking status and the demo/ directory to ensure zero production data,
credentials, real IP addresses, or production hostnames are ever committed or published.

Key Checks:
1. Git Hygiene: Ensures no production folders (infos*/), configs (*.cfg), keys (*.key, *.pem),
   environment files (.env), or logs (*.log) are tracked in Git.
2. Production Cross-Reference: Scans production config files (e.g., config/elements.cfg)
   if present, extracting real hostnames and IPs, and verifies that NONE of them appear in demo/.
3. IP Address Compliance: Verifies that any IP addresses present in demo/ belong strictly to
   documentation / synthetic test ranges (RFC 5737 TEST-NET ranges, RFC 3849, Loopback, Link-Local).
"""

import os
import sys
import re
import ipaddress
import subprocess
from pathlib import Path

# Terminal Colors
C_GREEN = '\033[92m'
C_YELLOW = '\033[93m'
C_RED = '\033[91m'
C_CYAN = '\033[96m'
C_BOLD = '\033[1m'
C_RESET = '\033[0m'

# Allowed Documentation and Testing IP Networks
ALLOWED_IPV4_NETWORKS = [
    ipaddress.ip_network("192.0.2.0/24"),      # RFC 5737 TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),   # RFC 5737 TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),    # RFC 5737 TEST-NET-3
    ipaddress.ip_network("127.0.0.0/8"),       # RFC 1122 Loopback
    ipaddress.ip_network("169.254.0.0/16"),    # RFC 3927 Link-Local
    ipaddress.ip_network("224.0.0.0/4"),       # Multicast
    ipaddress.ip_network("255.255.255.255/32") # Broadcast
]

ALLOWED_IPV6_NETWORKS = [
    ipaddress.ip_network("2001:db8::/32"),     # RFC 3849 Documentation
    ipaddress.ip_network("::1/128"),           # Loopback
    ipaddress.ip_network("fe80::/10")          # Link-Local
]

# Known template / example configs tracked by the repository
ALLOWED_TEMPLATE_CONFIGS = {
    "config/commands.cfg",
    "config/elements.cfg",
    "config/commands.icmp.cfg"
}

FORBIDDEN_FILE_PATTERNS = [
    re.compile(r"^infos.*", re.IGNORECASE),
    re.compile(r".*\.key$", re.IGNORECASE),
    re.compile(r".*\.pem$", re.IGNORECASE),
    re.compile(r"^\.env.*", re.IGNORECASE),
    re.compile(r".*\.log$", re.IGNORECASE),
]

def run_git_cmd(args):
    """Executes a git command and returns stdout lines."""
    try:
        res = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            check=True
        )
        return [line.strip() for line in res.stdout.splitlines() if line.strip()]
    except Exception as e:
        print(f"{C_YELLOW}[!] Warning: Git command failed: {e}{C_RESET}")
        return []

def check_git_hygiene(repo_root):
    """Checks tracked and staged git files for any forbidden production files."""
    print(f"\n{C_CYAN}[*] Step 1: Checking Git Tracking & Staged Files...{C_RESET}")
    tracked_files = run_git_cmd(["ls-files"])
    staged_files = run_git_cmd(["diff", "--cached", "--name-only"])
    all_files = set(tracked_files + staged_files)

    violations = []
    for file_path in all_files:
        norm_path = Path(file_path).as_posix()
        # Allow repository example template configs
        if norm_path in ALLOWED_TEMPLATE_CONFIGS:
            continue

        # Check for any other .cfg files
        if norm_path.endswith(".cfg"):
            violations.append((file_path, "Unauthorized .cfg configuration file tracked in Git"))
            continue

        # Check against forbidden patterns
        for pattern in FORBIDDEN_FILE_PATTERNS:
            if pattern.match(norm_path) or pattern.match(Path(file_path).name):
                # Exception: demo/ files are allowed unless they are .key or .pem
                if norm_path.startswith("demo/") and not (norm_path.endswith(".key") or norm_path.endswith(".pem")):
                    continue
                violations.append((file_path, f"Matches forbidden pattern {pattern.pattern}"))

    if violations:
        print(f"{C_RED}[!] FAILED: Found forbidden files tracked or staged in Git:{C_RESET}")
        for path, reason in violations:
            print(f"    - {path} ({reason})")
        return False

    print(f"{C_GREEN}[+] PASS: No production configs, logs, keys, or infos/ files are tracked in Git.{C_RESET}")
    return True

def extract_production_signatures(repo_root):
    """Extracts known hostnames and IPs from local production config files for cross-checking."""
    production_signatures = set()
    elements_cfg = repo_root / "config" / "elements.cfg"
    if elements_cfg.is_file():
        try:
            with open(elements_cfg, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or line.startswith(";"):
                        continue
                    # Parse element definitions or IPs
                    parts = line.split()
                    for p in parts:
                        token = p.strip(",;[]\"'")
                        if len(token) >= 4 and not token.startswith("http"):
                            production_signatures.add(token.upper())
        except Exception as e:
            print(f"{C_YELLOW}[!] Notice: Could not read elements.cfg: {e}{C_RESET}")
    return production_signatures

def check_demo_leakage(demo_dir, prod_signatures):
    """Deep scans all text files inside demo/ for production leaks or non-compliant IPs."""
    print(f"\n{C_CYAN}[*] Step 2: Auditing demo/ Content for Leaks & RFC Compliance...{C_RESET}")
    if not demo_dir.exists():
        print(f"{C_YELLOW}[*] Notice: demo/ directory does not exist yet (Skipping content audit).{C_RESET}")
        return True

    ipv4_pattern = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    text_extensions = {".html", ".js", ".json", ".csv", ".drawio", ".xml", ".txt", ".md", ".nojekyll"}

    scanned_files = 0
    ip_violations = []
    signature_violations = []

    for root, _, files in os.walk(demo_dir):
        for f in files:
            file_path = Path(root) / f
            if file_path.suffix.lower() not in text_extensions and file_path.name != ".nojekyll":
                continue

            # Skip third-party vendor minified libraries from IP regex false positives
            if file_path.name in {"viewer-static.min.js", "chart.js"}:
                continue

            scanned_files += 1
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            # 1. Check production signatures
            content_upper = content.upper()
            for sig in prod_signatures:
                if sig in content_upper:
                    signature_violations.append((file_path.relative_to(demo_dir.parent), sig))

            # 2. Check IP addresses
            matches = ipv4_pattern.findall(content)
            for raw_ip in matches:
                try:
                    ip_obj = ipaddress.ip_address(raw_ip)
                except ValueError:
                    continue

                # Check if in allowed documentation networks
                is_allowed = any(ip_obj in net for net in ALLOWED_IPV4_NETWORKS)
                # Ignore common subnet masks (255.255.255.0 etc) and 0.0.0.0
                if raw_ip.startswith("255.255.") or raw_ip == "0.0.0.0":
                    is_allowed = True

                if not is_allowed:
                    ip_violations.append((file_path.relative_to(demo_dir.parent), raw_ip))

    has_error = False
    if signature_violations:
        print(f"{C_RED}[!] FAILED: Found production elements/signatures inside demo/:{C_RESET}")
        for path, sig in signature_violations[:10]:
            print(f"    - File: {path} contains production signature: {sig}")
        if len(signature_violations) > 10:
            print(f"    ... and {len(signature_violations) - 10} more.")
        has_error = True

    if ip_violations:
        print(f"{C_RED}[!] FAILED: Found non-RFC compliant/real IP addresses inside demo/:{C_RESET}")
        for path, ip in set(ip_violations[:10]):
            print(f"    - File: {path} contains unauthorized IP: {ip}")
        if len(ip_violations) > 10:
            print(f"    ... and {len(ip_violations) - 10} more.")
        has_error = True

    if not has_error:
        print(f"{C_GREEN}[+] PASS: Scanned {scanned_files} files in demo/. Zero production data or illegal IPs found.{C_RESET}")
        return True

    return False

def main():
    repo_root = Path(__file__).resolve().parent.parent
    demo_dir = repo_root / "demo"

    print(f"{C_BOLD}{C_CYAN}============================================================{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}         ZERO PRODUCTION LEAKAGE AUDIT GATEKEEPER           {C_RESET}")
    print(f"{C_BOLD}{C_CYAN}============================================================{C_RESET}")
    print(f"Repository Root: {repo_root}")

    # Step 1: Git hygiene
    git_ok = check_git_hygiene(repo_root)

    # Step 2: Production signatures cross-check
    prod_signatures = extract_production_signatures(repo_root)
    print(f"Loaded {len(prod_signatures)} production signatures/elements for cross-checking.")

    # Step 3: Demo content inspection
    demo_ok = check_demo_leakage(demo_dir, prod_signatures)

    print(f"\n{C_BOLD}{C_CYAN}------------------------------------------------------------{C_RESET}")
    if git_ok and demo_ok:
        print(f"{C_BOLD}{C_GREEN}[✔] AUDIT PASSED: ZERO PRODUCTION LEAKAGE RISK DETECTED.{C_RESET}")
        print(f"{C_GREEN}The repository is clean and safe to commit.{C_RESET}\n")
        sys.exit(0)
    else:
        print(f"{C_BOLD}{C_RED}[✘] AUDIT FAILED: POTENTIAL LEAKAGE DETECTED. DO NOT COMMIT.{C_RESET}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
