# -*- coding: utf-8 -*-
"""
Storage Manager Facade
======================
Central routing facade for the Storage Abstraction Layer (SAL).
Coordinates persistence across Filesystem and Database backends according to
the configured storage mode ('files_only', 'db_only', 'hybrid').
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.storage.filesystem_driver import FilesystemDriver
from core.storage.interface import StorageDriver
from core.storage.sqlite_driver import SQLiteDriver

logger = logging.getLogger("ndx.storage.manager")


class StorageManager:
    """Singleton-friendly Storage Manager orchestrating multi-driver persistence."""

    def __init__(
        self,
        outbase: str = "infos",
        settings: Optional[Dict[str, Any]] = None,
        custom_db_path: Optional[str] = None,
        custom_mode: Optional[str] = None,
    ):
        self.outbase: str = outbase
        self.settings: Dict[str, Any] = settings or {}
        storage_cfg = self.settings.get("storage", {})

        self.mode: str = (custom_mode or storage_cfg.get("mode", "files_only")).lower()
        if self.mode not in ("files_only", "db_only", "hybrid"):
            logger.warning(f"Unknown storage mode '{self.mode}', defaulting to 'files_only'")
            self.mode = "files_only"

        self.backend: str = storage_cfg.get("backend", "sqlite").lower()

        # Initialize Drivers
        self.fs_driver: FilesystemDriver = FilesystemDriver()
        self.fs_driver.initialize(outbase, storage_cfg)

        self.db_driver: Optional[StorageDriver] = None
        if self.mode in ("db_only", "hybrid"):
            if self.backend == "sqlite":
                self.db_driver = SQLiteDriver(db_path=custom_db_path)
                self.db_driver.initialize(outbase, storage_cfg)
            else:
                logger.warning(
                    f"Backend '{self.backend}' not implemented, falling back to SQLite"
                )
                self.db_driver = SQLiteDriver(db_path=custom_db_path)
                self.db_driver.initialize(outbase, storage_cfg)

    @classmethod
    def from_settings(
        cls,
        outbase: str,
        custom_settings_path: Optional[str] = None,
        custom_db_path: Optional[str] = None,
        custom_mode: Optional[str] = None,
    ) -> "StorageManager":
        """Factory method loading settings from settings.json."""
        from core.utils_shared import load_settings

        cfg = load_settings(custom_settings_path)
        return cls(outbase=outbase, settings=cfg, custom_db_path=custom_db_path, custom_mode=custom_mode)

    # --- Mode Inspection ---

    def is_files_enabled(self) -> bool:
        return self.mode in ("files_only", "hybrid")

    def is_db_enabled(self) -> bool:
        return self.mode in ("db_only", "hybrid") and self.db_driver is not None

    def get_mode(self) -> str:
        return self.mode

    def get_database_path(self) -> Optional[str]:
        if isinstance(self.db_driver, SQLiteDriver):
            return self.db_driver.db_path
        return None

    # --- Write Coordination ---

    def create_run(
        self,
        run_id: str,
        started_at: datetime,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.is_files_enabled():
            self.fs_driver.create_run(run_id, started_at, self.mode, metadata)

        if self.is_db_enabled():
            try:
                self.db_driver.create_run(run_id, started_at, self.mode, metadata)
            except Exception as e:
                logger.error(f"Error creating run {run_id} in DB: {e}")
                if self.mode == "db_only":
                    raise

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
        if self.is_files_enabled():
            self.fs_driver.finish_run(
                run_id, finished_at, status, total_elements, successful_elements, failed_elements, metadata
            )

        if self.is_db_enabled():
            try:
                self.db_driver.finish_run(
                    run_id, finished_at, status, total_elements, successful_elements, failed_elements, metadata
                )
            except Exception as e:
                logger.error(f"Error finishing run {run_id} in DB: {e}")
                if self.mode == "db_only":
                    raise

    def save_raw_collection(
        self,
        run_id: str,
        hostname: str,
        ip: str,
        command: str,
        raw_output: str,
        collected_at: Optional[datetime] = None,
    ) -> None:
        if self.is_files_enabled():
            self.fs_driver.save_raw_collection(
                run_id, hostname, ip, command, raw_output, collected_at
            )

        if self.is_db_enabled():
            try:
                self.db_driver.save_raw_collection(
                    run_id, hostname, ip, command, raw_output, collected_at
                )
            except Exception as e:
                logger.error(f"Error saving raw collection {hostname}/{command} in DB: {e}")
                if self.mode == "db_only":
                    raise

    def save_successful_key(
        self,
        run_id: str,
        hostname: str,
        ip: str,
        key: str,
    ) -> None:
        if self.is_files_enabled():
            self.fs_driver.save_successful_key(run_id, hostname, ip, key)

        if self.is_db_enabled():
            try:
                self.db_driver.save_successful_key(run_id, hostname, ip, key)
            except Exception as e:
                logger.warning(f"Error saving successful key {hostname}/{key} in DB: {e}")

    def save_interfaces(
        self,
        run_id: str,
        interfaces: List[Dict[str, Any]],
    ) -> None:
        if self.is_files_enabled():
            self.fs_driver.save_interfaces(run_id, interfaces)

        if self.is_db_enabled():
            try:
                self.db_driver.save_interfaces(run_id, interfaces)
            except Exception as e:
                logger.error(f"Error saving interfaces for {run_id} in DB: {e}")
                if self.mode == "db_only":
                    raise

    def save_topology_connections(
        self,
        run_id: str,
        connections: List[Dict[str, Any]],
    ) -> None:
        if self.is_files_enabled():
            self.fs_driver.save_topology_connections(run_id, connections)

        if self.is_db_enabled():
            try:
                self.db_driver.save_topology_connections(run_id, connections)
            except Exception as e:
                logger.error(f"Error saving topology connections for {run_id} in DB: {e}")
                if self.mode == "db_only":
                    raise

    def save_lldp_neighbors(
        self,
        run_id: str,
        neighbors: List[Dict[str, Any]],
    ) -> None:
        if self.is_files_enabled():
            self.fs_driver.save_lldp_neighbors(run_id, neighbors)

        if self.is_db_enabled():
            try:
                self.db_driver.save_lldp_neighbors(run_id, neighbors)
            except Exception as e:
                logger.error(f"Error saving LLDP neighbors for {run_id} in DB: {e}")
                if self.mode == "db_only":
                    raise

    def save_ping_tests(
        self,
        run_id: str,
        ping_results: List[Dict[str, Any]],
    ) -> None:
        if self.is_files_enabled():
            self.fs_driver.save_ping_tests(run_id, ping_results)

        if self.is_db_enabled():
            try:
                self.db_driver.save_ping_tests(run_id, ping_results)
            except Exception as e:
                logger.error(f"Error saving ping tests for {run_id} in DB: {e}")
                if self.mode == "db_only":
                    raise

    def save_elements_status(
        self,
        run_id: str,
        elements_status: List[Dict[str, Any]],
    ) -> None:
        if self.is_files_enabled():
            self.fs_driver.save_elements_status(run_id, elements_status)

        if self.is_db_enabled():
            try:
                self.db_driver.save_elements_status(run_id, elements_status)
            except Exception as e:
                logger.error(f"Error saving elements status for {run_id} in DB: {e}")
                if self.mode == "db_only":
                    raise

    # --- Query Coordination ---

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        if self.is_db_enabled():
            res = self.db_driver.get_run(run_id)
            if res:
                return res
        return self.fs_driver.get_run(run_id)

    def list_runs(
        self,
        limit: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if self.is_db_enabled():
            runs = self.db_driver.list_runs(limit=limit, status=status)
            if runs:
                return runs
        return self.fs_driver.list_runs(limit=limit, status=status)

    def get_interfaces(self, run_id: str) -> List[Dict[str, Any]]:
        if self.is_db_enabled():
            data = self.db_driver.get_interfaces(run_id)
            if data:
                return data
        return self.fs_driver.get_interfaces(run_id)

    def get_topology_connections(self, run_id: str) -> List[Dict[str, Any]]:
        if self.is_db_enabled():
            data = self.db_driver.get_topology_connections(run_id)
            if data:
                return data
        return self.fs_driver.get_topology_connections(run_id)

    def get_ping_tests(self, run_id: str) -> List[Dict[str, Any]]:
        if self.is_db_enabled():
            data = self.db_driver.get_ping_tests(run_id)
            if data:
                return data
        return self.fs_driver.get_ping_tests(run_id)

    def get_ping_history(
        self,
        origin: str,
        dest: str,
        limit: int = 90,
    ) -> List[Dict[str, Any]]:
        if self.is_db_enabled():
            data = self.db_driver.get_ping_history(origin, dest, limit=limit)
            if data:
                return data
        return self.fs_driver.get_ping_history(origin, dest, limit=limit)

    def get_raw_collection(
        self,
        run_id: str,
        hostname: str,
        command: str,
    ) -> Optional[str]:
        if self.is_db_enabled():
            out = self.db_driver.get_raw_collection(run_id, hostname, command)
            if out is not None:
                return out
        return self.fs_driver.get_raw_collection(run_id, hostname, command)

    def health_check(self) -> Dict[str, Any]:
        """Runs health checks on all active drivers."""
        report = {
            "mode": self.mode,
            "backend": self.backend,
            "filesystem": self.fs_driver.health_check(),
            "database": self.db_driver.health_check() if self.db_driver else None,
        }
        return report

    def apply_retention(
        self,
        policy: Optional[Dict[str, Any]] = None,
        reference_now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Applies configured database retention policies to purge stale data and reclaim space."""
        if not self.is_db_enabled():
            return {"status": "skipped", "reason": "database_not_enabled"}

        if policy is None:
            retention_cfg = self.settings.get("storage", {}).get("retention", {}).get("database", {})
            if not retention_cfg:
                retention_cfg = self.settings.get("retention", {}).get("database", {})
            policy = retention_cfg or {}

        if not policy.get("enabled", True):
            return {"status": "skipped", "reason": "retention_disabled"}

        try:
            result = self.db_driver.purge_retention(policy, reference_now=reference_now)
            result["status"] = "success"
            return result
        except Exception as e:
            logger.error(f"Error applying database retention: {e}")
            return {"status": "error", "error": str(e)}
