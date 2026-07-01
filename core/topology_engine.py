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

    def run(self):
        print(f"[*] Analyzing topology base: {self.topology_dir}")
        self._ensure_dirs()
        
        runs = self._scan_runs()
        if not runs:
            print(f"{self.C_YELLOW}[!] No topology runs found in {self.topology_dir}.{self.C_RESET}")
            # Even if empty, write the dashboard so it exists
            self._update_dashboard()
            self._write_manifest([])
            return

        # Build manifest
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
        html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="description" content="Network Topology Interactive Visualizer">
    <meta property="og:title" content="Network Topology Dashboard">
    <title>Network Topology Portal</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #020617;
            --sidebar-bg: #0f172a;
            --accent: #06b6d4; /* Vibrant Cyan */
            --accent-hover: #0891b2;
            --text: #f8fafc;
            --text-dim: #94a3b8;
            --success: #10b981;
            --border: #1e293b;
            --glass: rgba(15, 23, 42, 0.7);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-dark); color: var(--text); display: flex; height: 100vh; overflow: hidden; width: 100vw; max-width: 100%; }

        /* Sidebar Styles */
        .sidebar { width: 300px; background-color: var(--sidebar-bg); border-right: 1px solid var(--border); display: flex; flex-direction: column; z-index: 100; box-shadow: 10px 0 30px rgba(0,0,0,0.5); transition: margin-left 0.3s ease; flex-shrink: 0; }
        .sidebar.collapsed { margin-left: -300px; }
        .sidebar .header { padding: 30px 24px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; background: radial-gradient(circle at top left, rgba(6,182,212,0.1), transparent);}
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

        /* Main Content */
        .main-content { flex: 1; min-width: 0; display: flex; flex-direction: column; position: relative; background: radial-gradient(circle at top right, #0f172a, #020617); overflow: hidden; }
        
        .hud-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding: 15px 25px;
            background: rgba(15, 23, 42, 0.4);
            backdrop-filter: blur(10px);
            position: relative;
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
        .sidebar-toggle-btn { background: var(--glass); backdrop-filter: blur(10px); color: white; border: 1px solid var(--border); padding: 8px 12px; border-radius: 6px; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 8px; transition: all 0.2s; font-size: 0.85rem; }
        .sidebar-toggle-btn:hover { border-color: var(--accent); color: var(--accent); }
        .back-portal {
            background: var(--glass);
            backdrop-filter: blur(10px);
            color: var(--accent);
            border: 1px solid var(--border);
            padding: 8px 12px;
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
            color: #fff;
            background: rgba(6, 182, 212, 0.15);
            box-shadow: 0 0 10px rgba(6, 182, 212, 0.2);
        }

        #welcome { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 40px; }
        #welcome .icon { font-size: 4rem; margin-bottom: 20px; }
        #welcome h2 { font-family: 'Outfit'; color: var(--accent); font-size: 3rem; font-weight: 800; margin-bottom: 10px; }
        #welcome p { color: var(--text-dim); font-size: 1.1rem; }

        #dashboardOverlay { display: none; flex-direction: column; flex: 1; padding: 20px 25px; overflow: hidden; min-height: 0; }
        
        /* Topology Selector Panel */
        .topo-controls { display: flex; justify-content: space-between; align-items: center; background: rgba(15, 23, 42, 0.8); border: 1px solid var(--border); padding: 12px 20px; border-radius: 6px; margin-bottom: 15px; flex-wrap: wrap; gap: 15px; }
        
        .topo-tabs { display: flex; gap: 10px; }
        .tab-btn { background: transparent; border: 1px solid var(--border); color: var(--text-dim); padding: 8px 16px; border-radius: 6px; font-weight: 600; cursor: pointer; transition: all 0.2s; font-size: 0.85rem; }
        .tab-btn.active { background: rgba(6, 182, 212, 0.1); border-color: var(--accent); color: var(--accent); }
        .tab-btn:hover:not(.active) { background: rgba(255, 255, 255, 0.05); color: var(--text); }

        .layout-options { display: flex; gap: 8px; align-items: center; }
        .layout-label { font-size: 0.8rem; color: var(--text-dim); font-weight: 600; text-transform: uppercase; margin-right: 5px; }
        .layout-btn { background: #020617; border: 1px solid var(--border); color: var(--text-dim); padding: 8px 14px; border-radius: 6px; font-size: 0.8rem; font-weight: 600; cursor: pointer; transition: all 0.2s; }
        .layout-btn:hover:not(.active) { border-color: var(--accent); color: var(--text); }
        .layout-btn.active { background: var(--accent); color: var(--bg-dark); font-weight: 700; border-color: var(--accent); box-shadow: 0 0 10px rgba(6, 182, 212, 0.3); }

        /* Viewer Frame area */
        .viewer-container { flex: 1; border: 1px solid var(--border); border-radius: 6px; background: #000; overflow: hidden; position: relative; display: flex; flex-direction: column; }
        iframe#drawio-viewer { width: 100%; height: 100%; border: none; background: #ffffff; }

        /* Fallback offline panel */
        .offline-fallback { display: none; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 40px; height: 100%; background: rgba(15, 23, 42, 0.95); z-index: 10; overflow-y: auto; }
        .offline-fallback h3 { font-family: 'Outfit'; font-size: 1.6rem; color: #f59e0b; margin-bottom: 15px; }
        .offline-fallback p { max-width: 600px; color: var(--text-dim); line-height: 1.6; margin-bottom: 25px; font-size: 0.95rem; }
        .offline-fallback code { background: #020617; padding: 6px 12px; border-radius: 4px; border: 1px solid var(--border); color: #10b981; font-family: monospace; font-size: 0.9rem; }
        
        .btn-group-download { display: flex; gap: 15px; justify-content: center; flex-wrap: wrap; margin-top: 15px; }
        .btn-action { text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 700; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.5px; cursor: pointer; transition: all 0.2s; display: inline-flex; align-items: center; gap: 8px; }
        .btn-primary { background: var(--accent); color: var(--bg-dark); border: 1px solid var(--accent); }
        .btn-primary:hover { background: var(--accent-hover); box-shadow: 0 0 15px rgba(6,182,212,0.4); transform: translateY(-2px); }
        .btn-secondary { background: transparent; border: 1px solid var(--border); color: var(--text); }
        .btn-secondary:hover { background: rgba(255, 255, 255, 0.05); border-color: var(--text-dim); transform: translateY(-2px); }

        .loader-overlay { display: none; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(2, 6, 23, 0.8); z-index: 5; flex-direction: column; align-items: center; justify-content: center; backdrop-filter: blur(3px); }
        .spinner { width: 50px; height: 50px; border: 4px solid rgba(6, 182, 212, 0.1); border-top: 4px solid var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; margin-bottom: 15px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

        /* Header action button */
        .btn-header-link { background: rgba(6, 182, 212, 0.1); border: 1px solid rgba(6, 182, 212, 0.3); color: var(--accent); text-decoration: none; padding: 6px 12px; border-radius: 6px; font-weight: 700; font-size: 0.75rem; transition: all 0.2s; text-transform: uppercase; }
        .btn-header-link:hover { background: var(--accent); color: var(--bg-dark); }
    </style>
    <script>window.topo_manifest = [];</script>
    <script src="manifest.js"></script>
</head>
<body>
    <div class="sidebar collapsed" id="sidebar">
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
            <div style="display: flex; align-items: center; gap: 10px;">
                <a id="headerDownloadBtn" class="btn-header-link" style="display:none;" href="#" onclick="downloadCurrentDiagram(event)">Download .drawio File</a>
                <a class="back-portal" href="../index.html">← Network Portal</a>
            </div>
        </div>

        <div id="welcome">
            <div class="icon">🕸️</div>
            <h2>Topology Viewer</h2>
            <p>Select a collection date from the history sidebar to load the interactive physical diagrams.</p>
        </div>

        <div id="dashboardOverlay">
            <div class="topo-controls">
                <div class="topo-tabs">
                    <button id="tab-summary" class="tab-btn active" onclick="switchType('summary')">Backbone Summary (SUM)</button>
                    <button id="tab-detailed" class="tab-btn" onclick="switchType('detailed')">Complete (Detailed)</button>
                </div>
                <div class="layout-options">
                    <span class="layout-label">Layout:</span>
                    <div id="layoutBtnGroup" style="display: flex; gap: 6px;">
                        <!-- Dynamic layout buttons go here -->
                    </div>
                </div>
            </div>

            <div class="viewer-container">
                <div class="loader-overlay" id="loader">
                    <div class="spinner"></div>
                    <p style="color: var(--accent); font-family: 'Outfit'; font-size: 1.1rem; font-weight: 600;">Loading Topology...</p>
                </div>

                <!-- Fallback offline panel -->
                <div class="offline-fallback" id="offlineFallback">
                    <h3>Browser Security Restriction (file:// Protocol)</h3>
                    <p>
                        For security reasons (CORS), browsers prevent local XML files from being read automatically.
                        To view this diagram interactively directly in the portal, you can start a local web server.
                    </p>
                    <p>
                        Run the following command in the terminal at the root of the reports directory:
                        <br><br>
                        <code>python3 -m http.server 8000</code>
                        <br><br>
                        Then access in the browser: <a href="http://localhost:8000/topology/" style="color:var(--accent); text-decoration: underline;" target="_blank">http://localhost:8000/topology/</a>
                    </p>
                    <div style="margin: 20px 0; border-top: 1px solid var(--border); width: 100%;"></div>
                    <p>If you want to open it manually now, you can download the diagram and drag it into the web version of Draw.io:</p>
                    
                    <div class="btn-group-download">
                        <a id="fallbackDownloadBtn" class="btn-action btn-primary" href="#" onclick="downloadCurrentDiagram(event)">📥 Download Diagram (.drawio)</a>
                        <a class="btn-action btn-secondary" href="https://app.diagrams.net/" target="_blank">🌐 Go to Draw.io Web</a>
                    </div>
                </div>

                <!-- Interactive Viewer Frame -->
                <iframe id="drawio-viewer" src="about:blank"></iframe>
            </div>
        </div>
    </div>

    <script>
        let manifest = window.topo_manifest || [];
        let currentRun = null;
        let activeType = 'summary'; // 'summary' or 'detailed'
        let activeLayout = null;
        let xmlContent = '';
        let currentFilename = '';
        let viewerLoaded = false;
        let isLocalProtocol = window.location.protocol === 'file:';

        function downloadCurrentDiagram(event) {
            if (isLocalProtocol) {
                return;
            }
            if (!xmlContent || !currentFilename) {
                event.preventDefault();
                return;
            }
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
                <div class="run-item" onclick="selectRun('${m.id}', this)">
                    <div class="run-date">${formatDate(m.id)}</div>
                    <div class="run-id">${m.id}</div>
                </div>
            `).join('');
        }

        function selectRun(id, el) {
            document.querySelectorAll('.run-item').forEach(it => it.classList.remove('active'));
            if(el) el.classList.add('active');
            
            if(window.innerWidth < 768) toggleSidebar();
            
            document.getElementById('welcome').style.display = 'none';
            document.getElementById('dashboardOverlay').style.display = 'flex';
            
            currentRun = manifest.find(m => m.id === id);
            
            document.getElementById('dashTitle').innerText = '🕸️ Mapped Topologies';
            document.getElementById('dashSubTitle').innerText = formatDate(id);
            
            // Auto detect available types for this run
            const hasSummary = currentRun.files.some(f => f.type === 'summary');
            const hasDetailed = currentRun.files.some(f => f.type === 'detailed');
            
            document.getElementById('tab-summary').style.display = hasSummary ? 'inline-block' : 'none';
            document.getElementById('tab-detailed').style.display = hasDetailed ? 'inline-block' : 'none';
            
            if (activeType === 'summary' && !hasSummary) {
                activeType = 'detailed';
            } else if (activeType === 'detailed' && !hasDetailed) {
                activeType = 'summary';
            }
            
            // Update Tab states
            document.getElementById('tab-summary').classList.toggle('active', activeType === 'summary');
            document.getElementById('tab-detailed').classList.toggle('active', activeType === 'detailed');
            
            updateLayouts();
        }

        function switchType(type) {
            if(activeType === type) return;
            activeType = type;
            document.getElementById('tab-summary').classList.toggle('active', type === 'summary');
            document.getElementById('tab-detailed').classList.toggle('active', type === 'detailed');
            updateLayouts();
        }

        function updateLayouts() {
            if (!currentRun) return;
            const container = document.getElementById('layoutBtnGroup');
            
            // Filter files of active type
            const filteredFiles = currentRun.files.filter(f => f.type === activeType);
            
            if(filteredFiles.length === 0) {
                container.innerHTML = '<span style="color:var(--text-dim); font-size:0.85rem;">Unavailable</span>';
                loadDiagram(null);
                return;
            }
            
            // Select default layout: geographic if available, otherwise circular, otherwise first
            let selectedFile = filteredFiles.find(f => f.layout === 'geographic');
            if (!selectedFile) selectedFile = filteredFiles.find(f => f.layout === 'circular');
            if (!selectedFile) selectedFile = filteredFiles[0];
            
            activeLayout = selectedFile.layout;
            
            container.innerHTML = filteredFiles.map(f => `
                <button class="layout-btn ${f.layout === activeLayout ? 'active' : ''}" onclick="switchLayout('${f.layout}')">${f.layout_label}</button>
            `).join('');
            
            loadDiagram(selectedFile);
        }

        function switchLayout(layout) {
            if (activeLayout === layout) return;
            activeLayout = layout;
            
            document.querySelectorAll('.layout-btn').forEach(btn => {
                btn.classList.toggle('active', btn.innerText.toLowerCase().includes(layout.substring(0,3)));
            });
            
            const file = currentRun.files.find(f => f.type === activeType && f.layout === activeLayout);
            loadDiagram(file);
        }

        function loadDiagram(file) {
            const viewerFrame = document.getElementById('drawio-viewer');
            const offlinePanel = document.getElementById('offlineFallback');
            const loader = document.getElementById('loader');
            const downloadBtn = document.getElementById('headerDownloadBtn');
            
            if (!file) {
                viewerFrame.src = 'about:blank';
                offlinePanel.style.display = 'none';
                downloadBtn.style.display = 'none';
                currentFilename = '';
                return;
            }
            
            const filePath = file.path;
            currentFilename = file.filename;
            
            // Setup download links
            downloadBtn.href = filePath;
            downloadBtn.style.display = 'inline-block';
            
            // Handle local file:/// protocol fallback
            if (isLocalProtocol) {
                viewerFrame.style.display = 'none';
                offlinePanel.style.display = 'flex';
                document.getElementById('fallbackDownloadBtn').href = filePath;
                loader.style.display = 'none';
                return;
            }
            
            viewerFrame.style.display = 'block';
            offlinePanel.style.display = 'none';
            loader.style.display = 'flex';
            
            viewerLoaded = false;
            
            // Fetch XML content via AJAX
            fetch(filePath)
                .then(response => {
                    if (!response.ok) throw new Error("Error loading diagram file.");
                    return response.text();
                })
                .then(xml => {
                    xmlContent = xml;
                    // Prepare embedded viewer
                    viewerFrame.src = 'https://viewer.diagrams.net/?embed=1&proto=json&layers=1&nav=1';
                })
                .catch(err => {
                    console.error(err);
                    loader.style.display = 'none';
                    alert("Error retrieving topology XML diagram.");
                });
        }

        // Listen to Draw.io embed API protocol
        window.addEventListener('message', function(event) {
            const allowedOrigins = [
                'https://viewer.diagrams.net',
                'https://embed.diagrams.net',
                'https://app.diagrams.net',
                'https://www.draw.io',
                'https://draw.io'
            ];
            if (!allowedOrigins.includes(event.origin)) return;
            
            try {
                const data = JSON.parse(event.data);
                if (data.event === 'init') {
                    // Send XML to load in viewer
                    const iframe = document.getElementById('drawio-viewer');
                    iframe.contentWindow.postMessage(JSON.stringify({
                        action: 'load',
                        xml: xmlContent
                    }), event.origin);
                    
                    // Hide loader
                    document.getElementById('loader').style.display = 'none';
                    viewerLoaded = true;
                }
            } catch (e) {
                // Ignore parsing errors for other system messages
            }
        });

        window.addEventListener('DOMContentLoaded', () => {
            renderList();
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
        with open(os.path.join(self.topology_dir, "index.html"), 'w', encoding='utf-8') as f:
            f.write(html_content)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate Network Topology Dashboard")
    parser.add_argument("--infos_dir", default="infos", help="Base directory for collections")
    args = parser.parse_args()
    TopologyEngine(args.infos_dir).run()
