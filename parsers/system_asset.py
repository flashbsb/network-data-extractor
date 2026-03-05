import re
import os
import glob
import csv
import argparse
from datetime import datetime

def parse_system_files(collect_dir, out_dir):
    """
    Scans for .show.system.txt (Datacom) and .show.version.txt / .show.platform.txt (Cisco)
    in the collect_dir and generates system_assets_all.csv in out_dir.
    """
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "system_assets_all.csv")
    
    # Store aggregated info keyed by element name to merge if both version/platform exist
    assets = {}

    def get_or_create_asset(element_name, timestamp):
        if element_name not in assets:
            assets[element_name] = {
                "Timestamp": timestamp,
                "Model": "-",
                "Serial_Number": "-",
                "MAC_Address": "-",
                "OS_Version": "-",
                "Uptime": "-"
            }
        return assets[element_name]

    # --- 1. Parse DATACOM `show system` ---
    system_files = glob.glob(os.path.join(collect_dir, "*.show.system.txt"))
    for f in system_files:
        filename = os.path.basename(f)
        parts = filename.split('.')
        if len(parts) >= 2:
            element = parts[0]
            timestamp = parts[1]
        else:
            continue
            
        asset = get_or_create_asset(element, timestamp)
        
        with open(f, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.read()
            
            # Datacom Model
            m_model = re.search(r'^\s*Model:\s+(.*)$', content, re.MULTILINE)
            if m_model: asset["Model"] = m_model.group(1).strip()
            
            # Datacom Serial number
            m_serial = re.search(r'^\s*Serial number:\s+(.*)$', content, re.MULTILINE)
            if m_serial: asset["Serial_Number"] = m_serial.group(1).strip()
            
            # Datacom MAC Address
            m_mac = re.search(r'^\s*MAC Address:\s+(.*)$', content, re.MULTILINE | re.IGNORECASE)
            if m_mac: asset["MAC_Address"] = m_mac.group(1).strip()

    # --- 2. Parse CISCO `show version` ---
    version_files = glob.glob(os.path.join(collect_dir, "*.show.version.txt"))
    for f in version_files:
        filename = os.path.basename(f)
        parts = filename.split('.')
        if len(parts) >= 2:
            element = parts[0]
            timestamp = parts[1]
        else:
            continue
            
        asset = get_or_create_asset(element, timestamp)
        
        with open(f, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.read()
            
            # Cisco OS Version (Variations for IOS, IOS-XE, NX-OS)
            m_ver = re.search(r'(?:Cisco IOS Software|Software|NXOS:).*?Version\s+([^,\s]+)', content, re.IGNORECASE)
            if m_ver: asset["OS_Version"] = m_ver.group(1).strip()
            
            # Cisco Uptime
            m_up = re.search(r'^\s*(?:.*uptime is\s+|uptime is\s+)(.*)$', content, re.MULTILINE | re.IGNORECASE)
            if m_up: asset["Uptime"] = m_up.group(1).strip()
            
            # Secondary check for Chassis / Serial directly in version buffer
            m_serial_ver = re.search(r'Processor board ID\s+(.*)$', content, re.MULTILINE)
            if m_serial_ver and asset["Serial_Number"] == "-": 
                asset["Serial_Number"] = m_serial_ver.group(1).strip()
                
            m_model_ver = re.search(r'cisco\s+([^ ]+).*?processor(?:\s+\(.*?\))*\s+with', content, re.IGNORECASE)
            if m_model_ver and asset["Model"] == "-":
                asset["Model"] = "Cisco " + m_model_ver.group(1).strip()


    # --- 3. Parse CISCO `show platform` (overwrites model/serial if explicitly listed as Chassis) ---
    platform_files = glob.glob(os.path.join(collect_dir, "*.show.platform.txt"))
    for f in platform_files:
        filename = os.path.basename(f)
        parts = filename.split('.')
        if len(parts) >= 2:
            element = parts[0]
            timestamp = parts[1]
        else:
            continue
            
        asset = get_or_create_asset(element, timestamp)
        
        with open(f, 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                # E.g. "Chassis   ASR1001-HX          JAE22130Q1K  "
                # E.g. "cisco ISR4331/K9 (1RU) processor with... "
                if 'Chassis' in line:
                    parts_line = line.split()
                    if len(parts_line) >= 3:
                        asset["Model"] = parts_line[1]
                        asset["Serial_Number"] = parts_line[2]
                        break

    # --- Write Output ---
    with open(out_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Element', 'Timestamp', 'Model', 'Serial_Number', 'MAC_Address', 'OS_Version', 'Uptime']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        for element, data in assets.items():
            row = {'Element': element}
            row.update(data)
            writer.writerow(row)
            
    print(f" -> Generated: {out_file} ({len(assets)} assets consolidated)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect_dir", required=True)
    parser.add_argument("--resume_dir", required=True)
    args = parser.parse_args()
    
    parse_system_files(args.collect_dir, args.resume_dir)
