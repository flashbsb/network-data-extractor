import re
import os
import glob
import csv
import argparse
from datetime import datetime

def parse_transceivers(collect_dir, out_dir):
    """
    Scans for .show.hardware-status.transceivers.detail.txt (Datacom) and .show.inventory.details.txt (Cisco)
    in the collect_dir and generates transceivers_health_all.csv in out_dir.
    """
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "transceivers_health_all.csv")
    
    rows = []

    # --- 1. Parse DATACOM `show hardware-status transceivers detail` ---
    dc_files = glob.glob(os.path.join(collect_dir, "*.show.hardware-status.transceivers.detail.txt"))
    
    # Datacom block Regex
    # We break the file by "Information of ETH port X/X" and parse each chunk
    block_pattern = r'Information of (.*?)(?=\nInformation of|\Z)'
    
    for f in dc_files:
        filename = os.path.basename(f)
        parts = filename.split('.')
        if len(parts) >= 2:
            element = parts[0]
            timestamp = parts[1]
        else:
            continue
            
        with open(f, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.read()
            blocks = re.findall(block_pattern, content, re.DOTALL | re.IGNORECASE)
            
            for block in blocks:
                # 1st line of the block is the port itself (due to how the regex split it, the first line is exactly the port string minus "Information of")
                lines = block.split('\n')
                port = lines[0].strip()
                
                vendor, serial, media, rx_power, tx_power = "-", "-", "-", "-", "-"
                
                m_vendor = re.search(r'Manufacturer:\s+(.*?)\s*$', block, re.MULTILINE)
                if m_vendor: vendor = m_vendor.group(1).strip()
                
                m_serial = re.search(r'Serial Number:\s+(.*?)\s*$', block, re.MULTILINE)
                if m_serial: serial = m_serial.group(1).strip()
                
                m_media = re.search(r'Media:\s+(.*?)\s*$', block, re.MULTILINE)
                if m_media: media = m_media.group(1).strip()
                
                m_rx = re.search(r'Rx-Power:\s+([-\d\.]+\s*dBm)', block, re.MULTILINE | re.IGNORECASE)
                if m_rx: rx_power = m_rx.group(1).strip()
                
                m_tx = re.search(r'Tx-Power:\s+([-\d\.]+\s*dBm)', block, re.MULTILINE | re.IGNORECASE)
                if m_tx: tx_power = m_tx.group(1).strip()
                
                # Filter out completely empty blocks where no SFP is present
                if vendor != "-" or serial != "-":
                    rows.append({
                        'Element': element,
                        'Timestamp': timestamp,
                        'Port': port,
                        'Vendor': vendor,
                        'Serial_Number': serial,
                        'Media_Type': media,
                        'Rx_Power(dBm)': rx_power,
                        'Tx_Power(dBm)': tx_power
                    })

    # --- 2. Parse CISCO `show inventory details` / `show inventory` ---
    # Cisco typically lists optical inventory items with specific formats.
    cisco_files = glob.glob(os.path.join(collect_dir, "*.show.inventory.details.txt"))
    cisco_files.extend(glob.glob(os.path.join(collect_dir, "*.show.inventory.txt")))
    
    for f in cisco_files:
        filename = os.path.basename(f)
        parts = filename.split('.')
        if len(parts) >= 2:
            element = parts[0]
            timestamp = parts[1]
        else:
            continue
            
        with open(f, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.read()
            
            # NAME: "GigabitEthernet0/0/0", DESCR: "SFP-GE-L"
            # PID: GLC-LX-SM-RGD     , VID: V01  , SN: FNS134XXXXX
            inv_blocks = re.findall(r'NAME:\s+"([^"]+)",\s+DESCR:\s+"([^"]+)"\s*\nPID:\s+([^,]+).*?SN:\s+(\S+)', content, re.IGNORECASE)
            
            for port, descr, pid, sn in inv_blocks:
                # We only care about Transceivers, not chassis fans or power supplies
                if 'SFP' in descr.upper() or 'XFP' in descr.upper() or 'QSFP' in descr.upper() or 'TRANSCEIVER' in descr.upper():
                    rows.append({
                        'Element': element,
                        'Timestamp': timestamp,
                        'Port': port.strip(),
                        'Vendor': "Cisco (Expected)",
                        'Serial_Number': sn.strip(),
                        'Media_Type': pid.strip(),
                        'Rx_Power(dBm)': '-', # 'show inventoy' doesn't show diagnostics natively
                        'Tx_Power(dBm)': '-'
                    })


    # --- Write Output ---
    with open(out_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Element', 'Timestamp', 'Port', 'Vendor', 'Serial_Number', 'Media_Type', 'Rx_Power(dBm)', 'Tx_Power(dBm)']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            
    print(f" -> Generated: {out_file} ({len(rows)} transceiver optics consolidated)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect_dir", required=True)
    parser.add_argument("--resume_dir", required=True)
    args = parser.parse_args()
    
    parse_transceivers(args.collect_dir, args.resume_dir)
