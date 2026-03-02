#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re
import csv
from glob import glob

def parse_inventory_details(file_path):
    base = os.path.basename(file_path)
    hostname, ident = base.split('.', 1)[0], base.split('.')[1]
    results = []
    current = {}

    with open(file_path, encoding='utf-8') as f:
        for line in f:
            # Início de novo bloco
            if line.startswith('NAME:'):
                if current:
                    current['elemento'] = hostname
                    current['id'] = ident
                    results.append(current)
                    current = {}
                # Extrai nome e descrição
                m = re.search(r'NAME:\s+"([^"]+)",\s+DESCR:\s+"([^"]+)"', line)
                if m:
                    current['name'], current['descr'] = m.groups()

            elif 'PID:' in line:
                m = re.search(r'PID:\s+(\S+)\s*,\s*VID:\s+(\S+),\s*SN:\s+(\S+)', line)
                if m:
                    current['pid'], current['vid'], current['sn'] = m.groups()

            elif 'MFG_NAME:' in line:
                m = re.search(r'MFG_NAME:\s+([^,]+),\s*SNMP_IDX:\s+(\S+)', line)
                if m:
                    current['mfg_name'], current['snmp_idx'] = m.groups()

            elif 'PN:' in line:
                current['pn'] = line.split(':', 1)[1].strip()

    if current:
        current['elemento'] = hostname
        current['id'] = ident
        results.append(current)

    return results

if __name__ == '__main__':
    import argparse, os
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', default='.')
    parser.add_argument('--indir', default='.')
    args = parser.parse_args()
    output_file = os.path.join(args.outdir, 'inventory_details_all.csv')
    header = ['elemento', 'id', 'name', 'descr', 'pid', 'vid', 'sn', 'mfg_name', 'snmp_idx', 'pn']

    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=header, delimiter=';')
        writer.writeheader()
        for file in glob(os.path.join(args.indir, '*.show.inventory.details.txt')):
            for row in parse_inventory_details(file):
                writer.writerow(row)

    print("CSV gerado:", output_file)
