import csv
import os
import argparse
import json

def generate_port_census(resume_dir, out_dir):
    """
    Reads resume/interfaces_all.csv, filters out virtual interfaces,
    and calculates Total/Up/Down port statistics per Element.
    """
    interfaces_csv = os.path.join(resume_dir, "interfaces_all.csv")
    out_file = os.path.join(out_dir, "port_census_all.csv")
    
    if not os.path.isfile(interfaces_csv):
        print(f" -> Error: {interfaces_csv} not found. Cannot generate port census.")
        return

    # Load ignore prefixes from settings if available
    ignore_prefixes = ["Bundle", "PW", "NULL", "Null", "Loopback", "Tunnel", "Vlan", "BVI", "Port-channel", "Mgmt", "NVI"]
    try:
        with open("config/settings.json", "r") as f:
            cfg = json.load(f)
            custom_ignores = cfg.get("topology", {}).get("ignore_virtual_prefixes", [])
            if custom_ignores:
                ignore_prefixes = custom_ignores
    except:
        pass
        
    ignore_prefixes = tuple(p.lower() for p in ignore_prefixes)
    
    # Structure: stats[element] = {'total': 0, 'up': 0, 'down': 0}
    stats = {}

    with open(interfaces_csv, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f, delimiter=';')
        
        for row in reader:
            element = row.get('element', '-').strip()
            interface = row.get('interface', '').strip()
            admin_status = row.get('admin_status', '').lower()
            line_protocol = row.get('line_protocol', '').lower()
            
            # Skip empty rows
            if not element or element == '-': continue
            
            # Filter virtual interfaces
            if interface.lower().startswith(ignore_prefixes):
                continue
                
            # Initialize element stats if not present
            if element not in stats:
                stats[element] = {'total': 0, 'up': 0, 'down': 0}
                
            stats[element]['total'] += 1
            
            # Count it as Up only if line_protocol is up (physically connected).
            # If admin_status is down or line_protocol is down/lowerlayerdown, count as down/available
            if 'up' in line_protocol and 'up' in admin_status:
                stats[element]['up'] += 1
            else:
                stats[element]['down'] += 1

    # Write output
    os.makedirs(out_dir, exist_ok=True)
    with open(out_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Element', 'Total_Physical_Ports', 'Ports_Up', 'Ports_Available', 'Utilization_Pct']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        
        for element, data in stats.items():
            total = data['total']
            up = data['up']
            down = data['down']
            util_pct = f"{(up / total * 100):.1f}%" if total > 0 else "0.0%"
            
            writer.writerow({
                'Element': element,
                'Total_Physical_Ports': total,
                'Ports_Up': up,
                'Ports_Available': down,
                'Utilization_Pct': util_pct
            })
            
    print(f" -> Generated: {out_file} ({len(stats)} elements mapped)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume_dir", required=True)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()
    
    generate_port_census(args.resume_dir, args.outdir)
