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
                'element': host,
                'id': identifier,
                'node': parts[0],
                'type': parts[1],
                'state': parts[2],
                'config_state': parts[3],
            })
    return data

if __name__ == '__main__':
    import argparse, os
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', default='.')
    parser.add_argument('--indir', default='.')
    args = parser.parse_args()
    out = os.path.join(args.outdir, 'platform_all.csv')
    hdr = ['element','id','node','type','state','config_state']
    with open(out, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=hdr, delimiter=';')
        writer.writeheader()
        files_to_parse = glob.glob(os.path.join(args.indir, '*.show.platform.txt'))

        print(f'Searching for files *.show.platform.txt in {args.indir}... Found {len(files_to_parse)} applicable files.')

        processed = 0

        for fn in files_to_parse:
            for row in parse_show_platform(fn):
                writer.writerow(row)
    if 'processed' in locals():

        print(f'-> Total parsed and successfully saved nodes: {processed}')

    print('CSV generated:', out)
