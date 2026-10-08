# -*- coding: utf-8 -*-
"""
Topology Data Engine (Phase 1: Native Interactive Topology)
===========================================================
Extracts, normalizes, and packages network topology graph payloads (nodes,
summary edges, detailed edges, hierarchy tiers, sites, and metadata) from
runs and SQLite persistence.

Generates standalone client-side JavaScript payloads:
  - topology/data/topology_<RUN_ID>.js
  - topology/manifest.js (enriched with native & drawio flags)

Operates 100% offline with zero CORS restrictions for both http:// and file:///.
"""

import os
import re
import csv
import json
from glob import glob
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple


class TopologyDataEngine:
    def __init__(self, outbase: str, storage_mgr: Optional[Any] = None):
        self.outbase = os.path.abspath(outbase)
        self.storage_mgr = storage_mgr
        self.runs_dir = os.path.join(self.outbase, "runs")
        self.topology_dir = os.path.join(self.outbase, "topology")
        self.data_dir = os.path.join(self.topology_dir, "data")
        
        self.repo_dir = str(Path(__file__).resolve().parent.parent)
        self.settings = self._load_settings()
        self.routing_hierarchy = self.settings.get("routing_hierarchy", {})

    def _load_settings(self) -> Dict[str, Any]:
        """Loads routing_hierarchy and styling from settings.json."""
        settings_path = os.path.join(self.repo_dir, "config", "settings.json")
        if os.path.isfile(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _ensure_dirs(self) -> None:
        """Ensures topology, data directories exist and theme/icons library is generated."""
        os.makedirs(self.data_dir, exist_ok=True)
        try:
            from core.topology_icons import TopologyIconsEngine
            TopologyIconsEngine(self.outbase).ensure_theme_icons_js()
        except Exception as e:
            print(f"    [!] Warning generating topology icons: {e}")

    def get_tier_for_hostname(self, hostname: str) -> Tuple[str, int]:
        """
        Determines the architectural layer and circular rank based on routing_hierarchy.
        Ranks for Concentric Orbital Layout:
          1: Core (RTIC) - Central Ring
          2: Core Aggregation (RTOC) - Ring 2
          3: Edge / Distribution (RTAC, RTED) - Ring 3
          4: Metro / Access (SWAC, SWAG) - Ring 4
          5: Peering / IX / Border (RTPR, PTT) - Ring 5
          6: Route Reflector (RTRR) - Ring 6
          7: Other / Unclassified - Outer Ring
        """
        if not hostname:
            return ("other", 7)
            
        clean_name = hostname.strip().upper()
        
        # Split on hyphen, underscore or dot to isolate prefix
        prefix_match = re.split(r"[-_.]", clean_name)
        prefix = prefix_match[0] if prefix_match else clean_name[:4]

        # Rank definition
        rank_map = {
            "core": 1,
            "core_agg": 2,
            "edge": 3,
            "metro": 4,
            "peering": 5,
            "router_reflector": 6,
        }

        for tier, prefixes in self.routing_hierarchy.items():
            if isinstance(prefixes, list):
                for p in prefixes:
                    p_clean = str(p).strip().upper()
                    if prefix.startswith(p_clean) or p_clean in prefix:
                        return (tier, rank_map.get(tier, 7))
        
        # Fallback heurístics
        if "RTIC" in clean_name or "CORE" in clean_name:
            return ("core", 1)
        if "RTOC" in clean_name or "AGGR" in clean_name:
            return ("core_agg", 2)
        if "RTAC" in clean_name or "RTED" in clean_name or "EDGE" in clean_name:
            return ("edge", 3)
        if "SW" in clean_name or "METRO" in clean_name:
            return ("metro", 4)
        if "PTT" in clean_name or "IX" in clean_name or "RTPR" in clean_name:
            return ("peering", 5)
        if "RTRR" in clean_name:
            return ("router_reflector", 6)
            
        return ("other", 7)

    def get_site_for_hostname(self, hostname: str) -> str:
        """Extracts site/location code from hostname (e.g., RTAC-BHE02-02 -> BHE02)."""
        if not hostname:
            return "UNKNOWN"
        parts = re.split(r"[-_.]", hostname.strip().upper())
        if len(parts) >= 2:
            return parts[1]
        return "DEFAULT"

    def _parse_capacity_gbps(self, text: str) -> float:
        """Parses connection text into numeric capacity in Gbps."""
        if not text:
            return 1.0
        text = text.upper().strip()
        match = re.search(r"(\d+)\s*X\s*(\d+)\s*(G|M)", text)
        if match:
            count = int(match.group(1))
            val = int(match.group(2))
            unit = match.group(3)
            gbps = count * val if unit == "G" else (count * val) / 1000.0
            return max(1.0, gbps)

        match_single = re.search(r"(\d+)\s*(G|M|T)", text)
        if match_single:
            val = int(match_single.group(1))
            unit = match_single.group(2)
            if unit == "T":
                return val * 1000.0
            elif unit == "G":
                return float(val)
            else:
                return max(0.1, val / 1000.0)
        return 1.0

    def _calculate_edge_width(self, capacity_gbps: float) -> int:
        """Calculates visual stroke width based on bandwidth."""
        if capacity_gbps >= 400:
            return 10
        elif capacity_gbps >= 200:
            return 8
        elif capacity_gbps >= 100:
            return 6
        elif capacity_gbps >= 40:
            return 5
        elif capacity_gbps >= 10:
            return 3
        return 2

    def extract_run_topology(self, run_id: str) -> Dict[str, Any]:
        """
        Extracts topology nodes and edges (summary and detailed) for a given run ID.
        Checks both flat files and SQLite database.
        """
        run_dir = os.path.join(self.runs_dir, run_id)
        nodes_dict: Dict[str, Dict[str, Any]] = {}
        edges_summary_list: List[Dict[str, Any]] = []
        edges_detail_list: List[Dict[str, Any]] = []
        
        # 1. Load Nodes Metadata from Resume Files if available
        platform_file = os.path.join(run_dir, "resume", "platform_all.csv")
        status_file = os.path.join(run_dir, "resume", "status.elements.csv")
        
        node_meta: Dict[str, Dict[str, str]] = {}
        if os.path.isfile(platform_file):
            try:
                with open(platform_file, "r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f, delimiter=";")
                    for row in reader:
                        host = row.get("element", "").strip()
                        if host:
                            node_meta[host] = {
                                "vendor": row.get("vendor", ""),
                                "model": row.get("model", ""),
                                "os_version": row.get("version", ""),
                            }
            except Exception:
                pass

        node_status: Dict[str, str] = {}
        if os.path.isfile(status_file):
            try:
                with open(status_file, "r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f, delimiter=";")
                    for row in reader:
                        host = row.get("element", "").strip()
                        if host:
                            node_status[host] = row.get("status", "ok")
            except Exception:
                pass

        # Helper to register or update node
        def register_node(hostname: str):
            h_clean = hostname.strip()
            if not h_clean or h_clean in nodes_dict:
                return
            tier, rank = self.get_tier_for_hostname(h_clean)
            site = self.get_site_for_hostname(h_clean)
            meta = node_meta.get(h_clean, {})
            st = node_status.get(h_clean, "ok")
            
            nodes_dict[h_clean] = {
                "id": h_clean,
                "label": h_clean,
                "tier": tier,
                "tier_rank": rank,
                "site": site,
                "vendor": meta.get("vendor", ""),
                "model": meta.get("model", ""),
                "os_version": meta.get("os_version", ""),
                "status": st
            }

        # 2. Extract Summary Edges from topology.connections.SUM.csv or SQLite
        sum_file = os.path.join(run_dir, "connections", "topology.connections.SUM.csv")
        raw_conn_file = os.path.join(run_dir, "connections", "topology.connections.csv")
        
        summary_loaded = False
        if os.path.isfile(sum_file):
            try:
                with open(sum_file, "r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f, delimiter=";")
                    for row in reader:
                        a = row.get("endpoint_a", "").strip()
                        b = row.get("endpoint_b", "").strip()
                        if not a or not b or a == b:
                            continue
                        register_node(a)
                        register_node(b)
                        
                        sorted_pair = sorted([a, b])
                        edge_id = f"{sorted_pair[0]}__{sorted_pair[1]}"
                        conn_text = row.get("connection_text", "").strip()
                        capacity = self._parse_capacity_gbps(conn_text)
                        width = self._calculate_edge_width(capacity)
                        color = row.get("strokeColor", "").strip() or "#0284c7"
                        is_dashed = bool(row.get("dashed", "").strip().lower() in ("1", "true", "yes"))
                        
                        edges_summary_list.append({
                            "id": edge_id,
                            "from": a,
                            "to": b,
                            "source": a,
                            "target": b,
                            "label": conn_text,
                            "capacity_gbps": capacity,
                            "width": width,
                            "color": color,
                            "dashed": is_dashed
                        })
                summary_loaded = True
            except Exception:
                summary_loaded = False

        # Fallback to topology.connections.csv if summary file is missing or empty
        if (not summary_loaded or len(edges_summary_list) == 0) and os.path.isfile(raw_conn_file):
            try:
                raw_pairs = {}
                with open(raw_conn_file, "r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f, delimiter=";")
                    for row in reader:
                        a = row.get("element", "").strip()
                        b = row.get("remote_element", "").strip()
                        if not a or not b or a == b:
                            continue
                        register_node(a)
                        register_node(b)
                        pair_key = "__".join(sorted([a, b]))
                        bw_raw = row.get("bandwidth", "0").strip()
                        try:
                            bw_gbps = float(bw_raw) / 1000000000.0 if float(bw_raw) > 1000000 else float(bw_raw)
                        except Exception:
                            bw_gbps = 10.0
                        if pair_key not in raw_pairs:
                            raw_pairs[pair_key] = (a, b, 1, bw_gbps)
                        else:
                            old_a, old_b, cnt, old_bw = raw_pairs[pair_key]
                            raw_pairs[pair_key] = (old_a, old_b, cnt + 1, old_bw + bw_gbps)

                for pair_key, (a, b, cnt, tot_bw) in raw_pairs.items():
                    edges_summary_list.append({
                        "id": pair_key,
                        "from": a,
                        "to": b,
                        "source": a,
                        "target": b,
                        "label": f"{cnt}x Link" if tot_bw == 0 else f"{int(tot_bw)}G",
                        "capacity_gbps": float(tot_bw if tot_bw > 0 else cnt * 10),
                        "width": self._calculate_edge_width(float(tot_bw if tot_bw > 0 else cnt * 10)),
                        "color": "#0284c7",
                        "dashed": False
                    })
                if len(edges_summary_list) > 0:
                    summary_loaded = True
            except Exception:
                pass
        if not summary_loaded or len(edges_summary_list) == 0:
            db_path = os.path.join(self.outbase, "database", "network_data.db")
            if os.path.isfile(db_path):
                try:
                    import sqlite3
                    with sqlite3.connect(db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT endpoint_a, endpoint_b, count(*) FROM topology_connections "
                            "WHERE run_id = ? GROUP BY endpoint_a, endpoint_b",
                            (run_id,)
                        )
                        seen_pairs: Set[str] = set()
                        for row in cursor.fetchall():
                            a = (row[0] or "").strip()
                            b = (row[1] or "").strip()
                            cnt = row[2] or 1
                            if not a or not b or a == b:
                                continue
                            register_node(a)
                            register_node(b)
                            pair_key = "__".join(sorted([a, b]))
                            if pair_key in seen_pairs:
                                continue
                            seen_pairs.add(pair_key)
                            
                            conn_text = f"{cnt}x Link"
                            edges_summary_list.append({
                                "id": pair_key,
                                "from": a,
                                "to": b,
                                "source": a,
                                "target": b,
                                "label": conn_text,
                                "capacity_gbps": float(cnt * 10),
                                "width": self._calculate_edge_width(float(cnt * 10)),
                                "color": "#0284c7",
                                "dashed": False
                            })
                except Exception:
                    pass

        # 3. Extract Detailed Edges from show_lldp_neighbors_detail_all.csv or connections.csv
        lldp_file = os.path.join(run_dir, "resume", "show_lldp_neighbors_detail_all.csv")
        if os.path.isfile(lldp_file):
            try:
                with open(lldp_file, "r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f, delimiter=";")
                    for row in reader:
                        local = row.get("element", "").strip()
                        remote_raw = row.get("system_name", "").strip()
                        remote = remote_raw.split(".")[0].strip() if remote_raw else ""
                        if not local or not remote or local == remote:
                            continue
                        register_node(local)
                        register_node(remote)
                        
                        l_intf = row.get("local_intf", "").strip()
                        r_intf = row.get("port_id", "").strip()
                        
                        # Normalize speed
                        speed = "10G"
                        if "Hundred" in l_intf or "100G" in l_intf:
                            speed = "100G"
                        elif "Gigabit" in l_intf and "Ten" not in l_intf:
                            speed = "1G"
                            
                        edge_id = f"{local}_{l_intf}__{remote}_{r_intf}"
                        edges_detail_list.append({
                            "id": edge_id,
                            "from": local,
                            "to": remote,
                            "source": local,
                            "target": remote,
                            "from_intf": l_intf,
                            "to_intf": r_intf,
                            "local_int": l_intf,
                            "remote_int": r_intf,
                            "label": f"{l_intf} ⇄ {r_intf}",
                            "speed": speed,
                            "width": 3 if speed == "100G" else 2,
                            "color": "#006400" if speed == "100G" else "#0085DA"
                        })
            except Exception:
                pass

        # Stats compilation
        tiers_count: Dict[str, int] = {}
        for n in nodes_dict.values():
            t = n["tier"]
            tiers_count[t] = tiers_count.get(t, 0) + 1

        formatted_date = run_id
        try:
            formatted_date = f"{run_id[:4]}-{run_id[4:6]}-{run_id[6:8]} {run_id[9:11]}:{run_id[11:13]}:{run_id[13:15]}"
        except Exception:
            pass

        return {
            "run_id": run_id,
            "timestamp": formatted_date,
            "stats": {
                "total_nodes": len(nodes_dict),
                "total_summary_edges": len(edges_summary_list),
                "total_detailed_edges": len(edges_detail_list),
                "tiers_count": tiers_count
            },
            "nodes": sorted(list(nodes_dict.values()), key=lambda x: (x["tier_rank"], x["id"])),
            "edges_summary": edges_summary_list,
            "edges_detail": edges_detail_list
        }

    def write_run_topology_payload(self, run_id: str, payload: Dict[str, Any]) -> str:
        """Writes the client-side JavaScript payload file for a run."""
        self._ensure_dirs()
        out_file = os.path.join(self.data_dir, f"topology_{run_id}.js")
        
        # Serialize to compact JSON safely wrapped in a global window assignment
        json_str = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
        content = (
            f"/* Topology Data Payload for Run {run_id} */\n"
            f"window.topology_data = window.topology_data || {{}};\n"
            f"window.topology_data['{run_id}'] = {json_str};\n"
        )
        
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(content)
            
        return out_file

    def build_all_runs(self, force_rebuild: bool = False) -> List[Dict[str, Any]]:
        """
        Scans all runs in runs/ directory, extracts topology payloads,
        writes individual .js data files, and generates topology/manifest.js.
        """
        self._ensure_dirs()
        
        all_runs = sorted(glob(os.path.join(self.runs_dir, "20*_*")), reverse=True)
        manifest_entries: List[Dict[str, Any]] = []

        print(f"[*] Scanning {len(all_runs)} snapshots for native topology data...")

        for r_path in all_runs:
            run_id = os.path.basename(r_path)
            data_file = os.path.join(self.data_dir, f"topology_{run_id}.js")
            
            # Check drawio presence in this run for hybrid support
            drawio_files = sorted(glob(os.path.join(r_path, "topology", "*.drawio")))
            has_drawio = len(drawio_files) > 0
            
            drawio_meta = []
            for f_path in drawio_files:
                fn = os.path.basename(f_path)
                topo_type = "summary" if ".connections.SUM" in fn else "detailed"
                layout = "circular" if "circular" in fn else ("geographic" if "geograf" in fn else "organic")
                drawio_meta.append({
                    "filename": fn,
                    "type": topo_type,
                    "layout": layout,
                    "path": f"../runs/{run_id}/topology/{fn}"
                })

            payload: Optional[Dict[str, Any]] = None
            if not os.path.isfile(data_file) or force_rebuild:
                try:
                    payload = self.extract_run_topology(run_id)
                    if payload["stats"]["total_nodes"] > 0 or has_drawio:
                        self.write_run_topology_payload(run_id, payload)
                except Exception as e:
                    print(f"    [!] Error extracting topology for {run_id}: {e}")
                    payload = None
            else:
                # Lightweight extraction of stats if already written
                try:
                    payload = self.extract_run_topology(run_id)
                except Exception:
                    payload = None

            total_nodes = payload["stats"]["total_nodes"] if payload else 0
            total_edges = payload["stats"]["total_summary_edges"] if payload else 0
            timestamp_str = payload["timestamp"] if payload else run_id

            # Only add to manifest if there is native data OR drawio files
            if total_nodes > 0 or has_drawio:
                manifest_entries.append({
                    "id": run_id,
                    "date": timestamp_str,
                    "has_native": total_nodes > 0,
                    "has_drawio": has_drawio,
                    "nodes_count": total_nodes,
                    "edges_count": total_edges,
                    "files": drawio_meta
                })

        # Write unified manifest.js
        manifest_file = os.path.join(self.topology_dir, "manifest.js")
        manifest_json = json.dumps(manifest_entries, indent=2, ensure_ascii=False)
        manifest_content = (
            f"/* Unified Topology Manifest (Native + Hybrid Draw.io) */\n"
            f"window.topo_manifest = {manifest_json};\n"
        )
        
        with open(manifest_file, "w", encoding="utf-8") as f:
            f.write(manifest_content)

        print(f"[+] Native topology data generated for {len(manifest_entries)} snapshots.")
        print(f"[*] Manifest written to: {manifest_file}")
        
        return manifest_entries

    def run(self, force_rebuild: bool = False) -> None:
        """Executes full engine run."""
        self.build_all_runs(force_rebuild=force_rebuild)
