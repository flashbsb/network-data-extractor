#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, glob, csv, os

def safe_search(pattern, text, default=''):
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1).strip() if m else default

def yes_no(feature, text):
    # busca "Feature:    yes    yes"
    return 'yes' if re.search(fr'{feature}:\s*yes\s+yes', text) else 'no'

def parse_show_system(filename):
    base = os.path.basename(filename)
    host, _, rest = base.partition('.')
    identifier = rest.split('.')[0]
    text = open(filename).read()
    return {
        'elemento':     host,
        'id':           identifier,
        'model':        safe_search(r'Model:\s*(.+)', text),
        'oid':          safe_search(r'OID:\s*([\d\.]+)', text),
        'mainboard_id': safe_search(r'Mainboard ID:\s*(\d+)', text),
        'mac_address':  safe_search(r'MAC Address:\s*([\dA-F:]+)', text),
        'bridge':       yes_no('Bridge', text),
        'router':       yes_no('Router', text),
        'mpls':         yes_no('MPLS', text),
        'name':         safe_search(r'Name:\s*(.+)', text),
        'location':     safe_search(r'Location:\s*(.+)', text),
        'contact':      safe_search(r'Contact:\s*(.+)', text),
    }

if __name__ == '__main__':
    import argparse, os
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', default='.')
    args = parser.parse_args()
    out = os.path.join(args.outdir, 'system_all.csv')
    hdr = [
        'elemento','id','model','oid','mainboard_id','mac_address',
        'bridge','router','mpls','name','location','contact'
    ]
    with open(out, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=hdr, delimiter=';')
        writer.writeheader()
        for fn in glob.glob('*.show.system.txt'):
            writer.writerow(parse_show_system(fn))
    print('CSV gerado:', out)
