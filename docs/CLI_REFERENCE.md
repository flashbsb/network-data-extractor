# 🛠️ Command-Line Interface (CLI) Reference

The **Network Data Extractor** is built for extreme automation, headless server deployments, and seamless integration into scheduled Cron jobs or CI/CD pipelines.

---

## 📑 Table of Contents
1. [General Syntax & Global Flags](#general-syntax--global-flags)
2. [Execution Modes [A] - [I]](#execution-modes)
   - [[A] Standard Live Polling & Topology](#a-standard-live-polling--topology)
   - [[B] Ping Matrix & ICMP Diagnostics](#b-ping-matrix--icmp-diagnostics)
   - [[C] Autonomous LLDP Discovery](#c-autonomous-lldp-discovery)
   - [[D] Offline Workspace & Dashboard Generation](#d-offline-workspace--dashboard-generation)
   - [[E] Offline Re-parsing](#e-offline-re-parsing)
   - [[F] Environment Pre-flight Diagnostics](#f-environment-pre-flight-diagnostics)
   - [[G] Data Retention & Storage Pruning](#g-data-retention--storage-pruning)
   - [[H] Enterprise Storage & SQLite Database](#h-enterprise-storage--sqlite-database)
   - [[I] Web Administration Server (`--serve`)](#i-web-administration-server---serve)
3. [Circuit Breaker Protection](#circuit-breaker-protection)
4. [Production Cron & Scheduling Automation](#production-cron--scheduling-automation)

---

## ⚙️ General Syntax & Global Flags

```bash
python3 network-data-extractor.py [OPTIONS]
```

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--skip-wizard` | Flag | `False` | Bypasses the interactive terminal wizard and proceeds immediately with CLI arguments. |
| `--user` | String | Prompted | SSH username for authentication across target devices. |
| `--key` | Path | `None` | Path to private SSH key file (e.g. `~/.ssh/id_rsa`). |
| `--outbase` | Path | `infos/` | Base directory where all runs, datasets, and static portals are written. |
| `--config-dir` | Path | `config/` | Path containing `elements.cfg`, `commands.cfg`, and domain JSON configurations. |
| `--settings` | Path | `config/settings.json` | Path to legacy monolithic settings file (deep-merged with modular JSONs). |
| `--workers` | Integer | `30` | Maximum parallel worker threads for concurrent SSH connections. |
| `--check-deps` | Flag | `False` | Audits system Python packages and exits immediately with status report. |

---

## 🚀 Execution Modes

### [A] Standard Live Polling & Topology
Performs massive, concurrent SSH extraction across the inventory, generates CSV spreadsheets, and builds L2/L3 topology maps:
```bash
python3 network-data-extractor.py \
  --skip-wizard \
  --user "nocadmin" \
  --key "~/.ssh/id_rsa" \
  --workers 40
```

### [B] Ping Matrix & ICMP Diagnostics
Performs an automated bidirectional ICMP sweep between network elements, applying architecture-aware filtering rules (`mode: "selective"`) to prevent non-routable traffic:
```bash
python3 network-data-extractor.py \
  --skip-wizard \
  --ping-matrix \
  --ping-commands config/commands.icmp.cfg \
  --ping-format html
```
- Outputs interactive heatmaps, latency SLA metrics, and peer-to-peer history files inside `runs/YYYYMMDD_HHMMSS/ping-matrix/`.

### [C] Autonomous LLDP Discovery
Instructs the engine to recursively inspect LLDP neighbor tables up to `N` hops, automatically mapping unmanaged devices and appending newly found IPs to subsequent collection iterations:
```bash
python3 network-data-extractor.py \
  --skip-wizard \
  --discovery \
  --hops 3
```

### [D] Offline Workspace & Dashboard Generation
Re-compiles or refreshes HTML dashboards from previously collected historical snapshots without logging into network equipment:
```bash
# Generate cumulative global inventory dashboard across all existing runs
python3 network-data-extractor.py --inventory

# Generate snapshot drift comparison dashboard (port status and bandwidth delta)
python3 network-data-extractor.py --diff

# Complete rebuild: regenerates Root Portal, Ping Matrix, Inventory, Diff, and Topology
python3 network-data-extractor.py --rebuild-index
```

### [E] Offline Re-parsing
Re-runs the parsing pipeline over raw CLI text dumps from an existing run directory (ideal when updating parser regexes or fixing device definitions):
```bash
python3 network-data-extractor.py --offline infos/20261014_140000
```

### [F] Environment Pre-flight Diagnostics
Validates that required system dependencies, cryptographic libraries (`paramiko`, `cryptography`), and analytical packages (`pandas`) are functional:
```bash
python3 network-data-extractor.py --check-deps
```

### [G] Data Retention & Storage Pruning
Enforces historical retention windows, removes obsolete snapshots, and cleans up orphaned telemetry link records:
```bash
# 1. Enforce 30-day retention on live collection run
python3 network-data-extractor.py --skip-wizard --retention-days 30

# 2. Standalone run archiver & snapshot pruner
python3 tools/manage_runs_retention.py --days 30 --apply

# 3. Standalone ICMP history link sanitizer (cleans out-of-scope link files)
python3 tools/sanitize_history.py --apply
```

### [H] Enterprise Storage & SQLite Database
Switches the storage persistence model between flat files, SQLite relational database, or both (hybrid):
```bash
# Run with Hybrid Storage (persists to filesystem and SQLite concurrently)
python3 network-data-extractor.py --storage-mode hybrid

# Run with Database-Only Storage (stores in SQLite and reclaims disk inodes)
python3 network-data-extractor.py --storage-mode db_only

# Interactive setup wizard
python3 tools/setup_database.py

# Non-interactive automated setup
python3 tools/setup_database.py -y
```

#### Dedicated CLI Storage Utilities (`tools/storage_manager.py`)
```bash
python3 tools/storage_manager.py init                 # Initialize SQLite schema and seed inventory
python3 tools/storage_manager.py import               # Ingest legacy flat runs into SQLite
python3 tools/storage_manager.py export --run <RUN>   # Export snapshot from DB to filesystem
python3 tools/storage_manager.py sync                 # Bidirectional sync between disk and database
python3 tools/storage_manager.py audit --deep-verify  # Deep database consistency verification
python3 tools/storage_manager.py backup               # Create compressed snapshot backup archive
python3 tools/storage_manager.py purge --max-runs 60  # Retain last 60 runs and vacuum database
```

### [I] Web Administration Server (`--serve`)
Launches the embedded, zero-dependency HTTP server hosting the authenticated Web Administration and Operations Portal:
```bash
# Launch with default settings (bind localhost, port 8080)
python3 network-data-extractor.py --serve

# Custom port and outbase directory
python3 network-data-extractor.py --serve --port 8080 --outbase /var/network-data/infos

# Remote access binding and custom user credentials database
python3 network-data-extractor.py --serve --host 0.0.0.0 --port 9090 --users-file config/users.json
```

---

## 🛑 Circuit Breaker Protection

To protect network infrastructure against cascading authentication failures and prevent account lockouts (e.g. TACACS+, RADIUS, Active Directory), the engine includes an autonomous **Systemic Failure Circuit Breaker**:

- **Authentication Failure Threshold:** Halts automatically if **10 consecutive** authentication errors occur.
- **Unreachability Threshold:** Halts automatically if **20 consecutive** hosts are unreachable (e.g. routing outage or VPN disconnect).
- **Exit Code `101`:** Emits exit code `101` immediately upon trip, suppressing downstream alert storms and outputting structured diagnostics.
- **Manual Override:** For intentional stress-testing or broken lab environments, bypass via:
  ```bash
  python3 network-data-extractor.py --ignore-circuit-breaker
  ```

---

## ⏱️ Production Cron & Scheduling Automation

For unattended operations, configure a Linux cron job:

```bash
# Open crontab editor
crontab -e

# Run standard collection every 6 hours
0 */6 * * * cd /opt/network-data-extractor && python3 network-data-extractor.py --skip-wizard --user "nocadmin" --key "/root/.ssh/id_rsa" --retention-days 30 >> /var/log/ndx_cron.log 2>&1

# Run daily at 02:00 AM with ICMP Ping Matrix sweep
0 2 * * * cd /opt/network-data-extractor && python3 network-data-extractor.py --skip-wizard --user "nocadmin" --key "/root/.ssh/id_rsa" --ping-matrix --ping-commands config/commands.icmp.cfg >> /var/log/ndx_icmp.log 2>&1
```

A production template script is also available at [`tools/run_cron_template.sh`](../tools/run_cron_template.sh).
