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
                'elemento': host,
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
    args = parser.parse_args()
    out = os.path.join(args.outdir, 'int_status_all.csv')
    hdr = ['elemento','id','port','mac_address','port_admin','speed_duplex','link_status','name']
    with open(out, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=hdr, delimiter=';')
        writer.writeheader()
        for fn in glob.glob('*.show.interfaces.status.txt'):
            for row in parse_show_int_status(fn):
                writer.writerow(row)
    print('CSV gerado:', out)
