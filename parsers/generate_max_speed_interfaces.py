#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import csv
import re
import os
import sys
import json

base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_path)

try:
    from core.utils_shared import load_settings
    json_config = load_settings()
except Exception:
    json_config = {}

ETH_STD_SPEED = {
    '100Base-TX': '100Mbps',
    '1000Base-T': '1Gbps',
    '1000Base-LX': '1Gbps',
    '1000Base-SX': '1Gbps',
    '10GBase-LR': '10Gbps',
    '10GBase-SR': '10Gbps',
    '10GBase-ER': '10Gbps',
    '25GBase-CR': '25Gbps',
    '25GBase-SR': '25Gbps',
    '40GBase-SR4': '40Gbps',
    '40GBase-LR4': '40Gbps',
    '100GBase-LR4': '100Gbps',
    '100GBase-SR10': '100Gbps',
    '': ''
}
if json_config.get("transceiver_speed_map"):
    ETH_STD_SPEED.update(json_config["transceiver_speed_map"])

INTERFACE_SPEED_INFERENCE = json_config.get("interface_speed_inference", {
    "100g": "100Gbps",
    "hundredgige": "100Gbps",
    "40g": "40Gbps",
    "fortygige": "40Gbps",
    "25g": "25Gbps",
    "twentyfivegige": "25Gbps",
    "10g": "10Gbps",
    "tengige": "10Gbps",
    "xge": "10Gbps",
    "giga": "1Gbps",
    "gigabitethernet": "1Gbps",
    "ge": "1Gbps",
    "eth": "1Gbps"
})

topology_cfg = json_config.get("topology", {})
IGNORE = tuple(topology_cfg.get("ignore_virtual_prefixes", ('Loopback', 'Bundle', 'Null', 'BVI', 'Vlan', 'Tunnel', 'Port-channel', 'Mgmt', 'NVI')))

def is_physical(iface):
    return not iface.startswith(IGNORE)

def normalize(name):
    name = re.sub(r'^(GigabitEthernet|TenGigE|FastEthernet|Eth|Port-channel)', '', name).strip()
    name = re.sub(r'\s*\(.*?\)', '', name)  # remove (1G), etc
    return name

def infer_speed(name):
    if not name:
        return ''
    n_lower = name.lower()
    for pattern, speed_str in INTERFACE_SPEED_INFERENCE.items():
        if pattern in n_lower:
            return speed_str
    if '100g' in n_lower or 'hundred' in n_lower:
        return '100Gbps'
    if '40g' in n_lower or 'forty' in n_lower:
        return '40Gbps'
    if '25g' in n_lower or 'twentyfive' in n_lower:
        return '25Gbps'
    if '10g' in n_lower or 'ten' in n_lower or 'xge' in n_lower:
        return '10Gbps'
    if 'giga' in n_lower or 'eth' in n_lower or 'ge' in n_lower:
        return '1Gbps'
    return ''

def load_interfaces(files):
    interfaces = []
    for csv_file in files:
        if not os.path.exists(csv_file):
            continue
        with open(csv_file, newline='') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                iface = row.get('interface') or row.get('port')
                if not iface or not is_physical(iface):
                    continue
                element_val = row.get('element', row.get('elemento', ''))
                interfaces.append({
                    'element': element_val.strip(),
                    'id': row['id'].strip(),
                    'interface': iface.strip(),
                    'normalized': normalize(iface.strip())
                })
    return interfaces

def load_transceivers_datacom(files):
    transceivers = {}
    for file in files:
        if not os.path.exists(file):
            continue
        with open(file, newline='') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                element_val = row.get('element', row.get('elemento', ''))
                key = (element_val.strip(), row['id'].strip(), normalize(row['port']))
                transceivers[key] = {
                    'media': row.get('media', '').strip(),
                    'eth_std': row.get('eth_std', '').strip(),
                    'connector': row.get('connector', '').strip()
                }
    return transceivers

def load_transceivers_cisco(files):
    transceivers = {}
    for file in files:
        if not os.path.exists(file):
            continue
        with open(file, newline='') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                name = row.get('name', '')
                if not name or not is_physical(name):
                    continue
                element_val = row.get('element', row.get('elemento', ''))
                key = (element_val.strip(), row['id'].strip(), normalize(name))
                descr = (row.get('descr', '') or '').upper()
                part = (row.get('pid', '') or '').upper()

                eth_std = ''
                if '1000' in descr or 'GE' in descr or 'SFP' in descr:
                    eth_std = '1000Base-LX'
                elif '10G' in descr or 'SFP+' in descr:
                    eth_std = '10GBase-LR'
                elif '40G' in descr or 'QSFP+' in descr:
                    eth_std = '40GBase-LR4'
                elif '100G' in descr or 'QSFP28' in descr:
                    eth_std = '100GBase-LR4'
                transceivers[key] = {
                    'media': 'SFP/QSFP',
                    'eth_std': eth_std,
                    'connector': ''
                }
    return transceivers

def generate_max_speed_csv():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', default='.')
    parser.add_argument('--indir', default='.', help='Input directory to scan (ignored internally as we use outdir to fetch files)')
    args = parser.parse_args()

    import os
    interfaces = load_interfaces([os.path.join(args.outdir, 'interfaces_all.csv'), os.path.join(args.outdir, 'int_status_all.csv')])

    transceivers = {}
    transceivers.update(load_transceivers_datacom([os.path.join(args.outdir, 'transceiver_simple_all.csv'), os.path.join(args.outdir, 'transceivers_detail_all.csv')]))
    transceivers.update(load_transceivers_cisco([os.path.join(args.outdir, 'inventory_all.csv'), os.path.join(args.outdir, 'inventory_details_all.csv')]))

    with open(os.path.join(args.outdir, 'interfaces_max_speed.csv'), 'w', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['element', 'id', 'interface', 'media', 'eth_std', 'connector', 'max_speed', 'status'])

        for iface in interfaces:
            key = (iface['element'], iface['id'], iface['normalized'])
            trans = transceivers.get(key)

            if trans:
                eth_std = trans.get('eth_std', '')
                speed = ETH_STD_SPEED.get(eth_std, infer_speed(iface['interface']))
                writer.writerow([
                    iface['element'], iface['id'], iface['interface'],
                    trans.get('media', ''), eth_std, trans.get('connector', ''),
                    speed, 'with_transceiver'
                ])
            else:
                speed = infer_speed(iface['interface'])
                writer.writerow([
                    iface['element'], iface['id'], iface['interface'],
                    '', '', '', speed, 'without_transceiver'
                ])

    print("✅ File generated: interfaces_max_speed.csv")

if __name__ == '__main__':
    generate_max_speed_csv()
