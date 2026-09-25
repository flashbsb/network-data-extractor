#!/usr/bin/env python3
"""
Synthetic Demo Dataset Generator
================================
Generates a realistic 30-element Brazilian backbone network dataset across 30 days
and 10 collection runs, enabling full offline and GitHub Pages web portal navigation.

Features:
- Models 30 diverse backbone nodes (Core, Aggregation, Distribution, Peering, DWDM).
- Geographic coordinates mapped across Brazilian regions (Central-West, Southeast, South, Northeast, North).
- Real-world propagation latencies (e.g. SPO-RJO 7ms, SPO-FOR 42ms, BSB-MAO 52ms).
- Simulates realistic operational events: jitter, link flap, config drift, and OS upgrade.
- Generates Draw.io topology diagrams (Geographic, Circular, Hierarchical).
- Orchestrates core presentation engines:
  - InventoryEngine
  - DiffEngine
  - PingHistoryGenerator & Master Index
  - TopologyEngine
  - RootPortalEngine
- Provides '--refresh-views' (fast re-render) and '--rebuild' (full synthesis) modes.
"""

import os
import sys
import json
import csv
import math
import shutil
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to sys.path to allow imports from core/
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.utils_shared import load_settings

# ANSI Terminal Colors
C_GREEN = '\033[92m'
C_YELLOW = '\033[93m'
C_RED = '\033[91m'
C_CYAN = '\033[96m'
C_BOLD = '\033[1m'
C_RESET = '\033[0m'

# ------------------------------------------------------------------------------
# 1. NETWORK MODEL DEFINITION (30 NODES IN BRAZIL)
# ------------------------------------------------------------------------------

NETWORK_NODES = {
    # --- Core Routers (4x) ---
    "RT-CORE-BSB-01": {"city": "Brasília", "uf": "DF", "role": "core", "lat": -15.793889, "lon": -47.882778, "model": "Cisco 8808", "os": "IOS-XR 7.5.2", "ip": "192.0.2.1"},
    "RT-CORE-SPO-01": {"city": "São Paulo", "uf": "SP", "role": "core", "lat": -23.550520, "lon": -46.633309, "model": "Cisco 8808", "os": "IOS-XR 7.5.2", "ip": "192.0.2.2"},
    "RT-CORE-RJO-01": {"city": "Rio de Janeiro", "uf": "RJ", "role": "core", "lat": -22.906847, "lon": -43.172896, "model": "Cisco 8808", "os": "IOS-XR 7.5.2", "ip": "192.0.2.3"},
    "RT-CORE-FOR-01": {"city": "Fortaleza", "uf": "CE", "role": "core", "lat": -3.731862, "lon": -38.526671, "model": "Cisco 8808", "os": "IOS-XR 7.5.2", "ip": "192.0.2.4"},

    # --- Aggregation Routers (8x) ---
    "RT-AGGR-POA-01": {"city": "Porto Alegre", "uf": "RS", "role": "aggregation", "lat": -30.034647, "lon": -51.217659, "model": "Juniper MX480", "os": "Junos 21.4R3", "ip": "192.0.2.10"},
    "RT-AGGR-CWB-01": {"city": "Curitiba", "uf": "PR", "role": "aggregation", "lat": -25.428954, "lon": -49.267137, "model": "Juniper MX480", "os": "Junos 21.4R3", "ip": "192.0.2.11"},
    "RT-AGGR-BHZ-01": {"city": "Belo Horizonte", "uf": "MG", "role": "aggregation", "lat": -19.916681, "lon": -43.934493, "model": "Juniper MX480", "os": "Junos 21.4R3", "ip": "192.0.2.12"},
    "RT-AGGR-SSA-01": {"city": "Salvador", "uf": "BA", "role": "aggregation", "lat": -12.977749, "lon": -38.501630, "model": "Juniper MX480", "os": "Junos 21.4R3", "ip": "192.0.2.13"},
    "RT-AGGR-REC-01": {"city": "Recife", "uf": "PE", "role": "aggregation", "lat": -8.047562, "lon": -34.876964, "model": "Juniper MX480", "os": "Junos 21.4R3", "ip": "192.0.2.14"},
    "RT-AGGR-BEL-01": {"city": "Belém", "uf": "PA", "role": "aggregation", "lat": -1.455755, "lon": -48.490180, "model": "Juniper MX480", "os": "Junos 21.4R3", "ip": "192.0.2.15"},
    "RT-AGGR-MAO-01": {"city": "Manaus", "uf": "AM", "role": "aggregation", "lat": -3.119028, "lon": -60.021731, "model": "Juniper MX480", "os": "Junos 21.4R3", "ip": "192.0.2.16"},
    "RT-AGGR-CGB-01": {"city": "Cuiabá", "uf": "MT", "role": "aggregation", "lat": -15.601411, "lon": -56.097892, "model": "Juniper MX480", "os": "Junos 21.4R3", "ip": "192.0.2.17"},

    # --- Distribution & Metro Switches (12x) ---
    "SW-DIST-SPO-01": {"city": "São Paulo", "uf": "SP", "role": "distribution", "lat": -23.530520, "lon": -46.613309, "model": "Huawei CE6857", "os": "VRP 8.180", "ip": "198.51.100.20"},
    "SW-DIST-SPO-02": {"city": "São Paulo", "uf": "SP", "role": "distribution", "lat": -23.570520, "lon": -46.653309, "model": "Huawei CE6857", "os": "VRP 8.180", "ip": "198.51.100.21"},
    "SW-DIST-RJO-01": {"city": "Rio de Janeiro", "uf": "RJ", "role": "distribution", "lat": -22.886847, "lon": -43.192896, "model": "Huawei CE6857", "os": "VRP 8.180", "ip": "198.51.100.22"},
    "SW-DIST-RJO-02": {"city": "Rio de Janeiro", "uf": "RJ", "role": "distribution", "lat": -22.926847, "lon": -43.152896, "model": "Huawei CE6857", "os": "VRP 8.180", "ip": "198.51.100.23"},
    "SW-DIST-BSB-01": {"city": "Brasília", "uf": "DF", "role": "distribution", "lat": -15.773889, "lon": -47.862778, "model": "Huawei CE6857", "os": "VRP 8.180", "ip": "198.51.100.24"},
    "SW-DIST-BSB-02": {"city": "Brasília", "uf": "DF", "role": "distribution", "lat": -15.813889, "lon": -47.902778, "model": "Huawei CE6857", "os": "VRP 8.180", "ip": "198.51.100.25"},
    "SW-DIST-POA-01": {"city": "Porto Alegre", "uf": "RS", "role": "distribution", "lat": -30.014647, "lon": -51.197659, "model": "Huawei CE6857", "os": "VRP 8.180", "ip": "198.51.100.26"},
    "SW-DIST-CWB-01": {"city": "Curitiba", "uf": "PR", "role": "distribution", "lat": -25.408954, "lon": -49.247137, "model": "Huawei CE6857", "os": "VRP 8.180", "ip": "198.51.100.27"},
    "SW-DIST-BHZ-01": {"city": "Belo Horizonte", "uf": "MG", "role": "distribution", "lat": -19.896681, "lon": -43.914493, "model": "Huawei CE6857", "os": "VRP 8.180", "ip": "198.51.100.28"},
    "SW-DIST-SSA-01": {"city": "Salvador", "uf": "BA", "role": "distribution", "lat": -12.957749, "lon": -38.481630, "model": "Huawei CE6857", "os": "VRP 8.180", "ip": "198.51.100.29"},
    "SW-DIST-REC-01": {"city": "Recife", "uf": "PE", "role": "distribution", "lat": -8.027562, "lon": -34.856964, "model": "Huawei CE6857", "os": "VRP 8.180", "ip": "198.51.100.30"},
    "SW-DIST-FOR-01": {"city": "Fortaleza", "uf": "CE", "role": "distribution", "lat": -3.711862, "lon": -38.506671, "model": "Huawei CE6857", "os": "VRP 8.180", "ip": "198.51.100.31"},

    # --- Peering IX.br & Optical DWDM (6x) ---
    "PTT-IX-SPO-01": {"city": "São Paulo", "uf": "SP", "role": "peering", "lat": -23.510520, "lon": -46.613309, "model": "EdgeCore Whitebox", "os": "OpenNetworkLinux", "ip": "203.0.113.50"},
    "PTT-IX-FOR-01": {"city": "Fortaleza", "uf": "CE", "role": "peering", "lat": -3.691862, "lon": -38.486671, "model": "EdgeCore Whitebox", "os": "OpenNetworkLinux", "ip": "203.0.113.51"},
    "PTT-IX-RJO-01": {"city": "Rio de Janeiro", "uf": "RJ", "role": "peering", "lat": -22.866847, "lon": -43.172896, "model": "EdgeCore Whitebox", "os": "OpenNetworkLinux", "ip": "203.0.113.52"},
    "DW-OPT-SPO-01": {"city": "São Paulo", "uf": "SP", "role": "dwdm", "lat": -23.590520, "lon": -46.673309, "model": "Padtec LightPad", "os": "LightPad-OS 5.2", "ip": "203.0.113.60"},
    "DW-OPT-RJO-01": {"city": "Rio de Janeiro", "uf": "RJ", "role": "dwdm", "lat": -22.946847, "lon": -43.132896, "model": "Padtec LightPad", "os": "LightPad-OS 5.2", "ip": "203.0.113.61"},
    "DW-OPT-BSB-01": {"city": "Brasília", "uf": "DF", "role": "dwdm", "lat": -15.833889, "lon": -47.922778, "model": "Padtec LightPad", "os": "LightPad-OS 5.2", "ip": "203.0.113.62"},
}

# Physical Links Definition (Endpoints, Bandwidth, Normal Base Latency ms, Jitter ms)
TOPOLOGY_LINKS = [
    # Core Mesh
    {"a": "RT-CORE-BSB-01", "b": "RT-CORE-SPO-01", "speed": 100000000, "text": "1x 100G", "rtt": 14.5, "jitter": 0.8},
    {"a": "RT-CORE-SPO-01", "b": "RT-CORE-RJO-01", "speed": 100000000, "text": "2x 100G", "rtt": 7.2, "jitter": 0.4},
    {"a": "RT-CORE-BSB-01", "b": "RT-CORE-RJO-01", "speed": 100000000, "text": "1x 100G", "rtt": 16.1, "jitter": 0.7},
    {"a": "RT-CORE-FOR-01", "b": "RT-CORE-BSB-01", "speed": 100000000, "text": "1x 100G", "rtt": 34.2, "jitter": 1.1},
    {"a": "RT-CORE-FOR-01", "b": "RT-CORE-SPO-01", "speed": 100000000, "text": "1x 100G", "rtt": 43.5, "jitter": 1.2},

    # Regional Aggregation Links
    {"a": "RT-CORE-SPO-01", "b": "RT-AGGR-CWB-01", "speed": 100000000, "text": "1x 40G", "rtt": 9.3, "jitter": 0.5},
    {"a": "RT-AGGR-CWB-01", "b": "RT-AGGR-POA-01", "speed": 100000000, "text": "1x 40G", "rtt": 11.2, "jitter": 0.6},
    {"a": "RT-CORE-SPO-01", "b": "RT-AGGR-POA-01", "speed": 10000000,  "text": "2x 10G", "rtt": 19.8, "jitter": 0.9},
    {"a": "RT-CORE-SPO-01", "b": "RT-AGGR-BHZ-01", "speed": 100000000, "text": "1x 40G", "rtt": 8.7, "jitter": 0.5},
    {"a": "RT-CORE-RJO-01", "b": "RT-AGGR-BHZ-01", "speed": 100000000, "text": "1x 40G", "rtt": 9.1, "jitter": 0.5},
    {"a": "RT-CORE-BSB-01", "b": "RT-AGGR-BHZ-01", "speed": 10000000,  "text": "1x 10G", "rtt": 13.5, "jitter": 0.6},
    {"a": "RT-CORE-FOR-01", "b": "RT-AGGR-REC-01", "speed": 100000000, "text": "1x 40G", "rtt": 11.5, "jitter": 0.6},
    {"a": "RT-AGGR-REC-01", "b": "RT-AGGR-SSA-01", "speed": 100000000, "text": "1x 40G", "rtt": 13.8, "jitter": 0.7},
    {"a": "RT-CORE-BSB-01", "b": "RT-AGGR-SSA-01", "speed": 10000000,  "text": "2x 10G", "rtt": 19.2, "jitter": 0.9},
    {"a": "RT-CORE-BSB-01", "b": "RT-AGGR-BEL-01", "speed": 100000000, "text": "1x 40G", "rtt": 31.8, "jitter": 1.4},
    {"a": "RT-CORE-BSB-01", "b": "RT-AGGR-MAO-01", "speed": 10000000,  "text": "2x 10G", "rtt": 52.4, "jitter": 1.8},
    {"a": "RT-AGGR-BEL-01", "b": "RT-AGGR-MAO-01", "speed": 10000000,  "text": "1x 10G", "rtt": 28.5, "jitter": 1.5},
    {"a": "RT-CORE-BSB-01", "b": "RT-AGGR-CGB-01", "speed": 100000000, "text": "1x 40G", "rtt": 15.6, "jitter": 0.8},
    {"a": "RT-CORE-SPO-01", "b": "RT-AGGR-CGB-01", "speed": 10000000,  "text": "1x 10G", "rtt": 21.3, "jitter": 1.0},

    # Distribution / Metro Uplinks
    {"a": "SW-DIST-SPO-01", "b": "RT-CORE-SPO-01", "speed": 10000000, "text": "2x 10G", "rtt": 1.4, "jitter": 0.2},
    {"a": "SW-DIST-SPO-02", "b": "RT-CORE-SPO-01", "speed": 10000000, "text": "2x 10G", "rtt": 1.6, "jitter": 0.2},
    {"a": "SW-DIST-RJO-01", "b": "RT-CORE-RJO-01", "speed": 10000000, "text": "2x 10G", "rtt": 1.3, "jitter": 0.2},
    {"a": "SW-DIST-RJO-02", "b": "RT-CORE-RJO-01", "speed": 10000000, "text": "2x 10G", "rtt": 1.5, "jitter": 0.2},
    {"a": "SW-DIST-BSB-01", "b": "RT-CORE-BSB-01", "speed": 10000000, "text": "2x 10G", "rtt": 1.2, "jitter": 0.2},
    {"a": "SW-DIST-BSB-02", "b": "RT-CORE-BSB-01", "speed": 10000000, "text": "2x 10G", "rtt": 1.3, "jitter": 0.2},
    {"a": "SW-DIST-POA-01", "b": "RT-AGGR-POA-01", "speed": 10000000, "text": "2x 10G", "rtt": 1.4, "jitter": 0.2},
    {"a": "SW-DIST-CWB-01", "b": "RT-AGGR-CWB-01", "speed": 10000000, "text": "2x 10G", "rtt": 1.5, "jitter": 0.2},
    {"a": "SW-DIST-BHZ-01", "b": "RT-AGGR-BHZ-01", "speed": 10000000, "text": "2x 10G", "rtt": 1.3, "jitter": 0.2},
    {"a": "SW-DIST-SSA-01", "b": "RT-AGGR-SSA-01", "speed": 10000000, "text": "2x 10G", "rtt": 1.4, "jitter": 0.2},
    {"a": "SW-DIST-REC-01", "b": "RT-AGGR-REC-01", "speed": 10000000, "text": "2x 10G", "rtt": 1.5, "jitter": 0.2},
    {"a": "SW-DIST-FOR-01", "b": "RT-CORE-FOR-01", "speed": 10000000, "text": "2x 10G", "rtt": 1.2, "jitter": 0.2},

    # Peering & Optical Infrastructure
    {"a": "PTT-IX-SPO-01", "b": "RT-CORE-SPO-01", "speed": 100000000, "text": "1x 100G", "rtt": 1.1, "jitter": 0.1},
    {"a": "PTT-IX-FOR-01", "b": "RT-CORE-FOR-01", "speed": 100000000, "text": "1x 100G", "rtt": 1.0, "jitter": 0.1},
    {"a": "PTT-IX-RJO-01", "b": "RT-CORE-RJO-01", "speed": 100000000, "text": "1x 100G", "rtt": 1.1, "jitter": 0.1},
    {"a": "DW-OPT-SPO-01", "b": "RT-CORE-SPO-01", "speed": 100000000, "text": "1x 100G", "rtt": 0.6, "jitter": 0.1},
    {"a": "DW-OPT-RJO-01", "b": "RT-CORE-RJO-01", "speed": 100000000, "text": "1x 100G", "rtt": 0.6, "jitter": 0.1},
    {"a": "DW-OPT-BSB-01", "b": "RT-CORE-BSB-01", "speed": 100000000, "text": "1x 100G", "rtt": 0.6, "jitter": 0.1},
]

# ------------------------------------------------------------------------------
# 2. DRAW.IO TOPOLOGY GENERATION HELPERS
# ------------------------------------------------------------------------------

def generate_drawio_xml(layout_type: str, nodes: dict, links: list) -> str:
    """Generates standard Draw.io XML for Geographic, Circular (concentric), or Organic layout."""
    cells = []
    node_positions = {}
    
    if layout_type == "geografico":
        # Bounding box for Brazil coordinates
        min_lon, max_lon = -62.0, -34.0
        min_lat, max_lat = -31.0, -2.0
        canvas_w, canvas_h = 1600, 1400

        for name, meta in nodes.items():
            norm_x = (meta["lon"] - min_lon) / (max_lon - min_lon)
            norm_y = 1.0 - ((meta["lat"] - min_lat) / (max_lat - min_lat))
            x = int(120 + norm_x * (canvas_w - 300) - 25)
            y = int(80 + norm_y * (canvas_h - 220) - 25)
            node_positions[name] = (x, y)

    elif layout_type == "circular":
        # Concentric orbital rings by function (Core -> Aggregation -> Distribution -> Peering/DWDM)
        center_x, center_y = 1100, 1100
        
        tier_groups = {
            "core": [],
            "aggregation": [],
            "distribution": [],
            "perimeter": []
        }
        for name, meta in nodes.items():
            r = meta.get("role", "core")
            if r == "core":
                tier_groups["core"].append(name)
            elif r == "aggregation":
                tier_groups["aggregation"].append(name)
            elif r == "distribution":
                tier_groups["distribution"].append(name)
            else:
                tier_groups["perimeter"].append(name)

        tier_radii = {
            "core": 220,
            "aggregation": 460,
            "distribution": 700,
            "perimeter": 940
        }

        for tier, tier_nodes in tier_groups.items():
            radius = tier_radii[tier]
            count = len(tier_nodes)
            if count == 0:
                continue
            for i, name in enumerate(sorted(tier_nodes)):
                angle = (2 * math.pi * i) / count - (math.pi / 2)
                x = int(center_x + radius * math.cos(angle) - 25)
                y = int(center_y + radius * math.sin(angle) - 25)
                node_positions[name] = (x, y)

    else:  # organico
        # Clustered / Organic layout grouping devices naturally around regional hubs
        organic_coords = {
            # Central Core Hub
            "RT-CORE-BSB-01": (750, 480),
            "RT-CORE-SPO-01": (650, 680),
            "RT-CORE-RJO-01": (900, 680),
            "RT-CORE-FOR-01": (1100, 420),
            
            # Central-West & North (attached to BSB)
            "SW-DIST-BSB-01": (650, 370),
            "SW-DIST-BSB-02": (760, 360),
            "DW-OPT-BSB-01": (860, 380),
            "RT-AGGR-CGB-01": (480, 480),
            "RT-AGGR-BEL-01": (750, 200),
            "RT-AGGR-MAO-01": (530, 220),
            
            # São Paulo & South Region (attached to SPO)
            "SW-DIST-SPO-01": (490, 620),
            "SW-DIST-SPO-02": (500, 720),
            "PTT-IX-SPO-01": (580, 800),
            "DW-OPT-SPO-01": (700, 810),
            "RT-AGGR-CWB-01": (440, 860),
            "SW-DIST-CWB-01": (330, 920),
            "RT-AGGR-POA-01": (440, 1020),
            "SW-DIST-POA-01": (330, 1100),
            
            # Rio de Janeiro & Minas Gerais (attached to RJO / SPO)
            "SW-DIST-RJO-01": (1020, 620),
            "SW-DIST-RJO-02": (1050, 720),
            "PTT-IX-RJO-01": (950, 800),
            "DW-OPT-RJO-01": (850, 810),
            "RT-AGGR-BHZ-01": (850, 280),
            "SW-DIST-BHZ-01": (970, 240),
            
            # Fortaleza & Northeast (attached to FOR / BSB)
            "SW-DIST-FOR-01": (1230, 390),
            "PTT-IX-FOR-01": (1230, 480),
            "RT-AGGR-REC-01": (1180, 600),
            "SW-DIST-REC-01": (1290, 680),
            "RT-AGGR-SSA-01": (1100, 760),
            "SW-DIST-SSA-01": (1210, 830),
        }
        for name in nodes.keys():
            node_positions[name] = organic_coords.get(name, (800, 600))

    # Style mapping by role using Cisco 2019 stencil shapes
    role_styles = {
        "core": "shape=mxgraph.cisco19.rect;prIcon=router;fillColor=#036897;strokeColor=#FFFFFF;",
        "aggregation": "shape=mxgraph.cisco19.rect;prIcon=router;fillColor=#0385BE;strokeColor=#FFFFFF;",
        "distribution": "shape=mxgraph.cisco19.rect;prIcon=l2_switch;fillColor=#228122;strokeColor=#FFFFFF;",
        "peering": "shape=mxgraph.cisco19.rect;prIcon=router;fillColor=#E98C2F;strokeColor=#FFFFFF;",
        "dwdm": "shape=mxgraph.cisco19.rect;prIcon=optical_transport;fillColor=#854D0E;strokeColor=#FFFFFF;",
    }

    # Render Node Cells
    for name, meta in nodes.items():
        x, y = node_positions.get(name, (100, 100))
        role = meta.get("role", "core")
        role_style = role_styles.get(role, role_styles["core"])
        style = f"{role_style}verticalLabelPosition=bottom;verticalAlign=top;align=center;fontSize=11;fontStyle=1;fontColor=#0f172a;html=1;"
        label = f"{name}&lt;br&gt;&lt;span style=&quot;font-size:9px;font-weight:normal;opacity:0.8;&quot;&gt;{meta.get('city', '')} ({meta.get('uf', '')})&lt;/span&gt;"
        cells.append(
            f'<mxCell id="{name}" value="{label}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="50" height="50" as="geometry"/>'
            f'</mxCell>'
        )

    # Render Edge Cells (Straight links, no curves, no rounded corners)
    for idx, link in enumerate(links):
        a = link["a"]
        b = link["b"]
        speed = link["speed"]
        dashed = link.get("dashed", "")
        
        # Color & Stroke by speed
        if speed >= 100000000:
            stroke_color = "#10b981"
            stroke_width = "3"
        elif speed >= 10000000:
            stroke_color = "#0085da"
            stroke_width = "2"
        else:
            stroke_color = "#800080"
            stroke_width = "1"

        dash_style = "dashed=1;strokeColor=#ef4444;" if dashed == 1 else ""
        edge_style = f"edgeStyle=none;rounded=0;curved=0;html=1;endArrow=none;endFill=0;strokeColor={stroke_color};strokeWidth={stroke_width};fontSize=9;{dash_style}"
        
        link_text = link.get("text", "")
        edge_id = f"edge_{idx}"
        cells.append(
            f'<mxCell id="{edge_id}" value="{link_text}" style="{edge_style}" edge="1" parent="1" source="{a}" target="{b}">'
            f'<mxGeometry relative="1" as="geometry"/>'
            f'</mxCell>'
        )

    content = "\n      ".join(cells)
    page_w = 2400 if layout_type == "circular" else 2000
    page_h = 2400 if layout_type == "circular" else 1800
    xml = f"""<mxfile host="Electron" modified="2026-09-25T12:00:00.000Z" agent="Mozilla/5.0" version="21.0.0" type="device">
  <diagram id="diag_{layout_type}" name="{layout_type.capitalize()}">
    <mxGraphModel dx="1600" dy="1200" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{page_w}" pageHeight="{page_h}" background="#ffffff" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
      {content}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>"""
    return xml

# ------------------------------------------------------------------------------
# 3. SNAPSHOT TELEMETRY GENERATION (30 DAYS / 10 RUNS)
# ------------------------------------------------------------------------------

def generate_mock_run(run_index: int, total_runs: int, timestamp: datetime, run_dir: Path):
    """Generates a complete mock snapshot run with simulated operational events."""
    run_id = timestamp.strftime("%Y%m%d_%H%M%S")
    resume_dir = run_dir / "resume"
    conn_dir = run_dir / "connections"
    topo_dir = run_dir / "topology"
    pm_dir = run_dir / "ping-matrix" / "resume"

    for d in [resume_dir, conn_dir, topo_dir, pm_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Clone links and apply event scenarios based on run_index (1 to 10)
    current_links = [dict(lnk) for lnk in TOPOLOGY_LINKS]
    current_nodes = {k: dict(v) for k, v in NETWORK_NODES.items()}

    # Event 1 (Run 3, Day 7): BSB-MAO link degradation
    if run_index == 3:
        for lnk in current_links:
            if (lnk["a"] == "RT-CORE-BSB-01" and lnk["b"] == "RT-AGGR-MAO-01") or \
               (lnk["b"] == "RT-CORE-BSB-01" and lnk["a"] == "RT-AGGR-MAO-01"):
                lnk["rtt"] = 96.5
                lnk["jitter"] = 18.2
                lnk["loss"] = 2.0

    # Event 2 (Run 4, Day 11): SW-DIST-POA-01 uplink flap
    if run_index == 4:
        for lnk in current_links:
            if lnk["a"] == "SW-DIST-POA-01" or lnk["b"] == "SW-DIST-POA-01":
                lnk["loss"] = 10.0
                lnk["jitter"] = 12.0

    # Event 3 (Run 5, Day 15): Configuration drift (MTU changed on RT-CORE-SPO-01)
    # Reflected in interfaces_all.json

    # Event 4 (Run 6, Day 18): Maintenance on BSB-BHZ backup link (Admin DOWN)
    if run_index == 6:
        for lnk in current_links:
            if (lnk["a"] == "RT-CORE-BSB-01" and lnk["b"] == "RT-AGGR-BHZ-01") or \
               (lnk["b"] == "RT-CORE-BSB-01" and lnk["a"] == "RT-AGGR-BHZ-01"):
                lnk["dashed"] = 1
                lnk["down"] = True
                lnk["loss"] = 100.0

    # Event 5 (Run 7, Day 22): OS Upgrade on RT-CORE-SPO-01
    if run_index >= 7:
        current_nodes["RT-CORE-SPO-01"]["os"] = "IOS-XR 7.7.1"

    # Event 6 (Run 8, Day 25): Transient loss on Belém
    if run_index == 8:
        for lnk in current_links:
            if lnk["a"] == "RT-AGGR-BEL-01" or lnk["b"] == "RT-AGGR-BEL-01":
                lnk["loss"] = 5.0

    # 1. Build interfaces_all.json and interfaces_all.csv
    interfaces_list = []
    for node_name, node_meta in current_nodes.items():
        # Node loopback
        interfaces_list.append({
            "element": node_name,
            "interface": "Loopback0",
            "description": f"SYSTEM_ROUTER_ID_{node_meta['ip']}",
            "admin_status": "UP",
            "line_protocol": "UP",
            "bandwidth_kbit": "1000000"
        })

        # Physical interfaces based on links
        port_num = 0
        for lnk in current_links:
            peer = None
            if lnk["a"] == node_name:
                peer = lnk["b"]
            elif lnk["b"] == node_name:
                peer = lnk["a"]

            if peer:
                port_num += 1
                if lnk["speed"] >= 100000000:
                    iface_name = f"HundredGigE0/0/0/{port_num}"
                elif lnk["speed"] >= 10000000:
                    iface_name = f"TenGigE0/1/0/{port_num}"
                else:
                    iface_name = f"GigabitEthernet0/2/0/{port_num}"

                is_down = lnk.get("down", False)
                status = "DOWN" if is_down else "UP"

                # Standard regex-compatible description for topology parser
                desc = f"CONEXAO_COM_{peer}_{iface_name.upper()}"
                if run_index >= 5 and node_name == "RT-CORE-SPO-01" and port_num == 1:
                    desc += " [MTU 9216]"  # Config drift

                interfaces_list.append({
                    "element": node_name,
                    "interface": iface_name,
                    "description": desc,
                    "admin_status": status,
                    "line_protocol": status,
                    "bandwidth_kbit": str(lnk["speed"] // 1000)
                })

    # Write interfaces_all.json
    with open(resume_dir / "interfaces_all.json", "w", encoding="utf-8") as f:
        json.dump(interfaces_list, f, indent=2)

    # Write interfaces_all.csv
    with open(resume_dir / "interfaces_all.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["element", "interface", "description", "admin_status", "line_protocol", "bandwidth_kbit"], delimiter=";")
        writer.writeheader()
        writer.writerows(interfaces_list)

    # 2. Build topology.connections.SUM.csv and topology.connections.csv
    sum_rows = []
    for lnk in current_links:
        width = 3 if lnk["speed"] >= 100000000 else (2 if lnk["speed"] >= 10000000 else 1)
        color = "#006400" if lnk["speed"] >= 100000000 else ("#0085DA" if lnk["speed"] >= 10000000 else "#800080")
        sum_rows.append({
            "endpoint_a": lnk["a"],
            "endpoint_b": lnk["b"],
            "connection_text": lnk["text"],
            "strokeWidth": width,
            "strokeColor": color,
            "dashed": lnk.get("dashed", ""),
            "fontStyle": "",
            "fontSize": ""
        })

    conn_fields = ["endpoint_a", "endpoint_b", "connection_text", "strokeWidth", "strokeColor", "dashed", "fontStyle", "fontSize"]
    for dest_file in [conn_dir / "topology.connections.SUM.csv", conn_dir / "topology.connections.csv"]:
        with open(dest_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=conn_fields, delimiter=";")
            writer.writeheader()
            writer.writerows(sum_rows)

    # 3. Build Draw.io Diagram files in topology/
    for layout in ["geografico", "circular", "organico"]:
        xml_data = generate_drawio_xml(layout, current_nodes, current_links)
        drawio_file = topo_dir / f"topology.connections.SUM_{layout}.drawio"
        with open(drawio_file, "w", encoding="utf-8") as f:
            f.write(xml_data)

    # 4. Build Ping Matrix JSON Payload
    ping_data = []
    healthy_cnt = 0
    warn_cnt = 0
    crit_cnt = 0
    dead_cnt = 0

    for lnk in current_links:
        a = lnk["a"]
        b = lnk["b"]
        base_rtt = lnk["rtt"]
        jitter = lnk["jitter"]
        loss = lnk.get("loss", 0.0)
        is_down = lnk.get("down", False)

        if is_down or loss >= 100.0:
            dead_cnt += 2
            avg_rtt = -1.0
            rtt_min = -1.0
            rtt_max = -1.0
            loss_pct = 100.0
            rx = 0
            is_unreach = True
        else:
            loss_pct = loss
            rx = 5 if loss == 0.0 else (4 if loss <= 20.0 else 2)
            avg_rtt = round(base_rtt + (run_index % 3) * 0.2, 1)
            rtt_min = round(max(0.5, avg_rtt - jitter), 1)
            rtt_max = round(avg_rtt + jitter, 1)
            is_unreach = False

            if loss_pct > 50.0:
                crit_cnt += 2
            elif loss_pct > 0.0 or jitter > 5.0:
                warn_cnt += 2
            else:
                healthy_cnt += 2

        # Both Directions A -> B and B -> A
        for orig, dest in [(a, b), (b, a)]:
            ping_data.append({
                "origin": orig,
                "dest": dest,
                "tx": 5,
                "rx": rx,
                "loss_pct": loss_pct,
                "min": rtt_min,
                "avg": avg_rtt,
                "max": rtt_max,
                "is_unreachable": is_unreach
            })

    node_stats = {}
    for node_name in current_nodes.keys():
        node_stats[node_name] = {
            "total_targets": 0,
            "success_targets": 0,
            "sum_latency": 0.0,
            "valid_latency_count": 0,
            "reachability_pct": 0.0,
            "avg_global_latency": -1.0
        }

    for p in ping_data:
        orig = p["origin"]
        if orig in node_stats:
            node_stats[orig]["total_targets"] += 1
            if not p["is_unreachable"] and p["loss_pct"] < 100:
                node_stats[orig]["success_targets"] += 1
            if p["avg"] > 0:
                node_stats[orig]["sum_latency"] += p["avg"]
                node_stats[orig]["valid_latency_count"] += 1

    for orig, stats in node_stats.items():
        if stats["total_targets"] > 0:
            stats["reachability_pct"] = round((stats["success_targets"] / stats["total_targets"]) * 100.0, 1)
        if stats["valid_latency_count"] > 0:
            stats["avg_global_latency"] = round(stats["sum_latency"] / stats["valid_latency_count"], 1)

    total_origins = len(set(p["origin"] for p in ping_data))

    matrix_payload = {
        "metadata": {
            "datetime": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "nodes_connected": len(current_nodes),
            "total_pings": len(ping_data),
            "config": {
                "count": 5,
                "datagram_size": 100,
                "timeout": 2,
                "threads": 10,
                "matrix_mode": "selective"
            },
            "execution_metrics": {
                "total_origins": total_origins,
                "pings_per_origin": round(len(ping_data) / max(1, total_origins), 1),
                "total_pings_expected": len(ping_data),
                "total_possible_pings": len(current_nodes) * max(1, len(current_nodes) - 1),
                "estimated_duration_seconds": round(len(ping_data) * 0.15, 1),
                "actual_duration_seconds": round(len(ping_data) * 0.12, 1)
            },
            "network_health": {
                "healthy": healthy_cnt,
                "warning": warn_cnt,
                "critical": crit_cnt,
                "dead": dead_cnt
            },
            "node_stats": node_stats
        },
        "data": ping_data
    }

    # Save ping_matrix_list.json in both locations for compatibility
    for target_json in [pm_dir / "ping_matrix_list.json", resume_dir / "ping_matrix_list.json"]:
        with open(target_json, "w", encoding="utf-8") as f:
            json.dump(matrix_payload, f, indent=2)

    # Render individual ping_matrix_dashboard.html in both locations
    try:
        from core.ping_matrix import render_ping_matrix_html
        html_content = render_ping_matrix_html(matrix_payload)
        for target_html in [pm_dir / "ping_matrix_dashboard.html", resume_dir / "ping_matrix_dashboard.html"]:
            with open(target_html, "w", encoding="utf-8") as f:
                f.write(html_content)
    except Exception as e:
        print(f"{C_YELLOW}[!] Warning: Could not render individual dashboard for {run_id}: {e}{C_RESET}")

# ------------------------------------------------------------------------------
# 4. ORCHESTRATION PIPELINE
# ------------------------------------------------------------------------------

def build_demo_runs(outbase: Path, total_runs: int = 10, days_span: int = 30):
    """Builds the 10 chronological snapshot runs across the past 30 days."""
    runs_dir = outbase / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{C_CYAN}[*] Step 1: Synthesizing {total_runs} Mock Runs across {days_span} Days...{C_RESET}")

    now = datetime.now()
    step_days = days_span / (total_runs - 1)

    for i in range(total_runs):
        day_offset = int((total_runs - 1 - i) * step_days)
        run_time = now - timedelta(days=day_offset, hours=(i % 3), minutes=(i * 7) % 60)
        run_id = run_time.strftime("%Y%m%d_%H%M%S")
        run_path = runs_dir / run_id

        print(f"  • Run {i+1:02d}/{total_runs:02d}: {run_id} (Day -{day_offset:02d})")
        generate_mock_run(run_index=i+1, total_runs=total_runs, timestamp=run_time, run_dir=run_path)

    print(f"{C_GREEN}[+] All {total_runs} mock snapshot runs synthesized in {runs_dir}{C_RESET}")

def run_presentation_engines(outbase: Path):
    """Runs all core presentation engines to update web portals, manifests, and charts."""
    print(f"\n{C_CYAN}[*] Step 2: Running Core Presentation Engines on {outbase}...{C_RESET}")

    # Ensure demo/.nojekyll exists
    (outbase / ".nojekyll").write_text("# Disable Jekyll processing on GitHub Pages\n", encoding="utf-8")

    # 1. Inventory Engine
    print(f"  • Updating Inventory Engine...")
    try:
        from core.inventory_engine import InventoryEngine
        InventoryEngine(str(outbase)).run(force_rebuild=True)
    except Exception as e:
        print(f"    {C_RED}[!] InventoryEngine failed: {e}{C_RESET}")

    # 2. Diff Engine
    print(f"  • Updating Diff Engine...")
    try:
        from core.diff_engine import DiffEngine
        DiffEngine(str(outbase)).run(force_rebuild=True)
    except Exception as e:
        print(f"    {C_RED}[!] DiffEngine failed: {e}{C_RESET}")

    # 3. Ping Matrix History & Master Index
    print(f"  • Updating Ping History & Master Dashboard...")
    try:
        from core.ping_history_generator import PingHistoryGenerator
        PingHistoryGenerator(str(outbase)).run(force_rebuild=True)
    except Exception as e:
        print(f"    {C_RED}[!] PingHistoryGenerator failed: {e}{C_RESET}")

    try:
        from core.ping_master_dashboard import generate_master_dashboard
        generate_master_dashboard(str(outbase))
    except Exception as e:
        print(f"    {C_RED}[!] generate_master_dashboard failed: {e}{C_RESET}")

    # 4. Topology Engine
    print(f"  • Updating Topology Engine...")
    try:
        # If offline viewer assets are available locally in infos/topology, copy them to demo/topology
        local_viewer_js = REPO_ROOT / "infos" / "topology" / "viewer-static.min.js"
        dest_topo_dir = outbase / "topology"
        dest_topo_dir.mkdir(parents=True, exist_ok=True)
        if local_viewer_js.is_file() and not (dest_topo_dir / "viewer-static.min.js").exists():
            shutil.copy2(local_viewer_js, dest_topo_dir / "viewer-static.min.js")

        local_viewer_html = REPO_ROOT / "infos" / "topology" / "viewer.html"
        if local_viewer_html.is_file() and not (dest_topo_dir / "viewer.html").exists():
            shutil.copy2(local_viewer_html, dest_topo_dir / "viewer.html")

        from core.topology_engine import TopologyEngine
        TopologyEngine(str(outbase)).run()
    except Exception as e:
        print(f"    {C_RED}[!] TopologyEngine failed: {e}{C_RESET}")

    # 5. Root Navigation Portal
    print(f"  • Updating Root Master Navigation Portal...")
    try:
        from core.root_portal_engine import generate_root_portal
        generate_root_portal(str(outbase))
    except Exception as e:
        print(f"    {C_RED}[!] Root Portal Engine failed: {e}{C_RESET}")

    print(f"\n{C_BOLD}{C_GREEN}[✔] Complete Demo Web Portal ready at: {outbase.resolve()}{C_RESET}")
    print(f"{C_CYAN}To view locally, run:{C_RESET}")
    print(f"  python3 -m http.server 8000 --directory {outbase.name}")
    print(f"{C_CYAN}Open in browser: http://localhost:8000{C_RESET}\n")

# ------------------------------------------------------------------------------
# 5. CLI INTERFACE & MAIN ENTRYPOINT
# ------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Synthetic Backbone Dataset Generator for Network Data Extractor Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="demo",
        help="Destination directory for the demo dataset (default: demo)"
    )
    parser.add_argument(
        "--refresh-views",
        action="store_true",
        help="Keep existing demo/runs/ telemetry and re-render only the presentation engines (takes ~3s)"
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Wipe and rebuild all 10 snapshot runs and data from scratch (takes ~15s)"
    )

    args = parser.parse_args()
    outbase = REPO_ROOT / args.output_dir

    print(f"{C_BOLD}{C_CYAN}============================================================{C_RESET}")
    print(f"{C_BOLD}{C_CYAN}       NETWORK DATA EXTRACTOR - DEMO DATASET GENERATOR       {C_RESET}")
    print(f"{C_BOLD}{C_CYAN}============================================================{C_RESET}")
    print(f"Target Directory: {outbase}")

    runs_dir = outbase / "runs"
    has_existing_runs = runs_dir.is_dir() and any(runs_dir.glob("20*_*"))

    if args.refresh_views:
        if not has_existing_runs:
            print(f"{C_YELLOW}[!] Notice: No existing runs found in {runs_dir}. Performing full build.{C_RESET}")
            build_demo_runs(outbase)
        run_presentation_engines(outbase)
        return

    if args.rebuild:
        print(f"{C_YELLOW}[*] Performing FULL REBUILD (wiping {outbase})...{C_RESET}")
        if outbase.exists():
            shutil.rmtree(outbase)
        outbase.mkdir(parents=True, exist_ok=True)
        build_demo_runs(outbase)
        run_presentation_engines(outbase)
        return

    # Default action
    if not has_existing_runs:
        print(f"[*] No existing demo data found. Generating synthetic backbone from scratch...")
        build_demo_runs(outbase)
    else:
        print(f"[*] Found existing runs in {runs_dir}. Re-rendering presentation engines...")

    run_presentation_engines(outbase)

if __name__ == "__main__":
    main()
