#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re
import csv
from glob import glob

def parse_inventory(file_path):
    base = os.path.basename(file_path)
    hostname, ident = base.split('.', 1)[0], base.split('.')[1]
    results = []
    current = {'element': hostname, 'id': ident}

    with open(file_path, encoding='utf-8') as f:
        for line in f:
            # Início de novo bloco
            if line.startswith("NAME:"):
                if 'name' in current:
                    results.append(current)
                    current = {'element': hostname, 'id': ident}
                m = re.search(r'NAME:\s+"([^"]+)",\s+DESCR:\s+"([^"]+)"', line)
                if m:
                    current['name'], current['descr'] = m.groups()
            elif line.strip().startswith("PID:"):
                m = re.search(r'PID:\s*(\S*),\s*VID:\s*(\S*),\s*SN:\s*(\S*)', line)
                if m:
                    current['pid'], current['vid'], current['sn'] = m.groups()

    if 'name' in current:
        results.append(current)

    return results

if __name__ == '__main__':
    import argparse, os
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', default='.')
    parser.add_argument('--indir', default='.')
    args = parser.parse_args()
    output_file = os.path.join(args.outdir, 'inventory_all.csv')
    header = ['element', 'id', 'name', 'descr', 'pid', 'vid', 'sn']

    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=header, delimiter=';')
        writer.writeheader()
        for file in glob(os.path.join(args.indir, '*.show.inventory.txt')):
            for row in parse_inventory(file):
                writer.writerow(row)

    print("CSV generated:", output_file)
