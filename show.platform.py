#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, glob, csv, os

def parse_show_platform(filename):
    base = os.path.basename(filename)
    host, _, rest = base.partition('.')
    identifier = rest.split('.')[0]
    data = []
    with open(filename) as f:
        lines = f.readlines()
    start = False
    for line in lines:
        if line.startswith('---'):
            start = True
            continue
        if not start or not line.strip():
            continue
        parts = re.split(r'\s{2,}', line.strip())
        if len(parts) >= 4:
            data.append({
                'elemento': host,
                'id': identifier,
                'node': parts[0],
                'type': parts[1],
                'state': parts[2],
                'config_state': parts[3],
            })
    return data

if __name__ == '__main__':
    out = 'platform_all.csv'
    hdr = ['elemento','id','node','type','state','config_state']
    with open(out, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=hdr, delimiter=';')
        writer.writeheader()
        for fn in glob.glob('*.show.platform.txt'):
            for row in parse_show_platform(fn):
                writer.writerow(row)
    print('CSV gerado:', out)
