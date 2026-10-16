<div align="center">
  <h1>🌐 Network Data Extractor</h1>
  <p><strong>The Ultimate Multivendor NOC Orchestrator & Autonomous Discovery Engine</strong></p>
  
  ![Version](https://img.shields.io/badge/version-1.97.2-blue.svg)
  ![Python](https://img.shields.io/badge/python-3.8%2B-green.svg)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
  [![Live Demo](https://img.shields.io/badge/Live_Demo-GitHub_Pages-0ea5e9?style=flat&logo=github)](https://flashbsb.github.io/network-data-extractor/)
</div>

<br />

> **Turn multi-vendor CLI outputs into actionable network intelligence in seconds.**  
> An asynchronous orchestration engine for Network Operations Centers (NOCs) and Network Engineers. It eliminates manual polling through high-concurrency SSH, parses unstructured CLI dumps into normalized datasets, autonomously discovers network topology, and compiles interactive, zero-dependency HTML dashboards for instant NOC diagnostics.

---

## 🌐 Live Interactive Demo (Online & Offline)

Explore the full Network Operations Center portal live in your browser without cloning or running Python:

<div align="center">
  <br />
  <a href="https://flashbsb.github.io/network-data-extractor/">
    <img src="https://img.shields.io/badge/🚀_LAUNCH_LIVE_DEMO-GitHub_Pages-38bdf8?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Launch Live Demo" />
  </a>
  <br /><br />
</div>

The bundled **[demo/](demo/)** workspace provides an authentic nationwide Brazilian backbone scenario (30 elements across Core, Aggregation, Metro Distribution, Peering, and Optical DWDM) spanning 30 days and 10 chronological snapshot collections:
- **📦 Global Inventory:** Hardware inventory, transceivers, and interface operational statuses.
- **⚖️ Drift Analysis (Diff):** Configuration drift, interface state changes, and BGP updates.
- **⚡ Ping Monitoring:** ICMP heatmaps, Chart.js 30-day degradation trends, and Dijkstra route analysis.
- **🕸️ Native Interactive Topology:** HTML5 Canvas graph with Concentric Orbital, Organic, and Site-Grouped layouts, boolean search (`&`, `|`, `!`, `()`), glowing halos, and 1-click **Draw.io (.drawio)** export.
- **🛡️ Admin & Operations:** (Available in DB mode via `--serve`) Executive health cockpit, cron monitor, and in-browser config editor.

---

## ✨ Core Superpowers

| Superpower | Why It Matters |
| :--- | :--- |
| **⚡ Massive Concurrency** | Multi-threaded SSH polling reduces network collection windows from hours to seconds across Cisco, Datacom, Huawei, and HP. |
| **🛑 Circuit Breaker** | Autonomous fail-fast engine halts collection on consecutive auth errors or disconnects, preventing TACACS/AD account lockouts. |
| **🗄️ SQLite WAL Storage** | Enterprise Storage Abstraction Layer (SAL) supporting `files_only`, `hybrid`, and `db_only` modes with sub-5ms in-memory query caching. |
| **🧭 Autonomous Discovery** | Recursively follows LLDP neighbors up to *N* hops, discovering missing devices and generating new inventory targets dynamically. |
| **📊 Zero-CORS Dashboards** | Local-First Single Page Applications (SPAs) embedded in HTML. Opens in any browser via `file:///` without CORS issues or web servers. |
| **🎨 Tri-Theme System** | One-click instant switching between **Dark (NOC Obsidian)**, **Light (Enterprise Clean)**, and **HighText (WCAG AAA)**. |

---

## ⚡ 3-Step Quick Start

Get up and running with your first network extraction in under 3 minutes:

### 1. Install Dependencies
```bash
git clone https://github.com/flashbsb/network-data-extractor.git
cd network-data-extractor

# Linux (Debian / Ubuntu / RHEL)
sudo ./installdep.sh

# Or cross-platform via pip
pip install -r requirements.txt
```

### 2. Define Targets (`config/elements.cfg`)
Add your network devices using `Hostname;IP;ProfileKey`:
```text
CORE-ROUTER-01;10.0.0.1;cisco02
AGG-SWITCH-01;10.0.1.1;datacom01
EDGE-ROUTER-01;10.0.2.1;huawei01
```

### 3. Run & View Results
```bash
# Run collection with SSH key authentication
python3 network-data-extractor.py --skip-wizard --user "nocadmin" --key "~/.ssh/id_rsa"

# Open the central navigation portal
xdg-open infos/index.html   # Linux
open infos/index.html       # macOS
start infos\index.html      # Windows
```

---

## 🖥️ The 5 Unified Workspaces

Every collection run automatically compiles 5 specialized diagnostic workspaces accessible from the master Root Portal (`infos/index.html`):

```
┌────────────────────────────────────────────────────────────────────────┐
│                      🏠 ROOT NAVIGATION PORTAL                        │
│                         (infos/index.html)                             │
└───────┬──────────────┬───────────────┬───────────────┬─────────────────┘
        │              │               │               │
        ▼              ▼               ▼               ▼
   📦 INVENTORY    ⚖️ DRIFT        ⚡ ICMP MATRIX   🕸️ TOPOLOGY
   Global ports,  Configuration   SLA heatmaps,   Interactive Canvas,
   transceivers,  drift & delta   history trends, boolean search &
   and inventory  event timelines Dijkstra path  Draw.io export
        │              │               │               │
        └──────────────┴───────┬───────┴───────────────┘
                               │ (When served in DB Mode)
                               ▼
                    🛡️ ADMIN & OPERATIONS
                    Executive telemetry cockpit, cron monitor,
                    RBAC security & in-browser config editor
```

---

## 📚 Documentation Directory

For in-depth guides, operational procedures, and developer blueprints, refer to the dedicated manuals:

| Guide | Description |
| :--- | :--- |
| 🚀 **[Quick Start Guide](docs/QUICKSTART.md)** | Step-by-step onboarding tutorial from installation to your first collection. |
| 🛠️ **[CLI Reference Manual](docs/CLI_REFERENCE.md)** | Exhaustive manual of all execution modes [A]-[I], CLI flags, and Cron automation. |
| ⚙️ **[Configuration Architecture](docs/CONFIGURATION.md)** | Deep dive into `config/*.json`, inventory syntax, regex rules, and merge precedence. |
| 🗄️ **[Database & Storage Layer](docs/STORAGE_AND_DB.md)** | SQLite WAL persistence, CLI `storage_manager.py`, backup, retention, and vacuuming. |
| 🛡️ **[Web Administration Portal](docs/ADMIN_PORTAL.md)** | Embedded server (`--serve`), RBAC roles, security, cron inspector, and config editor. |
| 🏗️ **[System Architecture](docs/ARCHITECTURE.md)** | Internal 7-layer pipeline blueprints, inter-dashboard URL routing, and SPA model. |

---

## 🤝 Ecosystem & Related Tools

Expand your automation suite with related NOC tools:
- [Network Topology Generator](https://github.com/flashbsb/network-topology-generator) — Generate physical topology visualizations dynamically.
- [Backbone Network Topology Generator](https://github.com/flashbsb/backbone-network-topology-generator) — Dimension and simulate backbone topologies.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
