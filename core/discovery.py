#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import csv
import json
import ipaddress
import argparse
import logging

def load_settings():
    settings_path = "config/settings.json"
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load {settings_path}: {e}")
    return {}

def is_ip_in_subnets(ip, subnets):
    try:
        ip_obj = ipaddress.ip_address(ip)
        for subnet in subnets:
            if ip_obj in ipaddress.ip_network(subnet):
                return True
    except:
        pass
    return False

def read_existing_elements(paths_str):
    existing_ips = set()
    existing_names = set()
    if not paths_str:
        return existing_ips, existing_names
    
    paths = paths_str.split(',')
    for path in paths:
        path = path.strip()
        if os.path.isfile(path):
            with open(path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split(';')
                    if len(parts) >= 2:
                        name = parts[0].strip()
                        ip = parts[1].strip()
                        existing_names.add(name)
                        existing_ips.add(ip)
    return existing_ips, existing_names

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume_dir", required=True, help="Directory containing show_lldp_neighbors_detail_all.csv")
    parser.add_argument("--elements_cfg", default="config/elements.cfg", help="Current elements config to avoid duplicates")
    parser.add_argument("--outdir", required=True, help="Directory to save the discovery results")
    parser.add_argument("--out_filename", help="Filename for the discovered elements (overrides settings.json)")
    args = parser.parse_args()

    settings = load_settings()
    discovery_cfg = settings.get("discovery", {})
    
    preferred_subnets = discovery_cfg.get("preferred_management_subnets", [])
    ignore_prefixes = discovery_cfg.get("ignore_new_prefixes", [])
    fallback_keys = discovery_cfg.get("fallback_cmd_keys", ["cisco_ios"])
    out_filename = args.out_filename or discovery_cfg.get("output_filename", "discovery.elements.cfg")

    csv_path = os.path.join(args.resume_dir, "show_lldp_neighbors_detail_all.csv")
    if not os.path.isfile(csv_path):
        print(f"Error: {csv_path} not found.")
        sys.exit(1)

    existing_ips, existing_names = read_existing_elements(args.elements_cfg)
    
    # Structure: { system_name: { 'ips': [ip1, ip2], 'best_ip': None } }
    discovered_nodes = {}

    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            name = row.get('system_name', '').strip()
            ip = row.get('mgmt_ipv4', '').strip()
            
            if not name or not ip or ip == '0.0.0.0':
                continue
            
            # Filter by ignore prefixes
            should_ignore = False
            for pref in ignore_prefixes:
                if name.startswith(pref):
                    should_ignore = True
                    break
            if should_ignore:
                continue

            # Skip if hostname OR ip is already known
            if name in existing_names:
                print(f"  [SKIP] {name} already exists in elements configuration.")
                continue
            if ip in existing_ips:
                print(f"  [SKIP] {name} ({ip}) already exists in elements configuration (IP match).")
                continue

            if name not in discovered_nodes:
                discovered_nodes[name] = {'ips': set()}
            
            discovered_nodes[name]['ips'].add(ip)

    # IP Election logic
    output_elements = []
    for name, data in discovered_nodes.items():
        ips = list(data['ips'])
        elected_ip = None
        
        # 1. Try preferred subnets
        for ip in ips:
            if is_ip_in_subnets(ip, preferred_subnets):
                elected_ip = ip
                break
        
        # 2. Fallback to the first discovered IP if none matched subnets
        if not elected_ip:
            elected_ip = ips[0]
            
        # For discovery, we provide the full list of fallbacks joined by '|'
        # core/commands.py will try them in order.
        cmd_key = "|".join(fallback_keys)
        output_elements.append(f"{name};{elected_ip};{cmd_key}")

    if output_elements:
        out_path = os.path.join(args.outdir, out_filename)
        with open(out_path, 'w') as f:
            f.write("# Discovered Elements\n")
            f.write("# Format: hostname;ip;cmd_key\n\n")
            for line in output_elements:
                f.write(line + "\n")
        print(f"Generated {len(output_elements)} potential new elements in {out_path}")
    else:
        print("No new elements discovered.")

if __name__ == "__main__":
    main()
