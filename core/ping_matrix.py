#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import paramiko
import getpass
import logging
import datetime
import os
import sys
import time
import concurrent.futures
import json
import argparse
import csv
import re
import threading

# Regex para Captura de Ping (Comporta formato normal de Cisco, Datacom, Huawei)
# Cisco: "5 packets transmitted, 5 packets received, 0% packet loss"
# Cisco RTT: "round-trip min/avg/max = 1/2/3 ms"
# Huawei: "5 packet(s) transmitted... 5 packet(s) received"
# Huawei RTT: "round-trip min/avg/max = 1/2/3 ms"

RE_TRANSMITTED = re.compile(r'(\d+)\s+packet[s]?\s*(?:\([a-zA-Z\s]+\))? transmitted', re.IGNORECASE)
RE_RECEIVED = re.compile(r'(\d+)\s+packet[s]?\s*(?:\([a-zA-Z\s]+\))? received', re.IGNORECASE)
RE_RTT = re.compile(r'min(?:imum)?/avg(?:erage)?/max(?:imum)?.*?=\s*([\d\.]+)/([\d\.]+)/([\d\.]+)', re.IGNORECASE)

def read_elements(path):
    elements = []
    if not os.path.isfile(path):
        logging.error(f"Element file not found: {path}")
        sys.exit(1)

    with open(path, 'r') as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(';')
            if len(parts) >= 3:
                # We only need hostname, first IP, and cmd_key
                ip = parts[1].split('|')[0] # Pega o primeiro IP
                elements.append({'hostname': parts[0], 'ip': ip, 'cmd_key': parts[2].split('|')[0]})
    return elements

def read_icmp_commands(path):
    commands = {}
    if not os.path.isfile(path):
        return commands
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ';' in line:
                key, cmd = line.split(';', 1)
                commands[key] = cmd
    return commands

def parse_ping_output(output, host_dest):
    # Valores default
    tx, rx = 0, 0
    t_min, t_avg, t_max = -1.0, -1.0, -1.0
    consistently_denied = False
    
    tx_match = RE_TRANSMITTED.search(output)
    if tx_match:
        tx = int(tx_match.group(1))
        
    rx_match = RE_RECEIVED.search(output)
    if rx_match:
        rx = int(rx_match.group(1))

    # Suporte ao formato nativo da Cisco: "Success rate is 100 percent (5/5)"
    cisco_match = re.search(r'Success rate is \d+\s*percent\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)', output, re.IGNORECASE)
    if cisco_match:
        rx = int(cisco_match.group(1))
        tx = int(cisco_match.group(2))
        
    rtt_match = RE_RTT.search(output)
    if rtt_match:
        try:
            t_min = float(rtt_match.group(1))
            t_avg = float(rtt_match.group(2))
            t_max = float(rtt_match.group(3))
        except:
            pass

    # Fallback/Deny analysis
    if "U.U.U" in output or "Admin Prohibited" in output or "Destination unreachable" in output:
        consistently_denied = True
        
    is_unreachable = (tx > 0 and rx == 0)
    
    # Se perdemos os pacotes mas o parse falhou
    if rx == 0:
        t_min, t_avg, t_max = -1.0, -1.0, -1.0
        
    loss_pct = 100.0
    if tx > 0:
        loss_pct = ((tx - rx) / tx) * 100.0
        
    return {
        'dest': host_dest,
        'tx': tx,
        'rx': rx,
        'min': t_min,
        'avg': t_avg,
        'max': t_max,
        'loss_pct': loss_pct,
        'is_unreachable': is_unreachable,
        'consistently_denied': consistently_denied,
        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect_dir", default=".")
    parser.add_argument("--resume_dir", default=".")
    parser.add_argument("--logdir", default=".")
    parser.add_argument("--elements_cfg", required=True)
    parser.add_argument("--settings", default="config/settings.json")
    parser.add_argument("--ping_commands", default="config/commands.icmp.cfg")
    parser.add_argument("--ping_format", default="csv")
    args = parser.parse_args()

    # Load Settings
    json_config = {}
    if os.path.exists(args.settings):
        with open(args.settings, "r") as f:
            json_config = json.load(f)
            
    ssh_cfg = json_config.get("ssh", {})
    SSH_TIMEOUT = ssh_cfg.get("timeout", 10)
    
    ping_cfg = json_config.get("ping_matrix", {})
    count = ping_cfg.get("count", 5)
    size = ping_cfg.get("datagram_size", 100)
    timeout_ping = ping_cfg.get("timeout", 2)
    max_latency_warning = ping_cfg.get("max_latency_warning", 200)
    thread_count = ping_cfg.get("parallel_sessions", 15)
    delay_between_commands = ping_cfg.get("delay_between_commands", 1.0)
    asymmetric_pct = ping_cfg.get("asymmetric_threshold_pct", 25.0)

    log_file = os.path.join(args.logdir, 'ping_matrix.log')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s',
                        handlers=[logging.FileHandler(log_file, mode='w', encoding='utf-8')])
    logging.getLogger("paramiko").setLevel(logging.WARNING)

    logging.info(f"Starting Ping Matrix with threads={thread_count}, count={count}, size={size}")

    elements = read_elements(args.elements_cfg)
    if not elements:
        print("No elements to process.")
        sys.exit(1)

    icmp_cmds = read_icmp_commands(args.ping_commands)
    if not icmp_cmds:
        print(f"Missing {args.ping_commands}")
        logging.error(f"Missing {args.ping_commands}")
        sys.exit(1)

    # Auth logic
    env_user = os.environ.get('NDX_SSH_USER')
    env_pass = os.environ.get('NDX_SSH_PASS')
    env_key  = os.environ.get('NDX_SSH_KEY')
    
    user = env_user if env_user else input('SSH Worker User: ')
    password = env_pass
    if not env_key and not env_pass:
        password = getpass.getpass('SSH Password: ')

    all_results = []
    results_lock = threading.Lock()
    counter = 0
    total_elements = len(elements)
    
    timestamp = datetime.datetime.now().strftime('%d%m%y%H%M%S')

    def execute_ping_matrix_for_origin(origin_elem):
        nonlocal counter
        origin_host = origin_elem['hostname']
        origin_ip = origin_elem['ip']
        cmd_key = origin_elem['cmd_key']
        
        base_cmd = icmp_cmds.get(cmd_key)
        if not base_cmd:
            logging.warning(f"No ICMP command found for {cmd_key} (Host: {origin_host})")
            with results_lock:
                counter += 1
            return

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            connect_kwargs = {"username": user, "timeout": SSH_TIMEOUT, "allow_agent": False, "look_for_keys": False}
            if env_key: connect_kwargs['key_filename'] = env_key
            elif password: connect_kwargs['password'] = password
            else: connect_kwargs['look_for_keys'] = True; connect_kwargs['allow_agent'] = True
                
            client.connect(origin_ip, **connect_kwargs)
            shell = client.invoke_shell()
            time.sleep(1)
            shell.recv(65535) # Clear banner

            # Disable paging
            for p_cmd in ['terminal length 0', 'terminal pager 0', 'screen-length 0 disable']:
                shell.send(p_cmd + '\n'); time.sleep(0.5)
            while shell.recv_ready(): shell.recv(65535)

            # Loop every other destination
            for dest_elem in elements:
                if origin_host == dest_elem['hostname']:
                    continue
                
                dest_ip = dest_elem['ip']
                # Formata comando
                # {ip}, {source_ip}, {count}, {size}, {timeout}
                cmd_run = base_cmd.replace("{ip}", dest_ip)\
                                  .replace("{source_ip}", origin_ip)\
                                  .replace("{count}", str(count))\
                                  .replace("{size}", str(size))\
                                  .replace("{timeout}", str(timeout_ping))
                                  
                shell.send(cmd_run + '\n')
                
                # Fetch output logic specific for pings
                buff = b''
                start_time = time.time()
                last_recv = time.time()
                # Max tolerance: (Timeout * Count) + 10s grace
                max_tolerance = (timeout_ping * count) + 10
                
                while True:
                    if time.time() - start_time > max_tolerance:
                        break
                    if shell.recv_ready():
                        chunk = shell.recv(65535)
                        if chunk:
                            buff += chunk
                            last_recv = time.time()
                    else:
                        # Se ficou 1.5s seguidos sem recarregar e já tem o proprio prompt no buffer, assume finalizado
                        if time.time() - last_recv > 1.5 and len(buff) > 10:
                            break
                        time.sleep(0.1)

                output_text = buff.decode('utf-8', errors='ignore')
                
                # Raw logger
                raw_filename = f"{origin_host}.{timestamp}.ping_to_{dest_elem['hostname']}.txt"
                raw_path = os.path.join(args.collect_dir, raw_filename)
                with open(raw_path, 'w', encoding='utf-8') as rf:
                    rf.write(f"# Origin: {origin_host} ({origin_ip})\n")
                    rf.write(f"# Dest:   {dest_elem['hostname']} ({dest_ip})\n")
                    rf.write(f"# Cmd:    {cmd_run}\n\n")
                    rf.write(output_text)
                
                parsed = parse_ping_output(output_text, dest_elem['hostname'])
                parsed['origin'] = origin_host
                
                # Armazena parcial
                with results_lock:
                    all_results.append(parsed)
                    
                # Visual feedback loop (progress simulator)
                print(".", end="", flush=True)
                
                # Ping Matrix Accelerator: Override the global SSH delay if it's too high. ICMP is low-cost.
                local_delay = min(delay_between_commands, 0.2)
                time.sleep(local_delay)

            client.close()
            with results_lock:
                counter += 1
                curr = counter
            print(f"\n  [{curr:>{len(str(total_elements))}}/{total_elements}] [+] Ping Matrix from {origin_host} done.")
            logging.info(f"Ping Matrix from {origin_host} done.")
            
        except Exception as e:
            logging.error(f"Failed Matrix for {origin_host}: {e}")
            with results_lock:
                counter += 1
                curr = counter
            print(f"\n  [{curr:>{len(str(total_elements))}}/{total_elements}] [-] Ping Matrix from {origin_host} failed.")

    print(f"Starting ICMP requests concurrently (Threads: {thread_count})...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
        executor.map(execute_ping_matrix_for_origin, elements)

    # Post processing: Asymmetry and Jitter Warning
    print("Generating statistical analysis and List CSV...")
    
    # Build dictionary for quick lookup of inverse route
    lookup = {}
    for r in all_results:
        lookup[(r['origin'], r['dest'])] = r

    # Setup parameters
    ping_format = args.ping_format.lower()
    if 'html' in ping_format and 'json' not in ping_format:
        ping_format += ',json' # HTML strictly requires JSON local dependency
        
    ex_csv  = 'csv' in ping_format or ping_format == ''
    ex_json = 'json' in ping_format
    ex_html = 'html' in ping_format
    
    final_csv_dados = []
    final_output_data = [] # Para armazenar toda a lista estendida no JSON
    
    for r in all_results:
        o = r['origin']
        d = r['dest']
        
        # Jitter estimado
        tmin = r['min']
        tmax = r['max']
        tavg = r['avg']
        jitter_warning = False
        if tavg > 0 and tmax >= 0 and tmin >= 0:
            if (tmax - tmin) > 5.0:
                if ((tmax - tmin) / tavg) > 0.4:
                    jitter_warning = True
        
        # Assimétrico
        asymmetric_warning = False
        inverse = lookup.get((d, o))
        if inverse and tavg > 0 and inverse['avg'] > 0:
            inv_avg = inverse['avg']
            diff = abs(tavg - inv_avg)
            base_avg = min(tavg, inv_avg)
            pct = (diff / base_avg) * 100.0
            if pct > asymmetric_pct:
                asymmetric_warning = True
                
        r['jitter_warning'] = jitter_warning
        r['asymmetric_warning'] = asymmetric_warning
        
        final_csv_dados.append([
            r.get('timestamp', ''),
            o, 
            d, 
            tmin, 
            tavg, 
            tmax, 
            size, 
            r['tx'], 
            r['rx'], 
            f"{r['loss_pct']:.1f}", 
            r['is_unreachable'], 
            jitter_warning, 
            asymmetric_warning,
            r['consistently_denied']
        ])
        final_output_data.append(r)

    if ex_csv:
        csv_path = os.path.join(args.resume_dir, "ping_matrix_list.csv")
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(["Timestamp", "Origin_Node", "Destination_Node", "Min_ms", "Avg_ms", "Max_ms", "Size", "Transmitted", "Received", "Loss_Pct", "Is_Unreachable", "Jitter_Warning", "Asymmetric_Warning", "Consistently_Denied"])
            writer.writerows(final_csv_dados)
        print(f"Done. CSV saved to {csv_path}")

    if ex_json:
        json_path = os.path.join(args.resume_dir, "ping_matrix_list.json")
        json_payload = {
            "metadata": {
                "datetime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "nodes_connected": total_elements,
                "config": {
                    "count": count,
                    "datagram_size": size,
                    "timeout": timeout_ping,
                    "threads": thread_count
                }
            },
            "data": final_output_data
        }
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_payload, f, indent=4)
        print(f"Done. JSON saved to {json_path}")
        
    if ex_html:
        html_path = os.path.join(args.resume_dir, "ping_matrix_dashboard.html")
        html_template = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Ping Matrix Dashboard - PRO</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Outfit:wght@400;600;800&display=swap" rel="stylesheet">
<style>
/* Base Theme & Glassmorphism */
body { 
    background: radial-gradient(circle at top, #0f172a 0%, #020617 100%); 
    color: #e2e8f0; 
    font-family: 'Inter', sans-serif; 
    margin: 0; 
    padding: 30px; 
    min-height: 100vh;
}
h1, h2, h3, h4, .outfit { font-family: 'Outfit', sans-serif; }

.header { text-align: center; margin-bottom: 30px; animation: fadeIn 0.8s ease; }
.header h1 { font-size: 38px; font-weight: 800; margin: 0; background: linear-gradient(90deg, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; filter: drop-shadow(0 0 10px rgba(56,189,248,0.3)); }
#sub-header { color: #94a3b8; font-size: 14px; margin-top: 5px; }

/* Dashboard UI Panels */
.dashboard-metrics { 
    display: flex; justify-content: space-around; 
    background: rgba(30, 41, 59, 0.4); 
    backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.05); 
    border-radius: 16px; padding: 20px; margin-bottom: 25px; 
    box-shadow: 0 10px 30px -10px rgba(0,0,0,0.5);
    animation: slideDown 0.5s ease;
}
.metric-box { text-align: center; }
.metric-box h3 { margin: 0 0 5px 0; font-size: 28px; color: #38bdf8; text-shadow: 0 0 15px rgba(56,189,248,0.4); }
.metric-box span { font-size: 13px; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px; font-weight: 600;}

/* Controls */
.controls { display: flex; justify-content: center; gap: 15px; margin-bottom: 25px; }
.controls input, .controls select { 
    padding: 10px 15px; background: rgba(15, 23, 42, 0.6); 
    border: 1px solid rgba(255,255,255,0.1); color: #f8fafc; 
    border-radius: 8px; font-family: 'Inter', sans-serif; font-size: 14px;
    transition: all 0.3s ease; box-shadow: inset 0 2px 4px rgba(0,0,0,0.5);
}
.controls input:focus, .controls select:focus { outline: none; border-color: #38bdf8; box-shadow: 0 0 0 2px rgba(56,189,248,0.2); }

/* Matrix Table */
.matrix-wrapper { 
    overflow: auto; max-height: 65vh; 
    border-radius: 12px; border: 1px solid rgba(255,255,255,0.1);
    box-shadow: 0 15px 35px rgba(0,0,0,0.6);
    background: rgba(15, 23, 42, 0.4); backdrop-filter: blur(8px);
}
table { border-collapse: separate; border-spacing: 0; margin: 0 auto; width: max-content;}
th, td { border: 1px solid rgba(255,255,255,0.03); min-width: 65px; height: 60px; text-align: center; position: relative; cursor: default; }

/* Sticky Glass Headers */
th { background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(10px); position: sticky; padding: 8px; font-size: 12px; z-index: 5; color: #cbd5e1; font-weight: 600;}
th.row-head { left: 0; z-index: 6; border-right: 2px solid rgba(255,255,255,0.1); }
th.col-head { top: 0; z-index: 5; writing-mode: vertical-lr; transform: rotate(180deg); text-align: left; border-bottom: 2px solid rgba(255,255,255,0.1); padding-left: 15px;}
td { font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; }

/* Crosshair Highlight Hover effect */
tr:hover td { background-color: rgba(255, 255, 255, 0.05); }
td:hover::after { content: ""; position: absolute; background-color: rgba(255, 255, 255, 0.05); left: 0; top: -5000px; height: 10000px; width: 100%; z-index: -1; pointer-events: none; }
td:hover { background-color: rgba(255,255,255,0.1) !important; transform: scale(1.02); z-index: 4; box-shadow: 0 0 10px rgba(0,0,0,0.5); border-radius: 6px;}

/* Cell Themes */
.st-good { color: #4ade80; }
.st-warn { color: #fbbf24; text-shadow: 0 0 5px rgba(251, 191, 36, 0.4); }
.st-crit { color: #f87171; background: rgba(127, 29, 29, 0.3); text-shadow: 0 0 5px rgba(248, 113, 113, 0.5); }
.st-dead { background: rgba(0,0,0,0.4) !important; color: #475569; }
.st-self { background: rgba(30,41,59,0.3) !important; color: #334155; }

/* Split cell */
.split-item { padding: 4px 0; border-bottom: 1px dashed rgba(255,255,255,0.1); }
.split-item:last-child { border-bottom: none; }

/* Markers */
.marker-jitter { border-bottom: 3px solid #f97316; }
.marker-asym { border-right: 3px solid #eab308; }
.marker-deny { text-decoration: line-through; opacity: 0.5; }

/* Floating Tooltip */
.tooltip { 
    display: none; position: absolute; 
    background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
    padding: 15px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.15); 
    z-index: 100; text-align: left; width: 270px; 
    box-shadow: 0 20px 40px rgba(0,0,0,0.7); pointer-events: none;
    color: #e2e8f0; font-weight: 400; line-height: 1.4;
    animation: popIn 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards;
}
td:hover .tooltip { display: block; top: calc(100% + 10px); left: 50%; transform: translateX(-50%); }

/* Sub Panels (Analytics, Legend) */
.analytics-panel, .legend-panel { 
    margin-top: 25px; background: rgba(30, 41, 59, 0.4); 
    backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.05); border-radius: 16px; 
    padding: 20px; display: flex; flex-wrap: wrap; gap: 20px; box-shadow: 0 10px 30px -10px rgba(0,0,0,0.5);
}
.analytics-card, .legend-col { flex: 1; min-width: 250px; }
.analytics-card h4, .legend-col h4 { border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 10px; margin-top: 0; color: #38bdf8; letter-spacing: 0.5px;}
.analytics-card ul { margin: 0; padding-left: 20px; font-size: 13px; color: #cbd5e1;}
.analytics-card li { margin-bottom: 8px; line-height: 1.5; }
.analytics-card li b { color: #f8fafc; }

/* Legend details */
.legend-item { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; font-size: 13px; color: #94a3b8; }
.leg-box { width: 14px; height: 14px; border-radius: 50%; display: inline-block; box-shadow: inset 0 2px 4px rgba(0,0,0,0.3); }
.leg-box.st-good { background: #4ade80; }
.leg-box.st-warn { background: #fbbf24; }
.leg-box.st-crit { background: #f87171; }
.leg-box.st-dead { background: #475569; }
.leg-border-j { border-bottom: 3px solid #f97316; width: 14px; height: 10px; display: inline-block; background: rgba(255,255,255,0.05); border-radius:2px;}
.leg-border-a { border-right: 3px solid #eab308; width: 10px; height: 14px; display: inline-block; background: rgba(255,255,255,0.05); border-radius:2px;}

/* Animations */
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes slideDown { from { opacity: 0; transform: translateY(-20px); } to { opacity: 1; transform: translateY(0); } }
@keyframes popIn { 0% { opacity: 0; transform: translateX(-50%) scale(0.9); } 100% { opacity: 1; transform: translateX(-50%) scale(1); } }

/* Drag Overlay */
#dropOverlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(2, 6, 23, 0.9); backdrop-filter: blur(10px); z-index: 9999; justify-content: center; align-items: center; color: #38bdf8; font-size: 48px; border: 4px dashed rgba(56,189,248,0.5); box-sizing: border-box; font-family:'Outfit'; font-weight:800; text-shadow: 0 0 30px rgba(56,189,248,0.6);}
</style>
</head>
<body>
<div id="dropOverlay">Drop JSON file to load!</div>
<div class="header">
    <h1>📡 Network Ping Matrix 2.0</h1>
    <p id="sub-header">Loading local data...</p>
</div>
<div class="dashboard-metrics" id="metricsbox"></div>
<div class="analytics-panel" id="analyticsPanels" style="display:none;"></div>
<div class="controls">
    <select id="perspectiveMode" onchange="renderMatrix()" style="border-color:#00d2ff">
        <option value="both">View: Full Duplex (A ⇄ B)</option>
        <option value="ab">View: Direct (A ➟ B)</option>
        <option value="ba">View: Reverse (B ➟ A)</option>
    </select>
    <select id="viewMode" onchange="renderMatrix()">
        <option value="all">Show ALL Values</option>
        <option value="lat">Show Avg Latency</option>
        <option value="loss">Show Packet Loss</option>
        <option value="jit">Show Jitter Marks</option>
    </select>
    <input type="text" id="filterOrigin" placeholder="Filter Origin..." onkeyup="renderMatrix()">
    <input type="text" id="filterDest" placeholder="Filter Dest..." onkeyup="renderMatrix()">
</div>
<div class="matrix-wrapper">
    <table id="matrixTable"></table>
</div>
<div class="legend-panel">
    <div class="legend-col">
        <h4>🎨 Severity Colors (Cell Status)</h4>
        <div class="legend-item"><span class="leg-box st-good"></span> Healthy (0% Loss, no warnings)</div>
        <div class="legend-item"><span class="leg-box st-warn"></span> Warning (Loss > 0% up to 50% or Jitter/Asym warn)</div>
        <div class="legend-item"><span class="leg-box st-crit"></span> Critical (Loss > 50%)</div>
        <div class="legend-item"><span class="leg-box st-dead"></span> Unreachable (Host/BGP down, 100% loss)</div>
    </div>
    <div class="legend-col">
        <h4>👁️ Symbols & Markers</h4>
        <div class="legend-item"><span class="leg-border-j"></span> <b>High Jitter (Orange Border):</b> High variance between packets.</div>
        <div class="legend-item"><span class="leg-border-a"></span> <b>Asymmetric Route (Yellow Border):</b> Severe bidirecional asymmetry.</div>
        <div class="legend-item"><span style="text-decoration: line-through; color:#ccc">Txt</span> &nbsp;<b>ADM Blocking (Strikethrough):</b> Firewall Filters (Deny).</div>
    </div>
    <div class="legend-col">
        <h4>🔄 Duplex Mode (A ⇄ B)</h4>
        <div class="legend-item"><span style="color:#00d2ff; font-weight:bold;">🡲</span> <b>Direct</b> Path Metric (A pinging B)</div>
        <div class="legend-item"><span style="color:#ff007f; font-weight:bold;">🡰</span> <b>Reverse</b> Path Metric (B pinging A)</div>
        <div class="legend-item"><i style="font-size:11px; color:#888;">*In Hybrid Duplex Mode, the overall cell color reflects the WORST-CASE scenario of both directions.</i></div>
    </div>
</div>
<div style="text-align:center; padding: 20px; margin-top:10px; font-size: 13px; color: #64748b; font-weight: 600;">
    🔗 Powered by <a href="https://github.com/flashbsb/network-data-extractor" target="_blank" style="color: #38bdf8; text-decoration: none; border-bottom: 1px dashed #38bdf8;">network-data-extractor</a> &nbsp;|&nbsp; 
    Contribute or check for <a href="https://github.com/flashbsb/network-data-extractor" target="_blank" style="color: #38bdf8; text-decoration: none; border-bottom: 1px dashed #38bdf8;">new versions on GitHub</a>.
</div>
<script>
let globalData = null;
async function loadData() {
    try {
        const response = await fetch('ping_matrix_list.json');
        if (!response.ok) throw new Error('File not found or CORS blocked');
        globalData = await response.json();
        buildHeader(); renderMatrix(); buildAnalytics();
    } catch(err) {
        document.getElementById('sub-header').innerHTML = `<span style="color:#ff5e5e">Local File Load Disabled by Browser Security.</span>
        <br><label style="cursor:pointer; background:#333; padding:5px 15px; border-radius:5px; font-size:13px; margin-top:10px; display:inline-block; border: 1px solid #555;">
        📂 Browse or Drag <b>ping_matrix_list.json</b> anywhere
        <input type="file" accept=".json" style="display:none;" onchange="handleFileSelect(event)">
        </label>`;
    }
}
function buildHeader() {
    let md = globalData.metadata;
    document.getElementById('sub-header').innerHTML = `<span style="color:#5eff84">&#10003; Loaded Successfully</span> | Last Updated: ${md.datetime} | Size: ${md.config.datagram_size}B | Threads: ${md.config.threads}`;
}
function handleFileSelect(event) { processFile(event.target.files[0]); }
function processFile(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function(e) {
        try {
            globalData = JSON.parse(e.target.result);
            buildHeader(); renderMatrix(); buildAnalytics();
        } catch (err) { alert("Error parsing JSON file: " + err.message); }
    };
    reader.readAsText(file);
}

// Drag functionality
document.body.addEventListener('dragover', (e) => { e.preventDefault(); document.getElementById('dropOverlay').style.display = 'flex'; });
document.getElementById('dropOverlay').addEventListener('dragleave', (e) => { e.preventDefault(); document.getElementById('dropOverlay').style.display = 'none'; });
document.getElementById('dropOverlay').addEventListener('drop', (e) => {
    e.preventDefault(); document.getElementById('dropOverlay').style.display = 'none';
    processFile(e.dataTransfer.files[0]);
});

function buildAnalytics() {
    if (!globalData) return;
    document.getElementById('analyticsPanels').style.display = 'flex';
    let validLinks = globalData.data.filter(d => !d.is_unreachable && d.loss_pct < 100);
    let topLatency = [...validLinks].sort((a,b) => b.avg - a.avg).slice(0, 5);
    let topJitter = [...validLinks].sort((a,b) => (b.max - b.min) - (a.max - a.min)).slice(0, 5);
    
    let h = `<div class="analytics-card"><h4>⏱️ High Latency Links (Top 5)</h4><ul>`;
    topLatency.forEach(t => h += `<li><b>${t.origin} &rarr; ${t.dest}</b>: <span class="st-crit">${t.avg}ms</span></li>`);
    h += `</ul></div><div class="analytics-card"><h4>〰️ Highest Variance (Jitter Top 5)</h4><ul>`;
    topJitter.forEach(t => {
        let v = t.max - t.min;
        let c = t.jitter_warning ? 'st-crit' : 'st-warn';
        h += `<li><b>${t.origin} &rarr; ${t.dest}</b>: <span class="${c}">+${v}ms span</span> (Min ${t.min} / Max ${t.max})</li>`;
    });
    h += `</ul></div>`;
    document.getElementById('analyticsPanels').innerHTML = h;
}

function buildTooltip(o, d, dOut, dIn) {
    let html = `<b>${o} ⇄ ${d}</b><hr style="border-color:#444;margin:5px 0;">`;
    if (dOut) {
        html += `<span style="color:#00d2ff">🡲 <b>Direct Route (${o} &rarr; ${d})</b></span><br>`;
        html += `&nbsp;&nbsp; Time: ${dOut.min>=0?dOut.min:'-'} / ${dOut.avg>=0?dOut.avg:'-'} / ${dOut.max>=0?dOut.max:'-'} ms<br>`;
        html += `&nbsp;&nbsp; Loss: ${dOut.loss_pct.toFixed(1)}% | Warns: ${dOut.jitter_warning?'<span class="st-warn">J</span>':'_'}${dOut.asymmetric_warning?'<span class="st-warn">A</span>':'_'}<br>`;
    } else {
        html += `<span style="color:#00d2ff">🡲 Direct Route</span>: No data<br>`;
    }
    html += `<hr style="border-color:#333;margin:4px 0; border-top: 1px dashed #333;">`;
    if (dIn) {
        html += `<span style="color:#ff007f">🡰 <b>Reverse Route (${d} &rarr; ${o})</b></span><br>`;
        html += `&nbsp;&nbsp; Time: ${dIn.min>=0?dIn.min:'-'} / ${dIn.avg>=0?dIn.avg:'-'} / ${dIn.max>=0?dIn.max:'-'} ms<br>`;
        html += `&nbsp;&nbsp; Loss: ${dIn.loss_pct.toFixed(1)}% | Warns: ${dIn.jitter_warning?'<span class="st-warn">J</span>':'_'}${dIn.asymmetric_warning?'<span class="st-warn">A</span>':'_'}<br>`;
    } else {
        html += `<span style="color:#ff007f">🡰 Reverse Route</span>: No data<br>`;
    }
    return html;
}

function evalCss(val) {
    if (!val) return 'st-dead';
    if (val.is_unreachable || val.loss_pct == 100 || val.consistently_denied) return 'st-dead';
    if (val.loss_pct > 50) return 'st-crit';
    if (val.loss_pct > 0 || val.jitter_warning || val.asymmetric_warning) return 'st-warn';
    return 'st-good';
}

function fmt(val, mode, prefix) {
    if (!val) return `<div class="split-item" style="color:#555">${prefix} N/A</div>`;
    if (val.is_unreachable) return `<div class="split-item st-crit">${prefix} FAIL</div>`;
    let txt = "";
    if (mode === 'all') txt = `${val.avg}ms <span style="color:#aaa">|</span> ${val.loss_pct.toFixed(0)}% <span style="color:#aaa">|</span> J:${val.jitter_warning?'Y':'N'}`;
    else if (mode === 'loss') txt = `${val.loss_pct.toFixed(1)}% Loss`;
    else if (mode === 'jit') txt = val.jitter_warning ? "WARN" : "OK";
    else txt = val.avg >= 0 ? `${val.avg}ms` : 'N/A';
    return `<div class="split-item">${prefix} ${txt}</div>`;
}

function renderMatrix() {
    if (!globalData) return;
    let mode = document.getElementById('viewMode').value;
    let perspective = document.getElementById('perspectiveMode').value;
    let fOrig = document.getElementById('filterOrigin').value.toLowerCase();
    let fDest = document.getElementById('filterDest').value.toLowerCase();
    let nodesSet = new Set();
    globalData.data.forEach(d => { nodesSet.add(d.origin); nodesSet.add(d.dest); });
    let nodes = Array.from(nodesSet).sort((a, b) => a.localeCompare(b));
    let rowNodes = nodes.filter(n => n.toLowerCase().includes(fOrig));
    let colNodes = nodes.filter(n => n.toLowerCase().includes(fDest));
    
    let stGood=0, stJitter=0, stAsym=0, stDead=0;
    let dataMap = {};
    globalData.data.forEach(d => { 
        dataMap[`${d.origin}|${d.dest}`] = d; 
        if(d.is_unreachable || d.consistently_denied) stDead++;
        else if (d.jitter_warning) stJitter++;
        else if (d.asymmetric_warning) stAsym++;
        else stGood++;
    });
    document.getElementById('metricsbox').innerHTML = `
        <div class="metric-box"><h3>${nodes.length}</h3><span>Nodes Parsed</span></div>
        <div class="metric-box"><h3>${stGood}</h3><span>Healthy Connections</span></div>
        <div class="metric-box"><h3>${stJitter}</h3><span class="st-warn">Jitter Warnings</span></div>
        <div class="metric-box"><h3>${stAsym}</h3><span class="st-warn">Asymmetry Warnings</span></div>
        <div class="metric-box"><h3>${stDead}</h3><span class="st-crit">Dead Links / Loss</span></div>
    `;
    let html = '<tr><th class="row-head">O &#92; D</th>';
    colNodes.forEach(c => { html += `<th class="col-head">${c}</th>` });
    html += '</tr>';
    rowNodes.forEach(r => {
        html += `<tr><th class="row-head">${r}</th>`;
        colNodes.forEach(c => {
             if (r === c) { html += '<td class="st-self">-</td>'; return; }
             
             let dOut = dataMap[`${r}|${c}`];
             let dIn = dataMap[`${c}|${r}`];
             
             if (!dOut && !dIn) { html += '<td class="st-dead">N/A</td>'; return; }
             
             let primary = dOut;
             if (perspective === 'ba') primary = dIn;
             if (perspective === 'both' && !primary) primary = dIn;
             
             // Definir Fundo da Celula (Modo Both julga o cenário mais danificado)
             let cssClass = 'st-good';
             if (perspective === 'ab') cssClass = evalCss(dOut);
             else if (perspective === 'ba') cssClass = evalCss(dIn);
             else {
                 let cOut = evalCss(dOut);
                 let cIn = evalCss(dIn);
                 let wgt = { 'st-dead':4, 'st-crit':3, 'st-warn':2, 'st-good':1 };
                 let wOut = dOut ? wgt[cOut] : 0;
                 let wIn = dIn ? wgt[cIn] : 0;
                 cssClass = wOut >= wIn ? cOut : cIn;
             }
             
             let extClass = '';
             if (primary && primary.jitter_warning) extClass += ' marker-jitter';
             if (primary && primary.asymmetric_warning) extClass += ' marker-asym';
             if (primary && primary.consistently_denied) extClass += ' marker-deny';
             // No modo hibrido, adiciona Warning se QUALQUER perna tiver jitter
             if (perspective === 'both') {
                 if (dIn && dIn.jitter_warning && !extClass.includes('marker-jitter')) extClass += ' marker-jitter';
                 if (dIn && dIn.asymmetric_warning && !extClass.includes('marker-asym')) extClass += ' marker-asym';
             }
             
             let display = "";
             if (perspective === 'ab') display = fmt(dOut, mode, '');
             else if (perspective === 'ba') display = fmt(dIn, mode, '');
             else {
                 let pOut = '<span style="color:#00d2ff">🡲</span>';
                 let pIn = '<span style="color:#ff007f">🡰</span>';
                 display = fmt(dOut, mode, pOut) + fmt(dIn, mode, pIn);
             }

             let tip = `<div class="tooltip">${buildTooltip(r, c, dOut, dIn)}</div>`;
             html += `<td class="${cssClass}${extClass}" style="${perspective==='both'?'padding:0 4px;':''}">${display}${tip}</td>`;
        });
        html += '</tr>';
    });
    document.getElementById('matrixTable').innerHTML = html;
}
loadData();
</script>
</body>
</html>"""
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_template)
        print(f"Done. Interactive HTML saved to {html_path}")

if __name__ == "__main__":
    main()
