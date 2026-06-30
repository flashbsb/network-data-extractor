#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import csv
from glob import glob

class InventoryEngine:
    def __init__(self, base_path):
        self.base_path = base_path
        # Store the inventory workspace inside the base collection folder
        self.inventory_dir = os.path.join(base_path, "inventory")
        self.data_dir = os.path.join(self.inventory_dir, "data")
        
        # ANSI Colors
        self.C_CYAN = '\033[96m'
        self.C_GREEN = '\033[92m'
        self.C_YELLOW = '\033[93m'
        self.C_RED = '\033[91m'
        self.C_RESET = '\033[0m'

        # Load routing hierarchy settings
        _dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.normpath(os.path.join(_dir, "..", "config", "settings.json"))
        self.routing_hierarchy = {
            "metro": ["SWAC", "SWAG"],
            "edge": ["RTAC", "RTED"],
            "core_agg": ["RTOC"],
            "core": ["RTIC"],
            "peering": ["RTPR"],
            "router_reflector": ["RTRR"]
        }
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    json_config = json.load(f)
                    self.routing_hierarchy = json_config.get("routing_hierarchy", self.routing_hierarchy)
            except Exception as e:
                print(f"Warning: Failed to load settings.json in InventoryEngine: {e}")

    def run(self):
        print(f"[*] Base path: {self.base_path}")
        self._ensure_dirs()
        
        collections = self._scan_collections()
        if not collections:
            print(f"{self.C_RED}[!] No collections found in {self.base_path}.{self.C_RESET}")
            return

        self._prune_workspace(collections)

        manifest = []
        for col in collections:
            interfaces = self._extract_interfaces(col)
            connections = self._extract_connections(col)
            
            if interfaces:
                # Gather unique device hostnames and precompute ranks
                unique_devices = set()
                for interface in interfaces:
                    el = interface.get("element")
                    if el:
                        unique_devices.add(el)
                for conn in (connections or []):
                    ea = conn.get("endpoint_a")
                    eb = conn.get("endpoint_b")
                    if ea:
                        unique_devices.add(ea)
                    if eb:
                        unique_devices.add(eb)
                
                device_ranks = {dev: self._get_device_rank(dev) for dev in unique_devices if dev}

                # Combine payload
                payload = {
                    "interfaces": interfaces,
                    "connections": connections if connections else [],
                    "routing_hierarchy": self.routing_hierarchy,
                    "device_ranks": device_ranks
                }
                
                # Save as JS for CORS bypass
                target_js = os.path.join(self.data_dir, f"{col['id']}.js")
                js_content = f"if(!window.inv_data) window.inv_data = {{}}; window.inv_data['{col['id']}'] = {json.dumps(payload)};"
                with open(target_js, 'w', encoding='utf-8') as f:
                    f.write(js_content)
                
                manifest.append({
                    "id": col['id'],
                    "date": col['date'],
                    "file": f"data/{col['id']}.js"
                })

        # Save Manifest
        manifest_js = f"window.inv_manifest = {json.dumps(manifest, indent=4)};"
        with open(os.path.join(self.inventory_dir, "manifest.js"), 'w', encoding='utf-8') as f:
            f.write(manifest_js)

        # Update Dashboard
        self._update_dashboard()
        
        print(f"\n{self.C_GREEN}[+] Inventory Dashboard ready!{self.C_RESET}")
        print(f"[*] Workspace: {os.path.abspath(self.inventory_dir)}")
        print(f"[*] Open: {os.path.abspath(os.path.join(self.inventory_dir, 'index.html'))}")

    def _ensure_dirs(self):
        for d in [self.inventory_dir, self.data_dir]:
            if not os.path.exists(d):
                os.makedirs(d)

    def _get_device_rank(self, hostname):
        if not hostname:
            return 0
        hostname_upper = hostname.strip().upper()
        categories = [
            ("metro", 1),
            ("edge", 2),
            ("core_agg", 3),
            ("core", 4),
            ("peering", 5),
            ("router_reflector", 6)
        ]
        for key, rank in categories:
            prefixes = self.routing_hierarchy.get(key, [])
            for prefix in prefixes:
                if hostname_upper.startswith(prefix.upper()):
                    return rank
        return 0

    def _prune_workspace(self, active_collections):
        active_ids = {c['id'] for c in active_collections}
        existing_js = glob(os.path.join(self.data_dir, "*.js"))
        
        pruned_count = 0
        for js_path in existing_js:
            js_id = os.path.basename(js_path).replace(".js", "")
            if js_id not in active_ids:
                try:
                    os.remove(js_path)
                    pruned_count += 1
                except: pass
        
        if pruned_count > 0:
            print(f"{self.C_YELLOW}[*] Pruned {pruned_count} orphaned inventory data files.{self.C_RESET}")

    def _scan_collections(self):
        dirs = sorted(glob(os.path.join(self.base_path, "runs", "20*_*")), reverse=True)
        results = []
        for d in dirs:
            basename = os.path.basename(d)
            json_file = os.path.join(d, "resume", "ping_matrix_list.json")
            date_str = basename
            if os.path.exists(json_file):
                try:
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                        date_str = data.get("metadata", {}).get("datetime", basename)
                except: pass
            
            results.append({"id": basename, "path": d, "date": date_str})
        return results

    def _extract_interfaces(self, col):
        sources = [
            os.path.join(col['path'], "resume", "interfaces_all.json"),
            os.path.join(col['path'], "resume", "interfaces_all.csv"),
            os.path.join(col['path'], "resume", "interfaces.all.csv")
        ]
        
        for src in sources:
            if os.path.exists(src):
                if src.endswith('.json'):
                    try:
                        with open(src, 'r', encoding='utf-8') as f:
                            return json.load(f)
                    except: continue
                else:
                    try:
                        data = []
                        with open(src, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read(4096)
                            f.seek(0)
                            delimiter = ';' if ';' in content else ','
                            reader = csv.DictReader(f, delimiter=delimiter)
                            for row in reader:
                                data.append({
                                    "element": row.get("element", row.get("device", row.get("node", ""))),
                                    "interface": row.get("interface", row.get("port", "")),
                                    "description": row.get("description", row.get("descr", "")),
                                    "admin_status": row.get("admin_status", row.get("admin", "")),
                                    "line_protocol": row.get("line_protocol", row.get("oper", row.get("status", ""))),
                                    "bandwidth_kbit": row.get("bandwidth_kbit", row.get("bandwidth", row.get("speed", "0")))
                                })
                        return data
                    except: continue
        return None

    def _extract_connections(self, col):
        sum_csv = os.path.join(col['path'], "connections", "topology.connections.SUM.csv")
        if not os.path.exists(sum_csv):
            # Try detailed one if SUM is not there
            sum_csv = os.path.join(col['path'], "connections", "topology.connections.csv")
            
        data = []
        if os.path.exists(sum_csv):
            try:
                with open(sum_csv, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(4096)
                    f.seek(0)
                    delimiter = ';' if ';' in content else ','
                    reader = csv.DictReader(f, delimiter=delimiter)
                    for row in reader:
                        data.append({
                            "endpoint_a": row.get("endpoint_a", ""),
                            "endpoint_b": row.get("endpoint_b", ""),
                            "connection_text": row.get("connection_text", ""),
                            "dashed": row.get("dashed", "")
                        })
            except Exception:
                pass
        return data

    def _update_dashboard(self):
        template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="description" content="Network Inventory Management Dashboard">
    <meta property="og:title" content="Network Inventory Portal">
    <title>Network Inventory & Connections</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #020617;
            --sidebar-bg: #0f172a;
            --accent: #38bdf8;
            --accent-hover: #0ea5e9;
            --text: #f8fafc;
            --text-dim: #94a3b8;
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
            --border: #1e293b;
            --glass: rgba(15, 23, 42, 0.7);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-dark); color: var(--text); display: flex; height: 100vh; overflow: hidden; width: 100vw; max-width: 100%; }

        /* Sidebar Styles */
        .sidebar { width: 300px; background-color: var(--sidebar-bg); border-right: 1px solid var(--border); display: flex; flex-direction: column; z-index: 100; box-shadow: 10px 0 30px rgba(0,0,0,0.5); transition: margin-left 0.3s ease; flex-shrink: 0; }
        .sidebar.collapsed { margin-left: -300px; }
        .sidebar .header { padding: 30px 24px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; background: radial-gradient(circle at top left, rgba(56,189,248,0.1), transparent);}
        .sidebar .header-text h2 { font-family: 'Outfit'; font-size: 1.3rem; color: var(--accent); }
        .sidebar .header-text p { font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; margin-top: 4px; }
        .sidebar-close-btn { background: none; border: none; color: var(--text-dim); cursor: pointer; font-size: 1.2rem; }
        .sidebar-close-btn:hover { color: var(--text); }
        .sidebar .list { flex: 1; overflow-y: auto; padding: 16px; scrollbar-width: thin; scrollbar-color: var(--border) transparent; }

        .run-item { padding: 14px; border-radius: 10px; margin-bottom: 8px; cursor: pointer; transition: all 0.2s; border: 1px solid transparent; display: flex; align-items: center; justify-content: space-between; background: rgba(30, 41, 59, 0.3); }
        .run-item:hover { background-color: rgba(30, 41, 59, 0.8); border-color: rgba(56, 189, 248, 0.3); transform: translateX(4px); }
        .run-item.active { background-color: rgba(14, 165, 233, 0.15); border-color: var(--accent); box-shadow: inset 4px 0 0 var(--accent); }
        .run-date { font-weight: 600; font-size: 0.9rem; color: var(--text); }
        .run-id { font-size: 0.7rem; color: var(--text-dim); font-family: monospace; margin-top: 2px; }

        /* Main Content */
        .main-content { flex: 1; min-width: 0; display: flex; flex-direction: column; position: relative; background: radial-gradient(circle at top right, #0f172a, #020617); overflow-y: auto; overflow-x: hidden; }
        .sidebar.collapsed ~ .main-content { width: 100vw; }
        .hud-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding: 15px 25px;
            background: rgba(15, 23, 42, 0.4);
            backdrop-filter: blur(10px);
            position: sticky;
            top: 0;
            z-index: 300;
            width: 100%;
        }
        .hud-title h1 {
            font-size: 1.5rem;
            font-weight: 800;
            color: var(--accent);
            font-family: 'Outfit', sans-serif;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin: 0;
        }
        .hud-title p {
            font-size: 0.7rem;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-top: 2px;
        }
        .sidebar-toggle-btn { background: var(--glass); backdrop-filter: blur(10px); color: white; border: 1px solid var(--border); padding: 8px 12px; border-radius: 8px; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 8px; transition: all 0.2s; }
        .sidebar-toggle-btn:hover { border-color: var(--accent); color: var(--accent); }
        .back-portal {
            background: var(--glass);
            backdrop-filter: blur(10px);
            color: var(--accent);
            border: 1px solid var(--border);
            padding: 8px 12px;
            border-radius: 8px;
            font-weight: 600;
            text-decoration: none;
            text-transform: uppercase;
            font-size: 0.85rem;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .back-portal:hover {
            border-color: var(--accent);
            color: #fff;
            background: rgba(56, 189, 248, 0.15);
        }

        #welcome { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 40px; animation: fadeIn 1s; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

        #dashboardOverlay { display: none; flex-direction: column; padding: 20px 40px; animation: slideIn 0.4s ease; min-height: 100vh; max-width: 100%;}
        @keyframes slideIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

        .dashboard-header { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 25px; border-bottom: 1px solid var(--border); padding-bottom: 20px;}
        .dashboard-title h1 { font-family: 'Outfit'; font-size: 2.2rem; color: var(--accent); margin-bottom: 5px; text-shadow: 0 0 20px rgba(56,189,248,0.3);}
        .dashboard-title p { color: var(--text-dim); font-weight: 500; }

        /* Metrics Box */
        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .metric-card { background: var(--glass); backdrop-filter: blur(12px); border: 1px solid var(--border); border-radius: 12px; padding: 20px; text-align: center; box-shadow: 0 10px 20px rgba(0,0,0,0.2); }
        .metric-card h3 { font-size: 0.8rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px; }
        .metric-card .val { font-family: 'Outfit'; font-size: 2.5rem; color: var(--text); font-weight: 800; }
        .metric-card .val.up, .up { color: var(--success); text-shadow: 0 0 15px rgba(34,197,94,0.3); }
        .metric-card .val.down, .down { color: var(--danger); text-shadow: 0 0 15px rgba(239,68,68,0.3); }

        /* Controls / Tabs */
        .controls-bar { display: flex; justify-content: space-between; align-items: center; background: rgba(15,23,42,0.8); border: 1px solid var(--border); padding: 15px 25px; border-radius: 12px; margin-bottom: 20px; flex-wrap: wrap; gap: 15px;}
        
        .tabs { display: flex; gap: 10px; }
        .tab-btn { background: transparent; border: 1px solid var(--border); color: var(--text-dim); padding: 8px 20px; border-radius: 8px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
        .tab-btn.active { background: rgba(56,189,248,0.1); border-color: var(--accent); color: var(--accent); }
        .tab-btn:hover:not(.active) { background: rgba(255,255,255,0.05); color: var(--text); }

        .filter-box { display: flex; gap: 15px; align-items: center; }
        
        /* Help Tooltip & Clear Button & Export */
        .search-wrapper { position: relative; display: flex; align-items: center; gap: 8px; }
        .clear-btn { background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); color: var(--danger); border-radius: 6px; width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: bold; cursor: pointer; transition: all 0.2s; }
        .clear-btn:hover { background: rgba(239,68,68,0.25); color: #f87171; }
        
        .export-btn { background: rgba(56,189,248,0.1); border: 1px solid rgba(56,189,248,0.3); color: var(--accent); border-radius: 6px; padding: 0 12px; height: 28px; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: bold; cursor: pointer; transition: all 0.2s; white-space: nowrap; margin-left: 5px; }
        .export-btn:hover { background: rgba(56,189,248,0.25); color: #fff; }
        
        .help-icon { background: rgba(56,189,248,0.2); color: var(--accent); border: 1px solid var(--accent); border-radius: 50%; width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: bold; cursor: help; }
        .help-tooltip { visibility: hidden; opacity: 0; width: 320px; background: rgba(15,23,42,0.95); color: #fff; text-align: left; border-radius: 8px; padding: 12px; position: absolute; z-index: 500; top: 120%; right: 0; border: 1px solid var(--border); box-shadow: 0 10px 25px rgba(0,0,0,0.5); font-size: 0.8rem; transition: opacity 0.3s; pointer-events: none; backdrop-filter: blur(5px); }
        .help-icon:hover .help-tooltip { visibility: visible; opacity: 1; }
        .help-tooltip strong { color: var(--accent); }
        .help-tooltip code { background: rgba(255,255,255,0.1); padding: 2px 4px; border-radius: 4px; color: #4ade80; }
        
        .input-styled { background: #020617; border: 1px solid var(--border); color: white; padding: 10px 15px; border-radius: 8px; font-size: 0.85rem; outline: none; min-width: 250px; transition: border-color 0.2s; }
        .input-styled:focus { border-color: var(--accent); }
        .status-filter { display: flex; gap: 10px; }
        .status-filter label { font-size: 0.8rem; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 5px; color: var(--text-dim); }
        .status-filter input { accent-color: var(--accent); cursor: pointer; }

        /* Tables */
        .table-container { background: var(--sidebar-bg); border-radius: 12px; border: 1px solid var(--border); overflow-x: auto; overflow-y: auto; box-shadow: 0 15px 40px rgba(0,0,0,0.4); max-height: calc(100vh - 350px); display: none; width: 100%; max-width: 100%; }
        .table-container.active { display: block; }
        table { width: 100%; border-collapse: collapse; min-width: 900px; }
        th { background: rgba(30,41,59,0.9); text-align: left; padding: 15px 20px; font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; font-weight: 800; position: sticky; top: 0; z-index: 10; backdrop-filter: blur(5px); border-bottom: 2px solid var(--border); white-space: nowrap;}
        td { padding: 15px 20px; border-bottom: 1px solid var(--border); font-size: 0.85rem; color: #cbd5e1; vertical-align: middle; white-space: nowrap;}
        tr:hover td { background: rgba(255,255,255,0.02); }
        tr:last-child td { border-bottom: none; }

        .tag { padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 800; text-transform: uppercase; display: inline-block; }
        .tag-up { background: rgba(34,197,94,0.15); color: #4ade80; border: 1px solid rgba(34,197,94,0.3); }
        .tag-down { background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.3); }
        .tag-bw { background: rgba(56,189,248,0.1); color: var(--accent); }

        .conn-row td { font-size: 0.95rem; }
        .conn-endpoints { display: flex; align-items: center; gap: 15px; }
        .conn-node { font-weight: 700; color: var(--text); background: rgba(255,255,255,0.05); padding: 5px 12px; border-radius: 6px; }
        .conn-arrow { color: var(--text-dim); font-size: 1.2rem; }
        .conn-dashed { text-decoration: line-through; opacity: 0.5; color: var(--danger); }

        /* Context Menu Styles */
        .context-menu {
            position: absolute;
            background: #0f172a;
            border: 1px solid var(--border);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            border-radius: 8px;
            z-index: 10000;
            display: none;
            flex-direction: column;
            padding: 8px 0;
            min-width: 200px;
            font-family: 'Inter', sans-serif;
        }
        .context-menu a {
            padding: 10px 16px;
            text-decoration: none;
            color: #cbd5e1;
            font-size: 0.85rem;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 10px;
            transition: background 0.2s, color 0.2s;
            text-align: left;
        }
        .context-menu a.disabled {
            opacity: 0.5;
            cursor: not-allowed;
            pointer-events: none;
        }
        .context-menu a:hover:not(.disabled) {
            background: rgba(56, 189, 248, 0.1);
            color: var(--accent);
        }
        .context-menu .menu-header {
            padding: 6px 16px;
            font-size: 0.7rem;
            font-weight: 700;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            margin-bottom: 4px;
            text-align: left;
        }

        .loader { display: none; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; }
        .spinner { width: 50px; height: 50px; border: 4px solid rgba(56, 189, 248, 0.1); border-top: 4px solid var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 15px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
    <script>window.inv_data = {};</script>
    <script src="manifest.js"></script>
</head>
<body>
    <div class="sidebar collapsed" id="sidebar">
        <div class="header">
            <div class="header-text">
                <h2>📡 INVENTORY</h2>
                <p>Network Status</p>
            </div>
            <button class="sidebar-close-btn" onclick="toggleSidebar()">✕</button>
        </div>
        <div class="list" id="runList"></div>
    </div>
    
    <div class="main-content">
        <div class="hud-header">
            <div style="display: flex; align-items: center; gap: 15px;">
                <button class="sidebar-toggle-btn" onclick="toggleSidebar()">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
                    HISTORY
                </button>
                <div class="hud-title">
                    <h1 id="dashTitle">📡 Global Inventory</h1>
                    <p id="dashSubTitle">Select a Snapshot from the sidebar</p>
                </div>
            </div>
            <a class="back-portal" href="../index.html">← Network Portal</a>
        </div>

        <div id="welcome">
            <div style="font-size: 4rem; margin-bottom: 20px;">🗄️</div>
            <div style="font-family:'Outfit'; color:var(--accent); font-size:3rem; font-weight:800; margin-bottom:10px;">Select a Snapshot.</div>
            <p style="color:var(--text-dim); font-size: 1.1rem;">Choose a date from the sidebar to view its complete interface inventory and physical topology state.</p>
        </div>

        <div class="loader" id="loader">
            <div class="spinner"></div>
            <p style="color: var(--accent); font-family: 'Outfit'; font-size: 1.2rem;">Loading Dataset...</p>
        </div>

        <div id="dashboardOverlay">

            <div class="metrics-grid">
                <div class="metric-card">
                    <h3>Total Interfaces</h3>
                    <div class="val" id="metTotal">0</div>
                </div>
                <div class="metric-card">
                    <h3>Admin State</h3>
                    <div class="val" style="font-size: 1.2rem;">
                        <span class="up" id="metAdminUp">0</span> UP | 
                        <span class="down" id="metAdminDown">0</span> DOWN
                    </div>
                </div>
                <div class="metric-card">
                    <h3>Oper Protocol</h3>
                    <div class="val" style="font-size: 1.2rem;">
                        <span class="up" id="metOperUp">0</span> UP | 
                        <span class="down" id="metOperDown">0</span> DOWN
                    </div>
                </div>
                <div class="metric-card" style="border: 1px solid rgba(239,68,68,0.5); background: rgba(239,68,68,0.05);">
                    <h3 style="color: var(--danger);">FAULTS (Admin UP / Oper DOWN)</h3>
                    <div class="val down" id="metFaults">0</div>
                </div>
                <div class="metric-card">
                    <h3>Network Devices</h3>
                    <div class="val" id="metDevices">0</div>
                </div>
                <div class="metric-card">
                    <h3>Topology Links</h3>
                    <div class="val" style="color: var(--accent)" id="metLinks">0</div>
                </div>
            </div>

            <div class="controls-bar">
                <div class="tabs">
                    <button class="tab-btn active" onclick="switchTab('interfaces')">📋 Interfaces</button>
                    <button class="tab-btn" onclick="switchTab('connections')">🔌 Topology Links</button>
                </div>
                <div class="filter-box">
                    <div class="status-filter" id="ifaceFilters" style="display: flex; flex-direction: row; gap: 20px; align-items: center; flex-wrap: wrap;">
                        <div style="font-size: 0.8rem; color: var(--text-dim);"><strong>Admin:</strong> 
                            <label style="margin-left: 5px;"><input type="checkbox" id="cbAdminUp" checked onchange="handleSearch()"> UP</label>
                            <label style="margin-left: 5px;"><input type="checkbox" id="cbAdminDown" checked onchange="handleSearch()"> DOWN</label>
                        </div>
                        <div style="font-size: 0.8rem; color: var(--text-dim);"><strong>Oper:</strong> 
                            <label style="margin-left: 5px;"><input type="checkbox" id="cbOperUp" checked onchange="handleSearch()"> UP</label>
                            <label style="margin-left: 5px;"><input type="checkbox" id="cbOperDown" checked onchange="handleSearch()"> DOWN</label>
                        </div>
                    </div>
                    <div class="search-wrapper">
                        <input type="text" id="searchInput" class="input-styled" placeholder="Search device, port, desc..." oninput="handleSearch()" aria-label="Search">
                        <button class="clear-btn" onclick="clearFilters()" title="Clear Filters">✕</button>
                        <div class="help-icon">?
                            <div class="help-tooltip">
                                <strong>Advanced Search Help</strong><br><br>
                                Use <code>;</code> for AND logic.<br>
                                Use <code>|</code> or <code>,</code> for OR logic.<br>
                                Use <code>-</code> or <code>!</code> to exclude (NOT).<br><br>
                                <em>Examples:</em><br>
                                • <code>RT-A | RT-B</code><br>
                                  (Matches RT-A OR RT-B)<br><br>
                                • <code>RT-A ; CONNECTION</code><br>
                                  (Matches rows containing BOTH terms)<br><br>
                                • <code>RT-A | RT-B ; !loopback</code><br>
                                  (Matches RT-A OR RT-B, but EXCLUDES loopbacks)
                            </div>
                        </div>
                        <button class="export-btn" onclick="exportCSV()" title="Export Filtered Data">📥 Export CSV</button>
                    </div>
                </div>
            </div>

            <div class="table-container active" id="tab-interfaces">
                <table>
                    <thead>
                        <tr>
                            <th>Device</th>
                            <th>Interface</th>
                            <th>Admin State</th>
                            <th>Oper Protocol</th>
                            <th>Bandwidth</th>
                            <th>Description</th>
                        </tr>
                    </thead>
                    <tbody id="ifaceBody"></tbody>
                </table>
            </div>

            <div class="table-container" id="tab-connections">
                <table>
                    <thead>
                        <tr>
                            <th>Endpoint A</th>
                            <th>Link Status</th>
                            <th>Endpoint B</th>
                            <th>Capacity Summary</th>
                        </tr>
                    </thead>
                    <tbody id="connBody"></tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        let manifest = window.inv_manifest || [];
        let currentData = null;
        let filteredInterfaces = [];
        let filteredConnections = [];
        let currentTab = 'interfaces';

        function toggleSidebar() { document.getElementById('sidebar').classList.toggle('collapsed'); }

        function formatDate(idStr) {
            if (!idStr || idStr.length !== 15) return idStr;
            const yyyy = idStr.substring(0, 4);
            const MM = idStr.substring(4, 6);
            const dd = idStr.substring(6, 8);
            const hh = idStr.substring(9, 11);
            const mm = idStr.substring(11, 13);
            const ss = idStr.substring(13, 15);
            return `${yyyy}-${MM}-${dd} ${hh}:${mm}:${ss}`;
        }

        function renderList() {
            const list = document.getElementById('runList');
            manifest.sort((a,b) => b.id.localeCompare(a.id));
            
            list.innerHTML = manifest.map(m => `
                <div class="run-item" onclick="selectRun('${m.id}', '${m.file}', this)">
                    <div>
                        <div class="run-date">${formatDate(m.id)}</div>
                        <div class="run-id">${m.id}</div>
                    </div>
                </div>
            `).join('');
        }

        async function selectRun(id, file, el) {
            document.querySelectorAll('.run-item').forEach(it => it.classList.remove('active'));
            if(el) el.classList.add('active');
            
            if(window.innerWidth < 768) toggleSidebar();
            
            document.getElementById('welcome').style.display = 'none';
            document.getElementById('dashboardOverlay').style.display = 'none';
            document.getElementById('loader').style.display = 'block';

            currentData = await loadRunData(id, file);
            if (currentData) currentData.id = id;
            
            document.getElementById('dashTitle').innerText = '📡 Inventory Dashboard';
            document.getElementById('dashSubTitle').innerText = formatDate(id);
            applyFilters();
            
            if(currentTab === 'interfaces') renderInterfaces();
            else renderConnections();

            setTimeout(() => {
                document.getElementById('loader').style.display = 'none';
                document.getElementById('dashboardOverlay').style.display = 'flex';
            }, 200);
        }

        async function loadRunData(id, file) {
            return new Promise((resolve) => {
                if (window.inv_data[id]) return resolve(window.inv_data[id]);
                const s = document.createElement('script');
                s.src = file;
                s.onload = () => resolve(window.inv_data[id]);
                document.head.appendChild(s);
            });
        }

        function applyFilters() {
            if(!currentData) return;
            const q = document.getElementById('searchInput').value.toLowerCase();
            const showAdminUp = document.getElementById('cbAdminUp').checked;
            const showAdminDown = document.getElementById('cbAdminDown').checked;
            const showOperUp = document.getElementById('cbOperUp').checked;
            const showOperDown = document.getElementById('cbOperDown').checked;
            
            filteredInterfaces = (currentData.interfaces || []).filter(i => {
                const admin = String(i.admin_status).toUpperCase();
                const oper = String(i.line_protocol).toUpperCase();
                
                const isAdminUp = admin.includes('UP') && !admin.includes('DOWN');
                const isAdminDown = admin.includes('DOWN') || admin.includes('LOWER');
                
                const isOperUp = oper.includes('UP') && !oper.includes('DOWN');
                const isOperDown = oper.includes('DOWN') || oper.includes('LOWER');
                
                if(isAdminUp && !showAdminUp) return false;
                if(isAdminDown && !showAdminDown) return false;
                if(isOperUp && !showOperUp) return false;
                if(isOperDown && !showOperDown) return false;
                
                if(q) {
                    const str = `${i.element} ${i.interface} ${i.description}`.toLowerCase();
                    if(!matchSearchQueries(str, q)) return false;
                }
                return true;
            });

            filteredConnections = (currentData.connections || []).filter(c => {
                if(q) {
                    const str = `${c.endpoint_a} ${c.endpoint_b} ${c.connection_text}`.toLowerCase();
                    if(!matchSearchQueries(str, q)) return false;
                }
                return true;
            });
            
            updateMetrics();
        }

        function updateMetrics() {
            let adminUp = 0, adminDown = 0;
            let operUp = 0, operDown = 0;
            let faults = 0;
            const devices = new Set();
            
            filteredInterfaces.forEach(i => {
                devices.add(i.element);
                const admin = String(i.admin_status).toUpperCase();
                const oper = String(i.line_protocol).toUpperCase();
                
                const isAdminUp = admin.includes('UP') && !admin.includes('DOWN');
                const isAdminDown = admin.includes('DOWN') || admin.includes('LOWER');
                const isOperUp = oper.includes('UP') && !oper.includes('DOWN');
                const isOperDown = oper.includes('DOWN') || oper.includes('LOWER');
                
                if(isAdminUp) adminUp++;
                if(isAdminDown) adminDown++;
                if(isOperUp) operUp++;
                if(isOperDown) operDown++;
                
                // FAULT: Admin is UP but Oper is DOWN
                if(isAdminUp && isOperDown) faults++;
            });

            document.getElementById('metTotal').innerText = filteredInterfaces.length;
            document.getElementById('metAdminUp').innerText = adminUp;
            document.getElementById('metAdminDown').innerText = adminDown;
            document.getElementById('metOperUp').innerText = operUp;
            document.getElementById('metOperDown').innerText = operDown;
            document.getElementById('metFaults').innerText = faults;
            document.getElementById('metDevices').innerText = devices.size;
            document.getElementById('metLinks').innerText = filteredConnections.length;
        }

        function switchTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.table-container').forEach(t => t.classList.remove('active'));
            
            document.querySelector(`.tab-btn[onclick="switchTab('${tab}')"]`).classList.add('active');
            document.getElementById(`tab-${tab}`).classList.add('active');
            
            document.getElementById('ifaceFilters').style.display = tab === 'interfaces' ? 'flex' : 'none';
            
            if(tab === 'interfaces') renderInterfaces();
            else renderConnections();
        }

        function handleSearch() {
            applyFilters();
            if(currentTab === 'interfaces') renderInterfaces();
            else renderConnections();
        }

        function clearFilters() {
            document.getElementById('searchInput').value = '';
            document.getElementById('cbAdminUp').checked = true;
            document.getElementById('cbAdminDown').checked = true;
            document.getElementById('cbOperUp').checked = true;
            document.getElementById('cbOperDown').checked = true;
            handleSearch();
        }

        function exportCSV() {
            if(!currentData) return;
            let csvContent = "\\uFEFF"; // BOM for Excel
            let filename = "inventory_export.csv";
            
            if (currentTab === 'interfaces') {
                filename = "inventory_interfaces.csv";
                csvContent += "Device,Interface,Admin State,Oper Protocol,Bandwidth,Description\\n";
                filteredInterfaces.forEach(i => {
                    let desc = i.description || "";
                    desc = desc.replace(/"/g, '""');
                    csvContent += `"${i.element}","${i.interface}","${i.admin_status}","${i.line_protocol}","${formatBw(i.bandwidth_kbit)}","${desc}"\\n`;
                });
            } else {
                filename = "inventory_connections.csv";
                csvContent += "Endpoint A,Status,Endpoint B,Capacity Summary\\n";
                filteredConnections.forEach(c => {
                    let text = c.connection_text || "";
                    text = text.replace(/"/g, '""');
                    let status = c.dashed == "1" ? "DOWN" : "UP";
                    csvContent += `"${c.endpoint_a}","${status}","${c.endpoint_b}","${text}"\\n`;
                });
            }
            
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement("a");
            if (link.download !== undefined) {
                const url = URL.createObjectURL(blob);
                link.setAttribute("href", url);
                link.setAttribute("download", filename);
                link.style.visibility = 'hidden';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }
        }

        function matchSearchQueries(text, queryStr) {
            if(!queryStr) return true;
            
            // Split by ; (AND logic)
            const andTokens = queryStr.split(/[;]+/).map(t => t.trim()).filter(t => t);
            if(andTokens.length === 0) return true;
            
            for(const token of andTokens) {
                const isExclude = token.startsWith('!') || token.startsWith('-');
                
                if (isExclude) {
                    const cleanToken = token.substring(1).trim();
                    if(!cleanToken) continue;
                    if(text.includes(cleanToken)) return false; // Fail because it contains excluded term
                } else {
                    // OR logic: split by | or ,
                    const orTokens = token.split(/[|,]+/).map(t => t.trim()).filter(t => t);
                    if(orTokens.length === 0) continue;
                    
                    let matchedOr = false;
                    for(const oToken of orTokens) {
                        if(text.includes(oToken)) {
                            matchedOr = true;
                            break;
                        }
                    }
                    if(!matchedOr) return false; // Fail because none of the OR conditions matched
                }
            }
            return true;
        }

        function formatBw(kbit) {
            try {
                let bw = parseInt(kbit);
                if(isNaN(bw)) return kbit;
                if(bw >= 100000000) return (bw/100000000*100) + 'G';
                if(bw >= 1000000) return (bw/1000000) + 'G';
                if(bw >= 1000) return (bw/1000) + 'M';
                return bw + 'K';
            } catch(e) { return kbit; }
        }

        function renderInterfaces() {
            if(!currentData) return;
            const html = filteredInterfaces.map(i => {
                const proto = String(i.line_protocol).toUpperCase();
                let statusTag = `<span class="tag tag-up">${i.line_protocol}</span>`;
                if(proto.includes('DOWN') || proto.includes('LOWER')) statusTag = `<span class="tag tag-down">${i.line_protocol}</span>`;
                
                const adminProto = String(i.admin_status).toUpperCase();
                let adminTag = adminProto;
                if(adminProto.includes('DOWN')) adminTag = `<span style="color:var(--danger)">${i.admin_status}</span>`;
                
                return `<tr style="cursor: pointer;" onclick="showInterfaceContextMenu(event, '${i.element}', '${i.interface}')">
                    <td style="font-weight:700; color:var(--accent)">${i.element}</td>
                    <td style="font-family:monospace; font-size:0.9rem;">${i.interface}</td>
                    <td>${adminTag}</td>
                    <td>${statusTag}</td>
                    <td><span class="tag tag-bw">${formatBw(i.bandwidth_kbit)}</span></td>
                    <td title="${i.description}">${i.description || '-'}</td>
                </tr>`;
            }).join('');
            
            document.getElementById('ifaceBody').innerHTML = html || `<tr><td colspan="6" style="text-align:center; padding:40px;">No interfaces match the filters.</td></tr>`;
        }

        function renderConnections() {
            if(!currentData) return;
            const html = filteredConnections.map(c => {
                const isDown = c.dashed == "1";
                const rowClass = isDown ? "conn-dashed" : "";
                
                return `<tr class="conn-row ${rowClass}" style="cursor: pointer;" onclick="showContextMenu(event, '${c.endpoint_a}', '${c.endpoint_b}')">
                    <td style="text-align:right;"><span class="conn-node">${c.endpoint_a}</span></td>
                    <td style="text-align:center;"><span class="conn-arrow">⟷</span></td>
                    <td><span class="conn-node">${c.endpoint_b}</span></td>
                    <td><span style="color:var(--accent); font-weight:600; font-family:monospace;">${c.connection_text}</span></td>
                </tr>`;
            }).join('');
            
            document.getElementById('connBody').innerHTML = html || `<tr><td colspan="4" style="text-align:center; padding:40px;">No connections match the search.</td></tr>`;
        }

        let hasDiff = false;
        async function checkDiffAvailability() {
            try {
                const response = await fetch('../diff/index.html', { method: 'HEAD' });
                hasDiff = response.ok || response.status === 0;
            } catch (e) {
                hasDiff = false;
            }
        }

        function showContextMenu(e, nodeA, nodeB) {
            e.preventDefault();
            e.stopPropagation();
            
            let menu = document.getElementById('connContextMenu');
            if (!menu) {
                menu = document.createElement('div');
                menu.id = 'connContextMenu';
                menu.className = 'context-menu';
                document.body.appendChild(menu);
            }
            
            const runId = currentData ? currentData.id : '';
            
            menu.innerHTML = `
                <div class="menu-header">${nodeA} ⟷ ${nodeB}</div>
                <a href="../ping-matrix/index.html?run=${runId}&origin=${nodeA}&dest=${nodeB}" target="_blank">⚡ Snapshots & Heatmaps</a>
                <a href="../ping-matrix/history.html?origin=${nodeA}&dest=${nodeB}" target="_blank">📈 P2P History & SLA</a>
                <a href="../ping-matrix/path.html?run=${runId}&origin=${nodeA}&dest=${nodeB}" target="_blank">🕸️ Route Analysis (Dijkstra)</a>
                <a href="../topology/index.html?run=${runId}&focus=${nodeA}" target="_blank">🕸️ Network Topology</a>
                ${hasDiff ? `
                    <a href="../diff/index.html?device=${nodeA}" target="_blank">⚖️ Drift Analysis (${nodeA})</a>
                    <a href="../diff/index.html?device=${nodeB}" target="_blank">⚖️ Drift Analysis (${nodeB})</a>
                ` : `
                    <a href="#" class="disabled" style="opacity:0.5; cursor:not-allowed; pointer-events:none;" onclick="return false;">⚖️ Drift Analysis (Unavailable)</a>
                `}
            `;
            
            menu.style.display = 'flex';
            
            const menuWidth = menu.offsetWidth || 200;
            const menuHeight = menu.offsetHeight || 250;
            
            let x = e.pageX;
            let y = e.pageY;
            
            if (x + menuWidth > window.innerWidth) {
                x = window.innerWidth - menuWidth - 10;
            }
            if (y + menuHeight > window.innerHeight + window.scrollY) {
                y = window.innerHeight + window.scrollY - menuHeight - 10;
            }
            
            menu.style.left = x + 'px';
            menu.style.top = y + 'px';
        }

        function showInterfaceContextMenu(e, device, iface) {
            e.preventDefault();
            e.stopPropagation();
            
            let menu = document.getElementById('connContextMenu');
            if (!menu) {
                menu = document.createElement('div');
                menu.id = 'connContextMenu';
                menu.className = 'context-menu';
                document.body.appendChild(menu);
            }
            
            const runId = currentData ? currentData.id : '';
            
            menu.innerHTML = `
                <div class="menu-header">${device} ➔ ${iface}</div>
                <a href="../ping-matrix/index.html?run=${runId}&origin=${device}" target="_blank">⚡ Snapshots & Heatmaps</a>
                <a href="../ping-matrix/history.html?origin=${device}" target="_blank">📈 P2P History & SLA</a>
                <a href="../ping-matrix/path.html?run=${runId}&origin=${device}" target="_blank">🕸️ Route Analysis (Dijkstra)</a>
                <a href="../topology/index.html?run=${runId}&focus=${device}" target="_blank">🕸️ Network Topology</a>
                ${hasDiff ? `
                    <a href="../diff/index.html?device=${device}&interface=${iface}" target="_blank">⏱️ Drift Timeline Tracker</a>
                    <a href="../diff/index.html?device=${device}" target="_blank">⚖️ Drift Analysis (${device})</a>
                ` : `
                    <a href="#" class="disabled" style="opacity:0.5; cursor:not-allowed; pointer-events:none;" onclick="return false;">⚖️ Drift Analysis (Unavailable)</a>
                `}
            `;
            
            menu.style.display = 'flex';
            
            const menuWidth = menu.offsetWidth || 200;
            const menuHeight = menu.offsetHeight || 250;
            
            let x = e.pageX;
            let y = e.pageY;
            
            if (x + menuWidth > window.innerWidth) {
                x = window.innerWidth - menuWidth - 10;
            }
            if (y + menuHeight > window.innerHeight + window.scrollY) {
                y = window.innerHeight + window.scrollY - menuHeight - 10;
            }
            
            menu.style.left = x + 'px';
            menu.style.top = y + 'px';
        }

        document.addEventListener('click', () => {
            const menu = document.getElementById('connContextMenu');
            if (menu) menu.style.display = 'none';
        });

        window.addEventListener('DOMContentLoaded', () => {
            renderList();
            checkDiffAvailability();
            
            // Check for device parameter in URL search query
            const urlParams = new URLSearchParams(window.location.search);
            const device = urlParams.get('device') || urlParams.get('element');
            if (device) {
                document.getElementById('searchInput').value = device;
            }
            
            if(manifest.length > 0 && window.innerWidth >= 768) {
                // Auto select newest
                document.querySelector('.run-item').click();
            } else if (window.innerWidth < 768) {
                document.getElementById('sidebar').classList.remove('collapsed');
            }
        });
    </script>
</body>
</html>
"""
        with open(os.path.join(self.inventory_dir, "index.html"), 'w', encoding='utf-8') as f:
            f.write(template)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate Network Inventory Dashboard")
    parser.add_argument("--infos_dir", default="infos", help="Base directory for collections")
    args = parser.parse_args()
    
    engine = InventoryEngine(args.infos_dir)
    engine.run()
