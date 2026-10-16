# 🚀 Quick Start Guide

Welcome to **Network Data Extractor**! This guide will take you from zero to your first multi-vendor network collection and interactive dashboard in under 5 minutes.

---

## 📋 Prerequisites

- **Python 3.8+** installed on Linux, macOS, or Windows.
- Network connectivity (SSH port 22) to your target network equipment.
- Credentials with read-only CLI privileges (e.g. `show` commands).

---

## 🛠️ Step 1: Installation

### Linux (Debian / Ubuntu / Rocky / RHEL)
Clone the repository and run the automated dependency installer:
```bash
git clone https://github.com/flashbsb/network-data-extractor.git
cd network-data-extractor
sudo ./installdep.sh
```

Alternatively, install using standard `pip`:
```bash
pip install -r requirements.txt
```

### Windows (PowerShell)
```powershell
git clone https://github.com/flashbsb/network-data-extractor.git
cd network-data-extractor
pip install -r requirements.txt
```

### Pre-flight Verification
Audit your environment and libraries before running any collection:
```bash
python3 network-data-extractor.py --check-deps
```

---

## 🎯 Step 2: Configure Your Targets

The tool requires two core configuration files located in the `config/` directory:

### 1. Target Inventory (`config/elements.cfg`)
List the network devices you want to poll. The format is `Hostname;IP_Address;ProfileKey`:

```text
# ==========================================
# Target Elements Inventory
# Format: Hostname;IP;ProfileKey
# Lines starting with # are comments
# ==========================================
CORE-ROUTER-01;10.0.0.1;cisco02
AGG-SWITCH-01;10.0.1.1;datacom01
EDGE-ROUTER-02;10.0.2.1;huawei01
# LAB-TEST-01;10.0.99.1;cisco02  <-- Ignored comment
```

### 2. Command Macros (`config/commands.cfg`)
Map vendor profiles to the CLI commands you want to execute:

```text
# ==========================================
# Vendor Command Macros
# Format: ProfileKey;CLI_Command
# ==========================================
cisco02;show version
cisco02;show ip interface brief
cisco02;show lldp neighbors detail

datacom01;show system
datacom01;show interface brief
datacom01;show lldp remote-systems

huawei01;display version
huawei01;display interface brief
huawei01;display lldp neighbor brief
```

---

## ⚡ Step 3: Run Your First Collection

### Interactive Terminal Wizard
Run without arguments to launch the step-by-step interactive wizard:
```bash
python3 network-data-extractor.py
```
The wizard will prompt you for SSH credentials, concurrency level, and optional features (Ping Matrix, Autonomous Discovery).

### Headless / Automated CLI Run
Execute directly using SSH key authentication:
```bash
python3 network-data-extractor.py \
  --skip-wizard \
  --user "nocadmin" \
  --key "~/.ssh/id_rsa"
```

Or execute using username/password prompt:
```bash
python3 network-data-extractor.py \
  --skip-wizard \
  --user "nocadmin"
```

---

## 📊 Step 4: Explore Your Results

Once the collection completes, open the central navigation portal in your browser:

```bash
# Linux
xdg-open infos/index.html

# macOS
open infos/index.html

# Windows
start infos\index.html
```

Or view it over a local lightweight web server:
```bash
python3 -m http.server 8000 --directory infos
# Open http://localhost:8000 in your browser
```

### What You Will Find in `infos/index.html`:
- 📦 **Global Inventory:** Filterable tables of all collected interfaces, IPs, operational statuses, and transceiver models.
- ⚖️ **Drift Analysis:** Instant comparison between snapshots to highlight port status changes and network drift.
- ⚡ **Ping Monitoring:** Bidirectional SLA heatmaps, latency history, and Dijkstra route calculations.
- 🕸️ **Network Topology:** Interactive Draw.io diagram layouts (Concentric, Geographic, Organic).
- 🛡️ **Admin & Operations:** (Available when running with `--serve`) Live telemetry cockpit and configuration manager.

---

## 📖 Next Steps & Deep Dives

Now that you have your first run up and running, explore the specialized guides:
- [CLI Reference Manual](CLI_REFERENCE.md) — All execution flags, Cron scheduling, and CI/CD automation.
- [Modular Configuration Guide](CONFIGURATION.md) — Deep-dive into tuning timeouts, tiers, and speed maps.
- [Database & Storage Layer](STORAGE_AND_DB.md) — SQLite WAL persistence, vacuuming, and retention.
- [Web Administration Portal](ADMIN_PORTAL.md) — Multi-user RBAC, executive cockpits, and cron monitoring.
- [System Architecture](ARCHITECTURE.md) — Pipeline internals and inter-dashboard URL parameter routing.
