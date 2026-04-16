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
                    
                time.sleep(delay_between_commands)

            client.close()
            with results_lock:
                counter += 1
                curr = counter
            print(f"  [{curr:>{len(str(total_elements))}}/{total_elements}] [+] Ping Matrix from {origin_host} done.")
            logging.info(f"Ping Matrix from {origin_host} done.")
            
        except Exception as e:
            logging.error(f"Failed Matrix for {origin_host}: {e}")
            with results_lock:
                counter += 1
                curr = counter
            print(f"  [{curr:>{len(str(total_elements))}}/{total_elements}] [-] Ping Matrix from {origin_host} failed.")

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
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ping Matrix Dashboard</title>
<style>
body { background: #121212; color: #e0e0e0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; }
.header { text-align: center; margin-bottom: 20px; }
.filters { display: flex; justify-content: center; gap: 20px; margin-bottom: 20px; }
.filters input { padding: 8px; background: #2c2c2c; border: 1px solid #444; color: #fff; border-radius: 4px; width: 250px;}
.dashboard-metrics { display: flex; justify-content: space-around; background: #1e1e1e; padding: 15px; border-radius: 8px; margin-bottom: 20px;}
.metric-box { text-align: center; }
.metric-box h3 { margin: 0 0 5px 0; font-size: 24px; color: #00d2ff; }
.metric-box span { font-size: 14px; color: #888; }
.matrix-wrapper { overflow-x: auto; max-height: 70vh; }
table { border-collapse: collapse; margin: 0 auto; background: #1e1e1e; }
th, td { border: 1px solid #333; min-width: 60px; height: 60px; text-align: center; position: relative; cursor: default; }
th { background: #2c2c2c; position: sticky; padding: 5px; font-size: 12px; }
th.row-head { left: 0; z-index: 2; }
th.col-head { top: 0; z-index: 1; writing-mode: vertical-lr; transform: rotate(180deg); text-align: right; }
td { font-size: 12px; font-weight: bold;}
.st-good { background: #1a4223; color: #5eff84; }
.st-warn { background: #544414; color: #ffd64f; }
.st-crit { background: #4a1515; color: #ff5e5e; }
.st-dead { background: #1a1a1a; color: #555; }
.st-self { background: #2c2c2c; }
.marker-jitter { border-bottom: 4px solid #ff9800; }
.marker-asym { border-right: 4px solid #ffeb3b; }
.marker-deny { text-decoration: line-through; }
.tooltip { display: none; position: absolute; background: rgba(0,0,0,0.9); padding: 15px; border-radius: 6px; border: 1px solid #444; z-index: 100; text-align: left; width: 220px; box-shadow: 0 8px 16px rgba(0,0,0,0.5); pointer-events: none;}
td:hover .tooltip { display: block; top: 100%; left: 50%; transform: translateX(-50%); }
</style>
</head>
<body>
<div class="header">
    <h1>📡 Network Ping Matrix Dashboard</h1>
    <p id="sub-header">Loading local data...</p>
</div>
<div class="dashboard-metrics" id="metricsbox"></div>
<div class="filters">
    <input type="text" id="filterOrigin" placeholder="Filter Origin..." onkeyup="renderMatrix()">
    <input type="text" id="filterDest" placeholder="Filter Dest..." onkeyup="renderMatrix()">
</div>
<div class="matrix-wrapper">
    <table id="matrixTable"></table>
</div>
<script>
let globalData = null;
async function loadData() {
    try {
        const response = await fetch('ping_matrix_list.json');
        if (!response.ok) throw new Error('File not found or CORS blocked');
        globalData = await response.json();
        let md = globalData.metadata;
        document.getElementById('sub-header').innerHTML = `Last Updated: ${md.datetime} | Size: ${md.config.datagram_size}B | Ping Count: ${md.config.count}`;
        renderMatrix();
    } catch(err) {
        document.getElementById('sub-header').innerHTML = `<span style="color:#ff5e5e">Local File Load Disabled by Browser Security.</span>
        <br><label style="cursor:pointer; background:#333; padding:5px 15px; border-radius:5px; font-size:13px; margin-top:10px; display:inline-block; border: 1px solid #555;">
        📂 Browse and Load <b>ping_matrix_list.json</b>
        <input type="file" accept=".json" style="display:none;" onchange="handleFileSelect(event)">
        </label>`;
    }
}
function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function(e) {
        try {
            globalData = JSON.parse(e.target.result);
            let md = globalData.metadata;
            document.getElementById('sub-header').innerHTML = `<span style="color:#5eff84">Loaded Manually!</span> Last Updated: ${md.datetime} | Size: ${md.config.datagram_size}B`;
            renderMatrix();
        } catch (err) {
            alert("Error parsing JSON file: " + err.message);
        }
    };
    reader.readAsText(file);
}
function renderMatrix() {
    if (!globalData) return;
    let fOrig = document.getElementById('filterOrigin').value.toLowerCase();
    let fDest = document.getElementById('filterDest').value.toLowerCase();
    let nodesSet = new Set();
    globalData.data.forEach(d => { nodesSet.add(d.origin); nodesSet.add(d.dest); });
    let nodes = Array.from(nodesSet).sort();
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
        <div class="metric-box"><h3>${stJitter}</h3><span style="color:#ff9800">Jitter Warnings</span></div>
        <div class="metric-box"><h3>${stAsym}</h3><span style="color:#ffeb3b">Asymmetry Warnings</span></div>
        <div class="metric-box"><h3>${stDead}</h3><span style="color:#ff5e5e">Dead Links / Loss</span></div>
    `;
    let html = '<tr><th class="row-head">O &#92; D</th>';
    colNodes.forEach(c => { html += `<th class="col-head">${c}</th>` });
    html += '</tr>';
    rowNodes.forEach(r => {
        html += `<tr><th class="row-head">${r}</th>`;
        colNodes.forEach(c => {
             if (r === c) { html += '<td class="st-self">-</td>'; return; }
             let val = dataMap[`${r}|${c}`];
             if (!val) { html += '<td class="st-dead">N/A</td>'; return; }
             let cssClass = 'st-good';
             if (val.is_unreachable || val.loss_pct == 100 || val.consistently_denied) cssClass = 'st-dead';
             else if (val.loss_pct > 0 && val.loss_pct <= 50) cssClass = 'st-warn';
             else if (val.loss_pct > 50) cssClass = 'st-crit';
             else if (val.jitter_warning || val.asymmetric_warning) cssClass = 'st-warn';
             let extClass = '';
             if (val.jitter_warning) extClass += ' marker-jitter';
             if (val.asymmetric_warning) extClass += ' marker-asym';
             if (val.consistently_denied) extClass += ' marker-deny';
             let display = val.is_unreachable ? "FAIL" : (val.avg >= 0 ? val.avg + "ms" : "N/A");
             let tip = `<div class="tooltip">
                <b>${r} &rarr; ${c}</b><hr style="border-color:#444;margin:5px 0;">
                <span class="st-good">T_Min:</span> ${val.min >= 0 ? val.min+'ms' : '-'}<br>
                <span class="st-warn">T_Avg:</span> ${val.avg >= 0 ? val.avg+'ms' : '-'}<br>
                <span class="st-crit">T_Max:</span> ${val.max >= 0 ? val.max+'ms' : '-'}<br>
                Loss: ${val.loss_pct.toFixed(1)}% (${val.rx}/${val.tx})<br><br>
                Jitter Warn: ${val.jitter_warning ? '<span style="color:#ff9800">YES</span>':'NO'}<br>
                Asym Warn: ${val.asymmetric_warning ? '<span style="color:#ffeb3b">YES</span>':'NO'}<br>
                Denied: ${val.consistently_denied ? 'YES':'NO'}<br>
             </div>`;
             html += `<td class="${cssClass}${extClass}">${display}${tip}</td>`;
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
