#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import glob
import math
import argparse
from datetime import datetime

C_GREEN  = '\033[92m'
C_RED    = '\033[91m'
C_CYAN   = '\033[96m'
C_YELLOW = '\033[93m'
C_RESET  = '\033[0m'

def percentile(data, percent):
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * percent
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return d0 + d1

def get_regression_slope(values):
    n = len(values)
    if n < 3:
        return 0.0
    x = list(range(n))
    y = values
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xx = sum(xi * xi for xi in x)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    denominator = (n * sum_xx - sum_x * sum_x)
    if denominator == 0:
        return 0.0
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    return slope

def detect_anomaly(values, current_val):
    n = len(values)
    if n < 5:
        return False, 0.0, 0.0
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / n
    std_dev = math.sqrt(variance)
    if std_dev == 0:
        return False, mean, std_dev
    is_anomaly = current_val > (mean + 3 * std_dev)
    return is_anomaly, mean, std_dev

class PingHistoryGenerator:
    def __init__(self, outbase):
        self.outbase = os.path.abspath(outbase)
        self.ping_matrix_dir = os.path.join(self.outbase, "ping-matrix")
        self.history_dir = os.path.join(self.ping_matrix_dir, "history")
        self.links_dir = os.path.join(self.history_dir, "links")
        
        # Max snapshots to hold per link series to prevent file bloat
        self.max_retention = 90
        
        # Sliders default thresholds
        self.thr_latency = 200.0  # ms
        self.thr_loss = 1.0       # %
        self.thr_jitter = 5.0     # ms
        self.thr_avail = 99.5     # %

    def run(self, force_rebuild=False):
        print(f"[*] Starting Ping History aggregation in: {self.ping_matrix_dir}")
        
        # Ensure directory structures exist
        os.makedirs(self.history_dir, exist_ok=True)
        os.makedirs(self.links_dir, exist_ok=True)

        # Copy history.html, path.html, and chart.js templates to outbase
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src_history = os.path.join(script_dir, "templates", "ping-matrix", "history.html")
        src_path = os.path.join(script_dir, "templates", "ping-matrix", "path.html")
        src_chart = os.path.join(script_dir, "templates", "ping-matrix", "chart.js")
        
        dest_history = os.path.join(self.ping_matrix_dir, "history.html")
        dest_path = os.path.join(self.ping_matrix_dir, "path.html")
        dest_chart = os.path.join(self.ping_matrix_dir, "chart.js")
        
        import shutil
        try:
            if os.path.isfile(src_history) and os.path.abspath(src_history) != os.path.abspath(dest_history):
                shutil.copy2(src_history, dest_history)
            if os.path.isfile(src_path) and os.path.abspath(src_path) != os.path.abspath(dest_path):
                shutil.copy2(src_path, dest_path)
            if os.path.isfile(src_chart) and os.path.abspath(src_chart) != os.path.abspath(dest_chart):
                shutil.copy2(src_chart, dest_chart)
        except Exception as e:
            print(f"{C_YELLOW}[!] Warning: Failed to copy static HTML templates to outbase: {e}{C_RESET}")

        # 1. Load manifest and existing runs list
        manifest_path = os.path.join(self.history_dir, "history_manifest.json")
        processed_runs = set()
        manifest_data = []

        if not force_rebuild and os.path.isfile(manifest_path):
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest_data = json.load(f)
                processed_runs = {r["id"] for r in manifest_data}
                print(f"[*] Found history manifest with {len(processed_runs)} indexed runs.")
            except Exception as e:
                print(f"{C_YELLOW}[!] Warning: Failed to load existing manifest ({e}). Forcing rebuild.{C_RESET}")
                force_rebuild = True

        if force_rebuild:
            manifest_data = []
            processed_runs = set()
            print(f"{C_CYAN}[*] Running FULL historical rebuild.{C_RESET}")

        # 2. Scan all snapshot directories
        run_dirs = sorted(glob.glob(os.path.join(self.ping_matrix_dir, "20*_*")))
        new_runs = []
        for run_dir in run_dirs:
            if not os.path.isdir(run_dir):
                continue
            run_id = os.path.basename(run_dir)
            if run_id not in processed_runs:
                # Validate the snapshot has the JSON file
                json_file = os.path.join(run_dir, "resume", "ping_matrix_list.json")
                if os.path.isfile(json_file):
                    new_runs.append((run_id, json_file))

        if not new_runs:
            print(f"{C_GREEN}[+] History is already up to date. No new snapshots found.{C_RESET}")
            # Still update manifest.js and rankings.js in case they were deleted
            self.write_manifest_js(manifest_data)
            self.recompute_rankings_and_write()
            return

        print(f"[*] Found {len(new_runs)} new snapshot(s) to process.")

        # 3. Process new runs chronologically
        # We need to load/create link histories. Since loading all link files one by one
        # can be slow during loops, we cache them in memory.
        link_histories = {} 
        
        # Load existing link histories for incremental updates
        if not force_rebuild:
            print("[*] Pre-loading active link historical caches...")
            # We'll load them dynamically on first access, then write them back at the end.

        # Process each run
        for run_id, json_file in new_runs:
            print(f"  • Processing run: {run_id} ... ", end="", flush=True)
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    run_payload = json.load(f)
                
                metadata = run_payload.get("metadata", {})
                run_data = run_payload.get("data", [])
                
                if not run_data:
                    print("Empty. Skipped.")
                    continue
                
                # Metrics parsing for the run
                total_links = 0
                healthy_links = 0
                warn_links = 0
                crit_links = 0
                dead_links = 0
                
                latencies = []
                losses = []
                jitters = []
                
                # ISO timestamp conversion
                dt_str = metadata.get("datetime")
                if not dt_str:
                    try:
                        # Extract from run_id format YYYYMMDD_HHMMSS
                        dt_str = f"{run_id[:4]}-{run_id[4:6]}-{run_id[6:8]} {run_id[9:11]}:{run_id[11:13]}:{run_id[13:15]}"
                    except:
                        dt_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                for entry in run_data:
                    o = entry["origin"]
                    d = entry["dest"]
                    key = f"{o}|{d}"
                    
                    tx = entry.get("tx", 5)
                    rx = entry.get("rx", 0)
                    loss = entry.get("loss_pct", 100.0)
                    avg_lat = entry.get("avg", -1.0)
                    tmin = entry.get("min", -1.0)
                    tmax = entry.get("max", -1.0)
                    
                    is_dead = entry.get("is_unreachable", False) or loss == 100.0 or entry.get("consistently_denied", False)
                    jitter = tmax - tmin if (tmax >= 0 and tmin >= 0) else 0.0
                    
                    total_links += 1
                    if is_dead:
                        dead_links += 1
                    elif loss > 50.0:
                        crit_links += 1
                    elif loss > 0.0 or entry.get("jitter_warning", False) or entry.get("asymmetric_warning", False):
                        warn_links += 1
                    else:
                        healthy_links += 1

                    if avg_lat >= 0:
                        latencies.append(avg_lat)
                        jitters.append(jitter)
                    losses.append(loss)
                    
                    # Update link history cache
                    if key not in link_histories:
                        # Try to load existing file
                        link_file = os.path.join(self.links_dir, f"{o}_{d}.json")
                        if not force_rebuild and os.path.isfile(link_file):
                            try:
                                with open(link_file, 'r', encoding='utf-8') as lf:
                                    link_histories[key] = json.load(lf)
                            except:
                                link_histories[key] = []
                        else:
                            link_histories[key] = []
                            
                    link_histories[key].append({
                        "t": dt_str,
                        "min": tmin,
                        "avg": avg_lat,
                        "max": tmax,
                        "loss": loss,
                        "jitter": jitter,
                        "status": "dead" if is_dead else ("critical" if loss > 50.0 else ("warning" if (loss > 0.0 or jitter > self.thr_jitter) else "healthy"))
                    })
                    
                    # Cap retention size
                    link_histories[key] = link_histories[key][-self.max_retention:]
                
                # Calculate global averages
                avg_lat_global = round(sum(latencies) / len(latencies), 1) if latencies else -1.0
                avg_loss_global = round(sum(losses) / len(losses), 2) if losses else 100.0
                avg_jitter_global = round(sum(jitters) / len(jitters), 1) if jitters else 0.0
                
                availability = round(((total_links - dead_links) / total_links) * 100.0, 2) if total_links else 0.0
                
                manifest_data.append({
                    "id": run_id,
                    "timestamp": dt_str,
                    "nodes": metadata.get("nodes_connected", 0),
                    "availability": availability,
                    "avg_latency": avg_lat_global,
                    "avg_loss": avg_loss_global,
                    "avg_jitter": avg_jitter_global,
                    "critical_links_count": crit_links,
                    "dead_links_count": dead_links
                })
                print("Done.")
            except Exception as e:
                print(f"Failed: {e}")

        # 4. Save updated link histories to disk (JSON + JS)
        print("[*] Writing link history files to disk...")
        for key, history in link_histories.items():
            o, d = key.split("|")
            link_json_path = os.path.join(self.links_dir, f"{o}_{d}.json")
            link_js_path = os.path.join(self.links_dir, f"{o}_{d}.js")
            
            # Save JSON cache
            with open(link_json_path, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=None)
                
            # Save JS for CORS-free dashboard load
            js_content = f'if(!window.ping_link_history) window.ping_link_history = {{}}; window.ping_link_history["{o}_{d}"] = {json.dumps(history)};'
            with open(link_js_path, 'w', encoding='utf-8') as f:
                f.write(js_content)

        # 5. Save manifest (JSON + JS)
        manifest_data.sort(key=lambda x: x["id"])
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest_data, f, indent=4)
            
        self.write_manifest_js(manifest_data)

        # 6. Recompute rankings and write them out
        self.recompute_rankings_and_write()
        print(f"{C_GREEN}[+] Ping History aggregation completed successfully!{C_RESET}")

    def write_manifest_js(self, manifest_data):
        js_path = os.path.join(self.history_dir, "history_manifest.js")
        js_content = f"window.ping_history_manifest = {json.dumps(manifest_data, indent=4)};"
        with open(js_path, 'w', encoding='utf-8') as f:
            f.write(js_content)

    def recompute_rankings_and_write(self):
        print("[*] Recomputing statistical rankings and baselines...")
        
        # Load all link histories from disk to compute rankings over full history
        all_links = {}
        link_files = glob.glob(os.path.join(self.links_dir, "*.json"))
        for fpath in link_files:
            fname = os.path.basename(fpath)
            parts = fname.replace(".json", "").split("_")
            if len(parts) == 2:
                o, d = parts[0], parts[1]
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        all_links[f"{o}|{d}"] = json.load(f)
                except:
                    pass

        # Calculations
        top_worst = []
        worsening_trend = []
        anomaly_events = []
        rankings_by_origin = {}
        rankings_by_dest = {}
        rankings_by_stability = []

        for key, history in all_links.items():
            o, d = key.split("|")
            
            # Get valid latencies (exclude -1.0) and losses
            latencies = [h["avg"] for h in history if h["avg"] >= 0]
            losses = [h["loss"] for h in history]
            jitters = [h["jitter"] for h in history if h["avg"] >= 0]
            
            if not history:
                continue
                
            latest = history[-1]
            
            # 1. Top Worst: calculated based on average loss and average latency over the last 10 snapshots
            recent_snapshots = history[-10:]
            recent_losses = [h["loss"] for h in recent_snapshots]
            recent_latencies = [h["avg"] for h in recent_snapshots if h["avg"] >= 0]
            
            avg_recent_loss = sum(recent_losses) / len(recent_losses) if recent_losses else 0.0
            avg_recent_lat = sum(recent_latencies) / len(recent_latencies) if recent_latencies else -1.0
            
            top_worst.append({
                "origin": o,
                "dest": d,
                "avg_loss": round(avg_recent_loss, 2),
                "avg_latency": round(avg_recent_lat, 1)
            })

            # 2. Worsening Trend: simple regression slope of latency over the last 10 runs
            if len(recent_latencies) >= 5:
                slope = get_regression_slope(recent_latencies)
                if slope > 0.2:  # Significant slope (ms increase per run)
                    worsening_trend.append({
                        "origin": o,
                        "dest": d,
                        "slope": round(slope, 3),
                        "start_latency": round(recent_latencies[0], 1),
                        "end_latency": round(recent_latencies[-1], 1)
                    })

            # 3. Anomaly Events: check latest snapshot against previous baseline (last 15 snapshots)
            if len(history) >= 7 and latest["avg"] >= 0:
                baseline_snapshots = history[:-1][-15:]
                baseline_lats = [h["avg"] for h in baseline_snapshots if h["avg"] >= 0]
                if len(baseline_lats) >= 5:
                    is_anom, mean, std = detect_anomaly(baseline_lats, latest["avg"])
                    if is_anom:
                        anomaly_events.append({
                            "timestamp": latest["t"],
                            "origin": o,
                            "dest": d,
                            "metric": "latency",
                            "baseline": round(mean, 1),
                            "actual": round(latest["avg"], 1),
                            "threshold": round(mean + 3 * std, 1)
                        })

            # 4. Aggregations by Node (Origin/Dest)
            # Origin stats
            if o not in rankings_by_origin:
                rankings_by_origin[o] = {"sum_lat": 0.0, "lat_count": 0, "sum_loss": 0.0, "total_count": 0, "dead_count": 0}
            rankings_by_origin[o]["sum_loss"] += latest["loss"]
            rankings_by_origin[o]["total_count"] += 1
            if latest["avg"] >= 0:
                rankings_by_origin[o]["sum_lat"] += latest["avg"]
                rankings_by_origin[o]["lat_count"] += 1
            if latest["loss"] == 100.0 or latest["avg"] < 0:
                rankings_by_origin[o]["dead_count"] += 1

            # Destination stats
            if d not in rankings_by_dest:
                rankings_by_dest[d] = {"sum_lat": 0.0, "lat_count": 0, "sum_loss": 0.0, "total_count": 0, "dead_count": 0}
            rankings_by_dest[d]["sum_loss"] += latest["loss"]
            rankings_by_dest[d]["total_count"] += 1
            if latest["avg"] >= 0:
                rankings_by_dest[d]["sum_lat"] += latest["avg"]
                rankings_by_dest[d]["lat_count"] += 1
            if latest["loss"] == 100.0 or latest["avg"] < 0:
                rankings_by_dest[d]["dead_count"] += 1

            # 5. Stability: calculate latency standard deviation over entire history
            if len(latencies) >= 5:
                mean_lat = sum(latencies) / len(latencies)
                var_lat = sum((x - mean_lat) ** 2 for x in latencies) / len(latencies)
                std_lat = math.sqrt(var_lat)
                rankings_by_stability.append({
                    "origin": o,
                    "dest": d,
                    "std_dev": round(std_lat, 2),
                    "avg": round(mean_lat, 1)
                })

        # Format Origin Rankings
        formatted_origins = {}
        for node, stats in rankings_by_origin.items():
            formatted_origins[node] = {
                "avg_latency": round(stats["sum_lat"] / stats["lat_count"], 1) if stats["lat_count"] > 0 else -1.0,
                "avg_loss": round(stats["sum_loss"] / stats["total_count"], 2) if stats["total_count"] > 0 else 100.0,
                "success_pct": round(((stats["total_count"] - stats["dead_count"]) / stats["total_count"]) * 100.0, 1) if stats["total_count"] > 0 else 0.0
            }

        # Format Dest Rankings
        formatted_dests = {}
        for node, stats in rankings_by_dest.items():
            formatted_dests[node] = {
                "avg_latency": round(stats["sum_lat"] / stats["lat_count"], 1) if stats["lat_count"] > 0 else -1.0,
                "avg_loss": round(stats["sum_loss"] / stats["total_count"], 2) if stats["total_count"] > 0 else 100.0,
                "success_pct": round(((stats["total_count"] - stats["dead_count"]) / stats["total_count"]) * 100.0, 1) if stats["total_count"] > 0 else 0.0
            }

        # Sort and slice
        top_worst.sort(key=lambda x: (x["avg_loss"], x["avg_latency"]), reverse=True)
        top_worst = top_worst[:15]
        
        worsening_trend.sort(key=lambda x: x["slope"], reverse=True)
        worsening_trend = worsening_trend[:15]
        
        anomaly_events.sort(key=lambda x: x["timestamp"], reverse=True)
        anomaly_events = anomaly_events[:30]
        
        rankings_by_stability.sort(key=lambda x: x["std_dev"], reverse=True)
        rankings_by_stability_worst = rankings_by_stability[:15] # Least stable (highest std dev)

        rankings_payload = {
            "top_worst_circuits": top_worst,
            "worsening_trend": worsening_trend,
            "anomaly_events": anomaly_events,
            "rankings_by_origin": formatted_origins,
            "rankings_by_dest": formatted_dests,
            "rankings_by_stability": rankings_by_stability_worst
        }

        # Write rankings JSON cache
        rankings_json_path = os.path.join(self.history_dir, "history_rankings.json")
        with open(rankings_json_path, 'w', encoding='utf-8') as f:
            json.dump(rankings_payload, f, indent=4)

        # Write rankings JS browser file
        rankings_js_path = os.path.join(self.history_dir, "history_rankings.js")
        js_content = f"window.ping_history_rankings = {json.dumps(rankings_payload, indent=4)};"
        with open(rankings_js_path, 'w', encoding='utf-8') as f:
            f.write(js_content)
            
        print(f"[+] Recomputing rankings done. Found {len(anomaly_events)} anomaly events, {len(worsening_trend)} worsening trends.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Consolidate Network Ping History")
    parser.add_argument("--outbase", default="infos", help="Root directory for outputs")
    parser.add_argument("--rebuild", action="store_true", help="Force complete rebuild of history")
    args = parser.parse_args()
    
    generator = PingHistoryGenerator(args.outbase)
    generator.run(force_rebuild=args.rebuild)
