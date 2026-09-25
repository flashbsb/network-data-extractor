#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ping Matrix Master Dashboard Generator
======================================
Builds the root ping-matrix navigation index.html, enabling interactive
sidebar selection of all historical snapshot runs and forwarding query parameters.
"""

import os
import json
import shutil
from glob import glob
from pathlib import Path

# Terminal Colors
C_CYAN = '\033[96m'
C_GREEN = '\033[92m'
C_YELLOW = '\033[93m'
C_RED = '\033[91m'
C_RESET = '\033[0m'

def generate_master_dashboard(outbase):
    portal_dir = os.path.join(outbase, "ping-matrix")
    os.makedirs(portal_dir, exist_ok=True)
    index_path = os.path.join(portal_dir, "index.html")
    runs = []
    
    # Ensure outbase is absolute for reliable globbing
    abs_outbase = os.path.abspath(outbase)
    portal_dir = os.path.join(abs_outbase, "ping-matrix")
    os.makedirs(portal_dir, exist_ok=True)

    # Copy history.html, path.html, and chart.js template files from repository to active outbase
    script_dir = Path(__file__).resolve().parent.parent
    src_history = os.path.join(script_dir, "templates", "ping-matrix", "history.html")
    src_path = os.path.join(script_dir, "templates", "ping-matrix", "path.html")
    src_chart = os.path.join(script_dir, "templates", "ping-matrix", "chart.js")
    
    dest_history = os.path.join(portal_dir, "history.html")
    dest_path = os.path.join(portal_dir, "path.html")
    dest_chart = os.path.join(portal_dir, "chart.js")
    
    try:
        if os.path.isfile(src_history) and os.path.abspath(src_history) != os.path.abspath(dest_history):
            shutil.copy2(src_history, dest_history)
        if os.path.isfile(src_path) and os.path.abspath(src_path) != os.path.abspath(dest_path):
            shutil.copy2(src_path, dest_path)
        if os.path.isfile(src_chart) and os.path.abspath(src_chart) != os.path.abspath(dest_chart):
            shutil.copy2(src_chart, dest_chart)
    except Exception as e:
        print(f"    {C_RED}[!] Failed to copy dashboard templates to outbase: {e}{C_RESET}")
    
    # Search for all timestamped run subfolders inside runs/
    run_dirs = sorted(glob(os.path.join(abs_outbase, "runs", "20*_*")), reverse=True)
    
    for run_dir in run_dirs:
        if not os.path.isdir(run_dir):
            continue
        ts_id = os.path.basename(run_dir)
        
        # Check both old location (for compatibility after migration) and new location
        json_file = os.path.join(run_dir, "ping-matrix", "resume", "ping_matrix_list.json")
        html_file = os.path.join(run_dir, "ping-matrix", "resume", "ping_matrix_dashboard.html")
        
        if not os.path.isfile(json_file):
            json_file = os.path.join(run_dir, "resume", "ping_matrix_list.json")
            html_file = os.path.join(run_dir, "resume", "ping_matrix_dashboard.html")
        
        if os.path.isfile(json_file):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Filter out empty or partial runs
                if not data.get("data") or len(data.get("data", [])) == 0:
                    continue

                # Re-render HTML dashboard to update UI code (e.g. activeCols column pruning)
                try:
                    from core.ping_matrix import render_ping_matrix_html
                    updated_html = render_ping_matrix_html(data)
                    with open(html_file, 'w', encoding='utf-8') as hf:
                        hf.write(updated_html)
                except Exception:
                    pass
                
                metadata = data.get("metadata", {})
                health = metadata.get("network_health", {})
                node_count = metadata.get("nodes_connected", 0)
                
                # Derive display date from folder name YYYYMMDD_HHMMSS
                try:
                    dt_label = f"{ts_id[:4]}-{ts_id[4:6]}-{ts_id[6:8]} {ts_id[9:11]}:{ts_id[11:13]}:{ts_id[13:15]}"
                except (IndexError, ValueError):
                    dt_label = ts_id
                
                if "ping-matrix" in html_file:
                    rel_path = f"../runs/{ts_id}/ping-matrix/resume/ping_matrix_dashboard.html"
                else:
                    rel_path = f"../runs/{ts_id}/resume/ping_matrix_dashboard.html"
                
                runs.append({
                    "id": ts_id,
                    "label": dt_label,
                    "nodes": node_count,
                    "healthy": health.get("healthy", 0),
                    "warn": health.get("warning", 0),
                    "crit": health.get("critical", 0),
                    "dead": health.get("dead", 0),
                    "path": rel_path
                })
            except Exception:
                continue

    if not runs:
        print(f"    {C_YELLOW}[!] No valid Ping Matrix runs found in: {portal_dir}{C_RESET}")
        print(f"    {C_YELLOW}    (Run with --ping-matrix to generate new runs){C_RESET}")
        return

    # Sort runs by ID descending
    runs.sort(key=lambda x: x["id"], reverse=True)

    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="description" content="Ping Matrix Historical Snapshots Navigation Portal">
    <meta property="og:title" content="Ping Matrix Master Index">
    <title>Ping Matrix Master Index</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; }
        body { margin: 0; padding: 0; font-family: 'Inter', sans-serif; display: flex; height: 100vh; background: #020617; color: #e2e8f0; overflow: hidden; }
        
        /* Sidebar */
        .sidebar { 
            width: 320px; min-width: 320px;
            background: #0f172a; 
            border-right: 1px solid rgba(255,255,255,0.05); 
            display: flex; flex-direction: column;
            box-shadow: 10px 0 30px rgba(0,0,0,0.5);
            z-index: 10;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .sidebar.collapsed { width: 0; min-width: 0; border-right: none; overflow: hidden; }
        
        .toggle-sidebar {
            background: rgba(15, 23, 42, 0.9); backdrop-filter: blur(8px);
            border: 1px solid rgba(56,189,248,0.3); color: #38bdf8;
            padding: 8px 12px; border-radius: 8px; cursor: pointer;
            font-size: 14px; font-weight: 600; transition: all 0.2s;
            display: flex; align-items: center; gap: 8px;
        }
        .toggle-sidebar:hover { background: rgba(15, 23, 42, 1); border-color: #38bdf8; }
        .sidebar-header {
            padding: 25px 20px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .sidebar-header .sidebar-title {
            font-family: 'Outfit', sans-serif;
            font-size: 22px; font-weight: 800; margin: 0;
            background: linear-gradient(90deg, #38bdf8, #818cf8);
            -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
        }
        .sidebar-header p { font-size: 11px; color: #64748b; margin: 5px 0 0 0; text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }
        
        .run-list { flex-grow: 1; overflow-y: auto; padding: 15px 12px; }
        .run-list::-webkit-scrollbar { width: 4px; }
        .run-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 10px; }
        
        .run-item {
            padding: 16px; margin-bottom: 12px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px; cursor: pointer;
            transition: all 0.2s ease;
        }
        .run-item:hover {
            background: rgba(56, 189, 248, 0.05);
            border-color: rgba(56, 189, 248, 0.3);
            transform: translateY(-2px);
        }
        .run-item.active {
            background: rgba(56, 189, 248, 0.1);
            border-color: #38bdf8;
        }
        .run-item .date { font-weight: 600; font-size: 14px; margin-bottom: 6px; }
        .run-item .stats { display: flex; gap: 8px; font-size: 11px; }
        .stat-group { display: flex; align-items: center; gap: 4px; background: rgba(0,0,0,0.2); padding: 2px 6px; border-radius: 4px; }
        .stat-dot { width: 6px; height: 6px; border-radius: 50%; }
        .nodes-badge { float: right; font-size: 10px; background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 4px; color: #94a3b8; }
        
        /* Main View */
        .main-content { flex-grow: 1; display: flex; flex-direction: column; height: 100vh; position: relative; }
        iframe { width: 100%; height: 100%; border: none; background: #020617; }
        
        .hud-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            padding: 15px 25px;
            background: rgba(15, 23, 42, 0.4);
            backdrop-filter: blur(8px);
            position: sticky;
            top: 0;
            z-index: 300;
            width: 100%;
        }
        .hud-title h1 {
            font-size: 1.5rem;
            font-weight: 800;
            color: #38bdf8;
            font-family: 'Outfit', sans-serif;
            margin: 0;
        }
        .hud-title p {
            font-size: 0.7rem;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-top: 2px;
        }
        .back-portal {
            background: rgba(15, 23, 42, 0.9); backdrop-filter: blur(8px);
            border: 1px solid rgba(56,189,248,0.3); color: #38bdf8;
            padding: 8px 12px; border-radius: 8px; cursor: pointer;
            font-size: 14px; font-weight: 600; text-decoration: none;
            transition: all 0.2s; display: flex; align-items: center; gap: 8px;
        }
        .back-portal:hover { background: rgba(15, 23, 42, 1); border-color: #38bdf8; box-shadow: 0 0 10px rgba(56,189,248,0.2); }
        
        #placeholder {
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            text-align: center; transition: opacity 0.3s ease;
        }
        #placeholder h2 { font-family: 'Outfit', sans-serif; font-size: 28px; margin-bottom: 10px; color: #1e293b; }
        #placeholder p { color: #0f172a; font-weight: 600; }
        
        .footer-logo {
            padding: 15px; text-align: center; font-size: 11px; color: #334155;
            border-top: 1px solid rgba(255,255,255,0.03);
        }
    </style>
</head>
<body>
    <div class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <div class="sidebar-title">📡 Ping Matrix</div>
            <p>Historical Analysis Portal</p>
        </div>
        <div class="run-list">
"""
    for r in runs:
        html += f"""
            <div class="run-item" onclick="loadRun('{r['path']}', this)">
                <div class="nodes-badge">{r['nodes']} Nodes</div>
                <div class="date">📅 {r['label']}</div>
                <div class="stats">
                    <div class="stat-group" title="Healthy"><span class="stat-dot" style="background:#4ade80"></span><span class="stat-val">{r['healthy']}</span></div>
                    <div class="stat-group" title="Warning"><span class="stat-dot" style="background:#fbbf24"></span><span class="stat-val">{r['warn']}</span></div>
                    <div class="stat-group" title="Critical"><span class="stat-dot" style="background:#f87171"></span><span class="stat-val">{r['crit']}</span></div>
                    <div class="stat-group" title="Dead"><span class="stat-dot" style="background:#475569"></span><span class="stat-val">{r['dead']}</span></div>
                </div>
            </div>"""

    html += """
        </div>
        <div class="footer-logo">
            Powered by <strong>network-data-extractor</strong>
        </div>
    </div>
    <div class="main-content">
        <div class="hud-header">
            <div style="display: flex; align-items: center; gap: 15px;">
                <button class="toggle-sidebar" onclick="toggleSidebar()" title="Toggle Sidebar">☰ HISTORY</button>
                <div class="hud-title">
                    <h1>📡 Ping Matrix Portal</h1>
                    <p>Historical Analysis Portal</p>
                </div>
            </div>
            <a class="back-portal" href="../index.html">← Network Portal</a>
        </div>
        <iframe id="viewer" src="about:blank"></iframe>
        <div id="placeholder">
            <h2>No run selected</h2>
            <p>Select a historical run from the sidebar to view the dashboard</p>
        </div>
    </div>
    
    <script>
        function toggleSidebar() {
            document.getElementById('sidebar').classList.toggle('collapsed');
        }

        function loadRun(path, el) {
            // Forward query parameters to the iframe
            const indexParams = new URLSearchParams(window.location.search);
            const origin = indexParams.get('origin');
            const dest = indexParams.get('dest');
            let iframeUrl = path;
            const iframeParams = new URLSearchParams();
            if (origin) iframeParams.set('origin', origin);
            if (dest) iframeParams.set('dest', dest);
            
            // Force reload by adding a cache-busting timestamp
            iframeParams.set('t', Date.now());
            
            iframeUrl += '?' + iframeParams.toString();

            document.getElementById('viewer').src = iframeUrl;
            document.getElementById('placeholder').style.display = 'none';
            document.querySelectorAll('.run-item').forEach(item => item.classList.remove('active'));
            if(el) el.classList.add('active');
            
            // Auto-collapse sidebar on smaller screens after selection
            if (window.innerWidth < 1024) {
                document.getElementById('sidebar').classList.add('collapsed');
            }
        }
        
        // Auto-load first or matched run
        window.onload = () => {
            const indexParams = new URLSearchParams(window.location.search);
            const runId = indexParams.get('run');
            let matchedRun = null;
            if (runId && runId !== 'undefined' && runId !== 'null') {
                const items = document.querySelectorAll('.run-item');
                for (let item of items) {
                    const onclickAttr = item.getAttribute('onclick');
                    if (onclickAttr && onclickAttr.includes(runId)) {
                        matchedRun = item;
                        break;
                    }
                }
            }
            
            if (window.innerWidth < 1024) {
                document.getElementById('sidebar').classList.add('collapsed');
            }
            const runToSelect = matchedRun || document.querySelector('.run-item');
            if (runToSelect) {
                setTimeout(() => runToSelect.click(), 50);
            }
        };
    </script>
</body>
</html>
"""
    try:
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"\n{C_CYAN}--- Master Index Generated ---{C_RESET}")
        print(f"[*] Portal available at: {index_path}")
    except Exception as e:
        print(f"\n{C_RED}[!] Failed to generate Master Index: {e}{C_RESET}")
