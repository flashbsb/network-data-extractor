#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, glob, csv, os

def parse_show_version(filename):
    base = os.path.basename(filename)
    host, _, rest = base.partition('.')
    identifier = rest.split('.')[0]
    software_version = ''
    uptime = ''
    with open(filename) as f:
        for line in f:
            if 'Cisco IOS XR Software, Version' in line:
                software_version = line.split('Version',1)[1].strip()
            elif 'System uptime is' in line:
                uptime = line.split('System uptime is',1)[1].strip()
    return {
        'element': host,
        'id': identifier,
        'software_version': software_version,
        'uptime': uptime
    }

if __name__ == '__main__':
    import argparse, os
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', default='.')
    parser.add_argument('--indir', default='.')
    args = parser.parse_args()
    out = os.path.join(args.outdir, 'version_all.csv')
    hdr = ['element','id','software_version','uptime']
    with open(out, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=hdr, delimiter=';')
        writer.writeheader()
        files_to_parse = glob.glob(os.path.join(args.indir, '*.show.version.txt'))

        print(f'Searching for files *.show.version.txt in {args.indir}... Found {len(files_to_parse)} applicable files.')

        processed = 0

        for fn in files_to_parse:
            writer.writerow(parse_show_version(fn))
    if 'processed' in locals():

        print(f'-> Total parsed and successfully saved nodes: {processed}')

    print('CSV generated:', out)
