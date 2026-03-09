#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import csv
import glob
import re
import argparse
import json
from datetime import datetime

# Load settings
base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
config_path = os.path.join(base_path, "config", "settings.json")
json_config = {}
if os.path.exists(config_path):
    try:
        with open(config_path, "r") as f:
            json_config = json.load(f)
    except:
        pass

discovery_cfg = json_config.get("discovery", {})
_raw_prefixes = discovery_cfg.get("ignore_new_prefixes", ["JOAO", "MARIA"])
IGNORE_NEW_PREFIXES = tuple(str(p).upper() for p in _raw_prefixes)

def is_ignored(name):
    if not name: return True
    return name.upper().startswith(IGNORE_NEW_PREFIXES)

def clean_system_name(name):
    """Removes domain part from FQDN hostnames like ROUTER.xyz.com -> ROUTER"""
    if not name: return ""
    return name.split('.')[0].strip()

def main():
    parser = argparse.ArgumentParser(description="Generates status.elements.csv consolidation report.")
    parser.add_argument("--collect_dir", required=True, help="Directory containing the raw SSH text files.")
    parser.add_argument("--resume_dir", required=True, help="Directory containing the parsed CSV files.")
    parser.add_argument("--elements_cfg", required=True, help="Path to config/elements.cfg")
    args = parser.parse_args()

    out_csv = os.path.join(args.resume_dir, "status.elements.csv")

    # 1. Load Expected Elements from elements.cfg
    expected_elements = set()
    if os.path.isfile(args.elements_cfg):
        with open(args.elements_cfg, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'): continue
                parts = line.split(';')
                if len(parts) >= 1:
                    expected_elements.add(parts[0].strip())

    report_data = []
    found_elements = set()

    # 2. Load Successful Keys from commands.py run (if any)
    working_keys = {}
    success_keys_file = os.path.join(args.collect_dir, "successful_keys.csv")
    if os.path.isfile(success_keys_file):
        with open(success_keys_file, 'r') as f:
            for line in f:
                parts = line.strip().split(';')
                if len(parts) >= 3:
                    working_keys[parts[0]] = parts[2]

    report_data = []
    found_elements = set()

    # 3. Scan collect_dir for successful TXT extractions
    for expected in expected_elements:
        # Search for any file matching: {expected}.*.txt
        pattern = os.path.join(args.collect_dir, f"{expected}.*.txt")
        matching_files = glob.glob(pattern)

        if matching_files:
            # OK status
            first_file = matching_files[0]
            basename = os.path.basename(first_file)
            
            # Extract timestamp: EXPECTED.TIMESTAMP.CMD.txt
            parts = basename.split('.')
            timestamp = parts[1] if len(parts) > 1 else "-"
            
            # Find Real Hostname by grabbing the last few lines looking for a prompt matching # or >
            real_hostname = "-"
            try:
                with open(first_file, 'r', errors='ignore') as f:
                    # Read only the last chunk to save memory on large files
                    f.seek(0, os.SEEK_END)
                    pos = f.tell()
                    chunk_size = min(2000, pos)
                    f.seek(pos - chunk_size, os.SEEK_SET)
                    tail = f.read()
                    
                    # Usually: RP/0/RSP0/CPU0:REAL-HOST-NAME#
                    # Cisco: REAL-HOST-NAME> or REAL-HOST-NAME#
                    # Datacom: REAL-HOST-NAME#
                    lines = [ln.strip() for ln in tail.splitlines() if ln.strip()]
                    if lines:
                        last_line = lines[-1]
                        prompt_match = re.search(r'[:]?([A-Za-z0-9_-]+)[#>]', last_line)
                        if prompt_match:
                            real_hostname = prompt_match.group(1).strip()
            except Exception as e:
                pass
            
            report_data.append({
                "element_name": expected,
                "real_hostname": real_hostname,
                "timestamp": timestamp,
                "status": "ok",
                "working_key": working_keys.get(expected, "-")
            })
            found_elements.add(expected)
        else:
            # FAIL status (SSH likely timeout/refused)
            report_data.append({
                "element_name": expected,
                "real_hostname": "-",
                "timestamp": "-",
                "status": "fail",
                "working_key": "-"
            })

    # 4. Scan LLDP Neighbors to find "New" elements
    lldp_csv = os.path.join(args.resume_dir, "show_lldp_neighbors_detail_all.csv")
    if os.path.isfile(lldp_csv):
        with open(lldp_csv, 'r', newline='', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                sys_name = clean_system_name(row.get('system_name', ''))
                
                # If valid, not in our expected roster, and not in the ignore list
                if sys_name and (sys_name not in expected_elements) and (sys_name not in found_elements):
                    if not is_ignored(sys_name):
                        report_data.append({
                            "element_name": sys_name,
                            "real_hostname": "-",
                            "timestamp": "-",
                            "status": "new",
                            "working_key": "-"
                        })
                        found_elements.add(sys_name) # Prevent duplicates

    # 5. Write output to collect/status.elements.csv
    headers = ["element_name", "real_hostname", "timestamp", "status", "working_key"]
    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=';')
        writer.writeheader()
        
        # Sort so OKs and FAVs are grouped neatly
        # Order preference: ok -> fail -> new
        order_map = {"ok": 0, "fail": 1, "new": 2}
        report_data.sort(key=lambda x: (order_map.get(x["status"], 9), x["element_name"]))
        
        for row in report_data:
            writer.writerow(row)

    print(f"✅ Consolidation Status Report generated: {out_csv}")

if __name__ == '__main__':
    main()
