#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import os
import glob
import csv
import argparse

def parse_bgp_summary(collect_dir, out_dir):
    """
    Scans for .show.bgp.vpnv4.unicast.all.summary.txt in collect_dir.
    Extracts BGP Peer data. Outputs to bgp_peers_all.csv.
    """
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "bgp_peers_all.csv")
    
    rows = []
    
    files = glob.glob(os.path.join(collect_dir, "*.show.bgp.vpnv4.unicast.all.summary.txt"))
    for f in files:
        filename = os.path.basename(f)
        element = filename.split('.')[0]
        
        with open(f, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.read()
            
            # Find the local AS Number (Local router info)
            m_local_as = re.search(r"local AS number\s+(\d+)", content)
            local_as = m_local_as.group(1) if m_local_as else ""
            
            # Start gathering peers (starts below "Neighbor        V           AS MsgRcvd MsgSent...")
            # We look for lines that begin with an IP address
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if not line or not line[0].isdigit():
                    continue
                
                # Strict check: Does the first token look like an IP address? (Basic IPv4 validation)
                cols = re.split(r'\s+', line)
                if len(cols) < 10 or not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', cols[0]):
                    continue
                
                neighbor = cols[0]
                    remote_as = cols[2]
                    uptime = cols[8]
                    # For State/PfxRcd, if it's purely digits it's the number of prefixes. If it's a word like "Active" or "Idle", the session is down.
                    state_pfx = cols[9]
                    
                    rows.append({
                        'Element': element,
                        'Local_AS': local_as,
                        'Neighbor': neighbor,
                        'Remote_AS': remote_as,
                        'Uptime': uptime,
                        'State_or_Prefixes': state_pfx
                    })
                    
    with open(out_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Element', 'Local_AS', 'Neighbor', 'Remote_AS', 'Uptime', 'State_or_Prefixes']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            
    print(f" -> Generated: {out_file} ({len(rows)} peers cataloged)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect_dir", required=True)
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()
    
    parse_bgp_summary(args.collect_dir, args.outdir)
