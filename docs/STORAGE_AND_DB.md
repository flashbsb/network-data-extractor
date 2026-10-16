# 🗄️ Database & Storage Layer Manual

Starting in **v1.95.0**, the **Network Data Extractor** includes an enterprise-grade **Storage Abstraction Layer (SAL)**. It combines the reliability of zero-dependency SQLite with high-concurrency Write-Ahead Logging (`WAL`), sub-millisecond in-memory caching, and seamless fallback to disk.

---

## 📑 Table of Contents
1. [The Three Persistence Modes](#the-three-persistence-modes)
2. [SQLite Engine Architecture](#sqlite-engine-architecture)
3. [Database Schema Overview](#database-schema-overview)
4. [Storage Manager CLI (`tools/storage_manager.py`)](#storage-manager-cli-toolsstorage_managerpy)
5. [Automated Retention & Database Vacuuming](#automated-retention--database-vacuuming)
6. [DB-Primary Web Acceleration](#db-primary-web-acceleration)

---

## 🔄 The Three Persistence Modes

Configure the active persistence strategy in `config/storage.json` or pass `--storage-mode <mode>` on the command line:

| Mode | Description | Use Case |
| :--- | :--- | :--- |
| **`files_only`** | Legacy pure filesystem mode. Writes raw `.txt` CLI logs, `.csv` and `.json` spreadsheets, and flat HTML portals. Zero database overhead. | Portable air-gapped environments, GitHub Pages demos, and minimal disk writes. |
| **`hybrid`** *(Default)* | Concurrent dual persistence. Persists to both the filesystem (`runs/`) and SQLite database simultaneously. | Production NOCs needing raw text audit logs alongside instant web query speeds. |
| **`db_only`** | Maximum density mode. All interfaces, metrics, logs, and ping sweeps are ingested directly into SQLite. Reclaims raw disk inodes. | High-frequency polling (e.g. every 15 mins) and large topologies (10,000+ nodes). |

---

## ⚡ SQLite Engine Architecture

The SQLite engine (`core/storage/sqlite_driver.py`) is tuned for zero-lock concurrency:

- **Write-Ahead Logging (`PRAGMA journal_mode = WAL;`):** Readers never block writers, and writers never block readers. Background collections ingest data while the web server serves reports simultaneously.
- **Normal Synchronization (`PRAGMA synchronous = NORMAL;`):** Balances ACID safety with high-throughput batch inserts.
- **64 MB RAM Cache (`PRAGMA cache_size = -64000;`):** Keeps B-tree indices in memory, allowing 100,000+ interface queries in under 5ms.
- **In-Memory Temporary Storage (`PRAGMA temp_store = MEMORY;`):** Eliminates disk I/O bottlenecks for complex relational joins.

---

## 📊 Database Schema Overview

The database (`infos/ndx_telemetry.db` by default) contains 7 relational tables:

```
┌────────────────────────────────────────────────────────┐
│                   elements                             │
│ (hostname, ip, profile, tier, site, vendor, model, os) │
└──────────────────────────┬─────────────────────────────┘
                           │ 1:N
┌──────────────────────────▼─────────────────────────────┐
│                      runs                              │
│ (run_id, timestamp, duration, total_nodes, status)     │
└──────┬───────────────────┬───────────────────┬─────────┘
       │ 1:N               │ 1:N               │ 1:N
┌──────▼─────────┐  ┌──────▼─────────┐  ┌──────▼─────────┐
│   interfaces   │  │   ping_tests   │  │  connections   │
│ (oper, admin,  │  │ (rtt_avg, loss,│  │ (local_port,   │
│  speed, vrf)   │  │  jitter, sla)  │  │  remote_port)  │
└────────────────┘  └────────────────┘  └────────────────┘
```

- **`elements`**: Master catalog of all managed and discovered network targets.
- **`runs`**: Execution metadata, timestamps, and overall collection health status.
- **`interfaces`**: Complete interface census (operational states, admin states, IP/mask, descriptions).
- **`ping_tests`**: Bidirectional SLA latency, packet loss, and jitter telemetry.
- **`connections`**: Deduplicated physical and logical L2/L3 topology links.
- **`lldp_neighbors`**: Raw and parsed discovery adjacencies for passive shadow network analysis.
- **`system_metrics`**: CPU, memory, power supply, and environmental telemetry.

---

## 🛠️ Storage Manager CLI (`tools/storage_manager.py`)

A standalone CLI tool is provided to manage the database lifecycle without running network collections:

### 1. Initialize Schema & Seed Inventory
```bash
python3 tools/storage_manager.py init
```

### 2. Ingest Historical Flat File Runs into SQLite
Import existing timestamped folders (`runs/20*_*`) into the database:
```bash
python3 tools/storage_manager.py import
```

### 3. Export Snapshot from Database to Disk
Recreate CSV/JSON files on disk from an SQLite snapshot:
```bash
python3 tools/storage_manager.py export --run 20261014_140000
```

### 4. Audit Database Integrity & Health
Performs deep row counting, index checking, and foreign key verification:
```bash
python3 tools/storage_manager.py audit --deep-verify
```

### 5. Create Transactional Compressed Backup
Safely creates a consistent `.tar.gz` snapshot while the system is live:
```bash
python3 tools/storage_manager.py backup
```

### 6. Purge Obsolete Runs & Reclaim Disk Space
```bash
python3 tools/storage_manager.py purge --max-runs 60
```

---

## 🧹 Automated Retention & Database Vacuuming

Retention is controlled in `config/storage.json`:
- **Sliding-Window Pruning:** Automatically deletes snapshots older than `max_days` or exceeding `max_runs`.
- **Auto-Vacuum:** Automatically triggers SQLite `VACUUM` when deleted row volume exceeds threshold, returning reclaimed disk blocks to the host operating system.

---

## 🚀 DB-Primary Web Acceleration

When serving dashboards via the embedded web server (`--serve`), requests to `/api/v1/summary`, `/api/v1/runs`, and interactive tables query SQLite first:
- **Query Latency:** Decreased from ~850ms (flat file parsing) to **< 15ms** (SQLite indexed queries).
- **Graceful Fallback:** If an older run directory exists on disk but was never imported into the database, the server dynamically falls back to parsing filesystem files without error.
