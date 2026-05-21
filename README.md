<div align="center">
  <h1>🌐 Network Data Extractor</h1>
  <p><strong>The Ultimate Multivendor NOC Orchestrator & Autonomous Discovery Engine</strong></p>
  
  ![Version](https://img.shields.io/badge/version-1.59.5-blue.svg)
  ![Python](https://img.shields.io/badge/python-3.8%2B-green.svg)
</div>

<br />

## 📖 What is the Network Data Extractor?

**Network Data Extractor** is a high-performance, asynchronous orchestration engine designed for Network Operations Centers (NOCs) and Network Engineers. It eliminates manual polling by performing massive, parallel SSH data extraction across multi-vendor topologies (Cisco, Datacom, Huawei, HP).

Beyond simple command execution, it acts as an **intelligence layer**—parsing raw CLI outputs into structured CSV datasets, automatically mapping L2/L3 topologies, detecting network drifts, and generating fully portable, interactive HTML dashboards for instant NOC diagnostics.

---

## ⚡ Core Capabilities & Power

- **🚀 Massive Concurrency**: Multi-threaded SSH polling reduces collection windows from hours to seconds.
- **🧭 Autonomous LLDP Discovery**: Recursively hops through the network, discovering missing devices and generating new inventory targets on the fly.
- **🧩 Universal Multivendor Parsing**: Regex-based "Blind Analyzer" bypasses human typos in descriptions to seamlessly map logical and physical topologies across different vendors.
- **📊 Local-First Dashboards**: Generates High-Performance SPAs (Single Page Applications) embedded directly in HTML. Works 100% offline without CORS issues.
- **🔍 Network Drift Analysis**: Instantly compares historical snapshots to detect port status changes, bandwidth variations, and missing links.
- **🛡️ Intelligent ICMP Diagnostics**: The *Ping Matrix* engine calculates latency, jitter, asymmetric routing, and highlights isolated nodes in a visual heatmap.
- **⚠️ Topology Fault Isolation**: Actively maps connection failures, proactively warning the operator when a router loses its logical LLDP adjacencies.

---

## 🏗️ Operational Architecture

The orchestrator operates through five distinct modular branches, designed to handle everything from live extraction to offline post-mortem analysis:

```mermaid
graph TD
    %% Styling Definitions
    classDef engine fill:#2563eb,stroke:#1e3a8a,stroke-width:2px,color:#fff,rx:10,ry:10;
    classDef branch fill:#7c3aed,stroke:#4c1d95,stroke-width:2px,color:#fff,rx:10,ry:10;
    classDef storage fill:#059669,stroke:#064e3b,stroke-width:2px,color:#fff,rx:5,ry:5;
    classDef module fill:#d97706,stroke:#92400e,stroke-width:2px,color:#fff;
    classDef web fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#38bdf8,rx:10,ry:10;
    classDef csv fill:#475569,stroke:#1e293b,stroke-width:1px,color:#94a3b8;

    %% Entry Point
    START["🚀 CLI / WIZARD"]:::engine --> MODE{EXECUTION MODE}:::branch

    subgraph "STANDARD EXTRACTION [A] & DISCOVERY [C]"
        MODE -->|"--discovery"| DISCO[Discovery Loop]:::module
        DISCO --> SSH
        MODE -->|"Standard (Default)"| SSH[Multithreaded SSH Engine]:::engine
        SSH --> RAW[("📁 collect/RAW_LOGS")]:::storage
    end

    subgraph "OFFLINE PARSING [E]"
        MODE -->|"--offline DIR"| RAW
        RAW --> PARSE{Data Parsers}:::module
        PARSE --> CSV_INT["📄 interfaces_all.csv"]:::csv
        PARSE --> CSV_LLDP["📄 lldp_neighbors.csv"]:::csv
        PARSE --> CSV_STAT["📄 status.elements.csv"]:::csv
        
        CSV_INT & CSV_LLDP & CSV_STAT --> TOPO[Topology Checker]:::module
        TOPO --> CSV_WARN["📄 topology_warnings.csv"]:::csv
    end

    subgraph "PING MATRIX [B]"
        MODE -->|"--ping-matrix"| ICMP[ICMP Diagnostic Motor]:::engine
        ICMP --> PING_RES[("📁 resume/PING_DATA")]:::storage
        PING_RES --> PING_HTML{{"📲 ping_matrix_dashboard.html"}}:::web
    end

    subgraph "WORKSPACE MODES [D]"
        MODE -->|"--inventory"| INV_GEN[Global Inventory Builder]:::module
        CSV_WARN -.->|"Auto-trigger"| INV_GEN
        INV_GEN --> INV_HTML{{"📲 inventory/index.html"}}:::web

        MODE -->|"--diff"| DIFF_GEN[Drift Analysis Engine]:::module
        DIFF_GEN --> DIFF_HTML{{"📲 diff/index.html"}}:::web

        MODE -->|"--rebuild-index"| PM_GEN[Master Index Generator]:::module
        PING_HTML -.->|"Auto-trigger"| PM_GEN
        PM_GEN --> PM_HTML{{"🌐 infos/ping-matrix/index.html"}}:::web
    end

    %% Link styles
    linkStyle default stroke:#64748b,stroke-width:1px;
```

---

## 🚀 Quick Start

### 1. Requirements & Installation
Ensure you have Python 3.8+ installed.

**Linux (Debian/Ubuntu):**
```bash
sudo ./installdep.sh
python3 network-data-extractor.py
```

**Windows (PowerShell Admin):**
```powershell
pip install pandas paramiko
python network-data-extractor.py
```

### 2. Core Configuration Files (`config/`)
The tool relies on two primary configuration files:

- **`elements.cfg`** (The targets list). Syntax: `Hostname;IP;ProfileKey`
  ```text
  CORE-ROUTER-A;10.0.0.1;cisco02
  EDGE-SW-01;10.0.50.22;datacom01
  ```

- **`commands.cfg`** (The SSH macros assigned). Syntax: `ProfileKey;Command`
  ```text
  cisco02;show int status
  cisco02;show lldp neighbors detail
  datacom01;show system
  ```

*(Note: Global behaviors, regex topology patterns, and authentication fallback configurations are safely managed in `config/settings.json`)*

---

## 🛠️ Execution Modes

You can run the orchestrator interactively via the terminal wizard, or fully automate it via CLI flags (perfect for CI/CD or Cron jobs).

### [A] Standard Extraction (Live Data & Topology)
Performs live multithreaded SSH polling and generates the base CSV tables and L2/L3 topology maps.
```bash
python3 network-data-extractor.py --skip-wizard --user "nocadmin" --key "~/.ssh/id_rsa"
```

### [B] Ping Matrix Diagnostics
Bypasses standard parsing to execute a bidirectional ICMP sweep, generating an interactive offline heatmap to detect routing issues.
```bash
python3 network-data-extractor.py --ping-matrix --ping-commands config/commands.icmp.cfg --ping-format html
```

### [C] Autonomous Discovery
Tells the engine to automatically follow LLDP neighbors for `N` hops, mapping uncharted territories and identifying new IP targets.
```bash
python3 network-data-extractor.py --discovery --hops 3
```

### [D] Workspace Generation (Offline Analytics)
Re-processes historical snapshots to generate comparative UI dashboards without logging into the live network.
```bash
python3 network-data-extractor.py --diff                 # Detects drift between two snapshots
python3 network-data-extractor.py --inventory            # Builds a cumulative global inventory UI
python3 network-data-extractor.py --rebuild-index        # Rebuild all dashboards (Root, Ping Matrix, Inventory, Diff) in the outbase using existing data.
```

### [E] Offline Parsing
If you have already collected raw data and simply want to rerun the parsing stack against an existing folder.
```bash
python3 network-data-extractor.py --offline infos/20261231_235959
```

---

## 📂 Output Directory Structure

Every run is securely encapsulated in an isolated, timestamped folder (`infos/YYYYMMDD_HHMMSS/`). If configured, the engine performs automatic post-execution zip compression to save disk space.

* `collect/` → Raw `.txt` logs directly from the equipment (Audit Proof).
* `resume/` → Clean, actionable `.csv` datasets (Interfaces, Licensing, Asset Matrix, Modules).
* `connections/` → Mathematically deduplicated L2/L3 physical topology links (`topology.connections.csv`).
* `log/` → Full audit trails of the execution and parsing errors.

At the root of the output base, you will find special portals like `infos/ping-matrix/index.html` acting as chronological side-bars to navigate past Dashboard reports.

---

## 🤝 Ecosystem & Related Tools

Expand your automation suite with related NOC tools:
- [Network Topology Generator](https://github.com/flashbsb/network-topology-generator) - Generate physical topology visualisations dynamically.
- [Backbone Network Topology Generator](https://github.com/flashbsb/backbone-network-topology-generator) - Dimension backbone topologies for testing.
