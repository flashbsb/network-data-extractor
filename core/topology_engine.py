#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
             NETWORK TOPOLOGY WORKSPACE ENGINE              
============================================================
 Creates and maintains the topology workspace, manifest, and
 the interactive Draw.io index.html portal.
"""

import os
import json
from glob import glob
from core.theme_system import THEME_HEAD_INIT, THEME_CSS, THEME_SWITCHER_HTML, THEME_SCRIPT_JS

class TopologyEngine:
    def __init__(self, base_path):
        self.base_path = os.path.abspath(base_path)
        self.topology_dir = os.path.join(self.base_path, "topology")
        self.runs_dir = os.path.join(self.base_path, "runs")
        
        # ANSI Colors
        self.C_CYAN = '\033[96m'
        self.C_GREEN = '\033[92m'
        self.C_YELLOW = '\033[93m'
        self.C_RED = '\033[91m'
        self.C_RESET = '\033[0m'

    def run(self, force_rebuild: bool = False):
        print(f"[*] Analyzing topology base: {self.topology_dir}")
        self._ensure_dirs()
        
        # 1. Generate Native Topology Payloads & Unified Manifest
        try:
            from core.topology_data_engine import TopologyDataEngine
            data_engine = TopologyDataEngine(self.base_path)
            manifest = data_engine.build_all_runs(force_rebuild=force_rebuild)
        except Exception as e:
            print(f"{self.C_YELLOW}[!] Warning running TopologyDataEngine: {e}{self.C_RESET}")
            manifest = []

        if manifest:
            self._update_dashboard()
            print(f"\n{self.C_GREEN}[+] Topology Dashboard ready!{self.C_RESET}")
            print(f"[*] Workspace: {self.topology_dir}")
            print(f"[*] Open: {os.path.join(self.topology_dir, 'index.html')}")
            return

        # Build manifest fallback (legacy Draw.io only)
        runs = self._scan_runs()
        manifest = []
        for run_id in runs:
            run_path = os.path.join(self.runs_dir, run_id, "topology")
            if not os.path.exists(run_path):
                run_path = os.path.join(self.topology_dir, run_id)
                
            drawio_files = sorted(glob(os.path.join(run_path, "*.drawio")))
            
            files_meta = []
            for f_path in drawio_files:
                filename = os.path.basename(f_path)
                
                # Categorize type (Summary vs Detailed)
                if ".connections.SUM" in filename:
                    topo_type = "summary"
                    type_label = "Summary"
                else:
                    topo_type = "detailed"
                    type_label = "Detailed"
                
                # Determine Layout
                layout = "other"
                layout_label = "Custom"
                if "circular" in filename:
                    layout = "circular"
                    layout_label = "Circular"
                elif "geografico" in filename or "geographic" in filename:
                    layout = "geographic"
                    layout_label = "Geographic"
                elif "organico" in filename or "organic" in filename:
                    layout = "organic"
                    layout_label = "Organic"
                elif "hierarquico" in filename or "hierarchical" in filename:
                    layout = "hierarchical"
                    layout_label = "Hierarchical"
                
                if "runs" in run_path:
                    rel_path = f"../runs/{run_id}/topology/{filename}"
                else:
                    rel_path = f"{run_id}/{filename}"
                    
                files_meta.append({
                    "filename": filename,
                    "type": topo_type,
                    "type_label": type_label,
                    "layout": layout,
                    "layout_label": layout_label,
                    "path": rel_path
                })
                
            if files_meta:
                # Derive display date from folder name YYYYMMDD_HHMMSS
                try:
                    dt_label = f"{run_id[:4]}-{run_id[4:6]}-{run_id[6:8]} {run_id[9:11]}:{run_id[11:13]}:{run_id[13:15]}"
                except (IndexError, ValueError):
                    dt_label = run_id

                manifest.append({
                    "id": run_id,
                    "date": dt_label,
                    "files": files_meta
                })
        
        # Sort manifest by id descending (newest first)
        manifest.sort(key=lambda x: x["id"], reverse=True)
        
        self._write_manifest(manifest)
        self._update_dashboard()
        
        print(f"\n{self.C_GREEN}[+] Topology Dashboard ready!{self.C_RESET}")
        print(f"[*] Workspace: {self.topology_dir}")
        print(f"[*] Open: {os.path.join(self.topology_dir, 'index.html')}")

    def _ensure_dirs(self):
        if not os.path.exists(self.topology_dir):
            os.makedirs(self.topology_dir, exist_ok=True)

    def _scan_runs(self):
        # Scan in self.runs_dir first, then self.topology_dir for backward compatibility
        run_ids = set()
        if os.path.exists(self.runs_dir):
            for d in glob(os.path.join(self.runs_dir, "20*_*")):
                if os.path.isdir(d):
                    run_ids.add(os.path.basename(d))
        if os.path.exists(self.topology_dir):
            for d in glob(os.path.join(self.topology_dir, "20*_*")):
                if os.path.isdir(d):
                    run_ids.add(os.path.basename(d))
        return sorted(list(run_ids), reverse=True)

    def _write_manifest(self, manifest):
        manifest_js = f"window.topo_manifest = {json.dumps(manifest, indent=4)};"
        manifest_path = os.path.join(self.topology_dir, "manifest.js")
        with open(manifest_path, 'w', encoding='utf-8') as f:
            f.write(manifest_js)

    def _update_dashboard(self):
        # Ensure native topology icons and graph scripts are generated
        try:
            from core.topology_icons import TopologyIconsEngine
            TopologyIconsEngine(self.base_path).ensure_theme_icons_js()
        except Exception as e:
            print(f"{self.C_YELLOW}[!] Warning ensuring topology icons: {e}{self.C_RESET}")
            
        try:
            from core.topology_graph import TopologyGraphEngine
            TopologyGraphEngine(self.base_path).ensure_graph_js()
        except Exception as e:
            print(f"{self.C_YELLOW}[!] Warning ensuring topology graph: {e}{self.C_RESET}")

        # Check and download local viewer-static.min.js if not present
        viewer_js_path = os.path.join(self.topology_dir, "viewer-static.min.js")
        if not os.path.exists(viewer_js_path):
            print("[*] Local viewer-static.min.js not found. Downloading...")
            try:
                import urllib.request
                url = "https://viewer.diagrams.net/js/viewer-static.min.js"
                req = urllib.request.Request(
                    url, 
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )
                with urllib.request.urlopen(req, timeout=15) as response:
                    with open(viewer_js_path, 'wb') as out_file:
                        out_file.write(response.read())
                print(f"[+] Local viewer-static.min.js saved successfully to {viewer_js_path}")
            except Exception as e:
                print(f"{self.C_RED}[!] Failed to download offline Draw.io viewer: {e}{self.C_RESET}")
                print(f"{self.C_YELLOW}[!] Please download 'https://viewer.diagrams.net/js/viewer-static.min.js' manually and place it in '{self.topology_dir}' to enable offline visualization.{self.C_RESET}")

        html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="description" content="Network Topology Interactive Visualizer">
    <meta property="og:title" content="Network Topology Dashboard">
    <title>Network Topology Portal</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@600;700;800&display=swap" rel="stylesheet">
<!-- THEME_HEAD_INIT -->
    <style>
/* THEME_CSS */
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-dark); color: var(--text); display: flex; height: 100vh; overflow: hidden; width: 100vw; max-width: 100%; }

        /* Sidebar Styles */
        .sidebar { width: 300px; background-color: var(--sidebar-bg); border-right: 1px solid var(--border); display: flex; flex-direction: column; z-index: 100; box-shadow: 10px 0 30px rgba(0,0,0,0.5); transition: margin-left 0.3s ease; flex-shrink: 0; }
        .sidebar.collapsed { margin-left: -300px; }
        .sidebar .header { padding: 24px 20px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; background: radial-gradient(circle at top left, rgba(6,182,212,0.1), transparent); }
        .sidebar .header-text h2 { font-family: 'Outfit'; font-size: 1.3rem; color: var(--accent); letter-spacing: 0.5px; }
        .sidebar .header-text p { font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; margin-top: 4px; }
        .sidebar-close-btn { background: none; border: none; color: var(--text-dim); cursor: pointer; font-size: 1.2rem; }
        .sidebar-close-btn:hover { color: var(--text); }
        .sidebar .list { flex: 1; overflow-y: auto; padding: 16px; scrollbar-width: thin; scrollbar-color: var(--border) transparent; }

        .run-item { padding: 14px; border-radius: 6px; margin-bottom: 8px; cursor: pointer; transition: all 0.2s; border: 1px solid transparent; display: flex; flex-direction: column; background: rgba(30, 41, 59, 0.3); }
        .run-item:hover { background-color: rgba(30, 41, 59, 0.8); border-color: rgba(6, 182, 212, 0.3); transform: translateX(4px); }
        .run-item.active { background-color: rgba(6, 182, 212, 0.15); border-color: var(--accent); box-shadow: inset 4px 0 0 var(--accent); }
        .run-date { font-weight: 600; font-size: 0.9rem; color: var(--text); }
        .run-id { font-size: 0.7rem; color: var(--text-dim); font-family: monospace; margin-top: 2px; }
        .run-badges { display: flex; gap: 6px; margin-top: 6px; }
        .run-badge { font-size: 0.65rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; }
        .badge-native { background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); }
        .badge-drawio { background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); }

        /* Main Content */
        .main-content { flex: 1; min-width: 0; display: flex; flex-direction: column; position: relative; background: var(--bg-dark); overflow: hidden; }
        
        .hud-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding: 12px 20px;
            background: var(--glass);
            backdrop-filter: blur(10px);
            position: relative;
            z-index: 300;
            width: 100%;
        }
        .hud-title h1 {
            font-size: 1.35rem;
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
        .sidebar-toggle-btn { background: var(--card-bg); color: var(--text); border: 1px solid var(--border); padding: 7px 12px; border-radius: 6px; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 8px; transition: all 0.2s; font-size: 0.85rem; }
        .sidebar-toggle-btn:hover { border-color: var(--accent); color: var(--accent); }
        .back-portal {
            background: var(--card-bg);
            color: var(--accent);
            border: 1px solid var(--border);
            padding: 7px 12px;
            border-radius: 6px;
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
            color: var(--text);
            background: rgba(6, 182, 212, 0.15);
            box-shadow: 0 0 10px rgba(6, 182, 212, 0.2);
        }

        /* Hybrid Mode Switcher in Header */
        .mode-tabs { display: flex; gap: 6px; background: rgba(15, 23, 42, 0.6); padding: 3px; border-radius: 8px; border: 1px solid var(--border); }
        .mode-tab-btn { background: transparent; border: none; color: var(--text-dim); padding: 6px 14px; border-radius: 6px; font-weight: 600; font-size: 0.8rem; cursor: pointer; transition: all 0.2s; display: inline-flex; align-items: center; gap: 6px; }
        .mode-tab-btn:hover:not(.active) { color: var(--text); }
        .mode-tab-btn.active { background: var(--accent); color: var(--bg-dark); font-weight: 700; box-shadow: 0 0 10px rgba(56, 189, 248, 0.3); }

        #welcome { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 40px; }
        #welcome .icon { font-size: 4rem; margin-bottom: 20px; }
        #welcome h2 { font-family: 'Outfit'; color: var(--accent); font-size: 3rem; font-weight: 800; margin-bottom: 10px; }
        #welcome p { color: var(--text-dim); font-size: 1.1rem; }

        #dashboardOverlay { display: none; flex-direction: column; flex: 1; padding: 15px 20px; overflow: hidden; min-height: 0; position: relative; }
        
        /* Native Topology Controls Bar */
        .native-controls-bar {
            display: flex;
            flex-direction: column;
            gap: 10px;
            background: var(--card-bg);
            border: 1px solid var(--border);
            padding: 10px 16px;
            border-radius: 8px;
            margin-bottom: 10px;
            backdrop-filter: blur(10px);
        }
        .controls-row-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
        }
        .controls-row-bottom {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
            border-top: 1px solid var(--border-light);
            padding-top: 8px;
        }

        /* Tier Pills Filter */
        .tier-pills-group { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
        .filter-label { font-size: 0.75rem; font-weight: 700; color: var(--text-dim); text-transform: uppercase; margin-right: 4px; }
        .tier-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            cursor: pointer;
            border: 1px solid var(--border);
            background: rgba(15, 23, 42, 0.4);
            color: var(--text);
            transition: all 0.2s;
            user-select: none;
        }
        .tier-pill:hover { border-color: var(--accent); }
        .tier-pill.active { border-color: var(--pill-color, var(--accent)); background: var(--pill-bg, rgba(56, 189, 248, 0.15)); }
        .tier-pill.inactive { opacity: 0.4; text-decoration: line-through; }
        .tier-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; background-color: var(--pill-color, #38bdf8); }
        .tier-count { font-size: 0.7rem; opacity: 0.8; font-family: monospace; }

        /* Search input & Match HUD */
        .search-container { display: flex; align-items: center; background: var(--sidebar-bg); border: 1px solid var(--border); border-radius: 6px; padding: 4px 10px; min-width: 280px; }
        .search-container input { background: transparent; border: none; outline: none; color: var(--text); font-size: 0.82rem; width: 100%; font-family: monospace; }
        .search-container .clear-btn { background: none; border: none; color: var(--text-dim); cursor: pointer; font-size: 0.8rem; margin-left: 6px; }
        .search-container:focus-within { border-color: var(--accent); box-shadow: 0 0 8px rgba(56, 189, 248, 0.25); }
        .match-hud-pill {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid rgba(56, 189, 248, 0.35);
            border-radius: 4px;
            padding: 2px 6px;
            margin-left: 6px;
            white-space: nowrap;
        }
        #topoMatchCount {
            font-size: 0.72rem;
            font-weight: 700;
            color: #38bdf8;
            font-family: monospace;
        }
        .hud-cycle-btn {
            background: rgba(56, 189, 248, 0.15);
            border: 1px solid rgba(56, 189, 248, 0.3);
            color: #38bdf8;
            border-radius: 3px;
            font-size: 0.68rem;
            padding: 1px 5px;
            cursor: pointer;
            transition: all 0.15s;
        }
        .hud-cycle-btn:hover {
            background: #38bdf8;
            color: #0f172a;
        }

        /* Button Groups */
        .btn-group { display: flex; gap: 6px; align-items: center; }
        .action-btn {
            background: var(--card-bg);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 5px 10px;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }
        .action-btn:hover { border-color: var(--accent); color: var(--accent); }
        .action-btn.active { background: var(--accent); color: var(--bg-dark); font-weight: 700; border-color: var(--accent); }
        .action-btn.frozen { background: rgba(239, 68, 68, 0.2); border-color: #ef4444; color: #f87171; }

        /* Phase 4: Drift Toolbar & Badges */
        .drift-toolbar {
            display: none;
            align-items: center;
            justify-content: space-between;
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 8px 16px;
            margin-bottom: 10px;
            gap: 12px;
            flex-wrap: wrap;
            backdrop-filter: blur(10px);
        }
        .drift-selector-group { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .drift-select { background: var(--sidebar-bg); border: 1px solid var(--border); color: var(--text); padding: 5px 10px; border-radius: 6px; font-size: 0.8rem; font-family: monospace; outline: none; }
        .drift-select:focus { border-color: var(--accent); }
        .drift-pills { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .drift-pill { font-size: 0.75rem; font-weight: 700; padding: 3px 8px; border-radius: 4px; display: inline-flex; align-items: center; gap: 4px; font-family: monospace; }
        .drift-pill-added { background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); color: #10b981; }
        .drift-pill-removed { background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.4); color: #f87171; }
        .drift-pill-stable { background: rgba(148, 163, 184, 0.15); border: 1px solid rgba(148, 163, 184, 0.3); color: #94a3b8; }

        /* Phase 4 & 5: Path Tracing Toolbar, Summary Card & Context Menu */
        .trace-toolbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(15, 23, 42, 0.75);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 8px 16px;
            margin-bottom: 10px;
            gap: 12px;
            flex-wrap: wrap;
            backdrop-filter: blur(10px);
        }
        .trace-group { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
        .trace-input {
            background: var(--sidebar-bg);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 5px 10px;
            border-radius: 6px;
            font-size: 0.8rem;
            font-family: monospace;
            outline: none;
            width: 170px;
            transition: border-color 0.2s;
        }
        .trace-input:focus { border-color: var(--accent); }
        .trace-input::placeholder { color: var(--text-dim); }

        .path-summary-card {
            position: absolute;
            top: 14px;
            right: 14px;
            z-index: 150;
            background: rgba(15, 23, 42, 0.90);
            border: 1px solid rgba(56, 189, 248, 0.35);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6);
            border-radius: 8px;
            padding: 12px 16px;
            min-width: 280px;
            backdrop-filter: blur(12px);
            pointer-events: auto;
        }
        .path-summary-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 6px;
        }
        .path-summary-title {
            font-family: 'Outfit', sans-serif;
            font-size: 0.88rem;
            font-weight: 700;
            color: var(--accent);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .path-summary-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            font-family: monospace;
        }
        .path-stat-box {
            background: rgba(30, 41, 59, 0.5);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 6px 8px;
            text-align: center;
        }
        .path-stat-val { font-size: 0.95rem; font-weight: 700; color: #38bdf8; }
        .path-stat-lbl { font-size: 0.62rem; color: var(--text-dim); text-transform: uppercase; margin-top: 2px; }

        /* Phase 4: Node Quick Summary Mini-Card */
        .node-quick-summary-card {
            position: absolute;
            bottom: 20px;
            right: 20px;
            z-index: 140;
            background: rgba(15, 23, 42, 0.94);
            border: 1px solid rgba(56, 189, 248, 0.35);
            box-shadow: 0 12px 36px rgba(0, 0, 0, 0.65), 0 0 24px rgba(56, 189, 248, 0.12);
            border-radius: 10px;
            padding: 14px 18px;
            width: 320px;
            backdrop-filter: blur(14px);
            pointer-events: auto;
            animation: fadeInCard 0.2s ease-out;
        }
        @keyframes fadeInCard {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .context-menu {
            position: fixed;
            z-index: 500;
            background: var(--sidebar-bg);
            border: 1px solid var(--border);
            border-radius: 6px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.65);
            padding: 6px 0;
            min-width: 195px;
            font-size: 0.8rem;
            backdrop-filter: blur(10px);
        }
        .context-menu-title {
            padding: 6px 14px 4px 14px;
            font-size: 0.7rem;
            color: var(--accent);
            font-weight: 700;
            font-family: monospace;
            border-bottom: 1px solid var(--border);
            margin-bottom: 4px;
        }
        .context-menu-item {
            padding: 7px 14px;
            cursor: pointer;
            color: var(--text);
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.15s;
        }
        .context-menu-item:hover {
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
        }
        .context-menu-divider {
            height: 1px;
            background: var(--border);
            margin: 4px 0;
        }

        /* Graph Canvas Wrapper */
        .graph-wrapper { flex: 1; border: 1px solid var(--border); border-radius: 8px; background: var(--card-bg); overflow: hidden; position: relative; display: flex; min-height: 0; }
        #nativeGraphContainer { width: 100%; height: 100%; position: relative; }

        /* Telemetry Sliding Drawer */
        .node-drawer {
            position: absolute;
            top: 0;
            right: 0;
            width: 380px;
            height: 100%;
            background: var(--sidebar-bg);
            border-left: 1px solid var(--border);
            z-index: 200;
            box-shadow: -5px 0 25px rgba(0,0,0,0.5);
            display: flex;
            flex-direction: column;
            transform: translateX(100%);
            transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .node-drawer.open { transform: translateX(0); }
        .drawer-header { padding: 16px 20px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; background: radial-gradient(circle at top right, rgba(56, 189, 248, 0.1), transparent); }
        .drawer-title { font-family: 'Outfit'; font-size: 1.1rem; color: var(--accent); font-weight: 700; word-break: break-all; }
        .drawer-close { background: none; border: none; color: var(--text-dim); cursor: pointer; font-size: 1.2rem; }
        .drawer-close:hover { color: var(--text); }
        .drawer-body { flex: 1; overflow-y: auto; padding: 16px 20px; font-size: 0.85rem; }
        .drawer-badges { display: flex; gap: 8px; margin-top: 6px; }
        .drawer-metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 14px 0; }
        .drawer-metric-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 6px; padding: 10px; text-align: center; }
        .drawer-metric-val { font-size: 1.1rem; font-weight: 700; color: var(--text); font-family: monospace; }
        .drawer-metric-lbl { font-size: 0.65rem; color: var(--text-dim); text-transform: uppercase; margin-top: 2px; }
        
        .neighbor-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.75rem; }
        .neighbor-table th { text-align: left; padding: 6px; border-bottom: 1px solid var(--border); color: var(--text-dim); text-transform: uppercase; }
        .neighbor-table td { padding: 6px; border-bottom: 1px solid rgba(255,255,255,0.05); font-family: monospace; word-break: break-all; }
        .neighbor-table tr:hover td { background: rgba(56, 189, 248, 0.08); cursor: pointer; }

        /* Legacy Draw.io Section */
        #drawioView { display: none; flex-direction: column; flex: 1; min-height: 0; }
        .topo-controls { display: flex; justify-content: space-between; align-items: center; background: var(--card-bg); border: 1px solid var(--border); padding: 10px 16px; border-radius: 8px; margin-bottom: 10px; flex-wrap: wrap; gap: 10px; }
        .topo-tabs { display: flex; gap: 8px; }
        .tab-btn { background: var(--card-bg); border: 1px solid var(--border); color: var(--text-dim); padding: 6px 14px; border-radius: 6px; font-weight: 600; cursor: pointer; transition: all 0.2s; font-size: 0.8rem; }
        .tab-btn.active { background: rgba(6, 182, 212, 0.15); border-color: var(--accent); color: var(--accent); }
        .layout-options { display: flex; gap: 6px; align-items: center; }
        .layout-btn { background: var(--card-bg); border: 1px solid var(--border); color: var(--text-dim); padding: 6px 12px; border-radius: 6px; font-size: 0.78rem; font-weight: 600; cursor: pointer; transition: all 0.2s; }
        .layout-btn.active { background: var(--accent); color: var(--bg-dark); font-weight: 700; border-color: var(--accent); }
        .viewer-container { flex: 1; border: 1px solid var(--border); border-radius: 8px; background: var(--card-bg); overflow: hidden; position: relative; display: flex; flex-direction: column; }
        iframe#drawio-viewer { width: 100%; height: 100%; border: none; background: #ffffff; overflow: hidden; }

        /* Theater Mode */
        body.theater-mode .sidebar { display: none !important; }
        body.theater-mode .hud-header { display: none !important; }
        body.theater-mode #dashboardOverlay { padding: 0 !important; margin: 0 !important; position: fixed !important; top: 0 !important; left: 0 !important; width: 100vw !important; height: 100vh !important; z-index: 99999 !important; background: var(--bg-dark); }
        body.theater-mode .native-controls-bar { position: absolute; top: 12px; left: 12px; z-index: 1000; max-width: calc(100% - 24px); box-shadow: 0 4px 25px rgba(0,0,0,0.7); }

        /* Loader & Tooltip */
        .loader-overlay { display: none; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(2, 6, 23, 0.85); z-index: 50; flex-direction: column; align-items: center; justify-content: center; backdrop-filter: blur(3px); }
        .spinner { width: 44px; height: 44px; border: 4px solid rgba(56, 189, 248, 0.15); border-top: 4px solid var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; margin-bottom: 12px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

        .topo-tooltip {
            position: fixed;
            z-index: 10000;
            background: rgba(15, 23, 42, 0.95);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 8px 12px;
            pointer-events: none;
            font-size: 0.8rem;
            backdrop-filter: blur(8px);
            box-shadow: 0 4px 20px rgba(0,0,0,0.6);
            display: none;
        }
        .tooltip-title { font-weight: 700; color: var(--text); margin-bottom: 4px; font-family: monospace; }
        .tooltip-meta { display: flex; gap: 6px; align-items: center; margin-bottom: 4px; }
        .tooltip-badge { font-size: 0.65rem; padding: 2px 6px; border-radius: 4px; font-weight: 700; text-transform: uppercase; background: rgba(56, 189, 248, 0.2); color: #38bdf8; }
        .tooltip-site { font-size: 0.7rem; color: var(--text-dim); }
        .tooltip-stats { font-size: 0.75rem; color: var(--text); font-family: monospace; }

        .offline-fallback { display: none; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 40px; height: 100%; background: var(--card-bg); z-index: 10; overflow-y: auto; }
        .offline-fallback h3 { font-family: 'Outfit'; font-size: 1.6rem; color: #f59e0b; margin-bottom: 15px; }
        .offline-fallback p { max-width: 600px; color: var(--text-dim); line-height: 1.6; margin-bottom: 25px; font-size: 0.95rem; }
        .btn-group-download { display: flex; gap: 15px; justify-content: center; flex-wrap: wrap; margin-top: 15px; }
        .btn-action { text-decoration: none; padding: 10px 20px; border-radius: 6px; font-weight: 700; font-size: 0.85rem; text-transform: uppercase; cursor: pointer; transition: all 0.2s; display: inline-flex; align-items: center; gap: 8px; }
        .btn-primary { background: var(--accent); color: var(--bg-dark); border: 1px solid var(--accent); }
        .btn-secondary { background: transparent; border: 1px solid var(--border); color: var(--text); }
        .btn-header-link { background: rgba(6, 182, 212, 0.1); border: 1px solid rgba(6, 182, 212, 0.3); color: var(--accent); text-decoration: none; padding: 6px 12px; border-radius: 6px; font-weight: 700; font-size: 0.75rem; transition: all 0.2s; text-transform: uppercase; }
        .btn-header-link:hover { background: var(--accent); color: var(--bg-dark); }
    </style>
    <script>
        window.topo_manifest = [];
        window.topology_data = window.topology_data || {};
        document.write('<script src="manifest.js?v=' + Date.now() + '"></' + 'script>');
    </script>
    <script src="topology_theme_icons.js"></script>
    <script src="topology_graph.js"></script>
</head>
<body>
    <div class="sidebar" id="sidebar">
        <div class="header">
            <div class="header-text">
                <h2>🕸️ TOPOLOGY</h2>
                <p>Network Mapping</p>
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
                    <h1 id="dashTitle">🕸️ Network Topology</h1>
                    <p id="dashSubTitle">Select a collection from the sidebar</p>
                </div>
            </div>
            
            <div style="display: flex; align-items: center; gap: 12px;">
                <!-- Mode switcher: Native vs Drawio -->
                <div class="mode-tabs" id="modeTabs">
                    <button id="modeBtnNative" class="mode-tab-btn active" onclick="switchMainMode('native')">⚡ Native Topology</button>
                    <button id="modeBtnDrawio" class="mode-tab-btn" onclick="switchMainMode('drawio')">📐 Draw.io Diagrams</button>
                </div>

                <!-- THEME_SWITCHER_HTML -->
                <a id="headerDownloadBtn" class="btn-header-link" style="display:none;" href="#" onclick="downloadCurrentDiagram(event)">Download .drawio</a>
                <a class="back-portal" href="../index.html">← Network Portal</a>
            </div>
        </div>

        <div id="welcome">
            <div class="icon">🕸️</div>
            <h2>Topology Explorer</h2>
            <p>Select a collection date from the history sidebar to explore the interactive physical graph.</p>
        </div>

        <div id="dashboardOverlay">
            <!-- 1. NATIVE TOPOLOGY VIEW (Default) -->
            <div id="nativeView" style="display: flex; flex-direction: column; flex: 1; min-height: 0;">
                <div class="native-controls-bar">
                    <!-- Row 1: Sub-mode (View vs Drift), Layer Tier Filters & Search -->
                    <div class="controls-row-top">
                        <div class="btn-group" style="flex-shrink: 0;">
                            <button id="btnSubModeView" class="action-btn active" onclick="switchNativeSubMode('view')">👁️ View Mode</button>
                            <button id="btnSubModeDrift" class="action-btn" onclick="switchNativeSubMode('drift')">⚖️ Compare Drift</button>
                        </div>
                        <div class="tier-pills-group" id="tierPills">
                            <span class="filter-label">Tiers:</span>
                            <!-- Dynamic tier pills generated by JS -->
                        </div>
                        <div class="search-container">
                            <input id="nodeSearchInput" type="text" placeholder="🔍 Filter: e.g. RTOC | tier:core, !BHE01" oninput="handleSearch(this.value)" onkeydown="handleSearchKeyDown(event)">
                            <button class="clear-btn" onclick="clearSearch()" title="Clear search (Esc)">✕</button>
                            <div id="topoMatchHUD" class="match-hud-pill" style="display:none;">
                                <span id="topoMatchCount">0 matches</span>
                                <button class="hud-cycle-btn" onclick="cycleSearchMatch(-1)" title="Previous match (Shift+Enter)">◀</button>
                                <button class="hud-cycle-btn" onclick="cycleSearchMatch(1)" title="Next match (Enter)">▶</button>
                            </div>
                        </div>
                    </div>

                    <!-- Row 2: Type, Layout, Physics & Camera Actions -->
                    <div class="controls-row-bottom">
                        <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
                            <div class="btn-group">
                                <span class="filter-label">Connections:</span>
                                <button id="nativeTypeSum" class="action-btn active" onclick="switchNativeType('summary')">Summary (SUM)</button>
                                <button id="nativeTypeDet" class="action-btn" onclick="switchNativeType('detailed')">Detailed (Ports)</button>
                            </div>
                            <div class="btn-group">
                                <span class="filter-label">Layout:</span>
                                <button id="layoutConcentric" class="action-btn active" onclick="switchNativeLayout('concentric')">🪐 Concentric Orbital</button>
                                <button id="layoutOrganic" class="action-btn" onclick="switchNativeLayout('organic')">🌐 Organic</button>
                                <button id="layoutSite" class="action-btn" onclick="switchNativeLayout('site')">🏢 By Site</button>
                            </div>
                            <div class="btn-group">
                                <span class="filter-label">Telemetry:</span>
                                <button id="telemetryModeSpeed" class="action-btn active" onclick="switchTelemetryMode('speed')">⚡ Speed</button>
                                <button id="telemetryModeLatency" class="action-btn" onclick="switchTelemetryMode('latency')">⏱️ Latency (RTT)</button>
                                <button id="telemetryModeLoss" class="action-btn" onclick="switchTelemetryMode('loss')">📉 Loss</button>
                            </div>
                        </div>

                        <div style="display: flex; gap: 8px; align-items: center;">
                            <button id="freezePhysicsBtn" class="action-btn" onclick="toggleNativePhysics()">⏸️ Freeze Physics</button>
                            <button class="action-btn" onclick="fitNativeGraph()" title="Fit to View">🔍 Fit</button>
                            <button class="action-btn" onclick="zoomNative(1.2)" title="Zoom In">➕</button>
                            <button class="action-btn" onclick="zoomNative(0.8)" title="Zoom Out">➖</button>
                            <button class="action-btn" id="theaterBtn" onclick="toggleTheaterMode()">🔲 Fullscreen</button>
                            <button class="action-btn" onclick="exportCurrentNativeTopology()" title="Export to Draw.io (.drawio)">📥 Export .drawio</button>
                        </div>
                    </div>
                </div>

                <!-- Phase 4: Path Tracing Toolbar -->
                <div class="trace-toolbar" id="traceToolbar">
                    <div class="trace-group">
                        <span style="font-size:0.8rem; font-weight:700; color:var(--accent);">🛣️ PATH TRACE:</span>
                        <label style="font-size:0.75rem; color:var(--text-dim);">Origin (A):</label>
                        <input list="topologyNodeList" id="traceSourceInput" class="trace-input" placeholder="Type or select Origin..." oninput="onTraceInputChange()">
                        <label style="font-size:0.75rem; color:var(--text-dim);">Target (B):</label>
                        <input list="topologyNodeList" id="traceTargetInput" class="trace-input" placeholder="Type or select Target..." oninput="onTraceInputChange()">
                        <datalist id="topologyNodeList"></datalist>
                        <button class="action-btn active" id="btnTraceRoute" onclick="triggerPathTrace()">🚀 Trace Path</button>
                        <button class="action-btn" id="btnClearTrace" onclick="clearPathTrace()" style="display:none;">✕ Clear</button>
                    </div>

                    <!-- Path Selection Toggle Buttons (Option 1: Path 1 Optimal by default) -->
                    <div class="trace-group" id="pathSelectorGroup" style="display:none;">
                        <span class="filter-label" style="font-size:0.75rem; color:var(--text-dim);">Select Route:</span>
                        <button id="btnPath0" class="action-btn active" onclick="selectActivePath(0)">🟢 Path 1 (Optimal)</button>
                        <button id="btnPath1" class="action-btn" onclick="selectActivePath(1)" style="display:none;">🟡 Path 2</button>
                        <button id="btnPath2" class="action-btn" onclick="selectActivePath(2)" style="display:none;">🔵 Path 3</button>
                    </div>
                </div>

                <!-- Phase 4: Drift Toolbar -->
                <div class="drift-toolbar" id="driftToolbar">
                    <div class="drift-selector-group">
                        <span style="font-size:0.8rem; font-weight:700; color:var(--accent);">⚖️ TEMPORAL COMPARATOR:</span>
                        <label style="font-size:0.75rem; color:var(--text-dim);">Baseline (A):</label>
                        <select id="driftSelectA" class="drift-select" onchange="runTopologicalDrift()"></select>
                        <span style="color:var(--text-dim); font-size:0.8rem;">vs</span>
                        <label style="font-size:0.75rem; color:var(--text-dim);">Comparison (B):</label>
                        <select id="driftSelectB" class="drift-select" onchange="runTopologicalDrift()"></select>
                        <button class="action-btn active" style="padding:4px 10px; font-size:0.75rem;" onclick="runTopologicalDrift()">Calculate Drift</button>
                    </div>
                    <div class="drift-pills" id="driftSummaryPills" style="display:none;">
                        <span class="drift-pill drift-pill-added" id="driftPillNodesAdded">+0 Nodes</span>
                        <span class="drift-pill drift-pill-removed" id="driftPillNodesRemoved">-0 Nodes</span>
                        <span class="drift-pill drift-pill-added" id="driftPillEdgesAdded">+0 Links</span>
                        <span class="drift-pill drift-pill-removed" id="driftPillEdgesRemoved">-0 Links</span>
                        <span class="drift-pill drift-pill-stable" id="driftPillStable">Stable</span>
                    </div>
                </div>

                <div class="graph-wrapper">
                    <div id="nativeGraphContainer"></div>

                    <!-- Floating Path Telemetry Summary Card (Phase 4 & 5) -->
                    <div class="path-summary-card" id="pathSummaryCard" style="display:none;">
                        <div class="path-summary-header">
                            <div>
                                <div class="path-summary-title" id="summaryRouteTitle">ROUTE TELEMETRY</div>
                                <div style="font-size:0.7rem; color:var(--text-dim); font-family:monospace;" id="summaryRouteEndpoints">- ➔ -</div>
                            </div>
                            <button class="drawer-close" onclick="clearPathTrace()" title="Clear Path" style="font-size:1rem;">✕</button>
                        </div>
                        <div class="path-summary-grid">
                            <div class="path-stat-box">
                                <div class="path-stat-val" id="summaryTotalHops">0</div>
                                <div class="path-stat-lbl">Total Hops</div>
                            </div>
                            <div class="path-stat-box">
                                <div class="path-stat-val" id="summaryCumulativeRtt">-</div>
                                <div class="path-stat-lbl">Cumulative RTT</div>
                            </div>
                            <div class="path-stat-box">
                                <div class="path-stat-val" id="summaryWorstLoss">0.0%</div>
                                <div class="path-stat-lbl">Worst Loss</div>
                            </div>
                            <div class="path-stat-box">
                                <div class="path-stat-val" id="summaryBottleneckBw">-</div>
                                <div class="path-stat-lbl">Bottleneck Cap</div>
                            </div>
                        </div>
                        <div id="summaryHopsList" style="margin-top:8px; font-size:0.72rem; max-height:130px; overflow-y:auto; border-top:1px solid var(--border); padding-top:6px; font-family:monospace;"></div>
                        <button class="action-btn" style="padding:4px 8px; font-size:0.72rem; margin-top:8px; width:100%; text-align:center;" onclick="openDrawerRouteDetails()">📋 Full Drilldown in Drawer</button>
                    </div>

                    <!-- Floating Node Quick Summary Mini-Card (Phase 4) -->
                    <div class="node-quick-summary-card" id="nodeQuickSummaryCard" style="display:none;">
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px; border-bottom:1px solid rgba(56,189,248,0.2); padding-bottom:8px;">
                            <div>
                                <div id="miniCardHostname" style="font-family:'Outfit',sans-serif; font-size:0.95rem; font-weight:700; color:#38bdf8;">-</div>
                                <div style="display:flex; gap:6px; align-items:center; margin-top:3px; flex-wrap:wrap;">
                                    <span id="miniCardTierBadge" class="tooltip-badge" style="font-size:0.65rem;">TIER</span>
                                    <span id="miniCardSiteBadge" style="font-size:0.7rem; color:var(--text-dim);">Site: -</span>
                                    <span id="miniCardModelBadge" style="font-size:0.68rem; color:var(--text-dim); font-family:monospace;">-</span>
                                </div>
                            </div>
                            <button class="drawer-close" onclick="closeMiniSummaryCard()" title="Close Card" style="font-size:0.9rem; line-height:1;">✕</button>
                        </div>
                        
                        <div class="drawer-metric-grid" style="margin:8px 0; gap:8px;">
                            <div class="drawer-metric-card" style="padding:6px 10px;">
                                <div class="drawer-metric-val" id="miniCardLinks" style="font-size:1.1rem; color:#38bdf8;">0</div>
                                <div class="drawer-metric-lbl" style="font-size:0.65rem;">Total Links</div>
                            </div>
                            <div class="drawer-metric-card" style="padding:6px 10px;">
                                <div class="drawer-metric-val" id="miniCardCapacity" style="font-size:1.1rem; color:#10b981;">-</div>
                                <div class="drawer-metric-lbl" style="font-size:0.65rem;">Aggregate Capacity</div>
                            </div>
                        </div>

                        <div style="margin:8px 0;">
                            <div style="font-size:0.68rem; color:var(--text-dim); text-transform:uppercase; font-weight:700; margin-bottom:4px;">Top Neighbors</div>
                            <div id="miniCardNeighborsList" style="font-size:0.72rem; font-family:monospace; display:flex; flex-direction:column; gap:4px; max-height:85px; overflow-y:auto;"></div>
                        </div>

                        <div style="display:flex; gap:6px; margin-top:10px;">
                            <button class="action-btn active" style="flex:1; padding:5px 8px; font-size:0.72rem; justify-content:center;" onclick="openFullDrawerFromMini()">📋 Open Full Drawer</button>
                            <button class="action-btn" style="padding:5px 8px; font-size:0.72rem;" onclick="focusMiniCardNode()" title="Focus on Canvas">🎯 Focus</button>
                        </div>
                    </div>
                    
                    <!-- Sliding Telemetry Drawer -->
                    <div class="node-drawer" id="nodeDrawer">
                        <div class="drawer-header">
                            <div>
                                <div class="drawer-title" id="drawerHostname">-</div>
                                <div class="drawer-badges">
                                    <span id="drawerTierBadge" class="tooltip-badge">TIER</span>
                                    <span id="drawerSiteBadge" style="font-size:0.7rem; color:var(--text-dim);">Site: -</span>
                                </div>
                            </div>
                            <button class="drawer-close" onclick="closeDrawer()">✕</button>
                        </div>
                        <div class="drawer-body">
                            <!-- Hardware & Platform Specs -->
                            <div class="drawer-spec-panel" style="margin-bottom:12px; padding:10px 12px; background:rgba(15,23,42,0.6); border:1px solid var(--border); border-radius:8px;">
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                                    <span style="font-size:0.7rem; color:var(--text-dim); text-transform:uppercase; font-weight:700;">Hardware / OS Platform</span>
                                    <span id="drawerVendorBadge" class="tooltip-badge" style="background:rgba(56,189,248,0.15); color:#38bdf8; font-size:0.68rem;">CISCO</span>
                                </div>
                                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:6px; font-size:0.75rem;">
                                    <div><span style="color:var(--text-dim);">Model:</span> <b id="drawerModel" style="color:var(--text);">-</b></div>
                                    <div><span style="color:var(--text-dim);">OS Ver:</span> <b id="drawerOsVersion" style="color:var(--text);">-</b></div>
                                    <div style="grid-column: span 2;"><span style="color:var(--text-dim);">Uptime:</span> <span id="drawerUptime" style="color:var(--text-dim); font-family:monospace; font-size:0.72rem;">-</span></div>
                                </div>
                            </div>

                            <!-- Quick Route Selection -->
                            <div style="display:flex; gap:8px; margin-bottom:12px;">
                                <button class="action-btn" style="flex:1; font-size:0.75rem;" onclick="setDrawerNodeAsOrigin()">🚩 Route Origin (A)</button>
                                <button class="action-btn" style="flex:1; font-size:0.75rem;" onclick="setDrawerNodeAsTarget()">🎯 Route Target (B)</button>
                            </div>

                            <!-- Phase 5: Collapsible Active Route Drilldown Section -->
                            <div id="drawerRouteTraceSection" style="display:none; margin-bottom:14px; border:1px solid rgba(56,189,248,0.3); border-radius:8px; background:rgba(15,23,42,0.85); overflow:hidden;">
                                <div style="padding:10px 14px; background:rgba(56,189,248,0.12); display:flex; justify-content:space-between; align-items:center; cursor:pointer;" onclick="toggleDrawerRouteDetails()">
                                    <div style="font-family:'Outfit'; font-weight:700; font-size:0.82rem; color:#38bdf8; display:flex; align-items:center; gap:6px;">
                                        <span>🛣️</span>
                                        <span id="drawerRouteTraceTitle">ACTIVE ROUTE TELEMETRY</span>
                                    </div>
                                    <span id="routeDrilldownToggleIcon" style="font-size:0.75rem; color:var(--text-dim);">▲</span>
                                </div>
                                <div id="drawerRouteDrilldownBody" style="padding:12px 14px;">
                                    <div class="drawer-metric-grid" style="margin:0 0 10px 0;">
                                        <div class="drawer-metric-card">
                                            <div class="drawer-metric-val" id="drawerRouteHops" style="color:#38bdf8;">0</div>
                                            <div class="drawer-metric-lbl">Total Hops</div>
                                        </div>
                                        <div class="drawer-metric-card">
                                            <div class="drawer-metric-val" id="drawerRouteRtt" style="color:#10b981;">-</div>
                                            <div class="drawer-metric-lbl">Cumulative RTT</div>
                                        </div>
                                        <div class="drawer-metric-card">
                                            <div class="drawer-metric-val" id="drawerRouteLoss" style="color:#10b981;">0.0%</div>
                                            <div class="drawer-metric-lbl">Worst Loss</div>
                                        </div>
                                        <div class="drawer-metric-card">
                                            <div class="drawer-metric-val" id="drawerRouteBottleneck">-</div>
                                            <div class="drawer-metric-lbl">Bottleneck Cap</div>
                                        </div>
                                    </div>
                                    <div style="font-size:0.7rem; color:var(--text-dim); text-transform:uppercase; margin-bottom:6px; font-weight:700;">Hop-by-Hop Breakdown</div>
                                    <table class="neighbor-table">
                                        <thead>
                                            <tr>
                                                <th>#</th>
                                                <th>From ➔ To</th>
                                                <th>Egress Port</th>
                                                <th>Ingress Port</th>
                                                <th>Speed</th>
                                                <th>RTT</th>
                                            </tr>
                                        </thead>
                                        <tbody id="drawerRouteHopsTable"></tbody>
                                    </table>
                                </div>
                            </div>

                            <!-- Phase 4: Drift Status if in drift mode -->
                            <div id="drawerDriftSection" style="display:none; margin-bottom:12px; padding:10px; border-radius:6px; background:rgba(15,23,42,0.6); border:1px solid var(--border);">
                                <div style="font-size:0.7rem; color:var(--text-dim); text-transform:uppercase; margin-bottom:4px; font-weight:700;">Topological Drift Status</div>
                                <div style="display:flex; align-items:center; gap:8px;">
                                    <span id="drawerDriftBadge" class="drift-pill"></span>
                                    <span id="drawerDriftDetail" style="font-size:0.78rem; color:var(--text);"></span>
                                </div>
                            </div>

                            <div class="drawer-metric-grid">
                                <div class="drawer-metric-card">
                                    <div class="drawer-metric-val" id="drawerDegree">0</div>
                                    <div class="drawer-metric-lbl">Total Links</div>
                                </div>
                                <div class="drawer-metric-card">
                                    <div class="drawer-metric-val" id="drawerBandwidth">-</div>
                                    <div class="drawer-metric-lbl">Aggregate Capacity</div>
                                </div>
                            </div>

                            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 14px;">
                                <h4 style="font-family:'Outfit'; font-size:0.85rem; color:var(--accent);">Neighbor Connections</h4>
                                <button class="action-btn" style="font-size:0.7rem;" onclick="focusDrawerNode()">🎯 Focus on Graph</button>
                            </div>

                            <table class="neighbor-table">
                                <thead>
                                    <tr>
                                        <th>Interface</th>
                                        <th>Neighbor</th>
                                        <th>Remote Port</th>
                                        <th>Speed</th>
                                        <th>RTT</th>
                                        <th>Loss</th>
                                    </tr>
                                </thead>
                                <tbody id="drawerNeighborsList">
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 2. LEGACY DRAW.IO VIEW (Conditional Hybrid) -->
            <div id="drawioView">
                <div class="topo-controls">
                    <div class="topo-tabs">
                        <button id="tab-summary" class="tab-btn active" onclick="switchDrawioType('summary')">Backbone Summary (SUM)</button>
                        <button id="tab-detailed" class="tab-btn" onclick="switchDrawioType('detailed')">Complete (Detailed)</button>
                    </div>
                    <div class="layout-options">
                        <span class="layout-label">Layout:</span>
                        <div id="layoutBtnGroup" style="display: flex; gap: 6px;"></div>
                    </div>
                </div>

                <div class="viewer-container" id="viewer-container">
                    <div class="loader-overlay" id="loader">
                        <div class="spinner"></div>
                        <p style="color: var(--accent); font-family: 'Outfit'; font-size: 1.1rem; font-weight: 600;">Loading Topology...</p>
                    </div>

                    <div class="offline-fallback" id="offlineFallback">
                        <h3>Browser Security Restriction (file:// Protocol)</h3>
                        <p>Draw.io XML embeds require a local web server when accessed via file:// protocol.</p>
                        <div class="btn-group-download">
                            <a id="fallbackDownloadBtn" class="btn-action btn-primary" href="#" onclick="downloadCurrentDiagram(event)">📥 Download Diagram (.drawio)</a>
                            <a class="btn-action btn-secondary" href="https://app.diagrams.net/" target="_blank">🌐 Go to Draw.io Web</a>
                        </div>
                    </div>

                    <iframe id="drawio-viewer" src="about:blank"></iframe>
                </div>
            </div>
        </div>
    </div>

    <script>
        let manifest = window.topo_manifest || [];
        let currentRun = null;
        let currentMainMode = 'native'; // 'native' or 'drawio'
        let currentNativeSubMode = 'view'; // 'view' or 'drift'
        let nativeGraph = null;
        let activeNativeType = 'summary';
        let activeDrawioType = 'summary';
        let activeDrawioLayout = null;
        let xmlContent = '';
        let currentFilename = '';
        let isLocalProtocol = window.location.protocol === 'file:';

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

        function toggleSidebar() { document.getElementById('sidebar').classList.toggle('collapsed'); }

        function renderList() {
            const list = document.getElementById('runList');
            manifest.sort((a,b) => b.id.localeCompare(a.id));
            
            list.innerHTML = manifest.map(m => `
                <div class="run-item" onclick="selectRun('${m.id}', this)">
                    <div class="run-date">${formatDate(m.id)}</div>
                    <div class="run-id">${m.id}</div>
                    <div class="run-badges">
                        ${m.has_native ? `<span class="run-badge badge-native">⚡ ${m.nodes_count || 0} nodes</span>` : ''}
                        ${m.has_drawio ? `<span class="run-badge badge-drawio">📐 Draw.io</span>` : ''}
                    </div>
                </div>
            `).join('');
        }

        function switchMainMode(mode) {
            currentMainMode = mode;
            document.getElementById('modeBtnNative').classList.toggle('active', mode === 'native');
            document.getElementById('modeBtnDrawio').classList.toggle('active', mode === 'drawio');
            
            document.getElementById('nativeView').style.display = (mode === 'native') ? 'flex' : 'none';
            document.getElementById('drawioView').style.display = (mode === 'drawio') ? 'flex' : 'none';
            
            if (mode === 'native' && nativeGraph) {
                setTimeout(() => {
                    nativeGraph.resize();
                    nativeGraph.fitToScreen();
                }, 50);
            }
        }

        function selectRun(id, el) {
            document.querySelectorAll('.run-item').forEach(it => it.classList.remove('active'));
            if(el) el.classList.add('active');
            if(window.innerWidth < 768) toggleSidebar();
            
            document.getElementById('welcome').style.display = 'none';
            document.getElementById('dashboardOverlay').style.display = 'flex';
            
            currentRun = manifest.find(m => m.id === id);
            document.getElementById('dashTitle').innerText = '🕸️ Network Topology';
            document.getElementById('dashSubTitle').innerText = formatDate(id);
            
            // Toggle visibility of Draw.io tab depending on whether files exist
            const hasDrawio = currentRun && currentRun.has_drawio && currentRun.files && currentRun.files.length > 0;
            document.getElementById('modeBtnDrawio').style.display = hasDrawio ? 'inline-flex' : 'none';

            // Default to Native view mode
            switchMainMode('native');
            switchNativeSubMode('view');

            // Load Native dataset
            loadNativeRun(id);

            // Prepare Drawio view if available
            if (hasDrawio) {
                prepareDrawioRun(currentRun);
            }
        }

        function loadNativeRun(runId) {
            if (!nativeGraph) {
                nativeGraph = new NetworkTopologyGraph('nativeGraphContainer');
                nativeGraph.onNodeSelected = (node) => handleNodeSelected(node);
                nativeGraph.onNodeContextMenu = (node, cx, cy) => showContextMenu(node, cx, cy);
                nativeGraph.onSearchMatchesChanged = (count, index) => updateMatchHUD(count, index);
            }

            if (window.topology_data && window.topology_data[runId]) {
                applyNativeDataset(window.topology_data[runId]);
            } else {
                // Dynamically inject script
                const script = document.createElement('script');
                script.src = `data/topology_${runId}.js?v=` + Date.now();
                script.onload = () => {
                    if (window.topology_data && window.topology_data[runId]) {
                        applyNativeDataset(window.topology_data[runId]);
                    }
                };
                script.onerror = () => {
                    console.error("Failed to load native topology dataset for run:", runId);
                };
                document.head.appendChild(script);
            }
        }

        function applyNativeDataset(dataset) {
            nativeGraph.setData(dataset, activeNativeType);
            buildTierPills(dataset);
            populateTraceDatalist(dataset);
            clearPathTrace();
        }

        function buildTierPills(dataset) {
            const container = document.getElementById('tierPills');
            const tiersCount = dataset.stats ? (dataset.stats.tiers_count || {}) : {};
            const allTiers = window.TopologyTheme ? window.TopologyTheme.getAllTiers() : ['core', 'core_agg', 'edge', 'metro', 'peering', 'router_reflector', 'dcn', 'demarcator', 'customer_cpe', 'customer_sdwan', 'other'];

            let html = '<span class="filter-label">Tiers:</span>';
            allTiers.forEach(t => {
                const count = tiersCount[t] || 0;
                if (count === 0 && !nativeGraph.nodes.some(n => n.tier === t)) return;

                const meta = window.TopologyTheme ? window.TopologyTheme.getMeta(t) : { label: t, shortLabel: t };
                const style = window.TopologyTheme ? window.TopologyTheme.getTierStyle(t) : { primary: '#38bdf8', fill: 'rgba(56,189,248,0.15)' };
                const isActive = nativeGraph.activeTiers.has(t);

                html += `
                    <div class="tier-pill ${isActive ? 'active' : 'inactive'}" 
                         style="--pill-color:${style.primary}; --pill-bg:${style.fill}"
                         onclick="toggleTierFilter('${t}', this)">
                        <span class="tier-dot"></span>
                        <span>${meta.shortLabel || t}</span>
                        <span class="tier-count">(${count})</span>
                    </div>
                `;
            });
            container.innerHTML = html;
        }

        function toggleTierFilter(tier, el) {
            const isCurrentlyActive = nativeGraph.activeTiers.has(tier);
            const newState = !isCurrentlyActive;
            nativeGraph.setFilterTier(tier, newState);
            el.classList.toggle('active', newState);
            el.classList.toggle('inactive', !newState);
        }

        function switchNativeSubMode(mode) {
            currentNativeSubMode = mode;
            document.getElementById('btnSubModeView').classList.toggle('active', mode === 'view');
            document.getElementById('btnSubModeDrift').classList.toggle('active', mode === 'drift');

            const driftBar = document.getElementById('driftToolbar');
            const summaryPills = document.getElementById('driftSummaryPills');

            if (mode === 'drift') {
                driftBar.style.display = 'flex';
                populateDriftDropdowns();
                runTopologicalDrift();
            } else {
                driftBar.style.display = 'none';
                summaryPills.style.display = 'none';
                if (currentRun && window.topology_data && window.topology_data[currentRun.id]) {
                    applyNativeDataset(window.topology_data[currentRun.id]);
                }
            }
        }

        function populateDriftDropdowns() {
            const selectA = document.getElementById('driftSelectA');
            const selectB = document.getElementById('driftSelectB');
            const nativeRuns = manifest.filter(m => m.has_native);

            if (nativeRuns.length === 0) return;

            const optionsHtml = nativeRuns.map(m => 
                `<option value="${m.id}">${formatDate(m.id)} (${m.id})</option>`
            ).join('');

            selectA.innerHTML = optionsHtml;
            selectB.innerHTML = optionsHtml;

            // Default: B is currently selected run (or newest), A is previous run
            const activeId = currentRun ? currentRun.id : nativeRuns[0].id;
            selectB.value = activeId;

            const activeIdx = nativeRuns.findIndex(m => m.id === activeId);
            if (activeIdx !== -1 && activeIdx + 1 < nativeRuns.length) {
                selectA.value = nativeRuns[activeIdx + 1].id;
            } else if (nativeRuns.length > 1) {
                selectA.value = nativeRuns[1].id;
            } else {
                selectA.value = activeId;
            }
        }

        function ensureDatasetLoaded(runId, callback) {
            if (window.topology_data && window.topology_data[runId]) {
                callback(window.topology_data[runId]);
                return;
            }
            const script = document.createElement('script');
            script.src = `data/topology_${runId}.js?v=` + Date.now();
            script.onload = () => {
                if (window.topology_data && window.topology_data[runId]) {
                    callback(window.topology_data[runId]);
                } else {
                    console.error("Dataset not found in window.topology_data for", runId);
                }
            };
            script.onerror = (err) => {
                console.error("Error loading topology script for", runId, err);
            };
            document.head.appendChild(script);
        }

        function runTopologicalDrift() {
            const selectA = document.getElementById('driftSelectA');
            const selectB = document.getElementById('driftSelectB');
            if (!selectA || !selectB) return;
            const idA = selectA.value;
            const idB = selectB.value;
            if (!idA || !idB) return;

            ensureDatasetLoaded(idA, () => {
                ensureDatasetLoaded(idB, () => {
                    const dataA = window.topology_data[idA];
                    const dataB = window.topology_data[idB];
                    if (!dataA || !dataB) return;

                    const stats = nativeGraph.setDriftData(dataA, dataB, activeNativeType);
                    if (stats) {
                        const pills = document.getElementById('driftSummaryPills');
                        pills.style.display = 'flex';
                        document.getElementById('driftPillNodesAdded').innerText = `+${stats.nodes_added} Nodes`;
                        document.getElementById('driftPillNodesRemoved').innerText = `-${stats.nodes_removed} Nodes`;
                        document.getElementById('driftPillEdgesAdded').innerText = `+${stats.edges_added} Links`;
                        document.getElementById('driftPillEdgesRemoved').innerText = `-${stats.edges_removed} Links`;

                        const isStable = (stats.nodes_added === 0 && stats.nodes_removed === 0 && stats.edges_added === 0 && stats.edges_removed === 0);
                        document.getElementById('driftPillStable').innerText = isStable ? 'Stable Topology (No Drift)' : 'Drift Detected';
                        document.getElementById('driftPillStable').className = 'drift-pill ' + (isStable ? 'drift-pill-stable' : 'drift-pill-removed');

                        // Rebuild tier pills with drift dataset
                        buildTierPills({
                            nodes: nativeGraph.nodes,
                            stats: {
                                tiers_count: nativeGraph.nodes.reduce((acc, n) => {
                                    acc[n.tier] = (acc[n.tier] || 0) + 1;
                                    return acc;
                                }, {})
                            }
                        });
                    }
                });
            });
        }

        function switchNativeType(type) {
            activeNativeType = type;
            document.getElementById('nativeTypeSum').classList.toggle('active', type === 'summary');
            document.getElementById('nativeTypeDet').classList.toggle('active', type === 'detailed');
            if (currentNativeSubMode === 'drift') {
                runTopologicalDrift();
            } else if (currentRun && window.topology_data[currentRun.id]) {
                nativeGraph.setData(window.topology_data[currentRun.id], type);
            }
        }

        function switchNativeLayout(layout) {
            document.getElementById('layoutConcentric').classList.toggle('active', layout === 'concentric');
            document.getElementById('layoutOrganic').classList.toggle('active', layout === 'organic');
            document.getElementById('layoutSite').classList.toggle('active', layout === 'site');
            nativeGraph.applyLayout(layout, true);
        }

        let activeTelemetryMode = 'speed';
        function switchTelemetryMode(mode) {
            activeTelemetryMode = mode;
            document.getElementById('telemetryModeSpeed').classList.toggle('active', mode === 'speed');
            document.getElementById('telemetryModeLatency').classList.toggle('active', mode === 'latency');
            document.getElementById('telemetryModeLoss').classList.toggle('active', mode === 'loss');
            if (nativeGraph) {
                nativeGraph.setTelemetryMode(mode);
            }
        }

        function toggleNativePhysics() {
            if (nativeGraph) nativeGraph.togglePhysics();
        }

        function fitNativeGraph() {
            if (nativeGraph) nativeGraph.fitToScreen();
        }

        function zoomNative(factor) {
            if (!nativeGraph) return;
            nativeGraph.targetCamera.zoom = Math.min(Math.max(nativeGraph.camera.zoom * factor, 0.15), 3.5);
        }

        function handleSearch(val) {
            if (nativeGraph) nativeGraph.setSearchQuery(val);
        }

        function handleSearchKeyDown(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (e.shiftKey) {
                    cycleSearchMatch(-1);
                } else {
                    cycleSearchMatch(1);
                }
            } else if (e.key === 'Escape') {
                clearSearch();
            }
        }

        function cycleSearchMatch(dir) {
            if (!nativeGraph) return;
            if (dir < 0) {
                nativeGraph.prevSearchMatch();
            } else {
                nativeGraph.nextSearchMatch();
            }
        }

        function updateMatchHUD(count, index) {
            const hud = document.getElementById('topoMatchHUD');
            const lbl = document.getElementById('topoMatchCount');
            if (!hud || !lbl) return;
            if (count > 0) {
                hud.style.display = 'inline-flex';
                lbl.innerText = `${index + 1}/${count} matches`;
                lbl.style.color = '#38bdf8';
            } else {
                const inp = document.getElementById('nodeSearchInput');
                if (inp && inp.value.trim()) {
                    hud.style.display = 'inline-flex';
                    lbl.innerText = '0 matches';
                    lbl.style.color = '#ef4444';
                } else {
                    hud.style.display = 'none';
                }
            }
        }

        function clearSearch() {
            const inp = document.getElementById('nodeSearchInput');
            if (inp) {
                inp.value = '';
                handleSearch('');
            }
        }

        function showNodeDrawer(node) {
            const drawer = document.getElementById('nodeDrawer');
            if (!node) {
                drawer.classList.remove('open');
                return;
            }

            // Phase 4: Drift status in drawer
            const driftSec = document.getElementById('drawerDriftSection');
            const driftBadge = document.getElementById('drawerDriftBadge');
            const driftDetail = document.getElementById('drawerDriftDetail');
            if (nativeGraph && nativeGraph.isDriftMode && node.drift && node.drift !== 'none') {
                driftSec.style.display = 'block';
                if (node.drift === 'added') {
                    driftBadge.className = 'drift-pill drift-pill-added';
                    driftBadge.innerText = '+ NEW ELEMENT';
                    driftDetail.innerText = 'Added in Snapshot B (new element in graph)';
                } else if (node.drift === 'removed') {
                    driftBadge.className = 'drift-pill drift-pill-removed';
                    driftBadge.innerText = '- REMOVED ELEMENT';
                    driftDetail.innerText = 'Missing in Snapshot B (removed from graph)';
                } else {
                    driftBadge.className = 'drift-pill drift-pill-stable';
                    driftBadge.innerText = '= STABLE ELEMENT';
                    driftDetail.innerText = 'Present in both compared snapshots';
                }
            } else {
                driftSec.style.display = 'none';
            }

            // Route Trace Section in drawer
            if (nativeGraph && nativeGraph.activePath) {
                renderDrawerRouteDetails(nativeGraph.activePath, nativeGraph.activePathIdx || 0);
            } else {
                const routeSec = document.getElementById('drawerRouteTraceSection');
                if (routeSec) routeSec.style.display = 'none';
            }

            document.getElementById('drawerHostname').innerText = node.id;
            const meta = window.TopologyTheme ? window.TopologyTheme.getMeta(node.tier) : { label: node.tier, shortLabel: node.tier };
            const tierBadge = document.getElementById('drawerTierBadge');
            tierBadge.innerText = meta.label || node.tier;

            const tierStyle = window.TopologyTheme ? window.TopologyTheme.getTierStyle(node.tier) : { primary: '#38bdf8', fill: 'rgba(56,189,248,0.2)' };
            tierBadge.style.backgroundColor = tierStyle.fill;
            tierBadge.style.color = tierStyle.primary;

            document.getElementById('drawerSiteBadge').innerText = 'Site: ' + (node.site || 'N/A');
            document.getElementById('drawerDegree').innerText = node.degree || 0;

            // Hardware & Platform specs (Phase 4)
            const vendorBadge = document.getElementById('drawerVendorBadge');
            if (vendorBadge) vendorBadge.innerText = (node.vendor || 'CISCO').toUpperCase();
            const modelEl = document.getElementById('drawerModel');
            if (modelEl) modelEl.innerText = node.model || 'N/A';
            const osVerEl = document.getElementById('drawerOsVersion');
            if (osVerEl) osVerEl.innerText = node.os_version || 'N/A';
            const uptimeEl = document.getElementById('drawerUptime');
            if (uptimeEl) uptimeEl.innerText = node.uptime || 'N/A';
            closeMiniSummaryCard();

            // Compute connected edges & total capacity
            const connectedEdges = nativeGraph.edges.filter(e => {
                const s = e.source || (e.sourceNode ? e.sourceNode.id : e.from);
                const t = e.target || (e.targetNode ? e.targetNode.id : e.to);
                return s === node.id || t === node.id;
            });
            let totalBwGbps = 0;
            const rowsHtml = connectedEdges.map(e => {
                const s = e.source || (e.sourceNode ? e.sourceNode.id : e.from);
                const t = e.target || (e.targetNode ? e.targetNode.id : e.to);
                const isSrc = (s === node.id);
                const neighbor = isSrc ? t : s;
                const localInt = isSrc ? (e.local_int || e.from_intf || '-') : (e.remote_int || e.to_intf || '-');
                const remoteInt = isSrc ? (e.remote_int || e.to_intf || '-') : (e.local_int || e.from_intf || '-');
                const speed = e.speed || (e.capacity_gbps ? (e.capacity_gbps + 'G') : (e.label || '-'));
                const cap = e.capacity_gbps || (e.bandwidth_mbps ? (e.bandwidth_mbps / 1000) : 0);
                totalBwGbps += cap;

                const p = e.ping;
                const rttStr = p ? (p.rtt_avg_ms + ' ms') : '-';
                const lossStr = p ? (p.loss_pct + '%') : '-';
                const rttColor = p ? (p.status === 'critical' ? '#ef4444' : (p.status === 'warning' ? '#f59e0b' : '#10b981')) : 'var(--text-dim)';

                return `
                    <tr onclick="focusNeighbor('${neighbor}')">
                        <td>${localInt}</td>
                        <td style="color:var(--accent); font-weight:600;">${neighbor}</td>
                        <td>${remoteInt}</td>
                        <td>${speed}</td>
                        <td style="color:${rttColor}; font-family:monospace; font-weight:600;">${rttStr}</td>
                        <td style="color:${rttColor}; font-family:monospace;">${lossStr}</td>
                    </tr>
                `;
            }).join('');

            document.getElementById('drawerBandwidth').innerText = totalBwGbps > 0 ? (totalBwGbps >= 1 ? totalBwGbps.toFixed(0) + ' Gbps' : (totalBwGbps * 1000).toFixed(0) + ' Mbps') : 'N/A';
            document.getElementById('drawerNeighborsList').innerHTML = rowsHtml || '<tr><td colspan="6" style="text-align:center; color:var(--text-dim);">No neighbor connections found</td></tr>';

            drawer.classList.add('open');
        }

        let currentMiniCardNode = null;

        function handleNodeSelected(node) {
            if (!node) {
                closeMiniSummaryCard();
                return;
            }
            const drawer = document.getElementById('nodeDrawer');
            if (drawer && drawer.classList.contains('open')) {
                showNodeDrawer(node);
                return;
            }
            showMiniSummaryCard(node);
        }

        function showMiniSummaryCard(node) {
            if (!node) return;
            currentMiniCardNode = node;
            const card = document.getElementById('nodeQuickSummaryCard');
            if (!card) return;

            document.getElementById('miniCardHostname').innerText = node.id || '-';
            const meta = window.TopologyTheme ? window.TopologyTheme.getMeta(node.tier) : { label: node.tier, shortLabel: node.tier };
            const tierBadge = document.getElementById('miniCardTierBadge');
            if (tierBadge) {
                tierBadge.innerText = meta.label || node.tier || 'NODE';
                const tierStyle = window.TopologyTheme ? window.TopologyTheme.getTierStyle(node.tier) : { primary: '#38bdf8', fill: 'rgba(56,189,248,0.2)' };
                tierBadge.style.backgroundColor = tierStyle.fill;
                tierBadge.style.color = tierStyle.primary;
            }

            const siteBadge = document.getElementById('miniCardSiteBadge');
            if (siteBadge) siteBadge.innerText = 'Site: ' + (node.site || 'N/A');

            const modelBadge = document.getElementById('miniCardModelBadge');
            if (modelBadge) modelBadge.innerText = node.model ? `[${node.model}]` : (node.vendor ? `[${node.vendor.toUpperCase()}]` : '');

            // Calculate metrics from edges
            const connectedEdges = (nativeGraph && nativeGraph.edges) ? nativeGraph.edges.filter(e => {
                const s = e.source || (e.sourceNode ? e.sourceNode.id : e.from);
                const t = e.target || (e.targetNode ? e.targetNode.id : e.to);
                return s === node.id || t === node.id;
            }) : [];

            let totalBwGbps = 0;
            const neighborsMap = new Map();

            connectedEdges.forEach(e => {
                const s = e.source || (e.sourceNode ? e.sourceNode.id : e.from);
                const t = e.target || (e.targetNode ? e.targetNode.id : e.to);
                const neighbor = (s === node.id) ? t : s;
                const cap = e.capacity_gbps || (e.bandwidth_mbps ? (e.bandwidth_mbps / 1000) : 0);
                totalBwGbps += cap;

                const speed = e.speed || (e.capacity_gbps ? (e.capacity_gbps + 'G') : (e.label || '-'));
                if (!neighborsMap.has(neighbor)) {
                    neighborsMap.set(neighbor, speed);
                }
            });

            document.getElementById('miniCardLinks').innerText = connectedEdges.length;
            const capStr = totalBwGbps > 0 ? (totalBwGbps >= 1 ? totalBwGbps.toFixed(0) + ' Gbps' : (totalBwGbps * 1000).toFixed(0) + ' Mbps') : 'N/A';
            document.getElementById('miniCardCapacity').innerText = capStr;

            // Render top neighbors (up to 4)
            const neighborsContainer = document.getElementById('miniCardNeighborsList');
            if (neighborsContainer) {
                if (neighborsMap.size === 0) {
                    neighborsContainer.innerHTML = '<span style="color:var(--text-dim);">No neighbors</span>';
                } else {
                    let items = [];
                    let count = 0;
                    for (const [neigh, spd] of neighborsMap.entries()) {
                        if (count >= 4) {
                            items.push(`<div style="color:var(--text-dim); font-size:0.68rem; text-align:right;">+${neighborsMap.size - count} more...</div>`);
                            break;
                        }
                        items.push(`
                            <div style="display:flex; justify-content:space-between; align-items:center; padding:2px 0; border-bottom:1px dashed rgba(255,255,255,0.06); cursor:pointer;" onclick="focusNeighbor('${neigh}')" title="Click to inspect ${neigh}">
                                <span style="color:var(--accent); font-weight:600;">${neigh}</span>
                                <span class="edge-speed-badge" style="font-size:0.62rem; padding:1px 4px;">${spd}</span>
                            </div>
                        `);
                        count++;
                    }
                    neighborsContainer.innerHTML = items.join('');
                }
            }

            card.style.display = 'block';
        }

        function closeMiniSummaryCard() {
            const card = document.getElementById('nodeQuickSummaryCard');
            if (card) card.style.display = 'none';
            currentMiniCardNode = null;
        }

        function openFullDrawerFromMini() {
            if (currentMiniCardNode) {
                showNodeDrawer(currentMiniCardNode);
            }
        }

        function focusMiniCardNode() {
            if (nativeGraph && currentMiniCardNode) {
                nativeGraph.focusNode(currentMiniCardNode);
            }
        }

        function closeDrawer() {
            document.getElementById('nodeDrawer').classList.remove('open');
            closeMiniSummaryCard();
            if (nativeGraph) nativeGraph.selectNode(null);
        }

        function focusDrawerNode() {
            if (nativeGraph && nativeGraph.selectedNode) {
                nativeGraph.focusNode(nativeGraph.selectedNode);
            }
        }

        function focusNeighbor(neighborId) {
            const n = nativeGraph.nodeMap.get(neighborId);
            if (n) {
                nativeGraph.focusNode(n);
                showNodeDrawer(n);
            }
        }

        function exportCurrentNativeTopology() {
            if (!nativeGraph) return;
            let filename = '';
            if (currentNativeSubMode === 'drift') {
                const idA = document.getElementById('driftSelectA') ? document.getElementById('driftSelectA').value : 'A';
                const idB = document.getElementById('driftSelectB') ? document.getElementById('driftSelectB').value : 'B';
                filename = `topology_drift_${idA}_vs_${idB}_${activeNativeType}.drawio`;
            } else {
                const runId = currentRun ? currentRun.id : 'export';
                filename = `topology_${runId}_${activeNativeType}_${nativeGraph.activeLayout}.drawio`;
            }
            nativeGraph.exportToDrawio(filename);
        }

        // Draw.io hybrid support functions
        function prepareDrawioRun(run) {
            const hasSummary = run.files.some(f => f.type === 'summary');
            const hasDetailed = run.files.some(f => f.type === 'detailed');
            document.getElementById('tab-summary').style.display = hasSummary ? 'inline-block' : 'none';
            document.getElementById('tab-detailed').style.display = hasDetailed ? 'inline-block' : 'none';
            updateDrawioLayouts();
        }

        function switchDrawioType(type) {
            activeDrawioType = type;
            document.getElementById('tab-summary').classList.toggle('active', type === 'summary');
            document.getElementById('tab-detailed').classList.toggle('active', type === 'detailed');
            updateDrawioLayouts();
        }

        function updateDrawioLayouts() {
            if (!currentRun || !currentRun.files) return;
            const container = document.getElementById('layoutBtnGroup');
            const filteredFiles = currentRun.files.filter(f => f.type === activeDrawioType);
            
            if(filteredFiles.length === 0) {
                container.innerHTML = '<span style="color:var(--text-dim); font-size:0.85rem;">Unavailable</span>';
                loadDrawioDiagram(null);
                return;
            }
            
            let selectedFile = filteredFiles.find(f => f.layout === 'circular') || filteredFiles[0];
            activeDrawioLayout = selectedFile.layout;
            
            container.innerHTML = filteredFiles.map(f => `
                <button class="layout-btn ${f.layout === activeDrawioLayout ? 'active' : ''}" onclick="switchDrawioLayout('${f.layout}')">${f.layout_label || f.layout}</button>
            `).join('');
            
            loadDrawioDiagram(selectedFile);
        }

        function switchDrawioLayout(layout) {
            activeDrawioLayout = layout;
            const file = currentRun.files.find(f => f.type === activeDrawioType && f.layout === activeDrawioLayout);
            loadDrawioDiagram(file);
        }

        function loadDrawioDiagram(file) {
            const viewerFrame = document.getElementById('drawio-viewer');
            const offlinePanel = document.getElementById('offlineFallback');
            const loader = document.getElementById('loader');
            const downloadBtn = document.getElementById('headerDownloadBtn');
            
            if (!file) {
                viewerFrame.src = 'about:blank';
                offlinePanel.style.display = 'none';
                downloadBtn.style.display = 'none';
                return;
            }
            
            const filePath = file.path;
            currentFilename = file.filename;
            downloadBtn.href = filePath;
            downloadBtn.style.display = 'inline-block';
            
            if (isLocalProtocol) {
                viewerFrame.src = 'about:blank';
                offlinePanel.style.display = 'flex';
                document.getElementById('fallbackDownloadBtn').href = filePath;
                loader.style.display = 'none';
                return;
            }
            
            offlinePanel.style.display = 'none';
            loader.style.display = 'flex';
            
            fetch(filePath)
                .then(r => r.text())
                .then(xml => {
                    xmlContent = xml;
                    viewerFrame.src = 'viewer.html';
                })
                .catch(err => {
                    console.error(err);
                    loader.style.display = 'none';
                });
        }

        function downloadCurrentDiagram(event) {
            if (!xmlContent || !currentFilename) return;
            event.preventDefault();
            const blob = new Blob([xmlContent], { type: 'application/octet-stream' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = currentFilename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }

        function toggleTheaterMode() {
            document.body.classList.toggle('theater-mode');
            setTimeout(() => {
                if (nativeGraph) {
                    nativeGraph.resize();
                    nativeGraph.fitToScreen();
                }
            }, 100);
        }

        /* ====================================================================
         * Phase 4 & 5: Path Tracing UI & Interaction Functions
         * ==================================================================== */

        let currentContextNode = null;

        function populateTraceDatalist(dataset) {
            const list = document.getElementById('topologyNodeList');
            if (!list || !dataset || !dataset.nodes) return;
            const sorted = [...dataset.nodes].sort((a, b) => a.id.localeCompare(b.id));
            list.innerHTML = sorted.map(n => `<option value="${n.id}">${n.tier ? '[' + n.tier + '] ' : ''}${n.id}</option>`).join('');
        }

        function onTraceInputChange() {
            // Optional reactive validation
        }

        function triggerPathTrace() {
            if (!nativeGraph) return;
            const srcInp = document.getElementById('traceSourceInput');
            const dstInp = document.getElementById('traceTargetInput');
            const src = srcInp ? srcInp.value.trim() : '';
            const dst = dstInp ? dstInp.value.trim() : '';

            if (!src || !dst) {
                alert("Please specify both Origin (A) and Target (B) nodes.");
                return;
            }
            if (src === dst) {
                alert("Origin and Target nodes must be different.");
                return;
            }
            if (!nativeGraph.nodeMap.has(src)) {
                alert(`Origin node "${src}" not found in current snapshot.`);
                return;
            }
            if (!nativeGraph.nodeMap.has(dst)) {
                alert(`Target node "${dst}" not found in current snapshot.`);
                return;
            }

            const paths = nativeGraph.calculateTopKPaths(src, dst, 3);
            if (!paths || paths.length === 0) {
                alert(`No viable network route found between "${src}" and "${dst}".`);
                return;
            }

            const clearBtn = document.getElementById('btnClearTrace');
            if (clearBtn) clearBtn.style.display = 'inline-block';

            const selectorGroup = document.getElementById('pathSelectorGroup');
            if (selectorGroup) selectorGroup.style.display = 'flex';

            for (let i = 0; i < 3; i++) {
                const btn = document.getElementById('btnPath' + i);
                if (btn) {
                    if (i < paths.length) {
                        btn.style.display = 'inline-block';
                        btn.innerText = (i === 0) ? `🟢 Path 1 (Optimal)` : (i === 1 ? `🟡 Path 2` : `🔵 Path 3`);
                        btn.title = `${paths[i].hops} Hops, ${paths[i].cumulativeRtt !== null ? paths[i].cumulativeRtt + 'ms' : 'Clean'}`;
                    } else {
                        btn.style.display = 'none';
                    }
                }
            }

            // Option 1: Display Path 1 (Optimal) by default
            selectActivePath(0);
        }

        function selectActivePath(idx) {
            if (!nativeGraph || !nativeGraph.activePaths || nativeGraph.activePaths.length === 0) return;
            const paths = nativeGraph.activePaths;
            if (idx < 0 || idx >= paths.length) idx = 0;

            for (let i = 0; i < 3; i++) {
                const btn = document.getElementById('btnPath' + i);
                if (btn) {
                    if (i === idx) btn.classList.add('active');
                    else btn.classList.remove('active');
                }
            }

            const selectedPath = nativeGraph.setActivePathIndex(idx);
            updatePathSummaryCard(selectedPath, idx);
            renderDrawerRouteDetails(selectedPath, idx);
        }

        function updatePathSummaryCard(p, idx) {
            const card = document.getElementById('pathSummaryCard');
            if (!card || !p) {
                if (card) card.style.display = 'none';
                return;
            }

            const routeTitle = (idx === 0) ? "Path 1 (Optimal)" : `Path ${idx + 1}`;
            document.getElementById('summaryRouteTitle').innerText = routeTitle;
            document.getElementById('summaryRouteEndpoints').innerText = `${p.path[0]} ➔ ${p.path[p.path.length - 1]}`;
            document.getElementById('summaryTotalHops').innerText = `${p.hops} ${p.hops === 1 ? 'Hop' : 'Hops'}`;
            document.getElementById('summaryCumulativeRtt').innerText = (p.cumulativeRtt !== null) ? `${p.cumulativeRtt} ms` : 'Clean';
            document.getElementById('summaryWorstLoss').innerText = (p.worstLoss !== null && p.worstLoss > 0) ? `${p.worstLoss}% Loss` : '0.0% Clean';
            document.getElementById('summaryBottleneckBw').innerText = p.bottleneckStr + (p.bottleneckInterface ? ' @ ' + p.bottleneckInterface : '');

            const hopsListEl = document.getElementById('summaryHopsList');
            if (hopsListEl && p.hopDetails) {
                hopsListEl.innerHTML = p.hopDetails.map((h, hIdx) => {
                    const rttText = (h.rtt !== null) ? `${h.rtt}ms` : 'clean';
                    const rttColor = (h.rtt && h.rtt > 30) ? '#f59e0b' : '#10b981';
                    return `
                        <div style="display:flex; justify-content:space-between; margin-bottom:4px; padding:2px 0; cursor:pointer;" onclick="nativeGraph && nativeGraph.focusHop('${h.from}', '${h.to}')" title="Click to focus hop on graph">
                            <span style="color:var(--text); font-weight:600;">${hIdx + 1}. ${h.from} ➔ ${h.to}</span>
                            <span style="color:${rttColor};">${rttText} (${h.bandwidth})</span>
                        </div>
                    `;
                }).join('');
            }

            card.style.display = 'block';
        }

        function toggleDrawerRouteDetails() {
            const body = document.getElementById('drawerRouteDrilldownBody');
            const icon = document.getElementById('routeDrilldownToggleIcon');
            if (!body) return;
            const isHidden = (body.style.display === 'none');
            body.style.display = isHidden ? 'block' : 'none';
            if (icon) icon.innerText = isHidden ? '▲' : '▼';
        }

        function openDrawerRouteDetails() {
            const drawer = document.getElementById('nodeDrawer');
            if (drawer) drawer.classList.add('open');
            const sec = document.getElementById('drawerRouteTraceSection');
            if (sec) sec.style.display = 'block';
            const body = document.getElementById('drawerRouteDrilldownBody');
            if (body) body.style.display = 'block';
            const icon = document.getElementById('routeDrilldownToggleIcon');
            if (icon) icon.innerText = '▲';
            if (nativeGraph && nativeGraph.activePath) {
                renderDrawerRouteDetails(nativeGraph.activePath, nativeGraph.activePathIdx || 0);
                if (!nativeGraph.selectedNode) {
                    const hostEl = document.getElementById('drawerHostname');
                    if (hostEl) hostEl.innerText = `${nativeGraph.activePath.path[0]} ➔ ${nativeGraph.activePath.path[nativeGraph.activePath.path.length - 1]}`;
                    const tierBadge = document.getElementById('drawerTierBadge');
                    if (tierBadge) {
                        tierBadge.innerText = 'Active Route';
                        tierBadge.style.backgroundColor = 'rgba(56,189,248,0.2)';
                        tierBadge.style.color = '#38bdf8';
                    }
                    const siteBadge = document.getElementById('drawerSiteBadge');
                    if (siteBadge) siteBadge.innerText = 'Multi-Hop Path';
                    const degEl = document.getElementById('drawerDegree');
                    if (degEl) degEl.innerText = nativeGraph.activePath.hops;
                    const bwEl = document.getElementById('drawerBandwidth');
                    if (bwEl) bwEl.innerText = nativeGraph.activePath.bottleneckStr;
                    const neighborsList = document.getElementById('drawerNeighborsList');
                    if (neighborsList) {
                        neighborsList.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-dim); font-size:0.75rem;">See Hop-by-Hop Breakdown above</td></tr>';
                    }
                }
            }
        }

        function renderDrawerRouteDetails(p, idx) {
            const sec = document.getElementById('drawerRouteTraceSection');
            if (!sec || !p) {
                if (sec) sec.style.display = 'none';
                return;
            }
            sec.style.display = 'block';
            const titleEl = document.getElementById('drawerRouteTraceTitle');
            if (titleEl) {
                titleEl.innerText = (idx === 0 ? "Path 1 (Optimal)" : `Path ${idx + 1}`) + ` [${p.path[0]} ➔ ${p.path[p.path.length - 1]}]`;
            }
            document.getElementById('drawerRouteHops').innerText = `${p.hops} ${p.hops === 1 ? 'Hop' : 'Hops'}`;
            document.getElementById('drawerRouteRtt').innerText = (p.cumulativeRtt !== null) ? `${p.cumulativeRtt} ms` : 'Clean';
            document.getElementById('drawerRouteLoss').innerText = (p.worstLoss !== null && p.worstLoss > 0) ? `${p.worstLoss}% Loss` : '0.0% Clean';
            document.getElementById('drawerRouteBottleneck').innerText = p.bottleneckStr + (p.bottleneckInterface ? ' @ ' + p.bottleneckInterface : '');

            const tbody = document.getElementById('drawerRouteHopsTable');
            if (tbody && p.hopDetails) {
                tbody.innerHTML = p.hopDetails.map((h, i) => {
                    const rttColor = (h.rtt && h.rtt > 30) ? '#f59e0b' : '#10b981';
                    const rttStr = (h.rtt !== null) ? `${h.rtt} ms` : 'clean';
                    return `
                        <tr onclick="nativeGraph && nativeGraph.focusHop('${h.from}', '${h.to}')" title="Click to focus hop on graph" style="cursor:pointer;">
                            <td style="font-weight:700; color:#38bdf8;">${i + 1}</td>
                            <td style="color:var(--text); font-weight:600;">${h.from} ➔ ${h.to}</td>
                            <td>${h.localInt || '-'}</td>
                            <td>${h.remoteInt || '-'}</td>
                            <td>${h.bandwidth || '10G'}</td>
                            <td style="color:${rttColor}; font-weight:600;">${rttStr}</td>
                        </tr>
                    `;
                }).join('');
            }
        }

        function clearPathTrace() {
            if (nativeGraph) nativeGraph.clearActivePath();
            const srcInp = document.getElementById('traceSourceInput');
            const dstInp = document.getElementById('traceTargetInput');
            if (srcInp) srcInp.value = '';
            if (dstInp) dstInp.value = '';
            const clearBtn = document.getElementById('btnClearTrace');
            if (clearBtn) clearBtn.style.display = 'none';
            const selectorGroup = document.getElementById('pathSelectorGroup');
            if (selectorGroup) selectorGroup.style.display = 'none';
            const card = document.getElementById('pathSummaryCard');
            if (card) card.style.display = 'none';
            const sec = document.getElementById('drawerRouteTraceSection');
            if (sec) sec.style.display = 'none';
        }

        function checkAutoTrace() {
            const src = document.getElementById('traceSourceInput').value.trim();
            const dst = document.getElementById('traceTargetInput').value.trim();
            if (src && dst && src !== dst) {
                triggerPathTrace();
            }
        }

        function setDrawerNodeAsOrigin() {
            if (!nativeGraph || !nativeGraph.selectedNode) return;
            const inp = document.getElementById('traceSourceInput');
            if (inp) {
                inp.value = nativeGraph.selectedNode.id;
                checkAutoTrace();
            }
        }

        function setDrawerNodeAsTarget() {
            if (!nativeGraph || !nativeGraph.selectedNode) return;
            const inp = document.getElementById('traceTargetInput');
            if (inp) {
                inp.value = nativeGraph.selectedNode.id;
                checkAutoTrace();
            }
        }

        /* Context Menu Interactions */
        function showContextMenu(node, x, y) {
            currentContextNode = node;
            const menu = document.getElementById('canvasContextMenu');
            if (!menu) return;
            document.getElementById('ctxMenuTitle').innerText = node.id + (node.tier ? ' [' + node.tier + ']' : '');
            menu.style.left = Math.min(x, window.innerWidth - 210) + 'px';
            menu.style.top = Math.min(y, window.innerHeight - 200) + 'px';
            menu.style.display = 'block';
        }

        function closeContextMenu() {
            const menu = document.getElementById('canvasContextMenu');
            if (menu) menu.style.display = 'none';
        }

        window.addEventListener('click', () => closeContextMenu());

        function setContextNodeAsOrigin() {
            if (!currentContextNode) return;
            const inp = document.getElementById('traceSourceInput');
            if (inp) {
                inp.value = currentContextNode.id;
                closeContextMenu();
                checkAutoTrace();
            }
        }

        function setContextNodeAsTarget() {
            if (!currentContextNode) return;
            const inp = document.getElementById('traceTargetInput');
            if (inp) {
                inp.value = currentContextNode.id;
                closeContextMenu();
                checkAutoTrace();
            }
        }

        function focusContextNode() {
            if (!currentContextNode || !nativeGraph) return;
            nativeGraph.focusNode(currentContextNode);
            closeContextMenu();
        }

        function openContextNodeDrawer() {
            if (!currentContextNode) return;
            showNodeDrawer(currentContextNode);
            closeContextMenu();
        }

        window.addEventListener('message', function(event) {
            try {
                const data = JSON.parse(event.data);
                if (data.event === 'init') {
                    const iframe = document.getElementById('drawio-viewer');
                    if (iframe && iframe.contentWindow) {
                        iframe.contentWindow.postMessage(JSON.stringify({
                            action: 'load',
                            xml: xmlContent
                        }), '*');
                    }
                    document.getElementById('loader').style.display = 'none';
                }
            } catch (e) {}
        });

        window.addEventListener('DOMContentLoaded', () => {
            renderList();
            if (window.innerWidth < 1024) {
                document.getElementById('sidebar').classList.add('collapsed');
            }
            if(manifest.length > 0) {
                const firstItem = document.querySelector('.run-item');
                if (firstItem && window.innerWidth >= 1024) firstItem.click();
            }
        });

        /* THEME_SCRIPT_JS */
    </script>

    <!-- Micro Context Menu for Canvas Elements -->
    <div id="canvasContextMenu" class="context-menu" style="display:none;">
        <div class="context-menu-title" id="ctxMenuTitle">DEVICE</div>
        <div class="context-menu-item" onclick="setContextNodeAsOrigin()">🚩 Set as Route Origin (A)</div>
        <div class="context-menu-item" onclick="setContextNodeAsTarget()">🎯 Set as Route Target (B)</div>
        <div class="context-menu-divider"></div>
        <div class="context-menu-item" onclick="focusContextNode()">🔍 Focus on Graph</div>
        <div class="context-menu-item" onclick="openContextNodeDrawer()">📋 View Details</div>
    </div>
</body>
</html>
"""
        html_content = html_content.replace("<!-- THEME_HEAD_INIT -->", THEME_HEAD_INIT)
        html_content = html_content.replace("/* THEME_CSS */", THEME_CSS)
        html_content = html_content.replace("<!-- THEME_SWITCHER_HTML -->", THEME_SWITCHER_HTML)
        html_content = html_content.replace("/* THEME_SCRIPT_JS */", THEME_SCRIPT_JS)

        with open(os.path.join(self.topology_dir, "index.html"), 'w', encoding='utf-8') as f:
            f.write(html_content)

        viewer_html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="description" content="Network Topology Interactive Viewer">
    <meta property="og:title" content="Network Topology Viewer">
    <title>Draw.io Offline Viewer</title>
<!-- THEME_HEAD_INIT -->
    <style>
        html, body {
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
            background-color: #ffffff;
        }
        #graph-container {
            width: 100%;
            height: 100%;
            overflow: auto !important;
            position: relative;
        }
        .geDiagramContainer {
            overflow: auto !important;
        }
        
        /* Adjust popup menus and dropdowns to have extreme z-index */
        body > div.mxPopupMenu, 
        body > div.mxWindow,
        body > div.geSidebarContainer {
            z-index: 100000 !important;
        }

        /* Custom Page Tabs Bar at the bottom */
        #page-tabs-bar {
            width: 100%;
            height: 40px;
            background-color: #0f172a; /* Dark slate matching NOC dashboard */
            border-top: 1px solid #334155;
            display: flex;
            align-items: center;
            padding: 0 12px;
            box-sizing: border-box;
            gap: 8px;
            overflow-x: auto;
            white-space: nowrap;
            scrollbar-width: none; /* Firefox */
        }
        :root[data-theme="light"] #page-tabs-bar {
            background-color: #f1f5f9;
            border-top: 1px solid #cbd5e1;
        }
        :root[data-theme="hightext"] #page-tabs-bar {
            background-color: #000000;
            border-top: 2px solid #ffffff;
        }
        #page-tabs-bar::-webkit-scrollbar {
            display: none; /* Chrome/Safari */
        }
        .page-tab {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: #94a3b8;
            padding: 6px 12px;
            border-radius: 4px;
            font-family: system-ui, -apple-system, sans-serif;
            font-size: 0.8rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .page-tab:hover {
            background: rgba(255, 255, 255, 0.1);
            color: #f1f5f9;
            border-color: rgba(255, 255, 255, 0.2);
        }
        .page-tab.active {
            background: #2563eb;
            color: #ffffff;
            border-color: #3b82f6;
            box-shadow: 0 0 10px rgba(37, 99, 255, 0.3);
        }
        :root[data-theme="light"] .page-tab {
            background: #e2e8f0;
            border-color: #cbd5e1;
            color: #475569;
        }
        :root[data-theme="light"] .page-tab:hover {
            background: #cbd5e1;
            color: #0f172a;
        }
        :root[data-theme="light"] .page-tab.active {
            background: #0284c7;
            color: #ffffff;
            border-color: #0284c7;
            box-shadow: 0 0 8px rgba(2, 132, 199, 0.3);
        }
        :root[data-theme="hightext"] .page-tab {
            background: #000000;
            border: 1px solid #ffffff;
            color: #ffffff;
        }
        :root[data-theme="hightext"] .page-tab:hover {
            background: #222222;
            color: #ffff00;
        }
        :root[data-theme="hightext"] .page-tab.active {
            background: #ffff00;
            color: #000000;
            border: 2px solid #ffffff;
            font-weight: bold;
        }

        /* Force cursor during dragging */
        body.grabbing, body.grabbing * {
            cursor: grabbing !important;
        }
    </style>
    <script src="viewer-static.min.js"></script>
</head>
<body>
    <div id="graph-container"></div>
    <div id="page-tabs-bar" style="display: none;"></div>
    <script>
        let activeXmlContent = null;
        let activePageIndex = 0;

        window.parent.postMessage(JSON.stringify({ event: 'init' }), '*');

        window.addEventListener('message', function(event) {
            try {
                const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
                const newTheme = (data && data.theme) ? data.theme : null;
                if (newTheme) {
                    document.documentElement.setAttribute('data-theme', newTheme);
                }
                if (data.action === 'load' && data.xml) {
                    activeXmlContent = data.xml;
                    activePageIndex = 0;
                    renderGraph(activeXmlContent, 0);
                    renderPageTabs(activeXmlContent);
                }
            } catch (e) {}
        });

        window.addEventListener('storage', function(e) {
            if ((e.key === 'ndx_theme' || e.key === 'nde_theme') && e.newValue) {
                document.documentElement.setAttribute('data-theme', e.newValue);
            }
        });

        function parseDiagramPages(xmlString) {
            const pages = [];
            try {
                const parser = new DOMParser();
                const xmlDoc = parser.parseFromString(xmlString, "text/xml");
                const diagrams = xmlDoc.getElementsByTagName("diagram");
                for (let i = 0; i < diagrams.length; i++) {
                    pages.push({
                        index: i,
                        name: diagrams[i].getAttribute("name") || ("Page " + (i + 1))
                    });
                }
            } catch (e) {
                console.warn("DOMParser failed, using regex fallback:", e);
            }
            
            if (pages.length === 0) {
                const re = /<diagram\\s+[^>]*name="([^"]+)"/g;
                let match;
                let index = 0;
                while ((match = re.exec(xmlString)) !== null) {
                    pages.push({
                        index: index++,
                        name: match[1]
                    });
                }
            }
            return pages;
        }

        function renderPageTabs(xmlString) {
            const tabsBar = document.getElementById('page-tabs-bar');
            const graphContainer = document.getElementById('graph-container');
            tabsBar.innerHTML = '';
            
            const pages = parseDiagramPages(xmlString);
            if (pages.length <= 1) {
                tabsBar.style.display = 'none';
                graphContainer.style.height = '100%';
                return;
            }
            
            tabsBar.style.display = 'flex';
            graphContainer.style.height = 'calc(100% - 40px)';
            
            pages.forEach(page => {
                const btn = document.createElement('button');
                btn.className = 'page-tab' + (page.index === activePageIndex ? ' active' : '');
                btn.innerText = page.name;
                btn.addEventListener('click', function() {
                    if (page.index === activePageIndex) return;
                    activePageIndex = page.index;
                    
                    document.querySelectorAll('.page-tab').forEach(t => t.classList.remove('active'));
                    btn.classList.add('active');
                    
                    renderGraph(activeXmlContent, page.index);
                });
                tabsBar.appendChild(btn);
            });
        }

        function renderGraph(xmlContent, pageIndex = 0) {
            const container = document.getElementById('graph-container');
            container.innerHTML = '';
            
            const graphDiv = document.createElement('div');
            graphDiv.className = 'mxgraph';
            graphDiv.style.width = '100%';
            graphDiv.style.height = '100%';
            
            graphDiv.setAttribute('data-mxgraph', JSON.stringify({
                xml: xmlContent,
                lightbox: false,
                nav: true,
                resize: true,
                page: pageIndex,
                toolbar: 'pages zoom layers tags',
                edit: '_blank'
            }));
            
            container.appendChild(graphDiv);
            
            if (window.GraphViewer && typeof window.GraphViewer.createViewerForElement === 'function') {
                initViewer(graphDiv);
            } else {
                let attempts = 0;
                const interval = setInterval(function() {
                    attempts++;
                    if (window.GraphViewer && typeof window.GraphViewer.createViewerForElement === 'function') {
                        clearInterval(interval);
                        initViewer(graphDiv);
                    } else if (attempts > 30) {
                        clearInterval(interval);
                    }
                }, 100);
            }
        }

        function initViewer(div) {
            try {
                window.GraphViewer.createViewerForElement(div);
                
                // Poll for the graph instance to ensure it is fully initialized and attached
                let pollAttempts = 0;
                const pollInterval = setInterval(function() {
                    pollAttempts++;
                    const graph = findGraphInstance(div);
                    if (graph) {
                        clearInterval(pollInterval);
                        applyGraphConfiguration(graph);
                        console.log("Successfully configured graph after " + (pollAttempts * 100) + "ms");
                    } else if (pollAttempts > 100) { // Timeout after 10 seconds
                        clearInterval(pollInterval);
                        console.warn("Failed to find mxGraph instance after 10 seconds.");
                    }
                }, 100);
            } catch (e) {
                console.error("Error creating viewer:", e);
            }
        }

        function findGraphInstance(div) {
            // 1. Check in GraphViewer.viewers for active graph whose container is in the DOM
            if (window.GraphViewer && window.GraphViewer.viewers) {
                for (let i = window.GraphViewer.viewers.length - 1; i >= 0; i--) {
                    const v = window.GraphViewer.viewers[i];
                    if (v && v.graph && v.graph.container && document.body.contains(v.graph.container)) {
                        return v.graph;
                    }
                }
            }
            
            // 2. Fallback: Check direct properties of the placeholder
            if (div.mxGraph) return div.mxGraph;
            if (div.graph && div.graph.panningHandler) return div.graph;
            
            // 3. Fallback: Search the entire active DOM body recursively for the mxGraph instance
            function searchDOM(el) {
                if (el.mxGraph) return el.mxGraph;
                if (el.graph && el.graph.panningHandler) return el.graph;
                for (let i = 0; i < el.childNodes.length; i++) {
                    const result = searchDOM(el.childNodes[i]);
                    if (result) return result;
                }
                return null;
            }
            return searchDOM(document.body);
        }

        function applyGraphConfiguration(graph) {
            // Keep graph disabled to prevent mxGraph from intercepting mouse dragging
            graph.setEnabled(false);
            
            // Enable scrollbars in mxGraph
            graph.useScrollbarsForPanning = true;
            graph.panningEnabled = false; // Disable mxGraph's native panning to prevent conflicts
            
            // Customize cursor and enable manual grab-to-scroll navigation
            const containerEl = graph.container;
            const mainContainer = document.getElementById('graph-container');
            if (containerEl && mainContainer) {
                let isDown = false;
                let startX, startY;
                let scrollLeft, scrollTop;
                let mainScrollLeft, mainScrollTop;
                let hasDragged = false;
                
                containerEl.style.cursor = 'grab';
                mainContainer.style.cursor = 'grab';
                
                // Capture phase on mousedown to intercept pointer interactions early
                containerEl.addEventListener('mousedown', function(e) {
                    if (e.button !== 0) return; // Left mouse button only
                    isDown = true;
                    hasDragged = false;
                    startX = e.clientX;
                    startY = e.clientY;
                    scrollLeft = containerEl.scrollLeft;
                    scrollTop = containerEl.scrollTop;
                    mainScrollLeft = mainContainer.scrollLeft;
                    mainScrollTop = mainContainer.scrollTop;
                }, true);
                
                // Use window events to capture mouse dragging outside diagram container bounds
                window.addEventListener('mousemove', function(e) {
                    if (!isDown) return;
                    const dx = e.clientX - startX;
                    const dy = e.clientY - startY;
                    
                    // Only treat as drag if mouse moved at least 3 pixels, preserving standard click events
                    if (!hasDragged && (Math.abs(dx) > 3 || Math.abs(dy) > 3)) {
                        hasDragged = true;
                        document.body.classList.add('grabbing');
                    }
                    
                    if (hasDragged) {
                        containerEl.scrollLeft = scrollLeft - dx;
                        containerEl.scrollTop = scrollTop - dy;
                        mainContainer.scrollLeft = mainScrollLeft - dx;
                        mainContainer.scrollTop = mainScrollTop - dy;
                        e.preventDefault();
                        e.stopPropagation(); // Stop browser text selection/default dragging
                    }
                }, true);
                
                const clearDragState = function(e) {
                    if (isDown) {
                        isDown = false;
                        document.body.classList.remove('grabbing');
                        if (hasDragged) {
                            e.preventDefault();
                            e.stopPropagation();
                        }
                    }
                };
                
                window.addEventListener('mouseup', clearDragState, true);
                window.addEventListener('mouseleave', clearDragState, true);
            }
        }
    </script>
</body>
</html>"""
        viewer_html_content = viewer_html_content.replace("<!-- THEME_HEAD_INIT -->", THEME_HEAD_INIT)

        with open(os.path.join(self.topology_dir, "viewer.html"), 'w', encoding='utf-8') as f:
            f.write(viewer_html_content)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate Network Topology Dashboard")
    parser.add_argument("--infos_dir", default="infos", help="Base directory for collections")
    parser.add_argument("--force-rebuild", "-f", action="store_true", help="Force rebuilding all topology data payloads from scratch")
    args = parser.parse_args()
    TopologyEngine(args.infos_dir).run(force_rebuild=args.force_rebuild)
