#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import argparse
import csv
from datetime import datetime

def format_bw(bw_kbit):
    try:
        bw = int(bw_kbit)
    except:
        return "Unknown"
    
    if bw >= 100000000:
        return f"{int(bw/100000000 * 100)}G"
    elif bw >= 1000000:
        return f"{int(bw/1000000)}G"
    elif bw >= 1000:
        return f"{int(bw/1000)}M"
    else:
        return f"{bw}K"

def load_data(snapshot_path):
    json_path = os.path.join(snapshot_path, "resume", "interfaces_all.json")
    csv_path = os.path.join(snapshot_path, "resume", "interfaces_all.csv")
    
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    elif os.path.exists(csv_path):
        data = []
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                data.append(row)
        return data
    return None

def compare_snapshots(old_data, new_data):
    # Key: (element, interface)
    old_map = {(d['element'], d['interface']): d for d in old_data}
    new_map = {(d['element'], d['interface']): d for d in new_data}
    
    all_keys = set(old_map.keys()) | set(new_map.keys())
    diffs = []
    
    for key in all_keys:
        old_item = old_map.get(key)
        new_item = new_map.get(key)
        
        if not old_item:
            # Added
            diffs.append({
                'element': key[0],
                'interface': key[1],
                'type': 'ADDED',
                'old': None,
                'new': {
                    'admin': new_item['admin_status'],
                    'oper': new_item['line_protocol'],
                    'bw': format_bw(new_item['bandwidth_kbit'])
                }
            })
        elif not new_item:
            # Removed
            diffs.append({
                'element': key[0],
                'interface': key[1],
                'type': 'REMOVED',
                'old': {
                    'admin': old_item['admin_status'],
                    'oper': old_item['line_protocol'],
                    'bw': format_bw(old_item['bandwidth_kbit'])
                },
                'new': None
            })
        else:
            # Compare
            changes = {}
            if old_item['admin_status'] != new_item['admin_status']:
                changes['admin'] = (old_item['admin_status'], new_item['admin_status'])
            if old_item['line_protocol'] != new_item['line_protocol']:
                changes['oper'] = (old_item['line_protocol'], new_item['line_protocol'])
            
            old_bw = format_bw(old_item['bandwidth_kbit'])
            new_bw = format_bw(new_item['bandwidth_kbit'])
            if old_bw != new_bw:
                changes['bw'] = (old_bw, new_bw)
                
            if changes:
                diffs.append({
                    'element': key[0],
                    'interface': key[1],
                    'type': 'MODIFIED',
                    'changes': changes,
                    'old': {
                        'admin': old_item['admin_status'],
                        'oper': old_item['line_protocol'],
                        'bw': old_bw
                    },
                    'new': {
                        'admin': new_item['admin_status'],
                        'oper': new_item['line_protocol'],
                        'bw': new_bw
                    }
                })
                
    return diffs

def main():
    parser = argparse.ArgumentParser(description="Network Topology/Interface Comparison Tool")
    parser.add_argument("--old", required=True, help="Path to OLD snapshot directory")
    parser.add_argument("--new", required=True, help="Path to NEW snapshot directory")
    parser.add_argument("--output", help="Path to output diff file (JSON)")
    args = parser.parse_args()
    
    print(f"Comparing {args.old} vs {args.new}...")
    
    old_data = load_data(args.old)
    new_data = load_data(args.new)
    
    if not old_data or not new_data:
        print("Error: Could not load data from one or both snapshots.")
        return
        
    diffs = compare_snapshots(old_data, new_data)
    
    print(f"Found {len(diffs)} differences.")
    
    if args.output:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump({
                'metadata': {
                    'old_snapshot': os.path.basename(args.old),
                    'new_snapshot': os.path.basename(args.new),
                    'timestamp': datetime.now().isoformat()
                },
                'diffs': diffs
            }, f, indent=2)
        print(f"Diff report saved to: {args.output}")
    else:
        # Simple CLI output
        for d in diffs:
            print(f"[{d['type']}] {d['element']} - {d['interface']}")
            if d['type'] == 'MODIFIED':
                for k, v in d['changes'].items():
                    print(f"  └─ {k}: {v[0]} -> {v[1]}")

if __name__ == "__main__":
    main()
