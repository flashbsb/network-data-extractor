# -*- coding: utf-8 -*-
"""
SQLite Storage Driver
=====================
High-performance, zero-dependency SQLite implementation with:
- WAL (Write-Ahead Logging) mode for concurrent reads
- Dynamic path resolution ({outbase}/database/network_data.db)
- Auto-provisioning and schema migrations
- Retry loop with exponential backoff for lock resilience
- Optional zlib compression for raw CLI text
"""

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
import zlib
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from core.storage.interface import StorageDriver

logger = logging.getLogger("ndx.storage.sqlite")

SCHEMA_VERSION = 1
SCHEMA_NAME = "v1_core_relational_schema"


class SQLiteDriver(StorageDriver):
    """SQLite backend driver supporting WAL, batching, and schema management."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path: Optional[str] = db_path
        self.busy_timeout_ms: int = 60000
        self.journal_mode: str = "WAL"
        self.synchronous: str = "NORMAL"
        self.compression_enabled: bool = True
        self._local = threading.local()
        self._lock = threading.Lock()
        self._initialized: bool = False

    def initialize(self, outbase: str, config: Dict[str, Any]) -> None:
        """Configures database path and applies initial schema idempotently."""
        sqlite_cfg = config.get("sqlite", {})

        # Path resolution hierarchy:
        # 1. Explicit constructor argument
        # 2. NDX_DATABASE_PATH environment variable
        # 3. Explicit config database_path
        # 4. Default: {outbase}/database/{database_name}
        env_path = os.environ.get("NDX_DATABASE_PATH")
        cfg_path = sqlite_cfg.get("database_path")
        db_name = sqlite_cfg.get("database_name", "network_data.db")

        if self.db_path:
            target_path = self.db_path
        elif env_path:
            target_path = env_path
        elif cfg_path:
            target_path = cfg_path
        else:
            target_path = os.path.join(outbase, "database", db_name)

        self.db_path = os.path.abspath(target_path)
        self.busy_timeout_ms = int(sqlite_cfg.get("busy_timeout_ms", 60000))
        self.journal_mode = sqlite_cfg.get("journal_mode", "WAL").upper()
        self.synchronous = sqlite_cfg.get("synchronous", "NORMAL").upper()
        self.compression_enabled = bool(sqlite_cfg.get("compression_enabled", True))

        # Ensure directory exists with secure permissions (0700)
        db_dir = os.path.dirname(self.db_path)
        if not os.path.isdir(db_dir):
            os.makedirs(db_dir, mode=0o700, exist_ok=True)

        # Set secure file permissions if new file
        if not os.path.exists(self.db_path):
            try:
                with open(self.db_path, "a"):
                    pass
                os.chmod(self.db_path, 0o600)
            except Exception as e:
                logger.warning(f"Could not enforce 0600 on {self.db_path}: {e}")

        self._apply_migrations()
        self._initialized = True

    def _get_connection(self) -> sqlite3.Connection:
        """Returns a thread-local SQLite connection configured with WAL and pragmas."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                self.db_path,
                timeout=self.busy_timeout_ms / 1000.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute(f"PRAGMA journal_mode = {self.journal_mode};")
            cursor.execute(f"PRAGMA synchronous = {self.synchronous};")
            cursor.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms};")
            cursor.close()
            self._local.conn = conn
        return self._local.conn

    def _execute_with_retry(
        self,
        func: Callable[[sqlite3.Connection], Any],
        max_retries: int = 5,
    ) -> Any:
        """Executes a database callback with exponential backoff on lock contention."""
        conn = self._get_connection()
        delay = 0.05
        for attempt in range(1, max_retries + 1):
            try:
                return func(conn)
            except sqlite3.OperationalError as e:
                err_msg = str(e).lower()
                if ("locked" in err_msg or "busy" in err_msg) and attempt < max_retries:
                    time.sleep(delay)
                    delay = min(delay * 2, 2.0)
                    continue
                raise

    def _apply_migrations(self) -> None:
        """Applies versioned schema migrations idempotently."""
        with self._lock:
            conn = self._get_connection()
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        checksum TEXT NOT NULL
                    );
                    """
                )
                cursor.execute(
                    "SELECT version FROM schema_migrations WHERE version = ?",
                    (SCHEMA_VERSION,),
                )
                row = cursor.fetchone()
                if not row:
                    self._create_v1_schema(cursor)
                    cursor.execute(
                        """
                        INSERT INTO schema_migrations (version, name, checksum)
                        VALUES (?, ?, ?);
                        """,
                        (SCHEMA_VERSION, SCHEMA_NAME, "initial_v1_hash"),
                    )

    def _create_v1_schema(self, cursor: sqlite3.Cursor) -> None:
        """Creates the V1 relational schema and indexes."""
        cursor.executescript(
            """
            -- Executions / Runs Table
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                started_at TIMESTAMP NOT NULL,
                finished_at TIMESTAMP,
                status TEXT NOT NULL CHECK(status IN ('IN_PROGRESS', 'SUCCESS', 'FAILED', 'INTERRUPTED')),
                storage_mode TEXT NOT NULL,
                total_elements INTEGER DEFAULT 0,
                successful_elements INTEGER DEFAULT 0,
                failed_elements INTEGER DEFAULT 0,
                metadata_json TEXT,
                run_hash TEXT
            );

            -- Registered Elements Table
            CREATE TABLE IF NOT EXISTS elements (
                hostname TEXT PRIMARY KEY,
                ip TEXT,
                cmd_key TEXT,
                status TEXT DEFAULT 'ok',
                last_seen TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Raw CLI Output Collections
            CREATE TABLE IF NOT EXISTS raw_collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                hostname TEXT NOT NULL,
                ip TEXT NOT NULL,
                command TEXT NOT NULL,
                raw_output BLOB NOT NULL,
                is_compressed BOOLEAN DEFAULT 0,
                output_hash TEXT NOT NULL,
                collected_at TIMESTAMP NOT NULL
            );

            -- Successful Command Keys per element
            CREATE TABLE IF NOT EXISTS successful_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                hostname TEXT NOT NULL,
                ip TEXT NOT NULL,
                command_key TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(run_id, hostname, ip, command_key)
            );

            -- Interfaces Table
            CREATE TABLE IF NOT EXISTS interfaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                element TEXT NOT NULL,
                interface TEXT NOT NULL,
                admin_status TEXT,
                line_protocol TEXT,
                description TEXT,
                ip_address TEXT,
                mtu INTEGER,
                bandwidth_kbit BIGINT,
                last_flapped TEXT
            );

            -- Topology Connections Table
            CREATE TABLE IF NOT EXISTS topology_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                endpoint_a TEXT NOT NULL,
                interface_a TEXT NOT NULL,
                endpoint_b TEXT NOT NULL,
                interface_b TEXT NOT NULL,
                connection_type TEXT,
                speed_kbit BIGINT
            );

            -- LLDP Neighbors Table
            CREATE TABLE IF NOT EXISTS lldp_neighbors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                local_host TEXT NOT NULL,
                local_interface TEXT NOT NULL,
                remote_host TEXT NOT NULL,
                remote_interface TEXT NOT NULL,
                remote_ip TEXT
            );

            -- Ping Matrix ICMP Tests
            CREATE TABLE IF NOT EXISTS ping_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                origin TEXT NOT NULL,
                dest TEXT NOT NULL,
                tx INTEGER NOT NULL,
                rx INTEGER NOT NULL,
                loss_pct REAL NOT NULL,
                min_rtt REAL,
                avg_rtt REAL,
                max_rtt REAL,
                jitter REAL,
                is_dead BOOLEAN NOT NULL,
                is_asymmetric BOOLEAN NOT NULL
            );

            -- Elements Audit and Status
            CREATE TABLE IF NOT EXISTS elements_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                element TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT
            );

            -- Performance Indexes
            CREATE INDEX IF NOT EXISTS idx_raw_run_host ON raw_collections(run_id, hostname);
            CREATE INDEX IF NOT EXISTS idx_raw_hash ON raw_collections(output_hash);
            CREATE INDEX IF NOT EXISTS idx_ifaces_run_elem ON interfaces(run_id, element);
            CREATE INDEX IF NOT EXISTS idx_ifaces_elem_iface ON interfaces(element, interface);
            CREATE INDEX IF NOT EXISTS idx_topo_run ON topology_connections(run_id);
            CREATE INDEX IF NOT EXISTS idx_ping_pair_run ON ping_tests(origin, dest, run_id);
            CREATE INDEX IF NOT EXISTS idx_ping_loss ON ping_tests(loss_pct);
            """
        )

    # --- Write Implementations ---

    def create_run(
        self,
        run_id: str,
        started_at: datetime,
        mode: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        def _op(conn):
            with conn:
                conn.execute(
                    """
                    INSERT INTO runs (run_id, started_at, status, storage_mode, metadata_json)
                    VALUES (?, ?, 'IN_PROGRESS', ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        started_at = excluded.started_at,
                        status = 'IN_PROGRESS',
                        storage_mode = excluded.storage_mode,
                        metadata_json = excluded.metadata_json;
                    """,
                    (
                        run_id,
                        started_at.strftime("%Y-%m-%d %H:%M:%S"),
                        mode,
                        json.dumps(metadata or {}),
                    ),
                )

        self._execute_with_retry(_op)

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
        def _op(conn):
            with conn:
                meta_json = json.dumps(metadata) if metadata is not None else None
                if meta_json:
                    conn.execute(
                        """
                        UPDATE runs SET
                            finished_at = ?,
                            status = ?,
                            total_elements = ?,
                            successful_elements = ?,
                            failed_elements = ?,
                            metadata_json = ?
                        WHERE run_id = ?;
                        """,
                        (
                            finished_at.strftime("%Y-%m-%d %H:%M:%S"),
                            status,
                            total_elements,
                            successful_elements,
                            failed_elements,
                            meta_json,
                            run_id,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE runs SET
                            finished_at = ?,
                            status = ?,
                            total_elements = ?,
                            successful_elements = ?,
                            failed_elements = ?
                        WHERE run_id = ?;
                        """,
                        (
                            finished_at.strftime("%Y-%m-%d %H:%M:%S"),
                            status,
                            total_elements,
                            successful_elements,
                            failed_elements,
                            run_id,
                        ),
                    )

        self._execute_with_retry(_op)

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

        output_bytes = raw_output.encode("utf-8", errors="replace")
        output_hash = hashlib.sha256(output_bytes).hexdigest()

        if self.compression_enabled:
            payload = zlib.compress(output_bytes)
            is_comp = 1
        else:
            payload = output_bytes
            is_comp = 0

        def _op(conn):
            with conn:
                conn.execute(
                    """
                    INSERT INTO raw_collections
                        (run_id, hostname, ip, command, raw_output, is_compressed, output_hash, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        run_id,
                        hostname,
                        ip,
                        command,
                        sqlite3.Binary(payload),
                        is_comp,
                        output_hash,
                        collected_at.strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )

        self._execute_with_retry(_op)

    def save_successful_key(
        self,
        run_id: str,
        hostname: str,
        ip: str,
        key: str,
    ) -> None:
        def _op(conn):
            with conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO successful_keys (run_id, hostname, ip, command_key)
                    VALUES (?, ?, ?, ?);
                    """,
                    (run_id, hostname, ip, key),
                )

        self._execute_with_retry(_op)

    def save_interfaces(
        self,
        run_id: str,
        interfaces: List[Dict[str, Any]],
    ) -> None:
        if not interfaces:
            return

        def _to_int(val: Any) -> Optional[int]:
            try:
                return int(val) if val not in (None, "", "-") else None
            except (ValueError, TypeError):
                return None

        rows = []
        for iface in interfaces:
            rows.append(
                (
                    run_id,
                    str(iface.get("element", "")).strip(),
                    str(iface.get("interface", "")).strip(),
                    iface.get("admin_status"),
                    iface.get("line_protocol"),
                    iface.get("description"),
                    iface.get("ip_address"),
                    _to_int(iface.get("mtu")),
                    _to_int(iface.get("bandwidth_kbit")),
                    iface.get("last_flapped"),
                )
            )

        def _op(conn):
            with conn:
                conn.executemany(
                    """
                    INSERT INTO interfaces
                        (run_id, element, interface, admin_status, line_protocol, description, ip_address, mtu, bandwidth_kbit, last_flapped)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    rows,
                )

        self._execute_with_retry(_op)

    def save_topology_connections(
        self,
        run_id: str,
        connections: List[Dict[str, Any]],
    ) -> None:
        if not connections:
            return

        def _to_int(val: Any) -> Optional[int]:
            try:
                return int(val) if val not in (None, "", "-") else None
            except (ValueError, TypeError):
                return None

        rows = []
        for c in connections:
            rows.append(
                (
                    run_id,
                    str(c.get("endpoint_a", "")).strip(),
                    str(c.get("interface_a", "")).strip(),
                    str(c.get("endpoint_b", "")).strip(),
                    str(c.get("interface_b", "")).strip(),
                    c.get("connection_type"),
                    _to_int(c.get("speed_kbit")),
                )
            )

        def _op(conn):
            with conn:
                conn.executemany(
                    """
                    INSERT INTO topology_connections
                        (run_id, endpoint_a, interface_a, endpoint_b, interface_b, connection_type, speed_kbit)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    rows,
                )

        self._execute_with_retry(_op)

    def save_lldp_neighbors(
        self,
        run_id: str,
        neighbors: List[Dict[str, Any]],
    ) -> None:
        if not neighbors:
            return

        rows = []
        for n in neighbors:
            rows.append(
                (
                    run_id,
                    str(n.get("local_host", "")).strip(),
                    str(n.get("local_interface", "")).strip(),
                    str(n.get("remote_host", "")).strip(),
                    str(n.get("remote_interface", "")).strip(),
                    n.get("remote_ip"),
                )
            )

        def _op(conn):
            with conn:
                conn.executemany(
                    """
                    INSERT INTO lldp_neighbors
                        (run_id, local_host, local_interface, remote_host, remote_interface, remote_ip)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    rows,
                )

        self._execute_with_retry(_op)

    def save_ping_tests(
        self,
        run_id: str,
        ping_results: List[Dict[str, Any]],
    ) -> None:
        if not ping_results:
            return

        def _to_float(val: Any) -> Optional[float]:
            try:
                return float(val) if val not in (None, "", "-") else None
            except (ValueError, TypeError):
                return None

        rows = []
        for p in ping_results:
            rows.append(
                (
                    run_id,
                    str(p.get("origin", "")).strip(),
                    str(p.get("dest", "")).strip(),
                    int(p.get("tx", 0)),
                    int(p.get("rx", 0)),
                    float(p.get("loss_pct", 100.0)),
                    _to_float(p.get("min")),
                    _to_float(p.get("avg")),
                    _to_float(p.get("max")),
                    _to_float(p.get("jitter")),
                    1 if p.get("is_dead") or p.get("is_unreachable") else 0,
                    1 if p.get("asymmetric_warning") else 0,
                )
            )

        def _op(conn):
            with conn:
                conn.executemany(
                    """
                    INSERT INTO ping_tests
                        (run_id, origin, dest, tx, rx, loss_pct, min_rtt, avg_rtt, max_rtt, jitter, is_dead, is_asymmetric)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    rows,
                )

        self._execute_with_retry(_op)

    def save_elements_status(
        self,
        run_id: str,
        elements_status: List[Dict[str, Any]],
    ) -> None:
        if not elements_status:
            return

        rows = []
        for s in elements_status:
            rows.append(
                (
                    run_id,
                    str(s.get("element", "")).strip(),
                    str(s.get("status", "")).strip().lower(),
                    json.dumps(s.get("details", {})),
                )
            )

        def _op(conn):
            with conn:
                conn.executemany(
                    """
                    INSERT INTO elements_status (run_id, element, status, details)
                    VALUES (?, ?, ?, ?);
                    """,
                    rows,
                )

        self._execute_with_retry(_op)

    # --- Query Implementations ---

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        def _op(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                if d.get("metadata_json"):
                    try:
                        d["metadata"] = json.loads(d["metadata_json"])
                    except Exception:
                        d["metadata"] = {}
                return d
            return None

        return self._execute_with_retry(_op)

    def list_runs(
        self,
        limit: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        def _op(conn):
            cursor = conn.cursor()
            query = "SELECT * FROM runs"
            params = []
            if status:
                query += " WHERE status = ?"
                params.append(status)
            query += " ORDER BY run_id DESC"
            if limit:
                query += " LIMIT ?"
                params.append(limit)

            cursor.execute(query, params)
            results = []
            for row in cursor.fetchall():
                d = dict(row)
                if d.get("metadata_json"):
                    try:
                        d["metadata"] = json.loads(d["metadata_json"])
                    except Exception:
                        d["metadata"] = {}
                results.append(d)
            return results

        return self._execute_with_retry(_op)

    def get_interfaces(self, run_id: str) -> List[Dict[str, Any]]:
        def _op(conn):
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT element, interface, admin_status, line_protocol, description,
                       ip_address, mtu, bandwidth_kbit, last_flapped
                FROM interfaces WHERE run_id = ? ORDER BY element, interface;
                """,
                (run_id,),
            )
            return [dict(r) for r in cursor.fetchall()]

        return self._execute_with_retry(_op)

    def get_topology_connections(self, run_id: str) -> List[Dict[str, Any]]:
        def _op(conn):
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT endpoint_a, interface_a, endpoint_b, interface_b, connection_type, speed_kbit
                FROM topology_connections WHERE run_id = ?;
                """,
                (run_id,),
            )
            return [dict(r) for r in cursor.fetchall()]

        return self._execute_with_retry(_op)

    def get_ping_tests(self, run_id: str) -> List[Dict[str, Any]]:
        def _op(conn):
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT origin, dest, tx, rx, loss_pct, min_rtt, avg_rtt, max_rtt, jitter, is_dead, is_asymmetric
                FROM ping_tests WHERE run_id = ?;
                """,
                (run_id,),
            )
            return [dict(r) for r in cursor.fetchall()]

        return self._execute_with_retry(_op)

    def get_ping_history(
        self,
        origin: str,
        dest: str,
        limit: int = 90,
    ) -> List[Dict[str, Any]]:
        def _op(conn):
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT p.run_id, r.started_at, p.origin, p.dest, p.tx, p.rx,
                       p.loss_pct, p.min_rtt, p.avg_rtt, p.max_rtt, p.jitter, p.is_dead
                FROM ping_tests p
                JOIN runs r ON p.run_id = r.run_id
                WHERE p.origin = ? AND p.dest = ?
                ORDER BY r.started_at DESC
                LIMIT ?;
                """,
                (origin, dest, limit),
            )
            rows = cursor.fetchall()
            results = []
            for r in reversed(rows):  # return chronological order
                results.append(
                    {
                        "t": r["started_at"],
                        "min": r["min_rtt"],
                        "avg": r["avg_rtt"],
                        "max": r["max_rtt"],
                        "loss": r["loss_pct"],
                        "jitter": r["jitter"],
                        "status": "dead" if r["is_dead"] else "healthy",
                    }
                )
            return results

        return self._execute_with_retry(_op)

    def get_raw_collection(
        self,
        run_id: str,
        hostname: str,
        command: str,
    ) -> Optional[str]:
        def _op(conn):
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT raw_output, is_compressed FROM raw_collections
                WHERE run_id = ? AND hostname = ? AND command = ?
                ORDER BY id DESC LIMIT 1;
                """,
                (run_id, hostname, command),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = row["raw_output"]
            if row["is_compressed"]:
                try:
                    data = zlib.decompress(data)
                except Exception as e:
                    logger.error(f"Decompression error for {hostname}/{command}: {e}")
                    return None
            if isinstance(data, bytes):
                return data.decode("utf-8", errors="replace")
            return str(data)

        return self._execute_with_retry(_op)

    def health_check(self) -> Dict[str, Any]:
        """Performs SQLite integrity check and returns table statistics."""
        def _op(conn):
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            integrity_row = cursor.fetchone()
            integrity = integrity_row[0] if integrity_row else "unknown"

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cursor.fetchall() if not r[0].startswith("sqlite_")]

            counts = {}
            for t in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {t};")
                counts[t] = cursor.fetchone()[0]

            size_bytes = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0

            return {
                "driver": "SQLiteDriver",
                "database_path": self.db_path,
                "integrity": integrity,
                "size_bytes": size_bytes,
                "size_mb": round(size_bytes / (1024 * 1024), 2),
                "journal_mode": self.journal_mode,
                "tables_count": len(tables),
                "row_counts": counts,
            }

        return self._execute_with_retry(_op)
