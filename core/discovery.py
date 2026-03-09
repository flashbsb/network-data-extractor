#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import csv
import json
import ipaddress
import argparse
import logging

def load_settings(custom_path=None):
    if custom_path:
        settings_path = custom_path
    else:
        # Default relative to root
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

def normalize_hostname(name, fmt='simple'):
    """Returns the name according to fmt: 'simple' (pre-dot) or 'fqdn' (full)."""
    if not name:
        return ""
    if fmt == 'fqdn':
        return name.strip().upper()
    return name.split('.')[0].strip().upper()

def read_existing_elements(paths_str, hostname_fmt='simple'):
    existing_ips = set()
    existing_names = set() # Store normalized names
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
                        existing_names.add(normalize_hostname(name, hostname_fmt))
                        existing_ips.add(ip)
    return existing_ips, existing_names

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume_dir", required=True, help="Directory containing show_lldp_neighbors_detail_all.csv")
    parser.add_argument("--elements_cfg", default="config/elements.cfg", help="Current elements config to avoid duplicates")
    parser.add_argument("--outdir", required=True, help="Directory to save the discovery results")
    parser.add_argument("--out_filename", help="Filename for the discovered elements (overrides settings.json)")
    parser.add_argument("--settings", help="Path to settings.json")
    parser.add_argument("--resumedir", help="Directory for the CSV report (discovered_elements.csv)")
    args = parser.parse_args()

    settings = load_settings(args.settings)
    discovery_cfg = settings.get("discovery", {})
    
    preferred_subnets = discovery_cfg.get("preferred_management_subnets", [])
    ignore_prefixes = discovery_cfg.get("ignore_new_prefixes", [])
    fallback_keys = discovery_cfg.get("fallback_cmd_keys", ["cisco_ios"])
    out_filename = args.out_filename or discovery_cfg.get("output_filename", "discovery.elements.cfg")
    hostname_fmt = discovery_cfg.get("hostname_format", "simple")

    csv_path = os.path.join(args.resume_dir, "show_lldp_neighbors_detail_all.csv")
    if not os.path.isfile(csv_path):
        print(f"Error: {csv_path} not found.")
        sys.exit(1)

    existing_ips, existing_names = read_existing_elements(args.elements_cfg, hostname_fmt)
    
    # Structure: { normalized_name: { 'display_name': '...', 'ips': {ip1, ip2}, 'sources': {source1, source2} } }
    discovered_nodes = {}

    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            raw_name = row.get('system_name', '').strip()
            raw_ip = row.get('mgmt_ipv4', '').strip()
            source_node = row.get('element', 'unknown').strip()
            
            # Split management IPs (might be comma separated from parser)
            ips_from_row = [i.strip() for i in raw_ip.split(',') if i.strip()]
            
            if not raw_name or not ips_from_row:
                continue
            
            norm_name = normalize_hostname(raw_name, hostname_fmt)
            
            # Filter by ignore prefixes
            should_ignore = False
            for pref in ignore_prefixes:
                if norm_name.startswith(pref.upper()):
                    should_ignore = True
                    break
            if should_ignore:
                continue

            # Skip if normalized hostname is already known
            if norm_name in existing_names:
                continue

            if norm_name not in discovered_nodes:
                discovered_nodes[norm_name] = {
                    'display_name': raw_name if hostname_fmt == 'fqdn' else raw_name.split('.')[0].strip(),
                    'ips': set(),
                    'sources': set()
                }
            
            discovered_nodes[norm_name]['sources'].add(source_node)
            for i in ips_from_row:
                # Skip if this specific IP is already known globally
                if i in existing_ips:
                    continue
                discovered_nodes[norm_name]['ips'].add(i)

    # Multi-IP Export logic
    output_rows = [] # List of dicts for easier CSV handling
    
    # Drop nodes that ended up with no new IPs
    for norm_name in list(discovered_nodes.keys()):
        if not discovered_nodes[norm_name]['ips']:
            del discovered_nodes[norm_name]

    for norm_name, data in discovered_nodes.items():
        ips = sorted(list(data['ips'])) # Consistent order
        display_name = data['display_name']
        sources = sorted(list(data['sources']))
        
        # Separate preferred IPs from others
        preferred = [ip for ip in ips if is_ip_in_subnets(ip, preferred_subnets)]
        others = [ip for ip in ips if ip not in preferred]
        
        # Combine (preferred first) and join by |
        all_ips = preferred + others
        ips_str = "|".join(all_ips)
            
        # For discovery, we also provide the full list of fallback cmd_keys
        cmd_key = "|".join(fallback_keys)
        
        output_rows.append({
            'hostname': display_name,
            'ips': ips_str,
            'cmd_keys': cmd_key,
            'discovered_by': "|".join(sources)
        })

    if output_rows:
        out_path = os.path.join(args.outdir, out_filename)
        with open(out_path, 'w') as f:
            f.write("# Discovered Elements\n")
            f.write("# Format: hostname;ip;cmd_key\n\n")
            for row in output_rows:
                f.write(f"{row['hostname']};{row['ips']};{row['cmd_keys']}\n")
        print(f"Generated {len(output_rows)} potential new elements in {out_path}")
        
        # Also generate CSV report in resumedir
        report_dir = args.resumedir if args.resumedir else args.outdir
        csv_report_path = os.path.join(report_dir, "discovered_elements.csv")
        csv_headers = ['hostname', 'ips', 'cmd_keys', 'discovered_by']
        try:
            with open(csv_report_path, 'w', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=csv_headers, delimiter=';')
                writer.writeheader()
                for row in output_rows:
                    writer.writerow(row)
            print(f"Discovery CSV report generated in {csv_report_path}")
        except Exception as e:
            print(f"Warning: Failed to generate discovery CSV report: {e}")
    else:
        print("No new elements discovered.")

if __name__ == "__main__":
    main()
