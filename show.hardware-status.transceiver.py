import os
import re
import csv
from glob import glob

def parse_transceiver_simple(file_path):
    base = os.path.basename(file_path)
    hostname, ident = base.split('.', 1)[0], base.split('.')[1]
    results = []
    current = {'elemento': hostname, 'id': ident}

    with open(file_path, encoding='utf-8') as f:
        for line in f:
            if line.startswith("Information of Eth"):
                if 'port' in current:
                    results.append(current)
                    current = {'elemento': hostname, 'id': ident}
                current['port'] = line.strip().split("Eth")[-1].strip()
            elif "Manufacturer:" in line:
                current['manufacturer'] = line.split(":", 1)[1].strip()
            elif "Part Number:" in line:
                current['part_number'] = line.split(":", 1)[1].strip()
            elif "Serial Number:" in line:
                current['serial_number'] = line.split(":", 1)[1].strip()
            elif "Media:" in line:
                current['media'] = line.split(":", 1)[1].strip()
            elif "Ethernet Standard:" in line:
                current['eth_std'] = line.split(":", 1)[1].strip()
            elif "Connector:" in line:
                current['connector'] = line.split(":", 1)[1].strip()

    if 'port' in current:
        results.append(current)

    return results

import argparse, os
parser = argparse.ArgumentParser()
parser.add_argument('--outdir', default='.')
args = parser.parse_args()
output_file = os.path.join(args.outdir, 'transceiver_simple_all.csv')
header = ['elemento', 'id', 'port', 'manufacturer', 'part_number',
          'serial_number', 'media', 'eth_std', 'connector']

with open(output_file, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=header, delimiter=';')
    writer.writeheader()
    for file in glob('*.show.hardware-status.transceiver.txt'):
        for row in parse_transceiver_simple(file):
            writer.writerow(row)

print("CSV gerado:", output_file)
