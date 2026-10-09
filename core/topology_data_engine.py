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
import sys

# Support root directory imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from core.utils_shared import load_settings
except ImportError:
    def load_settings(custom_path=None):
        return {}


class TopologyDataEngine:
    def __init__(self, outbase: str, storage_mgr: Optional[Any] = None):
        self.outbase = os.path.abspath(outbase)
        self.storage_mgr = storage_mgr
        self.runs_dir = os.path.join(self.outbase, "runs")
        self.topology_dir = os.path.join(self.outbase, "topology")
        self.data_dir = os.path.join(self.topology_dir, "data")
        
        self.repo_dir = str(Path(__file__).resolve().parent.parent)
        self.settings = self._load_settings()
        self.network_cfg = self.settings.get("network", {}) if isinstance(self.settings.get("network"), dict) else self.settings
        self.routing_hierarchy = self.settings.get("routing_hierarchy", self.network_cfg.get("routing_hierarchy", {}))
        self.tier_metadata = self.settings.get("tier_metadata", self.network_cfg.get("tier_metadata", {}))
        self.topology_cfg = self.settings.get("topology", self.network_cfg.get("topology", {}))
        
        self.site_regex_str = self.topology_cfg.get("site_regex", r"[-_.]?([A-Za-z]{3,4}\d{2,3})[-_.]?")
        self.site_regex = re.compile(self.site_regex_str) if self.site_regex_str else None
        self.speed_colors = self.topology_cfg.get("speed_colors", {})
        self.speed_inference = self.settings.get("interface_speed_inference", self.network_cfg.get("interface_speed_inference", {}))

    def _load_settings(self) -> Dict[str, Any]:
        """Loads routing_hierarchy and styling from settings or modular config files."""
        try:
            cfg = load_settings()
            if cfg:
                return cfg
        except Exception:
            pass
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
        Determines the architectural layer and circular rank based on routing_hierarchy and tier_metadata.
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

        # Dynamic rank map derived from tier_metadata
        rank_map = {}
        for t, meta in self.tier_metadata.items():
            if isinstance(meta, dict) and "rank" in meta:
                rank_map[t] = meta["rank"]
        if not rank_map:
            rank_map = {
                "core": 1,
                "core_agg": 2,
                "edge": 3,
                "metro": 4,
                "peering": 5,
                "router_reflector": 6,
                "dcn": 7,
                "demarcator": 8,
                "customer_cpe": 9,
                "customer_sdwan": 10,
                "other": 11
            }

        for tier, prefixes in self.routing_hierarchy.items():
            if isinstance(prefixes, list):
                for p in prefixes:
                    p_clean = str(p).strip().upper()
                    if prefix.startswith(p_clean) or p_clean in prefix:
                        return (tier, rank_map.get(tier, 11))
        
        # Fallback heuristics
        if "RTIC" in clean_name or "CORE" in clean_name:
            return ("core", rank_map.get("core", 1))
        if "RTOC" in clean_name:
            return ("core_agg", rank_map.get("core_agg", 2))
        if "RTRR" in clean_name:
            return ("router_reflector", rank_map.get("router_reflector", 6))
        if "PTT" in clean_name or "IX" in clean_name or "RTPR" in clean_name:
            return ("peering", rank_map.get("peering", 5))
        if "RTAC" in clean_name or "RTED" in clean_name or "EDGE" in clean_name:
            return ("edge", rank_map.get("edge", 3))
        if any(p in clean_name for p in ["DRTA", "DRTD", "DSWA", "DRST", "DCN"]):
            return ("dcn", rank_map.get("dcn", 7))
        if any(p in clean_name for p in ["SWED", "EDEX", "DEMARC", "SWGB", "SWCP", "SWCN"]):
            return ("demarcator", rank_map.get("demarcator", 8))
        if any(p in clean_name for p in ["SDCE", "FGT40F", "SDWAN", "SD-WAN"]):
            return ("customer_sdwan", rank_map.get("customer_sdwan", 10))
        if any(p in clean_name for p in ["RTCE", "SWCE", "SWTP", "CPE"]):
            return ("customer_cpe", rank_map.get("customer_cpe", 9))
        if any(p in clean_name for p in ["SWAC", "SWAG", "SMAC", "SMAG", "RTMA", "SWL2", "METRO"]):
            return ("metro", rank_map.get("metro", 4))
            
        return ("other", rank_map.get("other", 11))

    def get_site_for_hostname(self, hostname: str) -> str:
        """Extracts site/location code from hostname (e.g., RTAC-BHE02-02 -> BHE02)."""
        if not hostname:
            return "UNKNOWN"
        clean = hostname.strip().upper()
        if self.site_regex:
            m = self.site_regex.search(clean)
            if m:
                return m.group(1) if m.groups() else m.group(0)
        parts = re.split(r"[-_.]", clean)
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

    def _load_ping_metrics_for_run(self, run_id: str, run_dir: str) -> Dict[str, Dict[str, Any]]:
        """
        Loads ping test metrics for a given run from SQLite or filesystem.
        Returns a dict indexed by:
          1. Undirected key: pair_key (e.g. "NODE_A__NODE_B", sorted)
          2. Directional key: f"{origin}|{dest}"
        Each entry contains:
          - rtt_avg_ms: float
          - rtt_min_ms: float
          - rtt_max_ms: float
          - loss_pct: float
          - jitter_ms: float
          - status: "healthy" | "warning" | "critical"
        """
        records: List[Dict[str, Any]] = []
        db_path = os.path.join(self.outbase, "database", "network_data.db")
        if os.path.isfile(db_path):
            try:
                import sqlite3
                with sqlite3.connect(db_path) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT origin, dest, loss_pct, min_rtt, avg_rtt, max_rtt, jitter, is_dead "
                        "FROM ping_tests WHERE run_id = ?",
                        (run_id,)
                    )
                    for row in cur.fetchall():
                        records.append({
                            "origin": (row[0] or "").strip(),
                            "dest": (row[1] or "").strip(),
                            "loss_pct": float(row[2]) if row[2] is not None else 0.0,
                            "min_rtt": float(row[3]) if row[3] is not None else 0.0,
                            "avg_rtt": float(row[4]) if row[4] is not None else 0.0,
                            "max_rtt": float(row[5]) if row[5] is not None else 0.0,
                            "jitter": float(row[6]) if row[6] is not None else 0.0,
                            "is_dead": bool(row[7])
                        })
            except Exception:
                pass

        if not records:
            # Fallback to filesystem resume files
            json_file = os.path.join(run_dir, "ping-matrix", "resume", "ping_matrix_list.json")
            if not os.path.isfile(json_file):
                json_file = os.path.join(run_dir, "resume", "ping_matrix_list.json")
            if os.path.isfile(json_file):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                        raw_data = payload.get("data", [])
                        for r in raw_data:
                            records.append({
                                "origin": (r.get("origin") or "").strip(),
                                "dest": (r.get("dest") or "").strip(),
                                "loss_pct": float(r.get("loss_pct") if r.get("loss_pct") is not None else r.get("loss", 0.0)),
                                "min_rtt": float(r.get("min_rtt") if r.get("min_rtt") is not None else r.get("min", 0.0)),
                                "avg_rtt": float(r.get("avg_rtt") if r.get("avg_rtt") is not None else r.get("avg", 0.0)),
                                "max_rtt": float(r.get("max_rtt") if r.get("max_rtt") is not None else r.get("max", 0.0)),
                                "jitter": float(r.get("jitter", 0.0)),
                                "is_dead": bool(r.get("is_dead", False))
                            })
                except Exception:
                    pass

        # Aggregate metrics
        ping_lookup: Dict[str, Dict[str, Any]] = {}
        pair_aggregates: Dict[str, List[Dict[str, Any]]] = {}

        for rec in records:
            orig = rec["origin"]
            dest = rec["dest"]
            if not orig or not dest:
                continue

            loss = rec["loss_pct"]
            avg_r = rec["avg_rtt"]
            # Determine health
            if rec["is_dead"] or loss >= 20.0:
                st = "critical"
            elif loss > 0.0 or avg_r >= 35.0:
                st = "warning"
            else:
                st = "healthy"

            metric_obj = {
                "rtt_avg_ms": round(avg_r, 2),
                "rtt_min_ms": round(rec["min_rtt"], 2),
                "rtt_max_ms": round(rec["max_rtt"], 2),
                "loss_pct": round(loss, 1),
                "jitter_ms": round(rec["jitter"], 2),
                "status": st
            }

            # Directional key
            ping_lookup[f"{orig}|{dest}"] = metric_obj

            # Symmetrical pair
            pair_key = "__".join(sorted([orig, dest]))
            if pair_key not in pair_aggregates:
                pair_aggregates[pair_key] = []
            pair_aggregates[pair_key].append(rec)

        # Build symmetrical consolidated metrics for each pair
        for pair_key, recs in pair_aggregates.items():
            mean_avg = sum(r["avg_rtt"] for r in recs) / len(recs)
            min_r = min(r["min_rtt"] for r in recs)
            max_r = max(r["max_rtt"] for r in recs)
            max_loss = max(r["loss_pct"] for r in recs)
            mean_jit = sum(r["jitter"] for r in recs) / len(recs)
            any_dead = any(r["is_dead"] for r in recs)

            if any_dead or max_loss >= 20.0:
                st = "critical"
            elif max_loss > 0.0 or mean_avg >= 35.0:
                st = "warning"
            else:
                st = "healthy"

            ping_lookup[pair_key] = {
                "rtt_avg_ms": round(mean_avg, 2),
                "rtt_min_ms": round(min_r, 2),
                "rtt_max_ms": round(max_r, 2),
                "loss_pct": round(max_loss, 1),
                "jitter_ms": round(mean_jit, 2),
                "status": st
            }

        return ping_lookup

    def extract_run_topology(self, run_id: str) -> Dict[str, Any]:
        """
        Extracts topology nodes and edges (summary and detailed) for a given run ID.
        Checks both flat files and SQLite database.
        """
        run_dir = os.path.join(self.runs_dir, run_id)
        nodes_dict: Dict[str, Dict[str, Any]] = {}
        edges_summary_list: List[Dict[str, Any]] = []
        edges_detail_list: List[Dict[str, Any]] = []
        
        # 0. Load Ping Telemetry for Run
        ping_lookup = self._load_ping_metrics_for_run(run_id, run_dir)
        
        # 1. Load Nodes Metadata from Resume Files (version_all.csv & platform_all.csv)
        platform_file = os.path.join(run_dir, "resume", "platform_all.csv")
        version_file = os.path.join(run_dir, "resume", "version_all.csv")
        status_file = os.path.join(run_dir, "resume", "status.elements.csv")
        
        node_meta: Dict[str, Dict[str, str]] = {}
        
        # Load OS Version and Uptime
        if os.path.isfile(version_file):
            try:
                with open(version_file, "r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f, delimiter=";")
                    for row in reader:
                        host = row.get("element", "").strip()
                        if host:
                            node_meta.setdefault(host, {})["os_version"] = row.get("software_version", row.get("version", ""))
                            node_meta[host]["uptime"] = row.get("uptime", "")
            except Exception:
                pass

        # Load Hardware Model and Vendor
        if os.path.isfile(platform_file):
            try:
                plat_rows: Dict[str, List[Dict[str, str]]] = {}
                with open(platform_file, "r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f, delimiter=";")
                    for row in reader:
                        host = row.get("element", "").strip()
                        if host:
                            plat_rows.setdefault(host, []).append(row)

                for host, rows in plat_rows.items():
                    # Check for explicit columns first
                    first_row = rows[0]
                    if first_row.get("vendor") or first_row.get("model"):
                        node_meta.setdefault(host, {})["vendor"] = first_row.get("vendor", "")
                        node_meta[host]["model"] = first_row.get("model", "")
                        if "version" in first_row and not node_meta[host].get("os_version"):
                            node_meta[host]["os_version"] = first_row.get("version", "")
                        continue

                    # Intelligent chassis / card inference
                    chassis = ""
                    rsp = ""
                    for r in rows:
                        t = r.get("type", "").strip()
                        node = r.get("node", "").strip()
                        m_fc = re.search(r"(ASR-?\d+|NC55-\d+|A9K|ASR\d+|NCS-?\d+|C\d{4})", t, re.I)
                        if m_fc and any(k in t.upper() for k in ("FAN", "FC", "CHASSIS", "PEM")):
                            chassis = m_fc.group(1)
                        elif not chassis and m_fc:
                            chassis = m_fc.group(1)
                        if "Active" in t or "RSP" in node or "RP" in node:
                            rsp = t.replace("(Active)", "").replace("(Standby)", "").strip()

                    model = chassis or rsp or (rows[0].get("type", "") if rows else "")
                    
                    # Vendor inference
                    vendor = "Cisco"
                    all_text = " ".join([r.get("type", "") + " " + r.get("node", "") for r in rows]).upper()
                    if any(k in all_text for k in ("DATACOM", "DM4", "DM2", "DM3")):
                        vendor = "Datacom"
                    elif any(k in all_text for k in ("HUAWEI", "NE40", "NE8000", "CLOUDENGINE")):
                        vendor = "Huawei"
                    elif any(k in all_text for k in ("JUNIPER", "MX")):
                        vendor = "Juniper"
                    elif any(k in all_text for k in ("A9K", "ASR", "NC55", "NCS", "CISCO")):
                        vendor = "Cisco"

                    node_meta.setdefault(host, {})["model"] = model
                    node_meta[host]["vendor"] = vendor
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
                "uptime": meta.get("uptime", ""),
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
                        
                        pair_key = f"{sorted_pair[0]}__{sorted_pair[1]}"
                        p_metric = ping_lookup.get(pair_key) or ping_lookup.get(f"{a}|{b}") or ping_lookup.get(f"{b}|{a}")

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
                            "dashed": is_dashed,
                            "ping": p_metric
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
                    p_metric = ping_lookup.get(pair_key) or ping_lookup.get(f"{a}|{b}") or ping_lookup.get(f"{b}|{a}")
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
                        "dashed": False,
                        "ping": p_metric
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
                            p_metric = ping_lookup.get(pair_key) or ping_lookup.get(f"{a}|{b}") or ping_lookup.get(f"{b}|{a}")
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
                                "dashed": False,
                                "ping": p_metric
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
                        
                        # Normalize speed using configured inference map
                        l_lower = l_intf.lower()
                        speed = "10G"
                        for pattern, inferred in self.speed_inference.items():
                            if pattern in l_lower:
                                speed = inferred.replace("bps", "").replace("b", "").upper()
                                break
                        else:
                            if "hundred" in l_lower or "100g" in l_lower:
                                speed = "100G"
                            elif "forty" in l_lower or "40g" in l_lower:
                                speed = "40G"
                            elif "gigabit" in l_lower and "ten" not in l_lower:
                                speed = "1G"
                            
                        edge_id = f"{local}_{l_intf}__{remote}_{r_intf}"
                        p_metric = ping_lookup.get(f"{local}|{remote}") or ping_lookup.get(f"{remote}|{local}") or ping_lookup.get("__".join(sorted([local, remote])))
                        
                        # Style from speed_colors / zero purple
                        edge_width = 4 if speed == "100G" else (3 if speed == "40G" else 2)
                        edge_color = "#10b981" if speed == "100G" else ("#38bdf8" if speed == "40G" else "#0284c7")
                        
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
                            "width": edge_width,
                            "color": edge_color,
                            "ping": p_metric
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

        # Ping summary compilation
        tested_pairs = [v for k, v in ping_lookup.items() if "__" in k]
        ping_summary = {
            "total_pairs_tested": len(tested_pairs),
            "healthy_pairs": sum(1 for p in tested_pairs if p.get("status") == "healthy"),
            "warning_pairs": sum(1 for p in tested_pairs if p.get("status") == "warning"),
            "critical_pairs": sum(1 for p in tested_pairs if p.get("status") == "critical"),
            "avg_latency_ms": round(sum(p["rtt_avg_ms"] for p in tested_pairs) / len(tested_pairs), 2) if tested_pairs else 0.0,
            "worst_loss_pct": max([p["loss_pct"] for p in tested_pairs], default=0.0)
        }

        return {
            "run_id": run_id,
            "timestamp": formatted_date,
            "routing_hierarchy": self.routing_hierarchy,
            "tier_metadata": self.tier_metadata,
            "stats": {
                "total_nodes": len(nodes_dict),
                "total_summary_edges": len(edges_summary_list),
                "total_detailed_edges": len(edges_detail_list),
                "tiers_count": tiers_count,
                "ping_summary": ping_summary
            },
            "ping_summary": ping_summary,
            "ping_lookup": {k: v for k, v in ping_lookup.items() if "|" in k or "__" in k},
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
