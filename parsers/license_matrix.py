import re
import os
import glob
import csv
import argparse

def parse_licenses(collect_dir, out_dir):
    """
    Scans for .show.license.summary.txt or .show.license.feature.txt in collect_dir.
    Extracts Software licensing states. Outputs to license_matrix_all.csv.
    """
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "license_matrix_all.csv")
    
    rows = []

    # Parse License files
    license_files = glob.glob(os.path.join(collect_dir, "*.show.license.summary.txt"))
    license_files.extend(glob.glob(os.path.join(collect_dir, "*.show.license.feature.txt")))
    
    for f in license_files:
        filename = os.path.basename(f)
        parts = filename.split('.')
        if len(parts) >= 2:
            element = parts[0]
        else:
            continue
            
        with open(f, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.read()
            # This handles generic Cisco IOS-XE / NX-OS License table formats:
            # "advipservices      Active, In Use           Never"
            # Or Datacom formats etc. We implement a greedy catch-all regex for common table structures.
            lines = content.split('\n')
            
            for line in lines:
                line = line.strip()
                # Skip headers or empty lines
                if not line or '---' in line or 'Index' in line or 'Feature' in line:
                    continue
                    
                # Match typical rows with 2+ spaces separating Feature, Status/Type, Expiry
                cols = re.split(r'\s{2,}', line)
                if len(cols) >= 3:
                    feature = cols[0]
                    # Skip common junk lines that happen to have multiple spaces
                    if len(feature) > 40 or 'Total' in feature or 'Store' in feature:
                        continue
                        
                    status = cols[1]
                    expiry = cols[-1] if len(cols) > 2 else "-"
                    
                    rows.append({
                        'Element': element,
                        'License_Feature': feature,
                        'Status': status,
                        'Expiration_Date': expiry
                    })

    # Write Output
    with open(out_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Element', 'License_Feature', 'Status', 'Expiration_Date']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            
    print(f" -> Generated: {out_file} ({len(rows)} licenses cataloged)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect_dir", required=True)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()
    
    parse_licenses(args.collect_dir, args.outdir)
