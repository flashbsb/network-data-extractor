#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import csv
import argparse

def main():
    parser = argparse.ArgumentParser(description="Audits the generated topology for completely isolated successful nodes.")
    parser.add_argument("--resume_dir", required=True, help="Directory containing the parsed CSV files.")
    args = parser.parse_args()

    status_csv = os.path.join(args.resume_dir, "status.elements.csv")
    topology_csv = os.path.join(args.resume_dir, "interfaces.em.conexoes.csv")
    out_csv = os.path.join(args.resume_dir, "topology_warnings.isolated.csv")

    if not os.path.isfile(status_csv):
        print("Missing status.elements.csv, skipping isolation check.")
        return
    if not os.path.isfile(topology_csv):
        print("Missing interfaces.em.conexoes.csv, skipping isolation check.")
        return

    # 1. Gather all elements successfully collected ("ok")
    ok_elements = set()
    with open(status_csv, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            if row.get("status", "") == "ok":
                # Use element_name as the primary key since it maps to the config/elements.cfg (and the connection builder root)
                el = row.get("element_name", "").strip()
                if el:
                    ok_elements.add(el)

    if not ok_elements:
        return

    # 2. Gather every single node mentioned anywhere in the topology (Ponta A or Ponta B)
    topology_nodes = set()
    with open(topology_csv, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            a = row.get("equipamento", "").strip()
            b = row.get("vizinho", "").strip()
            if a: topology_nodes.add(a)
            if b: topology_nodes.add(b)

    # 3. Find the Delta (Isolated Nodes)
    isolated = []
    for node in ok_elements:
        if node not in topology_nodes:
            isolated.append(node)

    # 4. Generate Audit Report & Signal Orchestrator
    if isolated:
        # Sort alphabetically for a neat report
        isolated.sort()
        headers = ["element_name", "status", "issue", "recommended_reason"]
        with open(out_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter=';')
            writer.writeheader()
            for node in isolated:
                writer.writerow({
                    "element_name": node,
                    "status": "isolated",
                    "issue": "Missing from map",
                    "recommended_reason": "LLDP neighbors restricted, missing, or interface2connection Regex filters dropped it."
                })
        
        # We use a special return code (e.g. 50) to signal to the main script that isolated nodes exist
        import sys
        sys.exit(50)
    else:
        # Clear any old isolation reports if things are perfectly healthy
        if os.path.exists(out_csv):
            try:
                os.remove(out_csv)
            except:
                pass
        import sys
        sys.exit(0)

if __name__ == '__main__':
    main()
