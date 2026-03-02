#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, glob, csv, os

def parse_show_lldp_neighbors_detail(filename):
    # Extract hostname and id from filename
    base = os.path.basename(filename)
    host, _, rest = base.partition('.')
    identifier = rest.split('.')[0]

    with open(filename) as f:
        text = f.read()

    # Normalize newlines and avoid CR issues
    text = text.replace('\r', '')

    # If LLDP is disabled, nothing to do
    if '% LLDP is not enabled' in text:
        return []

    data = []

    # Split by dashed separators between entries
    blocks = re.split(r'\n-+\n', text)

    for blk in blocks:
        # Only keep blocks that look like LLDP entries
        if 'Local Interface:' not in blk and 'Local Intf:' not in blk:
            continue

        # Local interface (two possible formats)
        m_local = re.search(r'Local Interface:\s*(.+)', blk)
        if not m_local:
            m_local = re.search(r'Local Intf:\s*(.+)', blk)
        if not m_local:
            # Something strange, skip this block
            continue
        local_if = m_local.group(1).strip()

        # Parent interface (optional)
        m_parent = re.search(r'Parent Interface:\s*(.+)', blk)
        parent_if = m_parent.group(1).strip() if m_parent else ''

        # Chassis id
        m_chassis = re.search(r'Chassis id:\s*(.+)', blk)
        chassis_id = m_chassis.group(1).strip() if m_chassis else ''

        # Port id
        m_portid = re.search(r'Port id:\s*(.+)', blk)
        port_id = m_portid.group(1).strip() if m_portid else ''

        # Port description
        m_pdesc = re.search(r'Port Description:\s*(.+)', blk)
        port_desc = m_pdesc.group(1).strip() if m_pdesc else ''

        # System name
        m_sname = re.search(r'System Name:\s*(.+)', blk)
        system_name = m_sname.group(1).strip() if m_sname else ''

        # System description (can be on the same line or in following indented lines)
        system_desc = ''
        m_sdesc = re.search(r'System Description:\s*(.*)', blk)
        if m_sdesc:
            first = m_sdesc.group(1).strip()
            if first:
                system_desc = first
            else:
                # Collect following indented non empty lines
                tail = blk[m_sdesc.end():].splitlines()
                parts = []
                for line in tail:
                    if not line.strip():
                        break
                    if line.startswith(' '):
                        parts.append(line.strip())
                    else:
                        break
                system_desc = ' '.join(parts)

        # Time remaining
        m_trem = re.search(r'Time remaining:\s*(\d+)\s*seconds', blk)
        time_remaining = m_trem.group(1) if m_trem else ''

        # Hold time (optional)
        m_hold = re.search(r'Hold Time:\s*(\d+)\s*seconds', blk)
        hold_time = m_hold.group(1) if m_hold else ''

        # Age (optional)
        m_age = re.search(r'Age:\s*(\d+)\s*seconds', blk)
        age = m_age.group(1) if m_age else ''

        # System capabilities
        m_scaps = re.search(r'System Capabilities:\s*(.+)', blk)
        system_caps = m_scaps.group(1).strip() if m_scaps else ''

        # Enabled capabilities
        m_ecaps = re.search(r'Enabled Capabilities:\s*(.+)', blk)
        enabled_caps = m_ecaps.group(1).strip() if m_ecaps else ''

        # Management IPv4
        m_ipv4 = re.search(r'IPv4 address:\s*([\d\.]+)', blk)
        if not m_ipv4:
            m_ipv4 = re.search(r'\bIP:\s*([\d\.]+)', blk)
        mgmt_ipv4 = m_ipv4.group(1).strip() if m_ipv4 else ''

        # Management IPv6
        m_ipv6 = re.search(r'IPv6 address:\s*([0-9A-Fa-f:]+)', blk)
        if not m_ipv6:
            m_ipv6 = re.search(r'\bIPV6:\s*([0-9A-Fa-f:]+)', blk)
        mgmt_ipv6 = m_ipv6.group(1).strip() if m_ipv6 else ''

        # Peer MAC (two possible labels, support : and . formats)
        m_peer = re.search(r'Peer (?:MAC Address|Source MAC):\s*([0-9A-Fa-f:\.]+)', blk)
        peer_mac = m_peer.group(1).strip() if m_peer else ''

        data.append({
            'elemento': host,
            'id': identifier,
            'local_interface': local_if,
            'parent_interface': parent_if,
            'chassis_id': chassis_id,
            'port_id': port_id,
            'port_description': port_desc,
            'system_name': system_name,
            'system_description': system_desc,
            'time_remaining': time_remaining,
            'hold_time': hold_time,
            'age': age,
            'system_capabilities': system_caps,
            'enabled_capabilities': enabled_caps,
            'mgmt_ipv4': mgmt_ipv4,
            'mgmt_ipv6': mgmt_ipv6,
            'peer_mac': peer_mac,
        })

    return data

if __name__ == '__main__':
    import argparse, os
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', default='.')
    parser.add_argument('--indir', default='.')
    args = parser.parse_args()
    out_file = os.path.join(args.outdir, 'show_lldp_neighbors_detail_all.csv')
    headers = [
        'elemento',
        'id',
        'local_interface',
        'parent_interface',
        'chassis_id',
        'port_id',
        'port_description',
        'system_name',
        'system_description',
        'time_remaining',
        'hold_time',
        'age',
        'system_capabilities',
        'enabled_capabilities',
        'mgmt_ipv4',
        'mgmt_ipv6',
        'peer_mac',
    ]
    with open(out_file, 'w', newline='') as csvf:
        writer = csv.DictWriter(csvf, fieldnames=headers, delimiter=';')
        writer.writeheader()
        for fn in glob.glob('*.show.lldp.neighbors.detail.txt'):
            for row in parse_show_lldp_neighbors_detail(fn):
                writer.writerow(row)
    print('CSV generated:', out_file)
