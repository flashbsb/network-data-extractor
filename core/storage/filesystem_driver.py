# -*- coding: utf-8 -*-
"""
Filesystem Storage Driver
=========================
Encapsulates traditional file-based persistence for Network Data Extractor:
- runs/YYYYMMDD_HHMMSS/collect/*.txt
- runs/YYYYMMDD_HHMMSS/resume/*.csv, *.json
- runs/YYYYMMDD_HHMMSS/connections/*.csv
"""

import csv
import glob
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.storage.interface import StorageDriver


class FilesystemDriver(StorageDriver):
    """Filesystem driver managing traditional flat-file storage hierarchies."""

    def __init__(self, outbase: Optional[str] = None, runs_dir: Optional[str] = None):
        self.outbase: Optional[str] = outbase
        self.runs_dir: Optional[str] = runs_dir

    def initialize(self, outbase: str, config: Dict[str, Any]) -> None:
        self.outbase = os.path.abspath(outbase)
        if not self.runs_dir:
            os.makedirs(os.path.join(self.outbase, "runs"), exist_ok=True)
        else:
            os.makedirs(self.runs_dir, exist_ok=True)

    def _get_run_dirs(self, run_id: str) -> Dict[str, str]:
        if self.runs_dir:
            run_root = os.path.join(self.runs_dir, run_id)
        elif self.outbase:
            run_root = os.path.join(self.outbase, "runs", run_id)
        else:
            run_root = os.path.join(".", "runs", run_id)
        return {
            "root": run_root,
            "collect": os.path.join(run_root, "collect"),
            "resume": os.path.join(run_root, "resume"),
            "connections": os.path.join(run_root, "connections"),
            "log": os.path.join(run_root, "log"),
            "ping_resume": os.path.join(run_root, "ping-matrix", "resume"),
        }

    def create_run(
        self,
        run_id: str,
        started_at: datetime,
        mode: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        dirs = self._get_run_dirs(run_id)
        for d in (dirs["collect"], dirs["resume"], dirs["connections"], dirs["log"]):
            os.makedirs(d, exist_ok=True)

    def finish_run(
        self,
        run_id: str,
        finished_at: datetime,
        status: str,
        total_elements: int = 0,
        successful_elements: int = 0,
        failed_elements: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        pass  # File status is inferred by presence of outputs

    def save_raw_collection(
        self,
        run_id: str,
        hostname: str,
        ip: str,
        command: str,
        raw_output: str,
        collected_at: Optional[datetime] = None,
    ) -> None:
        if collected_at is None:
            collected_at = datetime.now()

        dirs = self._get_run_dirs(run_id)
        os.makedirs(dirs["collect"], exist_ok=True)

        sanitized_cmd = command.replace(" ", ".")
        for ch in ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]:
            sanitized_cmd = sanitized_cmd.replace(ch, "")
        sanitized_cmd = sanitized_cmd[:100]

        ts_str = collected_at.strftime("%d%m%y%H%M%S")
        fname = f"{hostname}.{ts_str}.{sanitized_cmd}.txt"
        filepath = os.path.join(dirs["collect"], fname)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# Host: {hostname}\n# IP: {ip}\n# Command: {command}\n# Date: {ts_str}\n\n")
            f.write(raw_output)

    def save_successful_key(
        self,
        run_id: str,
        hostname: str,
        ip: str,
        key: str,
    ) -> None:
        dirs = self._get_run_dirs(run_id)
        os.makedirs(dirs["collect"], exist_ok=True)
        sk_path = os.path.join(dirs["collect"], "successful_keys.csv")
        with open(sk_path, "a", encoding="utf-8") as f:
            f.write(f"{hostname};{ip};{key}\n")

    def save_interfaces(
        self,
        run_id: str,
        interfaces: List[Dict[str, Any]],
    ) -> None:
        if not interfaces:
            return
        dirs = self._get_run_dirs(run_id)
        os.makedirs(dirs["resume"], exist_ok=True)

        csv_path = os.path.join(dirs["resume"], "interfaces_all.csv")
        json_path = os.path.join(dirs["resume"], "interfaces_all.json")

        headers = [
            "element", "id", "interface", "admin_status", "line_protocol",
            "description", "ip_address", "mtu", "bandwidth_kbit", "reliability",
            "txload", "rxload", "last_flapped"
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(interfaces)

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(interfaces, f, indent=2)

    def save_topology_connections(
        self,
        run_id: str,
        connections: List[Dict[str, Any]],
    ) -> None:
        if not connections:
            return
        dirs = self._get_run_dirs(run_id)
        os.makedirs(dirs["connections"], exist_ok=True)

        csv_path = os.path.join(dirs["connections"], "topology.connections.csv")
        headers = [
            "endpoint_a", "interface_a", "endpoint_b", "interface_b",
            "connection_type", "speed_kbit"
        ]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(connections)

    def save_lldp_neighbors(
        self,
        run_id: str,
        neighbors: List[Dict[str, Any]],
    ) -> None:
        if not neighbors:
            return
        dirs = self._get_run_dirs(run_id)
        os.makedirs(dirs["resume"], exist_ok=True)

        csv_path = os.path.join(dirs["resume"], "show_lldp_neighbors_detail_all.csv")
        headers = ["local_host", "local_interface", "remote_host", "remote_interface", "remote_ip"]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(neighbors)

    def save_ping_tests(
        self,
        run_id: str,
        ping_results: List[Dict[str, Any]],
    ) -> None:
        if not ping_results:
            return
        dirs = self._get_run_dirs(run_id)
        os.makedirs(dirs["ping_resume"], exist_ok=True)

        csv_path = os.path.join(dirs["ping_resume"], "ping_matrix_list.csv")
        headers = [
            "origin", "dest", "tx", "rx", "loss_pct",
            "min", "avg", "max", "jitter", "is_dead", "asymmetric_warning"
        ]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(ping_results)

    def save_elements_status(
        self,
        run_id: str,
        elements_status: List[Dict[str, Any]],
    ) -> None:
        if not elements_status:
            return
        dirs = self._get_run_dirs(run_id)
        os.makedirs(dirs["resume"], exist_ok=True)

        csv_path = os.path.join(dirs["resume"], "status.elements.csv")
        headers = ["element_name", "element", "real_hostname", "timestamp", "status", "working_key", "details"]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", extrasaction="ignore")
            writer.writeheader()
            for s in elements_status:
                el = s.get("element_name") or s.get("element", "")
                row = {
                    "element_name": el,
                    "element": el,
                    "real_hostname": s.get("real_hostname", "-"),
                    "timestamp": s.get("timestamp", "-"),
                    "status": s.get("status", "ok"),
                    "working_key": s.get("working_key", "-"),
                    "details": s.get("details", "")
                }
                writer.writerow(row)

    # --- Query APIs ---

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        dirs = self._get_run_dirs(run_id)
        if not os.path.isdir(dirs["root"]):
            return None
        return {
            "run_id": run_id,
            "root": dirs["root"],
            "has_collect": os.path.isdir(dirs["collect"]),
            "has_resume": os.path.isdir(dirs["resume"]),
            "has_connections": os.path.isdir(dirs["connections"]),
        }

    def list_runs(
        self,
        limit: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        runs_dir = os.path.join(self.outbase, "runs")
        if not os.path.isdir(runs_dir):
            return []
        subdirs = sorted(glob.glob(os.path.join(runs_dir, "20*_*")), reverse=True)
        results = []
        for d in subdirs:
            r_id = os.path.basename(d)
            results.append({"run_id": r_id, "path": d})
            if limit and len(results) >= limit:
                break
        return results

    def get_interfaces(self, run_id: str) -> List[Dict[str, Any]]:
        dirs = self._get_run_dirs(run_id)
        json_path = os.path.join(dirs["resume"], "interfaces_all.json")
        if os.path.isfile(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        csv_path = os.path.join(dirs["resume"], "interfaces_all.csv")
        if os.path.isfile(csv_path):
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=";")
                return list(reader)
        return []

    def get_topology_connections(self, run_id: str) -> List[Dict[str, Any]]:
        dirs = self._get_run_dirs(run_id)
        csv_path = os.path.join(dirs["connections"], "topology.connections.csv")
        if os.path.isfile(csv_path):
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=";")
                return list(reader)
        return []

    def get_ping_tests(self, run_id: str) -> List[Dict[str, Any]]:
        dirs = self._get_run_dirs(run_id)
        json_path = os.path.join(dirs["ping_resume"], "ping_matrix_list.json")
        if not os.path.isfile(json_path):
            json_path = os.path.join(dirs["resume"], "ping_matrix_list.json")

        if os.path.isfile(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("data", [])
            except Exception:
                pass
        return []

    def get_ping_history(
        self,
        origin: str,
        dest: str,
        limit: int = 90,
    ) -> List[Dict[str, Any]]:
        # Traditional history reads from ping-matrix/history/links/{origin}_{dest}.json
        hist_file = os.path.join(
            self.outbase, "ping-matrix", "history", "links", f"{origin}_{dest}.json"
        )
        if os.path.isfile(hist_file):
            try:
                with open(hist_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data[-limit:] if isinstance(data, list) else []
            except Exception:
                pass
        return []

    def get_raw_collection(
        self,
        run_id: str,
        hostname: str,
        command: str,
    ) -> Optional[str]:
        dirs = self._get_run_dirs(run_id)
        collect_dir = dirs["collect"]
        if not os.path.isdir(collect_dir):
            return None

        sanitized_cmd = command.replace(" ", ".")
        for ch in ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]:
            sanitized_cmd = sanitized_cmd.replace(ch, "")
        sanitized_cmd = sanitized_cmd[:100]

        pattern = os.path.join(collect_dir, f"{hostname}.*.{sanitized_cmd}.txt")
        matches = glob.glob(pattern)
        if matches:
            try:
                with open(matches[0], "r", encoding="utf-8", errors="replace") as f:
                    return f.read()
            except Exception:
                return None
        return None

    def health_check(self) -> Dict[str, Any]:
        runs_dir = os.path.join(self.outbase, "runs")
        count = len(glob.glob(os.path.join(runs_dir, "20*_*"))) if os.path.isdir(runs_dir) else 0
        return {
            "driver": "FilesystemDriver",
            "outbase": self.outbase,
            "runs_directory": runs_dir,
            "runs_count": count,
            "status": "OK" if os.path.isdir(self.outbase) else "NOT_FOUND",
        }

    def purge_retention(
        self,
        policy: Dict[str, Any],
        reference_now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Filesystem retention is handled by orchestrator prune_old_runs."""
        return {"pruned_runs": 0, "pruned_raw_collections": 0, "driver": "FilesystemDriver"}
