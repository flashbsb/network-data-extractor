import os
import json
import csv
from glob import glob

class DiffEngine:
    def __init__(self, base_path):
        self.base_path = base_path
        # Store the diff workspace inside the base collection folder for better organization
        self.diff_dir = os.path.join(base_path, "diff")
        self.data_dir = os.path.join(self.diff_dir, "data")
        self.reports_dir = os.path.join(self.diff_dir, "reports")
        
        # ANSI Colors
        self.C_CYAN = '\033[96m'
        self.C_GREEN = '\033[92m'
        self.C_YELLOW = '\033[93m'
        self.C_RED = '\033[91m'
        self.C_RESET = '\033[0m'

    def run(self, force_rebuild=False):
        print(f"[*] Base path: {self.base_path}")
        self._ensure_dirs()
        
        # 1. Scan for collections
        collections = self._scan_collections()
        if not collections:
            print(f"{self.C_RED}[!] No collections found in {self.base_path}.{self.C_RESET}")
            return

        # 2. Prune old data (Sync deleted folders)
        self._prune_workspace(collections)

        # 3. Process/Normalize data
        manifest = []
        for col in collections:
            target_js = os.path.join(self.data_dir, f"{col['id']}.js")
            has_raw = os.path.exists(os.path.join(col['path'], "resume"))
            
            if os.path.exists(target_js) and (not force_rebuild or not has_raw):
                manifest.append({
                    "id": col['id'],
                    "date": col['date'],
                    "file": f"data/{col['id']}.js",
                    "path": col['path']
                })
                continue

            data = self._extract_data(col)
            if data:
                # Save as JS for CORS bypass
                js_content = f"if(!window.run_data) window.run_data = {{}}; window.run_data['{col['id']}'] = {json.dumps(data, indent=4)};"
                with open(target_js, 'w', encoding='utf-8') as f:
                    f.write(js_content)
                
                manifest.append({
                    "id": col['id'],
                    "date": col['date'],
                    "file": f"data/{col['id']}.js",
                    "path": col['path'] # Keep path for report generation
                })

        # 4. Save Manifest (as JS for CORS bypass)
        manifest_js = f"window.diff_manifest = {json.dumps(manifest, indent=4)};"
        with open(os.path.join(self.diff_dir, "manifest.js"), 'w', encoding='utf-8') as f:
            f.write(manifest_js)

        # 5. Generate Reports (Latest vs Previous)
        if len(manifest) >= 2:
            self._generate_diff_reports(manifest[0], manifest[1])

        # 6. Update Dashboard
        self._update_dashboard()
        
        print(f"\n{self.C_GREEN}[+] Drift Workspace ready (Offline Mode: ON)!{self.C_RESET}")
        print(f"[*] Workspace: {os.path.abspath(self.diff_dir)}")
        print(f"[*] Open: {os.path.abspath(os.path.join(self.diff_dir, 'index.html'))}")

    def _ensure_dirs(self):
        for d in [self.diff_dir, self.data_dir, self.reports_dir]:
            if not os.path.exists(d):
                os.makedirs(d)

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
            print(f"{self.C_YELLOW}[*] Pruned {pruned_count} orphaned data files.{self.C_RESET}")

    def _scan_collections(self):
        dirs = sorted(glob(os.path.join(self.base_path, "runs", "20*_*")), reverse=True)
        results = []
        for d in dirs:
            basename = os.path.basename(d)
            json_file = os.path.join(d, "ping-matrix", "resume", "ping_matrix_list.json")
            if not os.path.exists(json_file):
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

    def _extract_data(self, col):
        sources = [
            os.path.join(col['path'], "resume", "interfaces_all.json"),
            os.path.join(col['path'], "resume", "interfaces.all.csv"),
            os.path.join(col['path'], "resume", "interfaces_all.csv")
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
                        with open(src, 'r', encoding='utf-8') as f:
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

    def _generate_diff_reports(self, new_meta, old_meta):
        new_data = self._extract_data(new_meta)
        old_data = self._extract_data(old_meta)
        
        if not new_data or not old_data:
            print(f"{self.C_YELLOW}[!] Could not re-extract data for flat reports.{self.C_RESET}")
            return
            
        old_elements = {d['element'] for d in old_data if d['element']}
        new_elements = {d['element'] for d in new_data if d['element']}
        
        missing_in_new = old_elements - new_elements
        missing_in_old = new_elements - old_elements

        old_map = {f"{d['element']}||{d['interface']}": d for d in old_data}
        new_map = {f"{d['element']}||{d['interface']}": d for d in new_data}
        
        all_keys = set(old_map.keys()) | set(new_map.keys())
        diffs = []
        
        processed_missing_nodes = set()
        
        for key in all_keys:
            old_item = old_map.get(key)
            new_item = new_map.get(key)
            el, iface = key.split('||')
            
            # Fault Isolation Intelligence: Prevent mass interface REMOVED/ADDED if node itself is entirely missing
            if el in missing_in_new:
                if el not in processed_missing_nodes:
                    diffs.append({"type": "NODE_UNREACHABLE", "element": el, "interface": "ALL", "details": {"admin_status": "-", "line_protocol": "NODE OFFLINE", "bandwidth_kbit": "-", "description": "Element missing from new collection (Timeout/Unreachable)"}})
                    processed_missing_nodes.add(el)
                continue
                
            if el in missing_in_old:
                if el not in processed_missing_nodes:
                    diffs.append({"type": "NODE_ADDED", "element": el, "interface": "ALL", "details": {"admin_status": "-", "line_protocol": "NODE ADDED", "bandwidth_kbit": "-", "description": "Element missing from old collection (New Device/Reachable)"}})
                    processed_missing_nodes.add(el)
                continue
            
            if not old_item:
                diffs.append({"type": "ADDED", "element": el, "interface": iface, "details": new_item})
            elif not new_item:
                diffs.append({"type": "REMOVED", "element": el, "interface": iface, "details": old_item})
            else:
                changes = {}
                for field in ["admin_status", "line_protocol", "bandwidth_kbit", "description"]:
                    if str(old_item.get(field, "")) != str(new_item.get(field, "")):
                        changes[field] = [old_item.get(field, ""), new_item.get(field, "")]
                
                if changes:
                    diffs.append({"type": "MODIFIED", "element": el, "interface": iface, "changes": changes})

        report_base = f"diff_{new_meta['id']}_vs_{old_meta['id']}"
        with open(os.path.join(self.reports_dir, f"{report_base}.json"), 'w', encoding='utf-8') as f:
            json.dump(diffs, f, indent=4)
            
        with open(os.path.join(self.reports_dir, f"{report_base}.csv"), 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(["Type", "Element", "Interface", "Field", "Old Value", "New Value"])
            for d in diffs:
                if d['type'] == 'MODIFIED':
                    for field, vals in d['changes'].items():
                        writer.writerow([d['type'], d['element'], d['interface'], field, vals[0], vals[1]])
                else:
                    writer.writerow([d['type'], d['element'], d['interface'], "ALL", "-", "-"])

    def _update_dashboard(self):
        template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="description" content="Network Configuration Drift and Change Analysis Dashboard">
    <meta property="og:title" content="Network Drift Analyzer">
    <title>Network Drift Analysis Workspace</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #0f172a;
            --sidebar-bg: #1e293b;
            --accent: #38bdf8;
            --accent-hover: #0ea5e9;
            --text: #f8fafc;
            --text-dim: #94a3b8;
            --success: #22c55e;
            --warning: #ea580c;
            --danger: #ef4444;
            --border: #334155;
            --glass: rgba(30, 41, 59, 0.7);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-dark); color: var(--text); display: flex; height: 100vh; overflow: hidden; }

        .sidebar { width: 320px; background-color: var(--sidebar-bg); border-right: 1px solid var(--border); display: flex; flex-direction: column; z-index: 100; box-shadow: 10px 0 30px rgba(0,0,0,0.3); transition: margin-left 0.3s cubic-bezier(0.4, 0, 0.2, 1); flex-shrink: 0; }
        .sidebar.collapsed { margin-left: -320px; }
        .sidebar .header { padding: 32px 24px; border-bottom: 1px solid var(--border); background: linear-gradient(to bottom, #1e293b, #0f172a); display: flex; justify-content: space-between; align-items: flex-start;}
        .sidebar .header-text h2 { font-family: 'Outfit'; font-size: 1.4rem; color: var(--accent); letter-spacing: -0.5px; }
        .sidebar .header-text p { font-size: 0.75rem; color: var(--text-dim); margin-top: 4px; text-transform: uppercase; letter-spacing: 1px; }
        .sidebar-close-btn { background: none; border: none; color: var(--text-dim); cursor: pointer; font-size: 1.2rem; transition: color 0.2s; }
        .sidebar-close-btn:hover { color: var(--text); }
        .sidebar .list { flex: 1; overflow-y: auto; padding: 16px; scrollbar-width: thin; scrollbar-color: var(--border) transparent; }

        .run-item { padding: 16px; border-radius: 12px; margin-bottom: 10px; cursor: pointer; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); border: 1px solid transparent; display: flex; gap: 14px; align-items: center; background: rgba(51, 65, 85, 0.3); }
        .run-item:hover { background-color: rgba(51, 65, 85, 0.6); transform: translateX(5px); border-color: rgba(56, 189, 248, 0.3); }
        .run-item.active { background-color: rgba(12, 74, 110, 0.5); border-color: var(--accent); box-shadow: 0 0 20px rgba(56, 189, 248, 0.1); }

        .run-checkbox { width: 20px; height: 20px; cursor: pointer; accent-color: var(--accent); border-radius: 6px; }
        .run-content { flex: 1; min-width: 0; }
        .run-date { font-weight: 600; font-size: 0.95rem; color: var(--text); margin-bottom: 2px; }
        .run-id { font-size: 0.7rem; color: var(--text-dim); font-family: monospace; }

        .sidebar-footer { padding: 24px; background: #0f172a; border-top: 1px solid var(--border); }
        .compare-btn { width: 100%; padding: 14px; background: var(--accent); color: #0f172a; border: none; border-radius: 10px; font-weight: 800; font-size: 0.9rem; cursor: pointer; transition: all 0.2s; box-shadow: 0 4px 15px rgba(56, 189, 248, 0.2); text-transform: uppercase; }
        .compare-btn:hover:not(:disabled) { background: var(--accent-hover); transform: translateY(-2px); box-shadow: 0 6px 20px rgba(56, 189, 248, 0.3); }
        .compare-btn:active:not(:disabled) { transform: translateY(0); }
        .compare-btn:disabled { background: #334155; color: #64748b; cursor: not-allowed; box-shadow: none; opacity: 0.5; }

        .main-content { flex: 1; min-width: 0; display: flex; flex-direction: column; position: relative; background: radial-gradient(circle at top right, #1e293b, #020617); overflow-y: auto; overflow-x: hidden; transition: margin-left 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
        
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
        .sidebar-toggle-btn { background: rgba(15, 23, 42, 0.8); color: white; border: 1px solid var(--border); padding: 10px 15px; border-radius: 8px; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.3); transition: all 0.2s; }
        .sidebar-toggle-btn:hover { background: var(--sidebar-bg); border-color: var(--accent); color: var(--accent); }
        .back-portal {
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid var(--border);
            color: var(--accent);
            padding: 10px 15px;
            border-radius: 8px;
            font-weight: 600;
            text-decoration: none;
            text-transform: uppercase;
            font-size: 0.85rem;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 8px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
        }
        .back-portal:hover {
            background: var(--sidebar-bg);
            border-color: var(--accent);
            color: white;
            box-shadow: 0 0 10px rgba(56,189,248,0.2);
        }

        #welcome { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; max-width: 600px; margin: 0 auto; padding: 40px; animation: fadeIn 1s ease-out; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }

        #compareOverlay { display: none; flex-direction: column; width: 100%; animation: slideIn 0.4s cubic-bezier(0.4, 0, 0.2, 1); }
        @keyframes slideIn { from { opacity: 0; transform: scale(0.98); } to { opacity: 1; transform: scale(1); } }

        .compare-header { padding: 20px 40px; background: var(--sidebar-bg); border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }
        .compare-title-box h2 { font-family: 'Outfit'; font-size: 1.8rem; color: var(--accent); }
        .compare-title-box p { color: var(--text-dim); font-size: 0.9rem; margin-top: 4px; font-weight: 500; }

        .compare-filters { padding: 15px 40px; background: rgba(15, 23, 42, 0.6); border-bottom: 1px solid var(--border); display: flex; gap: 30px; align-items: center; flex-wrap: wrap; }
        .filter-group { display: flex; align-items: center; gap: 12px; }
        .filter-group label { font-size: 0.75rem; font-weight: 700; color: var(--text-dim); text-transform: uppercase; }
        
        .checkbox-group { display: flex; gap: 16px; background: #0f172a; border: 1px solid var(--border); padding: 8px 16px; border-radius: 8px; }
        .checkbox-label { display: flex; align-items: center; gap: 6px; font-size: 0.8rem; font-weight: 600; cursor: pointer; user-select: none; }
        .checkbox-label input { accent-color: var(--accent); width: 16px; height: 16px; cursor: pointer; }
        .cb-mod { color: var(--warning); }
        .cb-add { color: var(--success); }
        .cb-rem { color: var(--danger); }
        .cb-node-add { color: var(--success); text-decoration: underline; }
        .cb-node-rem { color: var(--danger); text-decoration: underline; }

        .input-styled { background: #0f172a; border: 1px solid var(--border); color: white; padding: 10px 16px; border-radius: 8px; font-size: 0.85rem; outline: none; transition: border-color 0.2s; min-width: 250px; }
        .input-styled:focus { border-color: var(--accent); }

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
        .context-menu a:hover {
            background: rgba(6, 182, 212, 0.1);
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

        .compare-body { flex: 1; overflow-y: auto; padding: 30px 40px; scrollbar-width: thin; scrollbar-color: var(--border) transparent; display: flex; flex-direction: column; }
        
        .diff-card { background: var(--sidebar-bg); border-radius: 16px; border: 1px solid var(--border); box-shadow: 0 20px 50px rgba(0,0,0,0.4); display: flex; flex-direction: column; flex: 1; overflow: hidden; }
        .table-responsive { overflow-x: auto; flex: 1; }
        .diff-table { width: 100%; border-collapse: collapse; min-width: 1000px; }
        .diff-table th { background: rgba(51, 65, 85, 0.5); text-align: left; padding: 16px 20px; font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; font-weight: 800; position: sticky; top: 0; z-index: 10; backdrop-filter: blur(5px); }
        .diff-table td { padding: 16px 20px; border-bottom: 1px solid rgba(51, 65, 85, 0.3); font-size: 0.9rem; vertical-align: top; white-space: nowrap; }
        .diff-table td.wrap-col { white-space: normal; min-width: 250px; }
        .diff-table tr:last-child td { border-bottom: none; }
        .diff-table tr:hover td { background: rgba(56, 189, 248, 0.03); }
        
        .tag { padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; display: inline-block; color: white; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }
        .tag-added { background: var(--success); }
        .tag-removed { background: var(--danger); }
        .tag-modified { background: var(--warning); }
        .tag-node_added { background: var(--success); box-shadow: 0 0 8px var(--success); }
        .tag-node_unreachable { background: var(--danger); border: 1px solid white; box-shadow: 0 0 8px var(--danger); }

        .val-change-box { display: flex; flex-direction: column; gap: 6px; min-width: 120px; }
        .drift-step { display: flex; align-items: center; gap: 8px; font-size: 0.85rem; }
        .drift-from { color: var(--text-dim); text-decoration: line-through; opacity: 0.6; }
        .drift-arrow { color: var(--accent); font-weight: 800; font-size: 1.1rem; }
        .drift-to { color: var(--text); font-weight: 700; background: rgba(56, 189, 248, 0.1); padding: 2px 6px; border-radius: 4px; }
        
        .loader { display: none; text-align: center; padding: 40px; margin-top: 50px; }
        .spinner { width: 60px; height: 60px; border: 5px solid rgba(56, 189, 248, 0.1); border-top: 5px solid var(--accent); border-radius: 50%; animation: spin 0.8s cubic-bezier(0.4, 0, 0.2, 1) infinite; margin: 0 auto 20px auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

        /* Tab Styles */
        .hud-tabs { display: flex; gap: 8px; margin-left: 20px; }
        .tab-btn { background: rgba(30, 41, 59, 0.6); border: 1px solid var(--border); color: var(--text-dim); padding: 8px 16px; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 0.85rem; transition: all 0.2s; display: flex; align-items: center; gap: 6px; text-transform: uppercase; }
        .tab-btn:hover { border-color: var(--accent); color: white; }
        .tab-btn.active { background: var(--accent); color: #0f172a; border-color: var(--accent); box-shadow: 0 0 10px rgba(56, 189, 248, 0.2); }

        /* Timeline Tracker Styles */
        #timelineOverlay { display: none; flex-direction: column; width: 100%; animation: slideIn 0.4s cubic-bezier(0.4, 0, 0.2, 1); }
        .timeline-form-card { background: var(--sidebar-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin: 30px 40px 10px 40px; box-shadow: 0 4px 20px rgba(0,0,0,0.2); display: flex; flex-direction: column; gap: 15px; }
        .form-row { display: flex; gap: 20px; flex-wrap: wrap; align-items: flex-end; }
        .form-col { display: flex; flex-direction: column; gap: 8px; flex: 1; min-width: 200px; }
        .form-col label { font-size: 0.75rem; font-weight: 700; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }
        .timeline-btn { padding: 12px 24px; background: var(--accent); color: #0f172a; border: none; border-radius: 8px; font-weight: 800; font-size: 0.85rem; cursor: pointer; transition: all 0.2s; box-shadow: 0 4px 10px rgba(56, 189, 248, 0.15); text-transform: uppercase; display: flex; align-items: center; gap: 8px; height: 38px; justify-content: center; }
        .timeline-btn:hover:not(:disabled) { background: var(--accent-hover); transform: translateY(-1px); box-shadow: 0 6px 15px rgba(56, 189, 248, 0.25); }
        .timeline-btn:disabled { background: #334155; color: #64748b; cursor: not-allowed; opacity: 0.5; box-shadow: none; }

        .timeline-results-container { padding: 10px 40px 30px 40px; flex: 1; display: flex; flex-direction: column; }
        .timeline-placeholder { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; max-width: 600px; margin: 40px auto; padding: 40px; }
        
        .timeline-wrapper { position: relative; padding: 20px 0; max-width: 900px; margin: 0 auto; width: 100%; display: flex; flex-direction: column; gap: 25px; }
        .timeline-wrapper::before { content: ''; position: absolute; left: 19px; top: 0; bottom: 0; width: 2px; background: var(--border); }
        
        .timeline-node { position: relative; padding-left: 50px; display: flex; flex-direction: column; transition: all 0.3s; }
        .timeline-dot { position: absolute; left: 11px; top: 4px; width: 18px; height: 18px; border-radius: 50%; background: var(--border); border: 4px solid var(--bg-dark); z-index: 5; transition: all 0.3s; }
        .timeline-node.active .timeline-dot { background: var(--accent); border-color: var(--bg-dark); box-shadow: 0 0 10px var(--accent); }
        .timeline-node.added .timeline-dot { background: var(--success); }
        .timeline-node.removed .timeline-dot { background: var(--danger); }
        .timeline-node.modified .timeline-dot { background: var(--warning); }
        .timeline-node.baseline .timeline-dot { background: var(--text-dim); }

        .timeline-box { background: var(--sidebar-bg); border: 1px solid var(--border); border-radius: 12px; padding: 18px 24px; box-shadow: 0 4px 15px rgba(0,0,0,0.15); transition: border-color 0.2s; }
        .timeline-node:hover .timeline-box { border-color: rgba(56, 189, 248, 0.3); }
        .timeline-meta { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 10px; }
        .timeline-ts { font-weight: 700; color: var(--accent); font-size: 0.95rem; }
        .timeline-run-id { font-family: monospace; font-size: 0.75rem; color: var(--text-dim); }
        
        .timeline-changes { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 10px; }
        .timeline-change-item { display: flex; flex-direction: column; gap: 4px; font-size: 0.85rem; }
        .timeline-field { font-weight: 700; color: var(--text-dim); text-transform: uppercase; font-size: 0.7rem; }
        
        /* Progress tracker */
        .progress-bar-container { width: 100%; background: #0f172a; border: 1px solid var(--border); height: 8px; border-radius: 4px; overflow: hidden; margin-top: 15px; display: none; }
        .progress-bar-fill { background: var(--accent); height: 100%; width: 0%; transition: width 0.1s ease-out; }

    </style>
    <script>window.run_data = {};</script>
    <script src="manifest.js"></script>
</head>
<body>
    <div class="sidebar collapsed" id="sidebar">
        <div class="header">
            <div class="header-text">
                <h2>📡 HISTORY</h2>
                <p>Snapshot Intelligence</p>
            </div>
            <button class="sidebar-close-btn" onclick="toggleSidebar()">✕</button>
        </div>
        <div class="list" id="runList"></div>
        <div class="sidebar-footer">
            <button id="compareBtn" class="compare-btn" disabled onclick="startComparison()">📊 Compare Snapshots (0/2)</button>
        </div>
    </div>
    
    <div class="main-content">
        <div class="hud-header">
            <div style="display: flex; align-items: center; gap: 15px;">
                <button class="sidebar-toggle-btn" onclick="toggleSidebar()">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
                    HISTORY
                </button>
                <div class="hud-title">
                    <h1 id="dashTitle">⚖️ Drift Analyzer</h1>
                    <p id="dashSubTitle">Select two snapshots from the sidebar</p>
                </div>
                <div class="hud-tabs">
                    <button class="tab-btn active" id="tabCompare" onclick="switchTab('drift')">📊 Compare Snapshots</button>
                    <button class="tab-btn" id="tabTimeline" onclick="switchTab('timeline')">⏱️ Interface Timeline Tracker</button>
                </div>
            </div>
            <a class="back-portal" href="../index.html">← Network Portal</a>
        </div>

        <div id="welcome">
            <div style="font-size: 5rem; margin-bottom: 20px;">🕵️‍♂️</div>
            <div style="font-family:'Outfit'; color:var(--accent); font-size:3.5rem; font-weight:800; margin-bottom:10px; letter-spacing: -1px;">Ready for Audit.</div>
            <p style="color:var(--text-dim); font-size: 1.1rem; font-weight: 500;">Select exactly two snapshots from the sidebar to visualize <span style="color: var(--accent)">configuration drift</span> and network changes.</p>
        </div>

        <div id="compareOverlay">
            <div class="compare-header">
                <div class="compare-title-box">
                    <h2 id="compareTitle">Network Configuration Drift</h2>
                    <p id="compareSubTitle">Comparing Timestamps</p>
                </div>
            </div>
            <div class="compare-filters">
                <div class="filter-group">
                    <label>Search</label>
                    <input type="text" id="filterEl" class="input-styled" placeholder="Hostname or IP..." oninput="applyFilters()" style="min-width: 150px;" aria-label="Filter element">
                    <input type="text" id="excludeEl" class="input-styled" placeholder="Exclude text..." oninput="applyFilters()" style="min-width: 150px;" aria-label="Exclude text">
                </div>
                <div class="filter-group">
                    <label>Change Type</label>
                    <div class="checkbox-group">
                        <label class="checkbox-label cb-mod"><input type="checkbox" class="filter-cb-type" value="MODIFIED" checked onchange="applyFilters()"> MODIFIED</label>
                        <label class="checkbox-label cb-add"><input type="checkbox" class="filter-cb-type" value="ADDED" checked onchange="applyFilters()"> ADDED</label>
                        <label class="checkbox-label cb-rem"><input type="checkbox" class="filter-cb-type" value="REMOVED" checked onchange="applyFilters()"> REMOVED</label>
                        <label class="checkbox-label cb-node-add"><input type="checkbox" class="filter-cb-type" value="NODE_ADDED" checked onchange="applyFilters()"> NODE ADDED</label>
                        <label class="checkbox-label cb-node-rem"><input type="checkbox" class="filter-cb-type" value="NODE_UNREACHABLE" checked onchange="applyFilters()"> NODE UNREACHABLE</label>
                    </div>
                </div>
                <div class="filter-group">
                    <label>Changed Fields (Modified Only)</label>
                    <div class="checkbox-group">
                        <label class="checkbox-label"><input type="checkbox" class="filter-cb-field" value="description" checked onchange="applyFilters()"> Desc</label>
                        <label class="checkbox-label"><input type="checkbox" class="filter-cb-field" value="admin_status" checked onchange="applyFilters()"> Admin</label>
                        <label class="checkbox-label"><input type="checkbox" class="filter-cb-field" value="line_protocol" checked onchange="applyFilters()"> Oper</label>
                        <label class="checkbox-label"><input type="checkbox" class="filter-cb-field" value="bandwidth_kbit" checked onchange="applyFilters()"> Bw</label>
                    </div>
                </div>
                <div class="filter-group">
                    <label>Current State</label>
                    <div class="checkbox-group">
                        <label class="checkbox-label cb-add"><input type="checkbox" class="filter-cb-state" value="UP" checked onchange="applyFilters()"> UP</label>
                        <label class="checkbox-label cb-rem"><input type="checkbox" class="filter-cb-state" value="DOWN" checked onchange="applyFilters()"> DOWN</label>
                        <label class="checkbox-label"><input type="checkbox" class="filter-cb-state" value="OTHER" checked onchange="applyFilters()"> OTHER</label>
                    </div>
                </div>
                <div class="filter-group" style="display: flex; gap: 8px;">
                    <button onclick="clearAllFilters()" style="background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); color: var(--danger); padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 0.8rem; font-weight: 600; transition: all 0.2s; height: 34px;" onmouseover="this.style.background='rgba(239,68,68,0.2)'" onmouseout="this.style.background='rgba(239,68,68,0.1)'">🧹 Clear All</button>
                    <button onclick="selectAllFilters()" style="background: rgba(56,189,248,0.1); border: 1px solid rgba(56,189,248,0.3); color: var(--accent); padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 0.8rem; font-weight: 600; transition: all 0.2s; height: 34px;" onmouseover="this.style.background='rgba(56,189,248,0.2)'" onmouseout="this.style.background='rgba(56,189,248,0.1)'">✅ Select All</button>
                    <button onclick="exportDriftCSV()" style="background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.3); color: var(--success); padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 0.8rem; font-weight: 600; transition: all 0.2s; height: 34px; display: flex; align-items: center; gap: 5px;" onmouseover="this.style.background='rgba(34,197,94,0.2)'" onmouseout="this.style.background='rgba(34,197,94,0.1)'">📥 Export CSV</button>
                </div>
                <div id="statsBox" style="margin-left: auto; display: flex; gap: 20px; font-size: 0.8rem; font-weight: 700; background: rgba(15,23,42,0.8); padding: 10px 20px; border-radius: 8px; border: 1px solid var(--border);">
                    <div id="statMod" style="color: var(--warning)">0 MODIFIED</div>
                    <div id="statAdd" style="color: var(--success)">0 ADDED</div>
                    <div id="statRem" style="color: var(--danger)">0 REMOVED</div>
                    <div id="statNodeAdd" style="color: var(--success); text-decoration: underline;">0 NODE ADDED</div>
                    <div id="statNodeRem" style="color: var(--danger); text-decoration: underline;">0 NODE UNREACHABLE</div>
                </div>
            </div>
            <div class="compare-body">
                <div class="diff-card">
                    <div class="table-responsive">
                        <table class="diff-table">
                            <thead>
                                <tr>
                                    <th>Drift Type</th>
                                    <th>Network Element</th>
                                    <th>Interface</th>
                                    <th>Description / Change Details</th>
                                    <th>Admin</th>
                                    <th>Protocol</th>
                                    <th>Bandwidth</th>
                                </tr>
                            </thead>
                            <tbody id="diffBody"></tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        
        <div id="timelineOverlay">
            <div class="timeline-form-card">
                <div class="form-row">
                    <div class="form-col">
                        <label for="timelineElement">Network Element</label>
                        <input type="text" id="timelineElement" class="input-styled" placeholder="Select or type router..." list="elementsList" onchange="onElementChanged()" aria-label="Select network element">
                        <datalist id="elementsList"></datalist>
                    </div>
                    <div class="form-col">
                        <label for="timelineInterface">Interface</label>
                        <input type="text" id="timelineInterface" class="input-styled" placeholder="Select or type interface..." list="interfacesList" aria-label="Select interface">
                        <datalist id="interfacesList"></datalist>
                    </div>
                    <div class="form-col" style="flex: 0.6; min-width: 150px;">
                        <label for="timelineStart">Start Date</label>
                        <input type="date" id="timelineStart" class="input-styled" style="width: 100%;" aria-label="Start date">
                    </div>
                    <div class="form-col" style="flex: 0.6; min-width: 150px;">
                        <label for="timelineEnd">End Date</label>
                        <input type="date" id="timelineEnd" class="input-styled" style="width: 100%;" aria-label="End date">
                    </div>
                    <button id="trackBtn" class="timeline-btn" onclick="trackTimeline()">📊 Track Changes</button>
                </div>
                <div class="progress-bar-container" id="timelineProgressContainer">
                    <div class="progress-bar-fill" id="timelineProgressFill"></div>
                </div>
            </div>
            
            <div class="timeline-results-container">
                <div id="timelinePlaceholder" class="timeline-placeholder">
                    <div style="font-size: 4rem; margin-bottom: 15px;">⏱️</div>
                    <h2 style="font-family:'Outfit'; color:var(--accent); font-size:2.2rem; font-weight:800; margin-bottom:10px;">Timeline Tracker</h2>
                    <p style="color:var(--text-dim); font-size: 1rem; font-weight: 500;">Select an element, interface, and date range to view its historical change logs.</p>
                </div>
                
                <div id="timelineCard" class="diff-card" style="display: none; padding: 25px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 15px;">
                        <div>
                            <h3 id="timelineTitle" style="font-family: 'Outfit'; font-size: 1.4rem; color: var(--text);">Timeline: -</h3>
                            <p id="timelineSub" style="color: var(--text-dim); font-size: 0.8rem; text-transform: uppercase; margin-top: 4px;"></p>
                        </div>
                        <div style="display: flex; gap: 15px; align-items: center; flex-wrap: wrap;">
                            <div class="checkbox-group">
                                <label class="checkbox-label"><input type="checkbox" class="timeline-cb-field" value="description" checked onchange="applyTimelineFilter()"> Desc</label>
                                <label class="checkbox-label"><input type="checkbox" class="timeline-cb-field" value="admin_status" checked onchange="applyTimelineFilter()"> Admin</label>
                                <label class="checkbox-label"><input type="checkbox" class="timeline-cb-field" value="line_protocol" checked onchange="applyTimelineFilter()"> Oper</label>
                                <label class="checkbox-label"><input type="checkbox" class="timeline-cb-field" value="bandwidth_kbit" checked onchange="applyTimelineFilter()"> Bw</label>
                            </div>
                            <input type="text" id="timelineFilterText" class="input-styled" placeholder="Filter timeline details..." oninput="applyTimelineFilter()" style="min-width: 200px; padding: 8px 12px;" aria-label="Filter timeline details">
                            <button onclick="clearTimelineFilter()" style="background: rgba(255,255,255,0.05); border: 1px solid var(--border); color: var(--text-dim); padding: 8px 12px; border-radius: 8px; cursor: pointer; font-size: 0.8rem; transition: all 0.2s;" onmouseover="this.style.color='white'" onmouseout="this.style.color='var(--text-dim)'">🧹 Clear</button>
                        </div>
                    </div>
                    
                    <div class="table-responsive" style="max-height: 600px;">
                        <div id="timelineList" class="timeline-wrapper"></div>
                    </div>
                </div>
            </div>
        </div>
        
        <div id="loader" class="loader">
            <div class="spinner"></div>
            <h2 style="font-family: 'Outfit'; color: var(--accent);">Analyzing Data Streams...</h2>
            <p style="color: var(--text-dim); margin-top: 10px;">Mapping interfaces and detecting state changes.</p>
        </div>
    </div>

    <script>
        let manifest = window.diff_manifest || [];
        let allDiffs = [];
        let filteredDiffs = [];

        function toggleSidebar() {
            document.getElementById('sidebar').classList.toggle('collapsed');
        }

        // Format raw ID YYYYMMDD_HHMMSS to DD/MM/YYYY HH:MM:SS
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
            // Sort manifest by ID descending to ensure order
            manifest.sort((a,b) => b.id.localeCompare(a.id));
            
            list.innerHTML = manifest.map((m, i) => `
                <div class="run-item" onclick="toggleItem(this)" data-id="${m.id}" data-file="${m.file}">
                    <input type="checkbox" class="run-checkbox" onclick="event.stopPropagation(); updateCount();" aria-label="Select snapshot for comparison">
                    <div class="run-content">
                        <div class="run-date">${formatDate(m.id)}</div>
                        <div class="run-id">${m.id}</div>
                    </div>
                </div>
            `).join('');
        }

        function toggleItem(el) {
            const cb = el.querySelector('.run-checkbox');
            cb.checked = !cb.checked;
            updateCount();
            
            document.querySelectorAll('.run-item').forEach(it => {
                it.classList.toggle('active', it.querySelector('.run-checkbox').checked);
            });
        }

        function updateCount() {
            const checked = document.querySelectorAll('.run-checkbox:checked');
            const btn = document.getElementById('compareBtn');
            btn.disabled = checked.length !== 2;
            btn.innerText = `📊 Compare Snapshots (${checked.length}/2)`;
            
            document.querySelectorAll('.run-item').forEach(it => {
                it.classList.toggle('active', it.querySelector('.run-checkbox').checked);
            });
        }

        async function loadRunData(id, file) {
            return new Promise((resolve) => {
                if (window.run_data[id]) return resolve(window.run_data[id]);
                const s = document.createElement('script');
                s.src = file;
                s.onload = () => resolve(window.run_data[id]);
                document.head.appendChild(s);
            });
        }

        async function startComparison() {
            const checked = Array.from(document.querySelectorAll('.run-checkbox:checked'));
            if(checked.length !== 2) return;
            
            // Auto close sidebar on mobile/desktop when comparing to free up space
            document.getElementById('sidebar').classList.add('collapsed');

            const items = checked.map(c => c.closest('.run-item')).sort((a,b) => a.dataset.id.localeCompare(b.dataset.id));
            
            document.getElementById('loader').style.display = 'block';
            document.getElementById('welcome').style.display = 'none';
            document.getElementById('compareOverlay').style.display = 'none';
            
            const [dataOld, dataNew] = await Promise.all(items.map(it => loadRunData(it.dataset.id, it.dataset.file)));
            
            document.getElementById('compareSubTitle').innerText = `${formatDate(items[0].dataset.id)} (Base) ➔ ${formatDate(items[1].dataset.id)} (Comparison)`;
            performDiff(dataOld, dataNew);
            
            setTimeout(() => {
                document.getElementById('loader').style.display = 'none';
                document.getElementById('compareOverlay').style.display = 'flex';
            }, 300);
        }

        function performDiff(oldData, newData) {
            const oldElements = new Set(oldData.map(d => d.element));
            const newElements = new Set(newData.map(d => d.element));
            
            const missingInNew = new Set([...oldElements].filter(x => !newElements.has(x)));
            const missingInOld = new Set([...newElements].filter(x => !oldElements.has(x)));

            const oldMap = new Map(oldData.map(d => [`${d.element}||${d.interface}`, d]));
            const newMap = new Map(newData.map(d => [`${d.element}||${d.interface}`, d]));
            const allKeys = new Set([...oldMap.keys(), ...newMap.keys()]);
            
            allDiffs = [];
            const processedMissingNodes = new Set();

            allKeys.forEach(key => {
                const oldItem = oldMap.get(key);
                const newItem = newMap.get(key);
                const [el, iface] = key.split('||');
                
                if (missingInNew.has(el)) {
                    if (!processedMissingNodes.has(el)) {
                        allDiffs.push({type:'NODE_UNREACHABLE', element:el, interface:'ALL', old:{description:'Element missing from new collection', line_protocol:'NODE OFFLINE', admin_status: '-', bandwidth_kbit: '-'}});
                        processedMissingNodes.add(el);
                    }
                    return;
                }
                
                if (missingInOld.has(el)) {
                    if (!processedMissingNodes.has(el)) {
                        allDiffs.push({type:'NODE_ADDED', element:el, interface:'ALL', new:{description:'Element missing from old collection', line_protocol:'NODE ADDED', admin_status: '-', bandwidth_kbit: '-'}});
                        processedMissingNodes.add(el);
                    }
                    return;
                }

                if(!oldItem) allDiffs.push({type:'ADDED', element:el, interface:iface, new:newItem});
                else if(!newItem) allDiffs.push({type:'REMOVED', element:el, interface:iface, old:oldItem});
                else {
                    const changes = {};
                    ['admin_status', 'line_protocol', 'bandwidth_kbit', 'description'].forEach(f => {
                        if(String(oldItem[f]) !== String(newItem[f])) changes[f] = [oldItem[f], newItem[f]];
                    });
                    if(Object.keys(changes).length > 0) {
                        allDiffs.push({type:'MODIFIED', element:el, interface:iface, changes, old:oldItem, new:newItem});
                    }
                }
            });
            applyFilters();
        }

        function clearAllFilters() {
            document.getElementById('filterEl').value = '';
            document.getElementById('excludeEl').value = '';
            document.querySelectorAll('.filter-cb-type, .filter-cb-field, .filter-cb-state').forEach(cb => cb.checked = false);
            applyFilters();
        }

        function selectAllFilters() {
            document.querySelectorAll('.filter-cb-type, .filter-cb-field, .filter-cb-state').forEach(cb => cb.checked = true);
            applyFilters();
        }

        function applyFilters() {
            const qEl = document.getElementById('filterEl').value.toLowerCase();
            const excEl = document.getElementById('excludeEl').value.toLowerCase();
            
            const checkedTypes = Array.from(document.querySelectorAll('.filter-cb-type:checked')).map(cb => cb.value);
            const checkedFields = Array.from(document.querySelectorAll('.filter-cb-field:checked')).map(cb => cb.value);
            const checkedStates = Array.from(document.querySelectorAll('.filter-cb-state:checked')).map(cb => cb.value);
            
            const filtered = allDiffs.filter(d => {
                // Text Search (Positive and Negative)
                const searchStr = `${d.element} ${d.interface} ${d.new ? d.new.description : d.old.description}`.toLowerCase();
                if(qEl && !searchStr.includes(qEl)) return false;
                if(excEl && searchStr.includes(excEl)) return false;
                
                // Drift Type
                if(!checkedTypes.includes(d.type)) return false;
                
                // Changed Fields (Only applies to MODIFIED)
                if (d.type === 'MODIFIED') {
                    const hasRelevantChange = checkedFields.some(f => d.changes[f]);
                    if (!hasRelevantChange) return false;
                }
                
                // Current State Filter
                const currentStateStr = String(d.new ? d.new.line_protocol : d.old.line_protocol).toUpperCase();
                let stateCat = 'OTHER';
                if (currentStateStr.includes('UP')) stateCat = 'UP';
                else if (currentStateStr.includes('DOWN')) stateCat = 'DOWN';
                
                if (!checkedStates.includes(stateCat)) return false;
                
                return true;
            });
            
            filteredDiffs = filtered;

            const modCount = filtered.filter(f => f.type === 'MODIFIED').length;
            const addCount = filtered.filter(f => f.type === 'ADDED').length;
            const remCount = filtered.filter(f => f.type === 'REMOVED').length;
            const nodeAddCount = filtered.filter(f => f.type === 'NODE_ADDED').length;
            const nodeRemCount = filtered.filter(f => f.type === 'NODE_UNREACHABLE').length;
            
            document.getElementById('statMod').innerText = `${modCount} MODIFIED`;
            document.getElementById('statAdd').innerText = `${addCount} ADDED`;
            document.getElementById('statRem').innerText = `${remCount} REMOVED`;
            document.getElementById('statNodeAdd').innerText = `${nodeAddCount} NODE ADDED`;
            document.getElementById('statNodeRem').innerText = `${nodeRemCount} NODE UNREACHABLE`;

            renderTable(filtered, checkedFields);
        }

        function exportDriftCSV() {
            if (filteredDiffs.length === 0) {
                alert("No data to export");
                return;
            }
            let csvContent = "\\uFEFF";
            csvContent += "Drift Type;Network Element;Interface;Field;Old Value;New Value;Description\\n";
            
            filteredDiffs.forEach(d => {
                const type = d.type || "";
                const element = d.element || "";
                const iface = d.interface || "";
                
                if (type === 'MODIFIED') {
                    Object.keys(d.changes).forEach(field => {
                        const oldVal = String(d.changes[field][0] || "NONE").replace(/"/g, '""');
                        const newVal = String(d.changes[field][1] || "NONE").replace(/"/g, '""');
                        const desc = String(d.new ? d.new.description : (d.old ? d.old.description : "")).replace(/"/g, '""');
                        csvContent += `"${type}";"${element}";"${iface}";"${field}";"${oldVal}";"${newVal}";"${desc}"\\n`;
                    });
                } else {
                    const desc = String(d.new ? d.new.description : (d.old ? d.old.description : "")).replace(/"/g, '""');
                    const admin = String(d.new ? d.new.admin_status : (d.old ? d.old.admin_status : "")).replace(/"/g, '""');
                    const oper = String(d.new ? d.new.line_protocol : (d.old ? d.old.line_protocol : "")).replace(/"/g, '""');
                    const bw = String(d.new ? d.new.bandwidth_kbit : (d.old ? d.old.bandwidth_kbit : "")).replace(/"/g, '""');
                    
                    csvContent += `"${type}";"${element}";"${iface}";"ALL";"${type === 'ADDED' ? 'NONE' : admin}/${type === 'ADDED' ? 'NONE' : oper}/${type === 'ADDED' ? 'NONE' : bw}";"${type === 'REMOVED' ? 'NONE' : admin}/${type === 'REMOVED' ? 'NONE' : oper}/${type === 'REMOVED' ? 'NONE' : bw}";"${desc}"\\n`;
                }
            });
            
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement("a");
            if (link.download !== undefined) {
                const url = URL.createObjectURL(blob);
                link.setAttribute("href", url);
                link.setAttribute("download", "drift_export.csv");
                link.style.visibility = 'hidden';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }
        }

        function renderTable(data, checkedFields) {
            const body = document.getElementById('diffBody');
            if(data.length === 0) {
                body.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:100px; color:var(--text-dim); font-style:italic;">No changes detected for the current filters.</td></tr>`;
                return;
            }

            body.innerHTML = data.map(d => {
                const renderVal = (f) => {
                    if(d.type === 'MODIFIED' && d.changes[f]) {
                        // Mask the change if the field is not selected in the filter
                        if (!checkedFields.includes(f)) {
                            return `<span style="opacity:0.4">${d.changes[f][1] || '-'}</span>`;
                        }
                        return `
                            <div class="val-change-box">
                                <div class="drift-step">
                                    <span class="drift-from">${d.changes[f][0] || 'NONE'}</span>
                                    <span class="drift-arrow">➔</span>
                                    <span class="drift-to">${d.changes[f][1] || 'NONE'}</span>
                                </div>
                            </div>
                        `;
                    }
                    const val = d.new ? d.new[f] : d.old[f];
                    return `<span style="${d.type === 'REMOVED' ? 'text-decoration:line-through; opacity:0.5' : ''}">${val || '-'}</span>`;
                };

                return `<tr>
                    <td><span class="tag tag-${d.type.toLowerCase()}">${d.type}</span></td>
                    <td style="font-weight:700; color:var(--text); cursor: pointer; text-decoration: underline;" onclick="showDeviceContextMenu(event, '${d.element}')" title="Click for external links to other dashboards">${d.element}</td>
                    <td style="font-weight:700; color:var(--accent); font-family: monospace; cursor: pointer; text-decoration: underline;" onclick="jumpToTimeline('${d.element}', '${d.interface}')" title="Click to view chronological timeline of this interface">${d.interface}</td>
                    <td class="wrap-col">${renderVal('description')}</td>
                    <td>${renderVal('admin_status')}</td>
                    <td>${renderVal('line_protocol')}</td>
                    <td>${renderVal('bandwidth_kbit')}</td>
                </tr>`;
            }).join('');
        }

        // Timeline tab navigation logic
        let currentTab = 'drift';
        function switchTab(tabName) {
            currentTab = tabName;
            document.getElementById('tabCompare').classList.toggle('active', tabName === 'drift');
            document.getElementById('tabTimeline').classList.toggle('active', tabName === 'timeline');
            
            if (tabName === 'drift') {
                document.getElementById('dashTitle').innerText = '⚖️ Drift Analyzer';
                document.getElementById('dashSubTitle').innerText = 'Select two snapshots from the sidebar';
                document.getElementById('sidebar').style.marginLeft = '';
                
                const checked = document.querySelectorAll('.run-checkbox:checked');
                if (checked.length === 2 && allDiffs.length > 0) {
                    document.getElementById('compareOverlay').style.display = 'flex';
                    document.getElementById('welcome').style.display = 'none';
                } else {
                    document.getElementById('compareOverlay').style.display = 'none';
                    document.getElementById('welcome').style.display = 'flex';
                }
                document.getElementById('timelineOverlay').style.display = 'none';
            } else {
                document.getElementById('dashTitle').innerText = '⏱️ Timeline Tracker';
                document.getElementById('dashSubTitle').innerText = 'Analyze interface changes over time';
                document.getElementById('sidebar').classList.add('collapsed');
                
                document.getElementById('compareOverlay').style.display = 'none';
                document.getElementById('welcome').style.display = 'none';
                document.getElementById('timelineOverlay').style.display = 'flex';
            }
        }

        // Jump from comparison to timeline shortcut (last 7 days)
        function jumpToTimeline(element, iface) {
            switchTab('timeline');
            document.getElementById('timelineElement').value = element;
            onElementChanged();
            document.getElementById('timelineInterface').value = iface;
            
            if (manifest.length > 0) {
                const latestId = manifest[0].id;
                const y = parseInt(latestId.substring(0,4));
                const m = parseInt(latestId.substring(4,6)) - 1;
                const d = parseInt(latestId.substring(6,8));
                
                const dateEnd = new Date(y, m, d);
                const dateStart = new Date(y, m, d);
                dateStart.setDate(dateStart.getDate() - 7);
                
                const formatDateInput = (date) => {
                    const yy = date.getFullYear();
                    const mm = String(date.getMonth() + 1).padStart(2, '0');
                    const dd = String(date.getDate()).padStart(2, '0');
                    return `${yy}-${mm}-${dd}`;
                };
                
                document.getElementById('timelineEnd').value = formatDateInput(dateEnd);
                document.getElementById('timelineStart').value = formatDateInput(dateStart);
            }
            trackTimeline();
        }

        // Timeline autocomplete
        let elementInterfaceMap = {};
        async function initTimelineAutocomplete() {
            if (manifest.length === 0) return;
            const latest = manifest[0];
            try {
                const data = await loadRunData(latest.id, latest.file);
                if (!data) return;
                
                elementInterfaceMap = {};
                data.forEach(item => {
                    const el = item.element;
                    const iface = item.interface;
                    if (el && iface) {
                        if (!elementInterfaceMap[el]) {
                            elementInterfaceMap[el] = [];
                        }
                        elementInterfaceMap[el].push(iface);
                    }
                });
                
                const elementsList = document.getElementById('elementsList');
                const elements = Object.keys(elementInterfaceMap).sort();
                elementsList.innerHTML = elements.map(el => `<option value="${el}">`).join('');
                
                if (manifest.length > 0) {
                    const earliestId = manifest[manifest.length - 1].id;
                    const latestId = manifest[0].id;
                    const formatDateInput = (id) => `${id.substring(0,4)}-${id.substring(4,6)}-${id.substring(6,8)}`;
                    
                    document.getElementById('timelineStart').value = formatDateInput(earliestId);
                    document.getElementById('timelineEnd').value = formatDateInput(latestId);
                }
            } catch (err) {
                console.error("Failed to initialize timeline autocomplete", err);
            }
        }

        function onElementChanged() {
            const elInput = document.getElementById('timelineElement').value.trim();
            const interfacesList = document.getElementById('interfacesList');
            interfacesList.innerHTML = '';
            
            if (elementInterfaceMap[elInput]) {
                const sortedIfaces = elementInterfaceMap[elInput].sort();
                interfacesList.innerHTML = sortedIfaces.map(iface => `<option value="${iface}">`).join('');
            }
        }

        // Timeline tracking logic
        let timelineEvents = [];
        async function trackTimeline() {
            const element = document.getElementById('timelineElement').value.trim();
            const iface = document.getElementById('timelineInterface').value.trim();
            const startDate = document.getElementById('timelineStart').value;
            const endDate = document.getElementById('timelineEnd').value;
            
            if (!element || !iface) {
                alert("Please select a valid Element and Interface to track.");
                return;
            }
            
            const matchedRuns = manifest.filter(m => {
                const runDate = `${m.id.substring(0,4)}-${m.id.substring(4,6)}-${m.id.substring(6,8)}`;
                return (!startDate || runDate >= startDate) && (!endDate || runDate <= endDate);
            }).sort((a,b) => a.id.localeCompare(b.id));
            
            if (matchedRuns.length === 0) {
                alert("No snapshots found in the selected date range.");
                return;
            }
            
            const trackBtn = document.getElementById('trackBtn');
            const progressContainer = document.getElementById('timelineProgressContainer');
            const progressFill = document.getElementById('timelineProgressFill');
            
            trackBtn.disabled = true;
            progressContainer.style.display = 'block';
            progressFill.style.width = '0%';
            
            document.getElementById('timelinePlaceholder').style.display = 'none';
            document.getElementById('timelineCard').style.display = 'none';
            
            const runDataMap = {};
            let loadedCount = 0;
            
            for (let i = 0; i < matchedRuns.length; i++) {
                const run = matchedRuns[i];
                const data = await loadRunData(run.id, run.file);
                runDataMap[run.id] = data;
                loadedCount++;
                progressFill.style.width = `${(loadedCount / matchedRuns.length) * 100}%`;
            }
            
            timelineEvents = [];
            let previousState = null;
            
            matchedRuns.forEach((run, idx) => {
                const data = runDataMap[run.id];
                const currentItem = data ? data.find(d => d.element === element && d.interface === iface) : null;
                
                if (idx === 0) {
                    previousState = currentItem ? { ...currentItem } : null;
                    timelineEvents.push({
                        type: 'BASELINE',
                        id: run.id,
                        date: formatDate(run.id),
                        state: previousState,
                        changes: {}
                    });
                } else {
                    if (!previousState && currentItem) {
                        timelineEvents.push({
                            type: 'ADDED',
                            id: run.id,
                            date: formatDate(run.id),
                            state: { ...currentItem },
                            changes: {}
                        });
                        previousState = { ...currentItem };
                    } else if (previousState && !currentItem) {
                        timelineEvents.push({
                            type: 'REMOVED',
                            id: run.id,
                            date: formatDate(run.id),
                            state: null,
                            changes: {}
                        });
                        previousState = null;
                    } else if (previousState && currentItem) {
                        const changes = {};
                        ['admin_status', 'line_protocol', 'bandwidth_kbit', 'description'].forEach(f => {
                            if (String(previousState[f]) !== String(currentItem[f])) {
                                changes[f] = [previousState[f], currentItem[f]];
                            }
                        });
                        
                        if (Object.keys(changes).length > 0) {
                            timelineEvents.push({
                                type: 'MODIFIED',
                                id: run.id,
                                date: formatDate(run.id),
                                state: { ...currentItem },
                                changes: changes
                            });
                            previousState = { ...currentItem };
                        }
                    }
                }
            });
            
            setTimeout(() => {
                progressContainer.style.display = 'none';
                trackBtn.disabled = false;
                
                document.getElementById('timelineTitle').innerText = `Timeline: ${element} ➔ ${iface}`;
                document.getElementById('timelineSub').innerText = `Tracked across ${matchedRuns.length} snapshots`;
                document.getElementById('timelineCard').style.display = 'block';
                
                renderTimeline(timelineEvents);
                applyTimelineFilter();
            }, 300);
        }

        function renderTimeline(events) {
            const container = document.getElementById('timelineList');
            if (events.length === 0) {
                container.innerHTML = `<div style="text-align:center; padding:50px; color:var(--text-dim); font-style:italic;">No changes detected for this interface in the selected range.</div>`;
                return;
            }
            
            const displayEvents = [...events].reverse();
            
            container.innerHTML = displayEvents.map(ev => {
                let typeTagClass = 'tag-modified';
                let detailsHtml = '';
                
                if (ev.type === 'BASELINE') {
                    typeTagClass = 'tag-added';
                    detailsHtml = `
                        <div style="font-size:0.85rem; color:var(--text-dim);">
                            <strong>Initial Baseline State:</strong><br/>
                            ${ev.state ? `
                                • Description: <span style="color:var(--text)">${ev.state.description || '-'}</span><br/>
                                • Admin: <span style="color:var(--text)">${ev.state.admin_status || '-'}</span> | Protocol: <span style="color:var(--text)">${ev.state.line_protocol || '-'}</span><br/>
                                • Speed: <span style="color:var(--text)">${ev.state.bandwidth_kbit || '-'} Kbit</span>
                            ` : '<span style="color:var(--danger)">Interface not present at this snapshot.</span>'}
                        </div>
                    `;
                } else if (ev.type === 'ADDED') {
                    typeTagClass = 'tag-added';
                    detailsHtml = `
                        <div style="font-size:0.85rem; color:var(--text-dim);">
                            <strong>Interface Added:</strong><br/>
                            • Description: <span style="color:var(--text)">${ev.state.description || '-'}</span><br/>
                            • Admin: <span style="color:var(--text)">${ev.state.admin_status || '-'}</span> | Protocol: <span style="color:var(--text)">${ev.state.line_protocol || '-'}</span>
                        </div>
                    `;
                } else if (ev.type === 'REMOVED') {
                    typeTagClass = 'tag-removed';
                    detailsHtml = `
                        <div style="font-size:0.85rem; color:var(--danger);">
                            <strong>Interface Removed / Node Offline</strong> (Missing from collection)
                        </div>
                    `;
                } else if (ev.type === 'MODIFIED') {
                    typeTagClass = 'tag-modified';
                    
                    const changesList = Object.keys(ev.changes).map(field => {
                        const oldVal = ev.changes[field][0] || 'NONE';
                        const newVal = ev.changes[field][1] || 'NONE';
                        return `
                            <div class="timeline-change-item" data-field="${field}">
                                <span class="timeline-field">${field.replace('_', ' ')}</span>
                                <div class="drift-step">
                                    <span class="drift-from">${oldVal}</span>
                                    <span class="drift-arrow">➔</span>
                                    <span class="drift-to">${newVal}</span>
                                </div>
                            </div>
                        `;
                    }).join('');
                    
                    detailsHtml = `
                        <div class="timeline-changes">
                            ${changesList}
                        </div>
                    `;
                }
                
                return `
                    <div class="timeline-node ${ev.type.toLowerCase()}" data-search="${ev.type} ${ev.id} ${ev.state ? ev.state.description : ''}">
                        <div class="timeline-dot"></div>
                        <div class="timeline-box">
                            <div class="timeline-meta">
                                <span class="timeline-ts">${ev.date}</span>
                                <span class="tag ${typeTagClass}">${ev.type}</span>
                                <span class="timeline-run-id">${ev.id}</span>
                            </div>
                            ${detailsHtml}
                        </div>
                    </div>
                `;
            }).join('');
        }

        function applyTimelineFilter() {
            const q = document.getElementById('timelineFilterText').value.toLowerCase();
            const checkedFields = Array.from(document.querySelectorAll('.timeline-cb-field:checked')).map(cb => cb.value);
            
            const nodes = document.querySelectorAll('.timeline-node');
            nodes.forEach(node => {
                const searchStr = node.dataset.search.toLowerCase();
                const matchesText = !q || searchStr.includes(q);
                
                if (!matchesText) {
                    node.style.display = 'none';
                    return;
                }
                
                if (node.classList.contains('modified')) {
                    const changeItems = node.querySelectorAll('.timeline-change-item');
                    let visibleChangesCount = 0;
                    
                    changeItems.forEach(item => {
                        const field = item.dataset.field;
                        if (checkedFields.includes(field)) {
                            item.style.display = 'flex';
                            visibleChangesCount++;
                        } else {
                            item.style.display = 'none';
                        }
                    });
                    
                    node.style.display = (visibleChangesCount === 0) ? 'none' : '';
                } else {
                    node.style.display = '';
                }
            });
        }

        function clearTimelineFilter() {
            document.getElementById('timelineFilterText').value = '';
            document.querySelectorAll('.timeline-cb-field').forEach(cb => cb.checked = true);
            applyTimelineFilter();
        }

        // Initialize
        window.addEventListener('DOMContentLoaded', () => {
            renderList();
            
            // Auto-select two latest snapshots
            const items = document.querySelectorAll('.run-item');
            if(items.length >= 2) {
                const latestCb = items[0].querySelector('.run-checkbox');
                const secondLatestCb = items[1].querySelector('.run-checkbox');
                latestCb.checked = true;
                secondLatestCb.checked = true;
                updateCount();
                
                // Automatically start comparison
                startComparison();
            }
            
            // URL parameter handling
            const urlParams = new URLSearchParams(window.location.search);
            const device = urlParams.get('device') || urlParams.get('element');
            const iface = urlParams.get('interface');
            
            if (device) {
                if (iface) {
                    // Jump to timeline tracker for device and interface
                    setTimeout(async () => {
                        await initTimelineAutocomplete();
                        switchTab('timeline');
                        document.getElementById('timelineElement').value = device;
                        onElementChanged();
                        document.getElementById('timelineInterface').value = iface;
                        trackTimeline();
                    }, 500);
                } else {
                    // Filter comparison by device
                    document.getElementById('filterEl').value = device;
                    setTimeout(() => applyFilters(), 100);
                    initTimelineAutocomplete();
                }
            } else {
                initTimelineAutocomplete();
            }
        });

        function showDeviceContextMenu(e, device) {
            e.preventDefault();
            e.stopPropagation();
            
            let menu = document.getElementById('deviceContextMenu');
            if (!menu) {
                menu = document.createElement('div');
                menu.id = 'deviceContextMenu';
                menu.className = 'context-menu';
                document.body.appendChild(menu);
            }
            
            menu.innerHTML = `
                <div class="menu-header">${device} Options</div>
                <a href="../inventory/index.html?device=${device}" target="_blank">📦 Global Inventory</a>
                <a href="../ping-matrix/index.html?origin=${device}" target="_blank">⚡ Snapshots & Heatmaps</a>
                <a href="../ping-matrix/history.html?origin=${device}" target="_blank">📈 P2P History & SLA</a>
                <a href="../ping-matrix/path.html?origin=${device}" target="_blank">🕸️ Route Analysis (Dijkstra)</a>
                <a href="../topology/index.html" target="_blank">🕸️ Network Topology</a>
            `;
            
            menu.style.display = 'flex';
            
            const menuWidth = menu.offsetWidth || 200;
            const menuHeight = menu.offsetHeight || 220;
            
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
            const menu = document.getElementById('deviceContextMenu');
            if (menu) menu.style.display = 'none';
        });
    </script>
</body>
</html>
"""
        with open(os.path.join(self.diff_dir, "index.html"), 'w', encoding='utf-8') as f:
            f.write(template)
