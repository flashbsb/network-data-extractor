#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, glob, csv, os

def parse_show_int_status(filename):
    base = os.path.basename(filename)
    host, _, rest = base.partition('.')
    identifier = rest.split('.')[0]
    text = open(filename).read()
    # Assume blocos separados por "Information of"
    blocks = re.split(r'Information of', text)[1:]
    data = []
    for blk in blocks:
        port = re.search(r'Eth\s*\S+', blk)
        mac  = re.search(r'MAC address:\s*([\dA-F:]+)', blk)
        admin = re.search(r'Port admin:\s*(\w+)', blk)
        spd   = re.search(r'Speed-duplex:\s*([^\n]+)', blk)
        link  = re.search(r'Link status:\s*(\w+)', blk)
        name  = re.search(r'Name:\s*(.*)', blk)
        if port and mac and admin and spd:
            data.append({
                'element': host,
                'id': identifier,
                'port': port.group(0),
                'mac_address': mac.group(1),
                'port_admin': admin.group(1),
                'speed_duplex': spd.group(1).strip(),
                'link_status': link.group(1) if link else '',
                'name': name.group(1).strip() if name else ''
            })
    return data

if __name__ == '__main__':
    import argparse, os
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', default='.')
    parser.add_argument('--indir', default='.')
    args = parser.parse_args()
    out = os.path.join(args.outdir, 'int_status_all.csv')
    hdr = ['element','id','port','mac_address','port_admin','speed_duplex','link_status','name']
    with open(out, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=hdr, delimiter=';')
        writer.writeheader()
        files_to_parse = glob.glob(os.path.join(args.indir, '*.show.interfaces.status.txt'))

        print(f'Searching for files *.show.interfaces.status.txt in {args.indir}... Found {len(files_to_parse)} applicable files.')

        processed = 0

        for fn in files_to_parse:
            for row in parse_show_int_status(fn):
                writer.writerow(row)
    if 'processed' in locals():

        print(f'-> Total parsed and successfully saved nodes: {processed}')

    print('CSV generated:', out)
