import re
import os
import glob
import csv
import argparse

def parse_subcomponents(collect_dir, out_dir):
    """
    Scans for .show.inventory.txt and .show.inventory.details.txt in collect_dir.
    Extracts non-optical modules (Fans, Power Supplies, Linecards, Route Processors)
    Outputs to subcomponents_all.csv.
    """
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "subcomponents_all.csv")
    
    rows = []

    # Parse CISCO `show inventory details` / `show inventory`
    cisco_files = glob.glob(os.path.join(collect_dir, "*.show.inventory.details.txt"))
    cisco_files.extend(glob.glob(os.path.join(collect_dir, "*.show.inventory.txt")))
    
    # regex block
    block_pattern = r'NAME:\s+"([^"]+)",\s+DESCR:\s+"([^"]+)"\s*\nPID:\s+([^,]+).*?SN:\s+(\S+)'
    
    for f in cisco_files:
        filename = os.path.basename(f)
        parts = filename.split('.')
        if len(parts) >= 2:
            element = parts[0]
        else:
            continue
            
        with open(f, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.read()
            inv_blocks = re.findall(block_pattern, content, re.IGNORECASE)
            
            for port, descr, pid, sn in inv_blocks:
                descr_upper = descr.upper()
                pid_upper = pid.upper()
                
                # Exclude optical transceivers (Handled by Axis 11)
                if 'SFP' in descr_upper or 'XFP' in descr_upper or 'QSFP' in descr_upper or 'TRANSCEIVER' in descr_upper:
                    continue
                if 'SFP' in pid_upper or 'XFP' in pid_upper or 'QSFP' in pid_upper:
                    continue
                    
                # Try to classify
                component_type = "Other"
                if 'FAN' in descr_upper or 'FAN' in pid_upper:
                    component_type = "Fan Tray"
                elif 'POWER' in descr_upper or 'PWR' in pid_upper or re.search(r'\bAC\b|\bDC\b', descr_upper):
                    component_type = "Power Supply"
                elif 'CHASSIS' in descr_upper:
                    component_type = "Chassis" # Axis 10 gets this, but good to have in inventory too
                elif 'PROCESSOR' in descr_upper or 'RSP' in pid_upper or 'RP' in pid_upper:
                    component_type = "Route Processor"
                elif 'LINECARD' in descr_upper or 'MODULE' in descr_upper or 'LC' in pid_upper:
                    component_type = "Line Card"
                    
                rows.append({
                    'Element': element,
                    'Component_Type': component_type,
                    'Part_Number': pid.strip(),
                    'Serial_Number': sn.strip(),
                    'Description': descr.strip()
                })

    # Write Output
    with open(out_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Element', 'Component_Type', 'Part_Number', 'Serial_Number', 'Description']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            
    print(f" -> Generated: {out_file} ({len(rows)} physical sub-components cataloged)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect_dir", required=True)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()
    
    parse_subcomponents(args.collect_dir, args.outdir)
