#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, glob, csv, os

def parse_show_interfaces(filename):
    # Extracts hostname and id from filename
    base = os.path.basename(filename)
    host, _, rest = base.partition('.')
    identifier = rest.split('.')[0]
    data = []
    with open(filename) as f:
        text = f.read()
    # Splits into blocks per interface
    blocks = re.split(r'\n(?=\S+ is )', text)
    for blk in blocks:
        m = re.match(r'^(?P<iface>\S+) is (?P<admin>[\w ]+), line protocol is (?P<prot>[\w ]+)', blk)
        if not m:
            continue
        iface = m.group('iface')
        admin = m.group('admin').strip()
        prot = m.group('prot').strip()
        desc = re.search(r'Description:\s*(.+)', blk)
        ip   = re.search(r'Internet address is ([\d\.\/]+)', blk)
        mtu  = re.search(r'MTU (\d+) bytes', blk)
        bw   = re.search(r'BW (\d+) Kbit', blk)
        rel  = re.search(r'reliability (\S+),', blk)
        tx   = re.search(r'txload (\S+),', blk)
        rx   = re.search(r'rxload (\S+)', blk)
        flap = re.search(r'Last link flapped ([\w\d]+)', blk)
        data.append({
            'element': host,
            'id': identifier,
            'interface': iface,
            'admin_status': admin,
            'line_protocol': prot,
            'description': desc.group(1).strip() if desc else '',
            'ip_address': ip.group(1) if ip else '',
            'mtu': mtu.group(1) if mtu else '',
            'bandwidth_kbit': bw.group(1) if bw else '',
            'reliability': rel.group(1) if rel else '',
            'txload': tx.group(1) if tx else '',
            'rxload': rx.group(1) if rx else '',
            'last_flapped': flap.group(1) if flap else '',
        })
    return data

if __name__ == '__main__':
    import argparse, os
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', default='.')
    parser.add_argument('--indir', default='.')
    args = parser.parse_args()
    out_file = os.path.join(args.outdir, 'interfaces_all.csv')
    headers = ['element','id','interface','admin_status','line_protocol','description',
               'ip_address','mtu','bandwidth_kbit','reliability','txload','rxload','last_flapped']
    with open(out_file, 'w', newline='') as csvf:
        writer = csv.DictWriter(csvf, fieldnames=headers, delimiter=';')
        writer.writeheader()
        files_to_parse = glob.glob(os.path.join(args.indir, '*.show.interfaces.txt'))

        print(f'Searching for files *.show.interfaces.txt in {args.indir}... Found {len(files_to_parse)} applicable files.')

        processed = 0

        for fn in files_to_parse:
            for row in parse_show_interfaces(fn):
                writer.writerow(row)
    print(f'CSV generated: {out_file}')
