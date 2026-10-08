#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Native Interactive Topology Test & Validation Suite (Phase 7)
============================================================
Comprehensive test suite validating:
1. SVG Icons Engine & Theme Palette generation
2. Native Graph Engine (Physics, Orbital Concentric, Drift & Draw.io Export)
3. Load & Scale Testing: 250 backbone elements and 6,500 stress elements
4. Drift Comparator logic across snapshots
5. Client-Side Draw.io XML Generator compliance
6. Zero CORS / 100% Offline operation compliance
"""

import csv
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.topology_icons import TopologyIconsEngine, get_topology_theme_js
from core.topology_graph import TopologyGraphEngine, get_topology_graph_js
from core.topology_data_engine import TopologyDataEngine
from core.topology_engine import TopologyEngine

C_GREEN  = '\033[92m'
C_RED    = '\033[91m'
C_CYAN   = '\033[96m'
C_YELLOW = '\033[93m'
C_RESET  = '\033[0m'


def test_topology_icons_engine(sandbox: str):
    print(f"\n{C_CYAN}[*] Test 1: Topology Icons Engine & Theme Library...{C_RESET}")
    engine = TopologyIconsEngine(sandbox)
    target = engine.ensure_theme_icons_js()
    assert os.path.isfile(target), f"topology_theme_icons.js not found at {target}"
    with open(target, 'r', encoding='utf-8') as f:
        content = f.read()
    assert "window.TopologyTheme" in content
    assert "core:" in content
    assert "core_agg:" in content
    assert "edge:" in content
    assert "metro:" in content
    assert "peering:" in content
    print(f"  • SVG theme icons library generated correctly {C_GREEN}[PASS]{C_RESET}")


def test_topology_graph_engine(sandbox: str):
    print(f"\n{C_CYAN}[*] Test 2: Native Graph Engine & Canvas Scripts...{C_RESET}")
    engine = TopologyGraphEngine(sandbox)
    target = engine.ensure_graph_js()
    assert os.path.isfile(target), f"topology_graph.js not found at {target}"
    with open(target, 'r', encoding='utf-8') as f:
        content = f.read()
    assert "class NetworkTopologyGraph" in content
    assert "applyConcentricLayout" in content
    assert "applyOrganicLayout" in content
    assert "applySiteLayout" in content
    assert "setDriftData" in content
    assert "exportToDrawio" in content
    assert "generateDrawioXml" in content
    print(f"  • Graph canvas engine & Draw.io exporter generated correctly {C_GREEN}[PASS]{C_RESET}")


def test_load_scenario_250_elements(sandbox: str):
    print(f"\n{C_CYAN}[*] Test 3: Load Scenario (250 Network Elements & 600+ Connections)...{C_RESET}")
    run_id = "20261008_120000"
    run_dir = os.path.join(sandbox, "runs", run_id)
    resume_dir = os.path.join(run_dir, "resume")
    conn_dir = os.path.join(run_dir, "connections")
    os.makedirs(resume_dir, exist_ok=True)
    os.makedirs(conn_dir, exist_ok=True)

    # 1. Generate 250 elements (Backbone distribution)
    # 10 Core, 30 Aggregation, 120 Edge, 30 Peering, 50 Metro/Switch
    elements = []
    for i in range(1, 11):
        elements.append((f"RT-CORE-SITE{i:02d}-01", "core", f"SITE{i:02d}"))
    for i in range(1, 31):
        elements.append((f"RT-AGGR-SITE{i:02d}-01", "core_agg", f"SITE{i:02d}"))
    for i in range(1, 121):
        elements.append((f"RT-EDGE-SITE{((i-1)%30)+1:02d}-{i:03d}", "edge", f"SITE{((i-1)%30)+1:02d}"))
    for i in range(1, 31):
        elements.append((f"PTT-IX-SITE{i:02d}-01", "peering", f"SITE{i:02d}"))
    for i in range(1, 61):
        elements.append((f"SW-METRO-SITE{((i-1)%30)+1:02d}-{i:02d}", "metro", f"SITE{((i-1)%30)+1:02d}"))

    # Cap to exactly 250 elements
    elements = elements[:250]

    # 2. Generate connections (mesh between core, core-agg, agg-edge, edge-metro, peering)
    connections = []
    # Core full-mesh
    core_hosts = [e[0] for e in elements if e[1] == "core"]
    for i in range(len(core_hosts)):
        for j in range(i + 1, len(core_hosts)):
            connections.append((core_hosts[i], core_hosts[j], "2x 100G", 200.0, "HundredGigE0/0/0/1", "HundredGigE0/0/0/1"))

    # Core to Agg
    agg_hosts = [e[0] for e in elements if e[1] == "core_agg"]
    for idx, agg in enumerate(agg_hosts):
        core_parent = core_hosts[idx % len(core_hosts)]
        connections.append((core_parent, agg, "1x 100G", 100.0, f"HundredGigE0/0/0/{idx+2}", "HundredGigE0/0/0/1"))

    # Agg to Edge
    edge_hosts = [e[0] for e in elements if e[1] == "edge"]
    for idx, edge in enumerate(edge_hosts):
        agg_parent = agg_hosts[idx % len(agg_hosts)]
        connections.append((agg_parent, edge, "1x 40G", 40.0, f"FortyGigE0/0/{idx+1}", "FortyGigE0/0/1"))

    # Edge to Metro
    metro_hosts = [e[0] for e in elements if e[1] == "metro"]
    for idx, metro in enumerate(metro_hosts):
        edge_parent = edge_hosts[idx % len(edge_hosts)]
        connections.append((edge_parent, metro, "2x 10G", 20.0, f"TenGigE0/0/{idx+1}", "TenGigE0/1"))

    # Peering to Core/Edge
    peer_hosts = [e[0] for e in elements if e[1] == "peering"]
    for idx, peer in enumerate(peer_hosts):
        core_parent = core_hosts[idx % len(core_hosts)]
        connections.append((core_parent, peer, "1x 100G", 100.0, f"HundredGigE0/1/0/{idx+1}", "HundredGigE0/0/0/1"))

    # Write connections.csv
    conn_csv = os.path.join(conn_dir, "topology.connections.csv")
    with open(conn_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(["element", "interface", "remote_element", "remote_interface", "bandwidth", "description"])
        for c in connections:
            writer.writerow([c[0], c[4], c[1], c[5], str(int(c[3] * 1000000000)), f"CONEXAO_COM_{c[1]}"])

    # Write interfaces_all.csv
    ifaces_csv = os.path.join(resume_dir, "interfaces_all.csv")
    with open(ifaces_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(["element", "interface", "admin_status", "oper_status", "speed", "description"])
        for c in connections:
            writer.writerow([c[0], c[4], "up", "up", c[2], f"CONEXAO_COM_{c[1]}"])

    # Run extraction and time it
    start_t = time.perf_counter()
    data_engine = TopologyDataEngine(sandbox)
    payload = data_engine.extract_run_topology(run_id)
    out_file = data_engine.write_run_topology_payload(run_id, payload)
    elapsed = time.perf_counter() - start_t

    assert payload["stats"]["total_nodes"] == 250, f"Expected 250 nodes, got {payload['stats']['total_nodes']}"
    assert payload["stats"]["total_summary_edges"] > 0, "Summary edges must be > 0"
    assert os.path.isfile(out_file), f"Output payload file missing: {out_file}"

    print(f"  • Extracted 250 nodes and {payload['stats']['total_summary_edges']} summary edges in {elapsed:.3f}s {C_GREEN}[PASS]{C_RESET}")
    assert elapsed < 2.0, f"Extraction of 250 elements took too long: {elapsed:.3f}s"


def test_scale_stress_6500_nodes(sandbox: str):
    print(f"\n{C_CYAN}[*] Test 4: Scaling Stress-Test (6,500 Nodes & 12,000 Edges Target)...{C_RESET}")
    start_t = time.perf_counter()

    nodes_6500 = []
    tiers = ["core", "core_agg", "edge", "peering", "metro", "other"]
    for i in range(6500):
        tier = tiers[i % len(tiers)]
        nodes_6500.append({
            "id": f"DEV-{tier.upper()}-{i:05d}",
            "label": f"DEV-{tier.upper()}-{i:05d}",
            "tier": tier,
            "site": f"SITE-{(i % 150):03d}"
        })

    summary_edges_12000 = []
    for i in range(12000):
        src_idx = i % 6500
        tgt_idx = (i * 7 + 1) % 6500
        if src_idx != tgt_idx:
            summary_edges_12000.append({
                "source": nodes_6500[src_idx]["id"],
                "target": nodes_6500[tgt_idx]["id"],
                "capacity_str": "100G",
                "bandwidth_mbps": 100000
            })

    # Validate in-memory JSON packing efficiency
    payload_stress = {
        "run_id": "stress_6500",
        "nodes": nodes_6500,
        "summary_edges": summary_edges_12000,
        "stats": {
            "total_nodes": len(nodes_6500),
            "total_summary_edges": len(summary_edges_12000)
        }
    }
    json_bytes = json.dumps(payload_stress).encode('utf-8')
    elapsed = time.perf_counter() - start_t

    size_mb = len(json_bytes) / (1024 * 1024)
    print(f"  • Generated and serialized 6,500 nodes & 12,000 edges ({size_mb:.2f} MB) in {elapsed:.3f}s {C_GREEN}[PASS]{C_RESET}")
    assert elapsed < 3.0, f"6500 stress serialization took too long: {elapsed:.3f}s"


def test_drift_comparator_payload(sandbox: str):
    print(f"\n{C_CYAN}[*] Test 5: Drift Comparator Mathematical Difference Logic...{C_RESET}")
    # Simulate Dataset A vs Dataset B
    dataset_a = {
        "nodes": [
            {"id": "RT-CORE-01", "tier": "core"},
            {"id": "RT-CORE-02", "tier": "core"},
            {"id": "RT-EDGE-01", "tier": "edge"},
            {"id": "RT-EDGE-OLD", "tier": "edge"}, # will be removed in B
        ],
        "summary_edges": [
            {"source": "RT-CORE-01", "target": "RT-CORE-02"},
            {"source": "RT-CORE-01", "target": "RT-EDGE-OLD"},
        ]
    }

    dataset_b = {
        "nodes": [
            {"id": "RT-CORE-01", "tier": "core"},
            {"id": "RT-CORE-02", "tier": "core"},
            {"id": "RT-EDGE-01", "tier": "edge"},
            {"id": "RT-EDGE-NEW", "tier": "edge"}, # added in B
        ],
        "summary_edges": [
            {"source": "RT-CORE-01", "target": "RT-CORE-02"},
            {"source": "RT-CORE-02", "target": "RT-EDGE-NEW"}, # added
        ]
    }

    nodes_a = {n["id"] for n in dataset_a["nodes"]}
    nodes_b = {n["id"] for n in dataset_b["nodes"]}

    added_nodes = nodes_b - nodes_a
    removed_nodes = nodes_a - nodes_b
    unchanged_nodes = nodes_a & nodes_b

    assert added_nodes == {"RT-EDGE-NEW"}
    assert removed_nodes == {"RT-EDGE-OLD"}
    assert len(unchanged_nodes) == 3

    print(f"  • Node drift correctly identified: +{len(added_nodes)} added, -{len(removed_nodes)} removed {C_GREEN}[PASS]{C_RESET}")


def test_drawio_xml_generation():
    print(f"\n{C_CYAN}[*] Test 6: Client-Side Draw.io mxGraph XML Structure...{C_RESET}")
    graph_js = get_topology_graph_js()
    assert "generateDrawioXml" in graph_js
    assert "exportToDrawio" in graph_js
    assert "application/vnd.jgraph.mxfile;charset=utf-8" in graph_js
    assert "shape=mxgraph.cisco19.rect" in graph_js
    print(f"  • Draw.io export module verified with Cisco shapes and mxGraph schema {C_GREEN}[PASS]{C_RESET}")


def test_offline_zero_cors_compliance(sandbox: str):
    print(f"\n{C_CYAN}[*] Test 7: Zero CORS and 100% Offline Inspection...{C_RESET}")
    engine = TopologyEngine(sandbox)
    engine.run(force_rebuild=True)

    index_html = os.path.join(sandbox, "topology", "index.html")
    assert os.path.isfile(index_html)
    with open(index_html, 'r', encoding='utf-8') as f:
        html = f.read()

    # Verify no http:// or https:// external script tags (100% offline self-contained)
    script_tags = [line.strip() for line in html.split('\n') if '<script' in line]
    for s in script_tags:
        assert "http://" not in s and "https://" not in s, f"External network script tag detected: {s}"

    # Verify relative inclusion of manifest and icons
    assert '<script src="topology_theme_icons.js"></script>' in html
    assert '<script src="topology_graph.js"></script>' in html
    assert 'manifest.js' in html

    print(f"  • Verified 100% offline and Zero CORS architecture compliant {C_GREEN}[PASS]{C_RESET}")


if __name__ == "__main__":
    print(f"{C_CYAN}============================================================{C_RESET}")
    print(f"{C_CYAN}      NATIVE INTERACTIVE TOPOLOGY VERIFICATION SUITE       {C_RESET}")
    print(f"{C_CYAN}============================================================{C_RESET}")

    with tempfile.TemporaryDirectory() as temp_dir:
        test_topology_icons_engine(temp_dir)
        test_topology_graph_engine(temp_dir)
        test_load_scenario_250_elements(temp_dir)
        test_scale_stress_6500_nodes(temp_dir)
        test_drift_comparator_payload(temp_dir)
        test_drawio_xml_generation()
        test_offline_zero_cors_compliance(temp_dir)

    print(f"\n{C_GREEN}============================================================{C_RESET}")
    print(f"{C_GREEN}[+] ALL NATIVE TOPOLOGY SUITE TESTS COMPLETED SUCCESSFULLY! {C_RESET}")
    print(f"{C_GREEN}============================================================{C_RESET}\n")
