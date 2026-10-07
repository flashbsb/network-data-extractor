# -*- coding: utf-8 -*-
"""
Storage Driver Interface
========================
Abstract base class defining the persistence and retrieval contract
for the Network Data Extractor storage layer.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional


class StorageDriver(ABC):
    """Abstract contract for storage backends (Filesystem, SQLite, PostgreSQL)."""

    @abstractmethod
    def initialize(self, outbase: str, config: Dict[str, Any]) -> None:
        """Initializes the backend (directories, connections, schemas)."""
        pass

    @abstractmethod
    def create_run(
        self,
        run_id: str,
        started_at: datetime,
        mode: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Registers a new execution run."""
        pass

    @abstractmethod
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
        """Marks a run as finished and updates metrics."""
        pass

    @abstractmethod
    def save_raw_collection(
        self,
        run_id: str,
        hostname: str,
        ip: str,
        command: str,
        raw_output: str,
        collected_at: Optional[datetime] = None,
    ) -> None:
        """Persists raw CLI output from a device command."""
        pass

    @abstractmethod
    def save_successful_key(
        self,
        run_id: str,
        hostname: str,
        ip: str,
        key: str,
    ) -> None:
        """Logs a successful command key for an element."""
        pass

    @abstractmethod
    def save_interfaces(
        self,
        run_id: str,
        interfaces: List[Dict[str, Any]],
    ) -> None:
        """Persists parsed interface records."""
        pass

    @abstractmethod
    def save_topology_connections(
        self,
        run_id: str,
        connections: List[Dict[str, Any]],
    ) -> None:
        """Persists topology connection adjacencies."""
        pass

    @abstractmethod
    def save_lldp_neighbors(
        self,
        run_id: str,
        neighbors: List[Dict[str, Any]],
    ) -> None:
        """Persists LLDP neighbor discovery records."""
        pass

    @abstractmethod
    def save_ping_tests(
        self,
        run_id: str,
        ping_results: List[Dict[str, Any]],
    ) -> None:
        """Persists ICMP ping matrix test results."""
        pass

    @abstractmethod
    def save_elements_status(
        self,
        run_id: str,
        elements_status: List[Dict[str, Any]],
    ) -> None:
        """Persists element audit and status summary records."""
        pass

    # --- Query & Retrieval APIs ---

    @abstractmethod
    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves details of a specific run."""
        pass

    @abstractmethod
    def list_runs(
        self,
        limit: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lists historical runs in chronological order (newest first)."""
        pass

    @abstractmethod
    def get_interfaces(self, run_id: str) -> List[Dict[str, Any]]:
        """Retrieves all interfaces for a given run."""
        pass

    @abstractmethod
    def get_topology_connections(self, run_id: str) -> List[Dict[str, Any]]:
        """Retrieves all topology connections for a given run."""
        pass

    @abstractmethod
    def get_ping_tests(self, run_id: str) -> List[Dict[str, Any]]:
        """Retrieves ping matrix tests for a given run."""
        pass

    @abstractmethod
    def get_ping_history(
        self,
        origin: str,
        dest: str,
        limit: int = 90,
    ) -> List[Dict[str, Any]]:
        """Retrieves latency/loss historical records for a specific link pair."""
        pass

    @abstractmethod
    def get_raw_collection(
        self,
        run_id: str,
        hostname: str,
        command: str,
    ) -> Optional[str]:
        """Retrieves raw output text for a specific device and command."""
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Performs a diagnostic check and returns backend status."""
        pass

    @abstractmethod
    def purge_retention(
        self,
        policy: Dict[str, Any],
        reference_now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Prunes historical database records based on retention policy and reclaims space."""
        pass
