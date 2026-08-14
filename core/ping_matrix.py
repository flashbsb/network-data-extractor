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

# Add project root to sys.path to allow imports from core/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Regex for Ping Capture (Supports normal Cisco, Datacom, Huawei formats)
# Cisco: "5 packets transmitted, 5 packets received, 0% packet loss"
# Cisco RTT: "round-trip min/avg/max = 1/2/3 ms"
# Huawei: "5 packet(s) transmitted... 5 packet(s) received"
# Huawei RTT: "round-trip min/avg/max = 1/2/3 ms"

from core.utils_shared import load_settings

json_config = load_settings()
ping_cfg = json_config.get("ping_matrix", {})

RE_TRANSMITTED = re.compile(ping_cfg.get("transmitted_regex", r"(\d+)\s+packet[s]?\s*(?:\([a-zA-Z\s]+\))? transmitted"), re.IGNORECASE)
RE_RECEIVED = re.compile(ping_cfg.get("received_regex", r"(\d+)\s+packet[s]?\s*(?:\([a-zA-Z\s]+\))? received"), re.IGNORECASE)
RE_RTT = re.compile(ping_cfg.get("rtt_regex", r"min(?:imum)?/avg(?:erage)?/max(?:imum)?.*?=\s*([\d\.]+)/([\d\.]+)/([\d\.]+)"), re.IGNORECASE)
CISCO_SUCCESS_PATTERN = ping_cfg.get("cisco_success_regex", r"Success rate is \d+\s*percent\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)")
UNREACHABLE_INDICATORS = ping_cfg.get("unreachable_indicators", ["U.U.U", "Admin Prohibited", "Destination unreachable"])

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
                ip = parts[1].split('|')[0] # Get the first IP
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
                # Normalize key to lowercase for case-insensitive matching
                commands[key.strip().lower()] = cmd.strip()
    return commands

def get_element_role(hostname, json_config):
    routing_hierarchy = json_config.get("routing_hierarchy", {})
    hostname_upper = hostname.upper()
    for role, prefixes in routing_hierarchy.items():
        if role.startswith("_help"):
            continue
        if isinstance(prefixes, list):
            for prefix in prefixes:
                if prefix.upper() in hostname_upper:
                    return role
    return None

def is_pair_allowed(origin_host, dest_host, json_config):
    ping_cfg = json_config.get("ping_matrix", {})
    mode = ping_cfg.get("mode", "selective")
    if str(mode).lower() == "full":
        return True

    matrix_rules = ping_cfg.get("matrix_rules", {})
    if not matrix_rules:
        return True

    default_allow = ping_cfg.get("default_allow_unmapped", False)
    routing_hierarchy = json_config.get("routing_hierarchy", {})

    origin_role = get_element_role(origin_host, json_config)
    dest_role = get_element_role(dest_host, json_config)

    origin_key = origin_role if (origin_role and origin_role in matrix_rules) else None
    if not origin_key:
        for k in matrix_rules.keys():
            if k.startswith("_help"):
                continue
            if k.upper() in origin_host.upper():
                origin_key = k
                break

    if not origin_key:
        return default_allow

    allowed_targets = matrix_rules.get(origin_key, [])
    
    if dest_role and dest_role in allowed_targets:
        return True

    dest_host_upper = dest_host.upper()
    for target in allowed_targets:
        if target.upper() in dest_host_upper:
            return True
        role_prefixes = routing_hierarchy.get(target, [])
        if isinstance(role_prefixes, list):
            for p in role_prefixes:
                if p.upper() in dest_host_upper:
                    return True

    return False


def parse_ping_output(output, host_dest):
    # Default values
    tx, rx = 0, 0
    t_min, t_avg, t_max = -1.0, -1.0, -1.0
    consistently_denied = False
    
    tx_match = RE_TRANSMITTED.search(output)
    if tx_match:
        tx = int(tx_match.group(1))
        
    rx_match = RE_RECEIVED.search(output)
    if rx_match:
        rx = int(rx_match.group(1))

    # Support for Cisco's native format: "Success rate is 100 percent (5/5)"
    if CISCO_SUCCESS_PATTERN:
        cisco_match = re.search(CISCO_SUCCESS_PATTERN, output, re.IGNORECASE)
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
    if UNREACHABLE_INDICATORS:
        for indicator in UNREACHABLE_INDICATORS:
            if indicator in output:
                consistently_denied = True
                break
        
    is_unreachable = (tx > 0 and rx == 0)
    
    # If packets were lost but parsing failed
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
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    _DEFAULT_SETTINGS = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "config", "settings.json"))
    parser.add_argument("--settings", default=_DEFAULT_SETTINGS)
    parser.add_argument("--ping_commands", default="config/commands.icmp.cfg")
    parser.add_argument("--ping_format", default="csv")
    parser.add_argument("--offline_mode", action="store_true")
    parser.add_argument("--timestamp", default="")
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
    if not args.offline_mode:
        env_user = os.environ.get('NDX_SSH_USER')
        env_pass = os.environ.get('NDX_SSH_PASS')
        env_key  = os.environ.get('NDX_SSH_KEY')
        
        user = env_user if env_user else input('SSH Worker User: ')
        password = env_pass
        if not env_key and env_pass is None:
            password = getpass.getpass('SSH Password: ')

    all_results = []
    results_lock = threading.Lock()
    counter = 0
    total_elements = len(elements)
    
    # Use provided timestamp or generate a new one
    # NOTE: when orchestrator passes --timestamp "" it means 'no suffix — each run has its own folder'
    # An empty string means no suffix. Only generate a new timestamp if the arg was truly not provided.
    if args.timestamp == "NONE":
        # Orchestrator-managed run: files get standard names (no suffix) inside their own folder
        timestamp = datetime.datetime.now().strftime('%d%m%y%H%M%S')
        file_suffix = ""
    else:
        timestamp = args.timestamp if args.timestamp else datetime.datetime.now().strftime('%d%m%y%H%M%S')
        file_suffix = f"_{timestamp}"

    def execute_ping_matrix_for_origin(origin_elem):
        nonlocal counter
        origin_host = origin_elem['hostname']
        origin_ip = origin_elem['ip']
        cmd_key = origin_elem['cmd_key']
        
        base_cmd = icmp_cmds.get(cmd_key.lower())
        if not base_cmd:
            logging.warning(f"No ICMP command found for '{cmd_key}' (Host: {origin_host}). Available keys: {list(icmp_cmds.keys())}")
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
                if not is_pair_allowed(origin_host, dest_elem['hostname'], json_config):
                    continue

                
                dest_ip = dest_elem['ip']
                # Format command
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
                        # If idle for 1.5s and prompt is in buffer, assume completed
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
                
                # Store partial result
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

    import math
    total_origins = len(elements)
    allowed_pair_count = 0
    for o_elem in elements:
        for d_elem in elements:
            if o_elem['hostname'] == d_elem['hostname']:
                continue
            if is_pair_allowed(o_elem['hostname'], d_elem['hostname'], json_config):
                allowed_pair_count += 1

    total_possible_pings = total_origins * (total_origins - 1) if total_origins > 1 else 0
    total_pings = allowed_pair_count
    pings_per_origin = math.ceil(total_pings / total_origins) if total_origins > 0 else 0
    matrix_start_time = time.time()

    if args.offline_mode:
        import glob
        print("\n" + "="*60)
        print(" 📡 PING MATRIX EXECUTION PLAN (OFFLINE MODE)")
        print("="*60)
        print(f" • Reading cached ping results from: {args.collect_dir}")
        
        # Find raw ping matrix files saved in previous runs
        files = glob.glob(os.path.join(args.collect_dir, "*.ping_to_*.txt"))
        print(f" • Found {len(files)} cached result files.")
        print("="*60)
        print("Parsing cached ICMP responses...")
        
        for fpath in files:
            fname = os.path.basename(fpath)
            origin_host = "Unknown"
            dest_host = "Unknown"
            content = ""
            
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.startswith("# Origin:"):
                        origin_host = line.split("Origin:")[1].split("(")[0].strip()
                    elif line.startswith("# Dest:"):
                        dest_host = line.split("Dest:")[1].split("(")[0].strip()
                    else:
                        content += line
            
            parsed = parse_ping_output(content, dest_host)
            parsed['origin'] = origin_host
            
            # Use the timestamp of the modified file
            mtime = os.path.getmtime(fpath)
            parsed['timestamp'] = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            all_results.append(parsed)
            print(".", end="", flush=True)
            
        print(f"\n\n[+] Offline Matrix processed {len(all_results)} entries.")
        actual_duration_seconds = round(time.time() - matrix_start_time, 1)
        est_total_seconds = actual_duration_seconds

    else:
        batches = math.ceil(total_origins / thread_count) if thread_count > 0 else 1
        local_delay = min(delay_between_commands, 0.2)
        time_per_dest = (10 * count) / 1000.0 + local_delay
        ssh_overhead = 1.5 
        time_per_batch = ssh_overhead + (pings_per_origin * time_per_dest)
        est_total_seconds = batches * time_per_batch
        
        m, s = divmod(int(est_total_seconds), 60)
        h, m = divmod(m, 60)
        est_str = f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s"
        
        mode_str = ping_cfg.get("mode", "selective").upper()
        saved_pings = total_possible_pings - total_pings
        print("\n" + "="*60)
        print(f" 📡 PING MATRIX EXECUTION PLAN ({mode_str} MODE)")
        print("="*60)
        print(f" • Origin Elements : {total_origins}")
        print(f" • Target Pings    : {total_pings} (Saved {saved_pings} out-of-scope pings from {total_possible_pings} max)")
        print(f" • Est. Duration   : ~{est_str} (Based on 10ms avg latency)")
        print("   * Note: Actual time will fluctuate depending on real network latency.")
        print("="*60)
        print(f"Starting ICMP requests concurrently (Threads: {thread_count})...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
            executor.map(execute_ping_matrix_for_origin, elements)
            
        actual_duration_seconds = round(time.time() - matrix_start_time, 1)

    # Post processing: Asymmetry and Jitter Warning
    print("Generating statistical analysis and List CSV...")
    
    # Build dictionary for quick lookup of inverse route
    lookup = {}
    for r in all_results:
        lookup[(r['origin'], r['dest'])] = r

    # Setup parameters
    ping_format = args.ping_format.lower()
    # The HTML option embeds the JSON natively. Do not force creation of the .json file
    # if the user specifically requested only HTML
        
    ex_csv  = 'csv' in ping_format or ping_format == ''
    ex_json = 'json' in ping_format
    ex_html = 'html' in ping_format
    
    final_csv_dados = []
    final_output_data = [] # To store the entire extended list in JSON
    
    for r in all_results:
        o = r['origin']
        d = r['dest']
        
        # Estimated jitter
        tmin = r['min']
        tmax = r['max']
        tavg = r['avg']
        jitter_warning = False
        if tavg > 0 and tmax >= 0 and tmin >= 0:
            if (tmax - tmin) > 5.0:
                if ((tmax - tmin) / tavg) > 0.4:
                    jitter_warning = True
        
        # Asymmetric
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

    # Analytical Health Aggregations
    matrix_health = {
        "total_links": len(final_output_data),
        "healthy": 0,
        "warning": 0,
        "critical": 0,
        "dead": 0
    }
    
    node_stats = {}
    for elem in elements:
        node_stats[elem['hostname']] = {
            "total_targets": 0,
            "success_targets": 0,
            "sum_latency": 0.0,
            "valid_latency_count": 0,
            "reachability_pct": 0.0,
            "avg_global_latency": -1.0
        }
        
    for r in final_output_data:
        # Matrix Health
        if r['is_unreachable'] or r['loss_pct'] == 100 or r['consistently_denied']:
            matrix_health["dead"] += 1
        elif r['loss_pct'] > 50:
            matrix_health["critical"] += 1
        elif r['loss_pct'] > 0 or r['jitter_warning'] or r['asymmetric_warning']:
            matrix_health["warning"] += 1
        else:
            matrix_health["healthy"] += 1
            
        # Node Stats
        o = r['origin']
        if o in node_stats:
            node_stats[o]["total_targets"] += 1
            if not r['is_unreachable'] and r['loss_pct'] < 100:
                node_stats[o]["success_targets"] += 1
            if r['avg'] > 0:
                node_stats[o]["sum_latency"] += r['avg']
                node_stats[o]["valid_latency_count"] += 1

    for o, stats in node_stats.items():
        if stats["total_targets"] > 0:
            stats["reachability_pct"] = round((stats["success_targets"] / stats["total_targets"]) * 100.0, 1)
        if stats["valid_latency_count"] > 0:
            stats["avg_global_latency"] = round(stats["sum_latency"] / stats["valid_latency_count"], 1)

    if ex_csv:
        csv_path = os.path.join(args.resume_dir, f"ping_matrix_list{file_suffix}.csv")
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(["Timestamp", "Origin_Node", "Destination_Node", "Min_ms", "Avg_ms", "Max_ms", "Size", "Transmitted", "Received", "Loss_Pct", "Is_Unreachable", "Jitter_Warning", "Asymmetric_Warning", "Consistently_Denied"])
            writer.writerows(final_csv_dados)
        print(f"Done. CSV saved to {csv_path}")

    json_payload = {
        "metadata": {
            "datetime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "nodes_connected": total_elements,
            "config": {
                "count": count,
                "datagram_size": size,
                "timeout": timeout_ping,
                "threads": thread_count,
                "matrix_mode": ping_cfg.get("mode", "selective")
            },
            "execution_metrics": {
                "total_origins": total_origins,
                "pings_per_origin": pings_per_origin,
                "total_pings_expected": total_pings,
                "total_possible_pings": total_possible_pings,
                "estimated_duration_seconds": round(est_total_seconds, 1),
                "actual_duration_seconds": actual_duration_seconds
            },
            "network_health": matrix_health,
            "node_stats": node_stats
        },
        "data": final_output_data
    }

    if ex_json:
        json_path = os.path.join(args.resume_dir, f"ping_matrix_list{file_suffix}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_payload, f, indent=4)
        print(f"Done. JSON saved to {json_path}")
    if ex_html:
        html_path = os.path.join(args.resume_dir, f"ping_matrix_dashboard{file_suffix}.html")
        html_content = render_ping_matrix_html(json_payload)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"Done. Interactive HTML saved to {html_path}")

def render_ping_matrix_html(json_payload):
    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="description" content="Network Ping Matrix Telemetry Dashboard">
<meta property="og:title" content="Network Ping Matrix">
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

.hud-header { 
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    padding-bottom: 15px;
    margin-bottom: 30px; 
    animation: fadeIn 0.8s ease; 
}
.title-group {
    text-align: left;
}
.header h1 { font-size: 38px; font-weight: 800; margin: 0; background: linear-gradient(90deg, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; filter: drop-shadow(0 0 10px rgba(56,189,248,0.3)); }
#sub-header { color: #94a3b8; font-size: 14px; margin-top: 5px; line-height: 1.4; }
.back-portal {
    background: rgba(30, 41, 59, 0.4);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    color: #38bdf8;
    border: 1px solid rgba(255, 255, 255, 0.05);
    padding: 8px 12px;
    border-radius: 8px;
    font-weight: 600;
    text-decoration: none;
    text-transform: uppercase;
    font-size: 0.85rem;
    transition: all 0.2s;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
}
.back-portal:hover {
    border-color: #38bdf8;
    color: #fff;
    background: rgba(56, 189, 248, 0.15);
    box-shadow: 0 0 15px rgba(56, 189, 248, 0.2);
}

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
.controls { display: flex; justify-content: center; align-items: center; gap: 15px; margin-bottom: 25px; flex-wrap: wrap; }
.controls input[type="text"], .controls select { 
    padding: 10px 15px; background: rgba(15, 23, 42, 0.6); 
    border: 1px solid rgba(255,255,255,0.1); color: #f8fafc; 
    border-radius: 8px; font-family: 'Inter', sans-serif; font-size: 14px;
    transition: all 0.3s ease; box-shadow: inset 0 2px 4px rgba(0,0,0,0.5);
}
.controls input[type="text"]:focus, .controls select:focus { outline: none; border-color: #38bdf8; box-shadow: 0 0 0 2px rgba(56,189,248,0.2); }

/* Toggle Checkboxes */
.filter-group { display: flex; align-items: center; gap: 8px; background: rgba(15,23,42,0.4); padding: 5px 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); }
.filter-group > span { font-size: 12px; color: #94a3b8; font-weight: 600; margin-right: 5px; text-transform: uppercase; letter-spacing: 0.5px;}
.toggle-btn { cursor: pointer; padding: 6px 12px; font-size: 13px; font-weight: 600; color: #64748b; border-radius: 6px; transition: all 0.2s ease; border: 1px solid rgba(255,255,255,0.05); background: rgba(255,255,255,0.02); display: flex; align-items: center; gap: 5px; user-select: none; }
.toggle-btn input[type="checkbox"] { display: none; }
.toggle-btn:has(input:checked) { background: rgba(56,189,248,0.1); color: #38bdf8; border-color: rgba(56,189,248,0.4); text-shadow: 0 0 8px rgba(56,189,248,0.5); box-shadow: inset 0 0 10px rgba(56,189,248,0.1); }
.toggle-btn:hover { background: rgba(255,255,255,0.08); }
.reset-btn { 
    padding: 10px 15px; background: rgba(248, 113, 113, 0.1); 
    border: 1px solid rgba(248, 113, 113, 0.3); color: #f87171; 
    border-radius: 8px; font-family: 'Inter', sans-serif; font-size: 13px;
    font-weight: 600; cursor: pointer; transition: all 0.3s ease;
}
.reset-btn:hover { background: rgba(248, 113, 113, 0.2); border-color: #f87171; box-shadow: 0 0 15px rgba(248, 113, 113, 0.2); }

/* Analytics Collapse */
.analytics-header { width: 100%; display: flex; justify-content: space-between; align-items: center; cursor: pointer; transition: all 0.3s ease;}
.analytics-header h3 { margin: 0; color: #38bdf8; font-size: 20px; transition: all 0.3s ease; }
.analytics-header:hover h3 { text-shadow: 0 0 15px rgba(56,189,248,0.6); }
.analytics-content { width: 100%; display: flex; flex-wrap: wrap; gap: 20px; margin-top: 20px; border-top: 1px dashed rgba(255,255,255,0.1); padding-top: 20px; }
.analytics-card { flex: 1 1 300px; min-width: 250px; background: rgba(15, 23, 42, 0.5); padding: 15px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); }
.analytics-card h4 { margin-top: 0; color: #cbd5e1; font-size: 14px; }
.analytics-card ul { padding-left: 20px; margin: 0; font-size: 13px; color: #94a3b8; }
.analytics-card li { margin-bottom: 5px; }

/* Matrix Table */
.matrix-wrapper { 
    overflow: auto; max-height: 85vh; 
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
.st-filtered { background: rgba(30, 41, 59, 0.2) !important; color: #475569; }
.st-self { background: rgba(30,41,59,0.3) !important; color: #334155; }

/* Split cell */
.split-item { padding: 4px 0; border-bottom: 1px dashed rgba(255,255,255,0.1); }
.split-item:last-child { border-bottom: none; }

/* Markers */
.marker-jitter { border-bottom: 3px solid #f97316; }
.marker-asym { border-right: 3px solid #eab308; }
.marker-deny { text-decoration: line-through; opacity: 0.5; }

/* Smart Floating Tooltip */
#globalTooltip { 
    display: none; position: fixed; 
    background: rgba(15, 23, 42, 0.9); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    padding: 15px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.15); 
    z-index: 10000; text-align: left; 
    width: max-content; min-width: 250px; max-width: 400px;
    box-sizing: border-box; word-break: normal; margin: 0 !important;
    box-shadow: 0 20px 40px rgba(0,0,0,0.6); pointer-events: none;
    color: #f8fafc; font-weight: 400; line-height: 1.4; font-size: 13px;
    opacity: 1; transition: opacity 0.15s ease;
}
#globalTooltip b { color: #38bdf8; }
#globalTooltip hr { border: none; border-top: 1px solid rgba(255,255,255,0.1); margin: 8px 0; }

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
.analytics-card li { margin-bottom: 8px; line-height: 1.5; cursor: pointer; transition: all 0.2s; border-radius: 4px; padding: 2px 4px; }
.analytics-card li:hover { background: rgba(56, 189, 248, 0.1); color: #38bdf8; }
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
@keyframes popIn { 0% { opacity: 0; transform: var(--tw, translateX(-50%)) scale(0.9); } 100% { opacity: 1; transform: var(--tw, translateX(-50%)) scale(1); } }

/* Drag Overlay */
#dropOverlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(2, 6, 23, 0.9); backdrop-filter: blur(10px); z-index: 9999; justify-content: center; align-items: center; color: #38bdf8; font-size: 48px; border: 4px dashed rgba(56,189,248,0.5); box-sizing: border-box; font-family:'Outfit'; font-weight:800; text-shadow: 0 0 30px rgba(56,189,248,0.6);}

/* Context Menu */
.context-menu {
    position: absolute;
    background: #0f172a;
    border: 1px solid rgba(255,255,255,0.1);
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
    color: #e2e8f0;
    font-size: 0.85rem;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 10px;
    transition: background 0.2s, color 0.2s;
    text-align: left;
}
.context-menu a:hover {
    background: rgba(56, 189, 248, 0.1);
    color: #38bdf8;
}
.context-menu .menu-header {
    padding: 6px 16px;
    font-size: 0.7rem;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    margin-bottom: 4px;
    text-align: left;
}
</style>
</head>
<body>
<div id="dropOverlay">Drop JSON file to load!</div>
<div class="hud-header">
    <div class="title-group">
        <h1>📡 Network Ping Matrix</h1>
        <p id="sub-header">Loading local data...</p>
    </div>
    <a class="back-portal" href="../../../../index.html">← Network Portal</a>
</div>
<div class="dashboard-metrics" id="metricsbox"></div>
<div class="controls" style="display: flex; flex-direction: column; gap: 15px; align-items: center;">
    <div class="filter-row" style="display: flex; gap: 15px; align-items: center; justify-content: center; width: 100%; flex-wrap: wrap;">
        <input type="text" id="filterOrigin" placeholder="Filter Origin (eg. bsa;gti)..." onkeyup="renderMatrix()" aria-label="Filter origin elements" style="width: 250px;">
        <input type="text" id="filterDest" placeholder="Filter Dest (eg. bsa;gti)..." onkeyup="renderMatrix()" aria-label="Filter destination elements" style="width: 250px;">
        <button class="reset-btn" onclick="clearAllFilters()" style="background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); color: #f87171; height: 38px;">🧹 Clear All</button>
        <button class="reset-btn" onclick="selectAllFilters()" style="background: rgba(56,189,248,0.1); border: 1px solid rgba(56,189,248,0.3); color: #38bdf8; height: 38px;">✅ Select All</button>
        <button class="reset-btn" onclick="exportMatrixCSV()" style="background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.3); color: #4ade80; height: 38px;">📥 Export CSV</button>
    </div>
    <div class="filter-row" style="display: flex; gap: 15px; align-items: center; justify-content: center; width: 100%; flex-wrap: wrap;">
        <div class="filter-group">
            <span>Path:</span>
            <label class="toggle-btn"><input type="checkbox" id="chkDirect" checked onchange="renderMatrix()"> Direct 🡲</label>
            <label class="toggle-btn"><input type="checkbox" id="chkReverse" checked onchange="renderMatrix()"> Reverse 🡰</label>
            <label class="toggle-btn"><input type="checkbox" id="chkHideScope" checked onchange="renderMatrix()"> Hide Out-of-Scope 🚫</label>
        </div>
        <div class="filter-group">
            <span>Metrics:</span>
            <label class="toggle-btn"><input type="checkbox" id="chkLat" checked onchange="renderMatrix()"> Latency</label>
            <label class="toggle-btn"><input type="checkbox" id="chkLoss" checked onchange="renderMatrix()"> Loss</label>
            <label class="toggle-btn"><input type="checkbox" id="chkWarn" checked onchange="renderMatrix()"> Warns</label>
        </div>
        <div class="filter-group" style="border-color: rgba(248, 113, 113, 0.3);">
            <span style="color: #f87171;">Severity:</span>
            <label class="toggle-btn" style="border-color: rgba(248, 113, 113, 0.4);"><input type="checkbox" id="sevCrit" checked onchange="renderMatrix()"> ❌ Critical</label>
            <label class="toggle-btn" style="border-color: rgba(248, 113, 113, 0.4);"><input type="checkbox" id="sevLoss" checked onchange="renderMatrix()"> 📉 Loss</label>
            <label class="toggle-btn" style="border-color: rgba(248, 113, 113, 0.4);"><input type="checkbox" id="sevJit" checked onchange="renderMatrix()"> 〰️ Jitter</label>
            <label class="toggle-btn" style="border-color: rgba(248, 113, 113, 0.4);"><input type="checkbox" id="sevAsym" checked onchange="renderMatrix()"> ⚖️ Asym</label>
            <label class="toggle-btn" style="border-color: rgba(74, 222, 128, 0.4);"><input type="checkbox" id="sevHealthy" checked onchange="renderMatrix()"> ✅ Healthy</label>
        </div>
    </div>
</div>
<div class="matrix-wrapper">
    <table id="matrixTable"></table>
</div>
<div class="analytics-panel" id="analyticsPanels" style="display:none;"></div>
<div class="legend-panel">
    <div class="analytics-header" onclick="toggleLegend()">
        <h3>📖 Documentation & Legend</h3>
        <span id="legendToggleIcon" style="color:#38bdf8; font-size:16px;">▼</span>
    </div>
    <div id="legendContent" class="analytics-content" style="display:none; margin-top: 5px; padding-top: 15px;">
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
</div>
<div style="text-align:center; padding: 20px; margin-top:10px; font-size: 13px; color: #64748b; font-weight: 600;">
    🔗 Powered by <a href="https://github.com/flashbsb/network-data-extractor" target="_blank" style="color: #38bdf8; text-decoration: none; border-bottom: 1px dashed #38bdf8;">network-data-extractor</a> &nbsp;|&nbsp; 
    Contribute or check for <a href="https://github.com/flashbsb/network-data-extractor" target="_blank" style="color: #38bdf8; text-decoration: none; border-bottom: 1px dashed #38bdf8;">new versions on GitHub</a>.
</div>
<script>
if (window.self !== window.top) {
    const backBtn = document.querySelector('.back-portal');
    if (backBtn) backBtn.style.display = 'none';
}
let globalData = __JSON_PAYLOAD_HERE__;
let dataMap = {};

function getQueryParam(name) {
    let params = new URLSearchParams(window.location.search);
    if (params.has(name)) return params.get(name);
    try {
        if (window.parent && window.parent !== window) {
            let parentParams = new URLSearchParams(window.parent.location.search);
            if (parentParams.has(name)) return parentParams.get(name);
        }
    } catch (e) {
        // Ignore cross-origin issues if any
    }
    return null;
}

function loadData() {
    const origin = getQueryParam('origin');
    const dest = getQueryParam('dest');
    if (origin) document.getElementById('filterOrigin').value = origin;
    if (dest) document.getElementById('filterDest').value = dest;

    buildHeader(); renderMatrix(); buildAnalytics();
}
function buildHeader() {
    let md = globalData.metadata;
    let html = `<span style="color:#5eff84">&#10003; Loaded Successfully</span> | <b>Run Date:</b> ${md.datetime}`;
    if (md.execution_metrics) {
        let em = md.execution_metrics;
        html += `<br><span style="font-size:12px; color:#64748b; margin-top:4px; display:inline-block;"><b>Scope:</b> ${em.total_origins} Nodes &nbsp;|&nbsp; <b>Total Tests:</b> ${em.total_pings_expected} &nbsp;|&nbsp; <b>Threads:</b> ${md.config.threads} &nbsp;|&nbsp; <b>Time Taken:</b> ${em.actual_duration_seconds}s (Est: ${em.estimated_duration_seconds}s)</span>`;
    } else {
        html += ` | Size: ${md.config.datagram_size}B | Threads: ${md.config.threads}`;
    }
    document.getElementById('sub-header').innerHTML = html;
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

function toggleAnalytics() {
    let content = document.getElementById('analyticsContent');
    let icon = document.getElementById('analyticsToggleIcon');
    if (content.style.display === 'none') {
        content.style.display = 'flex';
        icon.innerHTML = '▲';
    } else {
        content.style.display = 'none';
        icon.innerHTML = '▼';
    }
}

function toggleLegend() {
    let content = document.getElementById('legendContent');
    let icon = document.getElementById('legendToggleIcon');
    if (content.style.display === 'none') {
        content.style.display = 'flex';
        icon.innerHTML = '▲';
    } else {
        content.style.display = 'none';
        icon.innerHTML = '▼';
    }
}

function clearAllFilters() {{
    const ids = ['chkDirect', 'chkReverse', 'chkLat', 'chkLoss', 'chkWarn', 'sevCrit', 'sevLoss', 'sevJit', 'sevAsym', 'sevHealthy'];
    ids.forEach(id => {{
        let el = document.getElementById(id);
        if (el) el.checked = false;
    }});
    let fOrig = document.getElementById('filterOrigin');
    if (fOrig) fOrig.value = '';
    let fDest = document.getElementById('filterDest');
    if (fDest) fDest.value = '';
    renderMatrix();
}}

function selectAllFilters() {{
    const ids = ['chkDirect', 'chkReverse', 'chkLat', 'chkLoss', 'chkWarn', 'sevCrit', 'sevLoss', 'sevJit', 'sevAsym', 'sevHealthy'];
    ids.forEach(id => {{
        let el = document.getElementById(id);
        if (el) el.checked = true;
    }});
    renderMatrix();
}}

function exportMatrixCSV() {{
    if (!globalData || !dataMap) {{
        alert("No data available");
        return;
    }}
    
    let showDirect = document.getElementById('chkDirect').checked;
    let showReverse = document.getElementById('chkReverse').checked;
    let perspective = 'none';
    if (showDirect && showReverse) perspective = 'both';
    else if (showDirect) perspective = 'ab';
    else if (showReverse) perspective = 'ba';
    
    let isAllSelected = document.getElementById('sevCrit').checked && 
                        document.getElementById('sevLoss').checked && 
                        document.getElementById('sevJit').checked && 
                        document.getElementById('sevAsym').checked && 
                        document.getElementById('sevHealthy').checked;
                        
    let fOrig = document.getElementById('filterOrigin').value.toLowerCase();
    let fDest = document.getElementById('filterDest').value.toLowerCase();
    
    let nodesSet = new Set();
    let validPairs = new Set();
    
    globalData.data.forEach(d => {{
        let r = d.origin; let c = d.dest;
        let dOut = d;
        let dIn = dataMap[`${c}|${r}`];
        
        let isMatch = false;
        if (perspective === 'ab') isMatch = checkCond(dOut);
        else if (perspective === 'ba') isMatch = checkCond(dIn);
        else isMatch = checkCond(dOut) || checkCond(dIn);

        if (isMatch) {{
            nodesSet.add(r);
            nodesSet.add(c);
            validPairs.add(`${r}|${c}`);
            validPairs.add(`${c}|${r}`);
        }}
    }});

    let nodes = Array.from(nodesSet).sort((a, b) => a.localeCompare(b));
    let rowNodes = nodes.filter(n => multiMatch(n, fOrig));
    let colNodes = nodes.filter(n => multiMatch(n, fDest));

    let csvContent = "\\uFEFF";
    csvContent += "Origin;Destination;Direction;Min (ms);Avg (ms);Max (ms);Loss (%);Status\\n";

    rowNodes.forEach(r => {{
        colNodes.forEach(c => {{
            if (r === c) return;
            if (!isAllSelected && !validPairs.has(`${r}|${c}`)) return;

            let dOut = dataMap[`${r}|${c}`];
            let dIn = dataMap[`${c}|${r}`];

            if (showDirect && dOut) {{
                let status = dOut.is_unreachable ? "DOWN" : "UP";
                csvContent += `"${r}";"${c}";"Direct";"${dOut.min}";"${dOut.avg}";"${dOut.max}";"${dOut.loss_pct.toFixed(1)}%";"${status}"\\n`;
            }}
            if (showReverse && dIn) {{
                let status = dIn.is_unreachable ? "DOWN" : "UP";
                csvContent += `"${c}";"${r}";"Reverse";"${dIn.min}";"${dIn.avg}";"${dIn.max}";"${dIn.loss_pct.toFixed(1)}%";"${status}"\\n`;
            }}
        }});
    }});

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    if (link.download !== undefined) {{
        const url = URL.createObjectURL(blob);
        link.setAttribute("href", url);
        link.setAttribute("download", "ping_matrix_export.csv");
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }}
}}

function setTipData(e, r, c) {
    const tip = document.getElementById('globalTooltip');
    const dOut = dataMap[`${r}|${c}`];
    const dIn = dataMap[`${c}|${r}`];
    
    tip.innerHTML = buildTooltip(r, c, dOut, dIn);
    tip.style.display = 'block';
    moveTip(e);
}

function moveTip(e) {
    const tip = document.getElementById('globalTooltip');
    if (tip.style.display !== 'block') return;
    
    const w = tip.offsetWidth;
    const h = tip.offsetHeight;
    const winW = window.innerWidth;
    const winH = window.innerHeight;
    
    // Quadrant logic: push tooltip towards center of screen
    const isRight = e.clientX > winW / 2;
    const isBottom = e.clientY > winH / 2;
    
    let x = isRight ? e.clientX - w - 20 : e.clientX + 20;
    let y = isBottom ? e.clientY - h - 20 : e.clientY + 20;
    
    // Final boundary clamping to prevent ANY cut-off
    x = Math.max(10, Math.min(x, winW - w - 10));
    y = Math.max(10, Math.min(y, winH - h - 10));
    
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
}

function hideTip() {
    document.getElementById('globalTooltip').style.display = 'none';
}

function buildAnalytics() {
    if (!globalData) return;
    let validLinks = globalData.data.filter(d => !d.is_unreachable && d.loss_pct < 100);
    
    let latencyLinks = validLinks.filter(d => d.avg > 0);
    let topLatency = [...latencyLinks].sort((a,b) => b.avg - a.avg).slice(0, 5);
    
    let jitterLinks = validLinks.filter(d => d.max >= 0 && d.min >= 0 && (d.max - d.min) > 0);
    let topJitter = [...jitterLinks].sort((a,b) => (b.max - b.min) - (a.max - a.min)).slice(0, 5);
    
    let degradedLinks = globalData.data.filter(d => d.loss_pct > 0 && d.loss_pct < 100);
    let topLoss = [...degradedLinks].sort((a,b) => b.loss_pct - a.loss_pct).slice(0, 5);
    
    let asymLinks = globalData.data.filter(d => d.asymmetric_warning);
    let lookup = {};
    globalData.data.forEach(d => lookup[`${d.origin}|${d.dest}`] = d);
    let asymDeltas = [];
    let seenPairs = new Set();
    asymLinks.forEach(d => {
        let inv = lookup[`${d.dest}|${d.origin}`];
        if (inv && !inv.is_unreachable && inv.avg >= 0 && d.avg >= 0) {
            let p1 = `${d.origin}|${d.dest}`;
            let p2 = `${d.dest}|${d.origin}`;
            if (!seenPairs.has(p1) && !seenPairs.has(p2)) {
                asymDeltas.push({ o: d.origin, d: d.dest, delta: Math.abs(d.avg - inv.avg), oAvg: d.avg, iAvg: inv.avg });
                seenPairs.add(p1);
            }
        }
    });
    let topAsym = asymDeltas.sort((a,b) => b.delta - a.delta).slice(0, 5);
    
    let md = globalData.metadata;
    let isolatedNodes = [];
    if (md && md.node_stats) {
        isolatedNodes = Object.entries(md.node_stats)
            .map(([node, stats]) => ({ node, pct: stats.reachability_pct }))
            .filter(t => t.pct < 100)
            .sort((a,b) => a.pct - b.pct)
            .slice(0, 5);
    }
    
    let h = `
    <div class="analytics-header" onclick="toggleAnalytics()">
        <h3>📊 Advanced Analytics</h3>
        <span id="analyticsToggleIcon" style="color:#38bdf8; font-size:16px;">▼</span>
    </div>
    <div id="analyticsContent" class="analytics-content" style="display:none;">
        <div class="analytics-card"><h4>⏱️ High Latency Links</h4><ul>`;
        
    if (topLatency.length > 0) {
        topLatency.forEach(t => h += `<li style="cursor:pointer" onclick="showCellContextMenu(event, '${t.origin}', '${t.dest}')"><b>${t.origin} &rarr; ${t.dest}</b>: <span class="st-crit">${t.avg}ms</span></li>`);
    } else {
        h += `<li><span class="st-good">No latency data available</span></li>`;
    }
    
    h += `</ul></div><div class="analytics-card"><h4>〰️ Highest Jitter Variance</h4><ul>`;
    if (topJitter.length > 0) {
        topJitter.forEach(t => {
            let v = (t.max - t.min).toFixed(1);
            let c = t.jitter_warning ? 'st-crit' : 'st-warn';
            h += `<li style="cursor:pointer" onclick="showCellContextMenu(event, '${t.origin}', '${t.dest}')"><b>${t.origin} &rarr; ${t.dest}</b>: <span class="${c}">+${v}ms span</span> (Min ${t.min} / Max ${t.max})</li>`;
        });
    } else {
        h += `<li><span class="st-good">No variance detected</span></li>`;
    }
    
    h += `</ul></div><div class="analytics-card"><h4>📉 Highest Packet Loss</h4><ul>`;
    if (topLoss.length > 0) {
        topLoss.forEach(t => {
            let c = t.loss_pct > 50 ? 'st-crit' : 'st-warn';
            h += `<li style="cursor:pointer" onclick="showCellContextMenu(event, '${t.origin}', '${t.dest}')"><b>${t.origin} &rarr; ${t.dest}</b>: <span class="${c}">${t.loss_pct.toFixed(1)}% Loss</span></li>`;
        });
    } else {
        h += `<li><span class="st-good">All reachable links have 0% loss!</span></li>`;
    }
    
    h += `</ul></div><div class="analytics-card"><h4>⚖️ Most Asymmetric Routes</h4><ul>`;
    if (topAsym.length > 0) {
        topAsym.forEach(t => {
            h += `<li style="cursor:pointer" onclick="showCellContextMenu(event, '${t.o}', '${t.d}')"><b>${t.o} ⇄ ${t.d}</b>: <span class="st-warn">&Delta; ${t.delta.toFixed(1)}ms</span> (Ida: ${t.oAvg} | Volta: ${t.iAvg})</li>`;
        });
    } else {
        h += `<li><span class="st-good">No severe asymmetry detected!</span></li>`;
    }
    
    h += `</ul></div><div class="analytics-card"><h4>🏝️ Most Isolated Nodes</h4><ul>`;
    if (isolatedNodes.length > 0) {
        isolatedNodes.forEach(t => {
            let c = t.pct < 50 ? 'st-crit' : (t.pct < 95 ? 'st-warn' : 'st-good');
            h += `<li style="cursor:pointer" onclick="showCellContextMenu(event, '${t.node}', '')"><b>${t.node}</b>: Reachability <span class="${c}">${t.pct}%</span></li>`;
        });
    } else if (md && md.node_stats) {
        h += `<li><span class="st-good">All nodes are 100% reachable!</span></li>`;
    } else {
        h += `<li><span class="st-good">Data not available</span></li>`;
    }
    
    h += `</ul></div></div>`;
    
    let panel = document.getElementById('analyticsPanels');
    panel.innerHTML = h;
    panel.style.display = 'block';
    panel.style.padding = '15px 20px';
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

function fmt(val, prefix) {
    if (!val) return `<div class="split-item" style="color:#555">${prefix} N/A</div>`;
    if (val.is_unreachable) return `<div class="split-item st-crit">${prefix} FAIL</div>`;
    
    let showLat = document.getElementById('chkLat').checked;
    let showLoss = document.getElementById('chkLoss').checked;
    let showWarn = document.getElementById('chkWarn').checked;
    
    let parts = [];
    if (showLat) parts.push(val.avg >= 0 ? `${val.avg}ms` : 'N/A');
    if (showLoss) parts.push(`${val.loss_pct.toFixed(0)}%`);
    if (showWarn) {
        let wTags = "";
        if (val.jitter_warning) wTags += "J";
        if (val.asymmetric_warning) wTags += "A";
        if (wTags) parts.push(`<span class="st-warn" style="font-weight:bold">${wTags}</span>`);
    }
    
    let txt = parts.join(' <span style="color:#aaa">|</span> ');
    if (parts.length === 0) txt = "-";
    
    return `<div class="split-item">${prefix} ${txt}</div>`;
}

function multiMatch(nodeName, filterValue) {
    let parts = filterValue.toLowerCase().split(';').map(s => s.trim()).filter(s => s.length > 0);
    if (parts.length === 0) return true;
    let nodeLower = nodeName.toLowerCase();
    for (let p of parts) {
        if (nodeLower.includes(p)) return true;
    }
    return false;
}

function checkCond(item) {
    if (!item) return false;
    let sCrit = document.getElementById('sevCrit').checked;
    let sLoss = document.getElementById('sevLoss').checked;
    let sJit = document.getElementById('sevJit').checked;
    let sAsym = document.getElementById('sevAsym').checked;
    let sHealth = document.getElementById('sevHealthy').checked;
    
    let isCrit = item.loss_pct > 50 || item.is_unreachable || item.consistently_denied;
    let isLoss = item.loss_pct > 0 && item.loss_pct <= 50;
    let isJit = item.jitter_warning;
    let isAsym = item.asymmetric_warning;
    let isHealthy = !isCrit && !isLoss && !isJit && !isAsym;
    
    if (isCrit && sCrit) return true;
    if (isLoss && sLoss) return true;
    if (isJit && sJit) return true;
    if (isAsym && sAsym) return true;
    if (isHealthy && sHealth) return true;
    
    return false;
}

function renderMatrix() {
    if (!globalData) return;
    
    let showDirect = document.getElementById('chkDirect').checked;
    let showReverse = document.getElementById('chkReverse').checked;
    let perspective = 'none';
    if (showDirect && showReverse) perspective = 'both';
    else if (showDirect) perspective = 'ab';
    else if (showReverse) perspective = 'ba';
    
    let isAllSelected = document.getElementById('sevCrit').checked && 
                        document.getElementById('sevLoss').checked && 
                        document.getElementById('sevJit').checked && 
                        document.getElementById('sevAsym').checked && 
                        document.getElementById('sevHealthy').checked;
                        
    let fOrig = document.getElementById('filterOrigin').value.toLowerCase();
    let fDest = document.getElementById('filterDest').value.toLowerCase();
    
    let stGood=0, stJitter=0, stAsym=0, stDead=0;
    dataMap = {};
    globalData.data.forEach(d => { 
        dataMap[`${d.origin}|${d.dest}`] = d; 
        
        // Match the logic in checkCond
        const isCrit = d.loss_pct > 50 || d.is_unreachable || d.consistently_denied;
        const isLoss = d.loss_pct > 0 && d.loss_pct <= 50;
        const isJit = d.jitter_warning;
        const isAsym = d.asymmetric_warning;

        if (isCrit || isLoss) stDead++;
        else if (isJit) stJitter++;
        else if (isAsym) stAsym++;
        else stGood++;
    });

    let nodesSet = new Set();
    let validPairs = new Set();
    
    globalData.data.forEach(d => {
        let r = d.origin; let c = d.dest;
        let dOut = d;
        let dIn = dataMap[`${c}|${r}`];
        
        let isMatch = false;
        if (perspective === 'ab') isMatch = checkCond(dOut);
        else if (perspective === 'ba') isMatch = checkCond(dIn);
        else isMatch = checkCond(dOut) || checkCond(dIn);

        if (isMatch) {
            nodesSet.add(r);
            nodesSet.add(c);
            validPairs.add(`${r}|${c}`);
            validPairs.add(`${c}|${r}`);
        }
    });

    let nodes = Array.from(nodesSet).sort((a, b) => a.localeCompare(b));
    let rowNodes = nodes.filter(n => multiMatch(n, fOrig));
    let colNodes = nodes.filter(n => multiMatch(n, fDest));

    let hideScope = document.getElementById('chkHideScope') ? document.getElementById('chkHideScope').checked : true;
    if (hideScope) {
        let activeCols = colNodes.filter(c => rowNodes.some(r => dataMap[`${r}|${c}`] || dataMap[`${c}|${r}`]));
        let activeRows = rowNodes.filter(r => activeCols.some(c => dataMap[`${r}|${c}`] || dataMap[`${c}|${r}`]));
        if (activeCols.length > 0) colNodes = activeCols;
        if (activeRows.length > 0) rowNodes = activeRows;
    }
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
             
             if (!dOut && !dIn) {
                 let hideScope = document.getElementById('chkHideScope') ? document.getElementById('chkHideScope').checked : true;
                 if (hideScope && !isAllSelected) {
                     html += '<td style="background:transparent; border:none; opacity:0"></td>';
                 } else {
                     html += '<td class="st-filtered" title="Out of Scope by Architecture Policy">-</td>';
                 }
                 return;
             }
             
             let primary = dOut;
             if (perspective === 'ba') primary = dIn;
             if (perspective === 'both' && !primary) primary = dIn;
             
             // Define Cell Background (Both Mode judges the worst-case scenario)
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
             if (perspective === 'ab') display = fmt(dOut, '');
             else if (perspective === 'ba') display = fmt(dIn, '');
             else if (perspective === 'both') {
                 let pOut = '<span style="color:#00d2ff">🡲</span>';
                 let pIn = '<span style="color:#ff007f">🡰</span>';
                 display = fmt(dOut, pOut) + fmt(dIn, pIn);
             } else {
                 display = '<div class="split-item" style="color:#555">-</div>';
             }

             let styleStr = perspective === 'both' ? 'padding:0 4px;' : '';
              if (!isAllSelected && !validPairs.has(`${r}|${c}`)) {
                  html += '<td style="background:transparent; border:none; opacity:0"></td>';
                  return;
              }
               html += `<td class="${cssClass}${extClass}" style="${styleStr} cursor: pointer;" onmouseenter="setTipData(event, '${r}', '${c}')" onmousemove="moveTip(event)" onmouseleave="hideTip()" onclick="showCellContextMenu(event, '${r}', '${c}')">${display}</td>`;
        });
        html += '</tr>';
    });
    document.getElementById('matrixTable').innerHTML = html;
}

let hasDiff = false;
async function checkDiffAvailability() {
    try {
        const response = await fetch('../../../../diff/index.html', { method: 'HEAD' });
        hasDiff = response.ok || response.status === 0;
    } catch (e) {
        hasDiff = false;
    }
}
checkDiffAvailability();

function showCellContextMenu(e, origin, dest) {
    e.preventDefault();
    e.stopPropagation();
    
    let menu = document.getElementById('cellContextMenu');
    if (!menu) {
        menu = document.createElement('div');
        menu.id = 'cellContextMenu';
        menu.className = 'context-menu';
        document.body.appendChild(menu);
    }
    
    const runIdMatch = window.location.pathname.match(/(20\d{6}_\d{6})/);
    const runId = runIdMatch ? runIdMatch[1] : '';
    
    menu.innerHTML = `
        <div class="menu-header">${origin}${dest ? ' ⇄ ' + dest : ''}</div>
        <a href="#" onclick="filterMatrix('${origin}', '${dest || ''}'); return false;">🔍 Filter Matrix by this Element(s)</a>
        ${dest ? `<a href="../../../../ping-matrix/history.html?origin=${origin}&dest=${dest}" target="_blank">📈 P2P History & SLA</a>` : ''}
        ${dest ? `<a href="../../../../ping-matrix/path.html?run=${runId}&origin=${origin}&dest=${dest}" target="_blank">🕸️ Route Analysis (Dijkstra)</a>` : ''}
        <a href="../../../../inventory/index.html?run=${runId}&device=${origin}" target="_blank">📦 Global Inventory (${origin})</a>
        ${dest ? `<a href="../../../../inventory/index.html?run=${runId}&device=${dest}" target="_blank">📦 Global Inventory (${dest})</a>` : ''}
        ${hasDiff ? `
            <a href="../../../../diff/index.html?device=${origin}" target="_blank">⚖️ Drift Analysis (${origin})</a>
            ${dest ? `<a href="../../../../diff/index.html?device=${dest}" target="_blank">⚖️ Drift Analysis (${dest})</a>` : ''}
        ` : `
            <a href="#" class="disabled" style="opacity:0.5; cursor:not-allowed; pointer-events:none;" onclick="return false;">⚖️ Drift Analysis (Unavailable)</a>
        `}
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
function filterMatrix(origin, dest) {
    document.getElementById('filterOrigin').value = origin;
    document.getElementById('filterDest').value = dest;
    renderMatrix();
    const menu = document.getElementById('cellContextMenu');
    if (menu) menu.style.display = 'none';
}
document.addEventListener('click', () => {
    const menu = document.getElementById('cellContextMenu');
    if (menu) menu.style.display = 'none';
});
loadData();
</script>
<div id="globalTooltip"></div>
</body>
</html>"""
    return html_template.replace("__JSON_PAYLOAD_HERE__", json.dumps(json_payload, indent=None))
