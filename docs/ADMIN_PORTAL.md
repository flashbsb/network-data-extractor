# 🛡️ Web Administration & Operations Portal Manual

The **Web Administration & Operations Portal** is an embedded, production-grade management application served directly by `network-data-extractor.py --serve`. It gives Network Operations Centers (NOCs) real-time visibility, telemetry summaries, cron health monitoring, and in-browser configuration management.

---

## 📑 Table of Contents
1. [Starting the Web Server](#starting-the-web-server)
2. [Cryptographic Security & RBAC](#cryptographic-security--rbac)
   - [Default Credentials](#default-credentials)
   - [Role Permissions Matrix](#role-permissions-matrix)
3. [Executive Telemetry Cockpit](#executive-telemetry-cockpit)
4. [Target Element Drilldown & Boolean Filtering](#target-element-drilldown--boolean-filtering)
5. [Cron & Automation Health Inspector](#cron--automation-health-inspector)
6. [In-Browser Configuration Management](#in-browser-configuration-management)
7. [Passive Discovery & Shadow Network](#passive-discovery--shadow-network)

---

## 🚀 Starting the Web Server

The web server is built on Python's zero-dependency `http.server.ThreadingHTTPServer`. It requires no external dependencies like Flask, Django, or Nginx.

```bash
# 1. Standard launch (binds to 127.0.0.1:8080)
python3 network-data-extractor.py --serve

# 2. Custom port and custom outbase path
python3 network-data-extractor.py --serve --port 8080 --outbase /var/network-data/infos

# 3. Network-accessible binding with custom users file
python3 network-data-extractor.py --serve --host 0.0.0.0 --port 9090 --users-file config/users.json
```

Once started, access the portal at:
```
http://localhost:8080/admin/index.html
```

---

## 🔒 Cryptographic Security & RBAC

### Security Architecture
- **PBKDF2-HMAC-SHA256 Password Hashing:** 100,000 salt iterations prevent rainbow table attacks.
- **Sliding Session Cookies:** Ephemeral 4-hour cookie (`session_id`) marked `HttpOnly; SameSite=Lax`.
- **Anti-CSRF Tokens:** All mutating `POST` and `PUT` requests require a cryptographically random `X-CSRF-Token` header.
- **Path Traversal Isolation:** Configuration and file editors enforce strict canonical path checking within authorized directories.

### Default Credentials
Upon initial launch, the system automatically initializes an administrator account:
- **Username:** `admin`
- **Password:** `admin`
- **Role:** `SuperAdmin`

> ⚠️ **Security Warning:** Change the default password immediately on first login via the user profile modal in the top navigation bar.

### Role Permissions Matrix

| Permission | SuperAdmin | NetOps | Operator | Auditor |
| :--- | :---: | :---: | :---: | :---: |
| `view_metrics` | ✅ | ✅ | ✅ | ✅ |
| `export_data` | ✅ | ✅ | ✅ | ✅ |
| `edit_config` | ✅ | ✅ | ❌ | ❌ |
| `manage_users` | ✅ | ❌ | ❌ | ❌ |
| `rebuild_index` | ✅ | ✅ | ❌ | ❌ |

---

## 📊 Executive Telemetry Cockpit

Located under the **Telemetry Overview** tab (`#pane-summary`), the cockpit provides deep point-in-time and historical health analytics:

- **Snapshot Selector (`[ 📅 Select Snapshot ▾ ]`):** Jump to any historical run to inspect SSH success rates, active nodes, and collection elapsed times.
- **Reliability & Trends HUD (6 Diagnostic Cards):**
  1. 📋 **Configured Elements:** Total managed target nodes in `elements.cfg`.
  2. ✅ **Fully Stable:** Elements achieving ≥90% collection success rate across historical snapshots.
  3. ⚡ **Flapping / Intermittent:** Elements experiencing transient reachability or authentication drops.
  4. ⚠️ **Chronic Failures:** Elements failing 100% of collection attempts.
  5. 🚫 **Never Collected:** Newly registered elements with zero historical collection runs.
  6. 🌐 **Discovered / External:** Unmanaged nodes detected via LLDP adjacencies.

---

## 🔍 Target Element Drilldown & Boolean Filtering

The target element table supports advanced boolean query syntax for rapid troubleshooting across 10,000+ nodes:

- **Operators:** `&` (AND), `|` (OR), `!` (NOT), `( )` (Grouping).
- **Field Selectors:**
  - `status:ok` or `status:fail`
  - `host:BSB-CORE`
  - `tier:CORE` or `tier:METRO`
  - `"Exact Match String"`
- **1-Click CSV Export:** Generates an Excel-ready UTF-8 BOM CSV containing filtered search results.

---

## ⏱️ Cron & Automation Health Inspector

Located under the **System Health** tab (`#pane-health`), this monitor inspects automated background runs:
- Parses `cron_execution.log` in real time.
- Calculates elapsed hours since the last completed run.
- Emits visual status badges:
  - 🟢 `HEALTHY` — Run completed within schedule window (< 24h).
  - 🟡 `DELAYED` — No run completed within expected threshold (> 96h).
  - 🔵 `RUNNING` — Active collection in progress.
  - 🔴 `ERROR` — Last collection exited with failure code.

---

## ⚙️ In-Browser Configuration Management

Located under the **Configuration Editor** tab (`#pane-config`):
- Edit `config/elements.cfg` and `config/commands.cfg` directly from the browser with syntax highlighting.
- Modify modular JSON settings (`extractor.json`, `ssh.json`, `network.json`, `ping.json`, `storage.json`).
- Built-in JSON validator catches syntax mistakes before saving.
- Automatically creates backup copies before writing changes.

---

## 📡 Passive Discovery & Shadow Network

The **Shadow Network** tab correlates LLDP adjacencies reported by managed routers against your authorized `elements.cfg` catalog:
- Automatically detects rogue leaf switches, unmanaged customer premises equipment (CPEs), and unexpected transit peerings.
- Highlights multi-attached nodes connected across multiple managed routers.
- Export discovery reports to CSV for network audit compliance.
