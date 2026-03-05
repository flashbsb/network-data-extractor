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
            # Normalize interface name for lookup (e.g. remove spaces, lower case)
            norm_intf = intf.replace(' ', '').lower()
            interface_descs[(elem, norm_intf)] = desc

    mismatches = []
    
    with open(lldp_file, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            elem = row.get('element', '').strip()
            local_intf = row.get('local_intf', '').strip()
            
            # The actual neighbor detected by LLDP
            actual_neighbor = row.get('system_name', '').strip()
            # FQDN removal (e.g. RTOC-CBA01-03.telebras.net.br -> RTOC-CBA01-03)
            base_neighbor = actual_neighbor.split('.')[0] if '.' in actual_neighbor else actual_neighbor
            
            # Skip if the neighbor is the device itself (common in some loopback/virtual scenarios)
            if base_neighbor.upper() == elem.upper():
                continue

            # Normalize local interface name for lookup
            norm_local_intf = local_intf.replace(' ', '').lower()
            expected_desc = interface_descs.get((elem, norm_local_intf), "")
            
            # If not found directly, try to see if it's a sub-interface or if there's a naming variation
            if not expected_desc:
                # Try a partial match or case-insensitive lookup if needed, 
                # but focus on the exact normalized path first.
                pass

            # If the description is completely empty but we have an LLDP neighbor, it's missing docs
            missing_desc = (expected_desc == "")
            
            # Mismatch if the actual neighbor FQDN or base hostname is NOT in the description
            # We check for both the full name and the base name (no domain)
            found_in_desc = (base_neighbor.upper() in expected_desc.upper()) or (actual_neighbor.upper() in expected_desc.upper())
            
            if not missing_desc and not found_in_desc:
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
