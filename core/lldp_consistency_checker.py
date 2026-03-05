#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This script performs an L2 Topology Consistency Check.
It cross-references interfaces_all.csv (the description of the port)
with show_lldp_neighbors_detail_all.csv (the actual neighbor detected by LLDP).
If the LLDP System Name is not found anywhere within the description, it is flagged as a mismatch.
"""

import os
import csv
import argparse

def check_lldp_consistency(resume_dir):
    interfaces_file = os.path.join(resume_dir, "interfaces_all.csv")
    lldp_file = os.path.join(resume_dir, "show_lldp_neighbors_detail_all.csv")
    out_file = os.path.join(resume_dir, "lldp_mismatch_report.csv")
    
    if not os.path.isfile(interfaces_file) or not os.path.isfile(lldp_file):
        print(" -> Required files for LLDP validation not found. Exiting.")
        return

    csv.field_size_limit(10000000)
    
    # Load interface descriptions into a dictionary
    # Key: (Element, Interface)
    interface_descs = {}
    with open(interfaces_file, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            elem = row.get('element', '').strip()
            intf = row.get('interface', '').strip()
            desc = row.get('description', '').strip()
            interface_descs[(elem, intf)] = desc

    mismatches = []
    
    with open(lldp_file, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            elem = row.get('element', '').strip()
            local_intf = row.get('local_if', '').strip()
            
            # The actual neighbor detected by LLDP
            actual_neighbor = row.get('system_name', '').strip()
            # FQDN removal (e.g. RTOC-CBA01-03.telebras.net.br -> RTOC-CBA01-03)
            base_neighbor = actual_neighbor.split('.')[0] if '.' in actual_neighbor else actual_neighbor
            
            if not base_neighbor:
                continue
                
            expected_desc = interface_descs.get((elem, local_intf), "")
            
            # If the description is completely empty but we have an LLDP neighbor, it's missing docs
            missing_desc = (expected_desc == "")
            
            # Mismatch if the actual neighbor FQDN or base hostname is NOT in the description
            if not missing_desc and base_neighbor.upper() not in expected_desc.upper():
                mismatches.append({
                    'Element': elem,
                    'Interface': local_intf,
                    'Configured_Description': expected_desc,
                    'Actual_LLDP_Neighbor': actual_neighbor,
                    'Mismatch_Reason': 'WRONG_DESCRIPTION'
                })
            elif missing_desc:
                mismatches.append({
                    'Element': elem,
                    'Interface': local_intf,
                    'Configured_Description': 'EMPTY',
                    'Actual_LLDP_Neighbor': actual_neighbor,
                    'Mismatch_Reason': 'MISSING_DESCRIPTION'
                })

    # Write Output
    with open(out_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Element', 'Interface', 'Configured_Description', 'Actual_LLDP_Neighbor', 'Mismatch_Reason']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        for m in mismatches:
            writer.writerow(m)
            
    print(f" -> Generated: {out_file} ({len(mismatches)} mismatches/omissions detected)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cross reference LLDP actuals vs Interface descriptions")
    parser.add_argument("--resume_dir", required=True)
    args = parser.parse_args()
    
    check_lldp_consistency(args.resume_dir)
