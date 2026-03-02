#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, glob, csv, os

def safe_search(pattern, text, default=''):
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1).strip() if m else default

def parse_show_firmware(filename):
    base = os.path.basename(filename)
    host, _, rest = base.partition('.')
    identifier = rest.split('.')[0]
    text = open(filename).read()
    # extrai flashes (pode não existir nenhum)
    flashes = re.findall(
        r'^\s*(\d+)\s+([\d\.]+)\s+(\d{2}/\d{2}/\d{4} [\d:]+)\s+(\S*)\s+(\d+)',
        text, re.MULTILINE
    )
    flashes_str = ';'.join(f"{i}|{v}|{d}|{f}|{s}" for (i,v,d,f,s) in flashes)
    return {
        'elemento': host,
        'id': identifier,
        'running_version':    safe_search(r'Firmware version:\s*(\S+)', text),
        'stack_version':      safe_search(r'Stack version:\s*(\S+)', text),
        'compile_date':       safe_search(r'Compile date:\s*(.+)', text),
        'bootloader_version': safe_search(r'Bootloader version:\s*(\S+)', text),
        'flashes':            flashes_str
    }

if __name__ == '__main__':
    import argparse, os
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', default='.')
    parser.add_argument('--indir', default='.')
    args = parser.parse_args()
    out = os.path.join(args.outdir, 'firmware_all.csv')
    hdr = [
        'elemento','id','running_version','stack_version',
        'compile_date','bootloader_version','flashes'
    ]
    with open(out, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=hdr, delimiter=';')
        writer.writeheader()
        for fn in glob.glob(os.path.join(args.indir, '*.show.firmware.txt')):
            writer.writerow(parse_show_firmware(fn))
    print('CSV gerado:', out)
