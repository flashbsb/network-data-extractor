# ⚙️ Configuration Architecture Manual

Starting in **v1.91.0**, the Network Data Extractor decomposed monolithic settings into dedicated, domain-specific configuration files under the `config/` directory. This modular approach eliminates hardcoded values and enables clear separation of concerns.

---

## 📑 Table of Contents
1. [Core Text Inventories](#core-text-inventories)
   - [`config/elements.cfg` (Targets)](#configelementscfg-targets)
   - [`config/commands.cfg` (CLI Commands)](#configcommandscfg-cli-commands)
2. [Modular JSON Domain Files](#modular-json-domain-files)
   - [`config/extractor.json` (Polling Engine)](#configextractorjson-polling-engine)
   - [`config/ssh.json` (SSH & Protocol Layer)](#configsshjson-ssh--protocol-layer)
   - [`config/network.json` (Topology & Hierarchy)](#confignetworkjson-topology--hierarchy)
   - [`config/ping.json` (ICMP & SLA Thresholds)](#configpingjson-icmp--sla-thresholds)
   - [`config/storage.json` (Database & Retention)](#configstoragejson-database--retention)
3. [Deep-Merge Precedence & Backward Compatibility](#deep-merge-precedence--backward-compatibility)
4. [Validating Configuration Integrity](#validating-configuration-integrity)

---

## 📋 Core Text Inventories

### `config/elements.cfg` (Targets)
Defines the target nodes to be polled.
- **Syntax:** `Hostname;IP_Address;ProfileKey`
- Lines starting with `#` or empty lines are ignored as comments.

```text
# ==========================================
# Target Elements Inventory
# ==========================================
# Syntax: Hostname;IP;ProfileKey
BR-DF-BSB-CORE-01;10.100.0.1;cisco02
BR-SP-SPO-AGG-01;10.100.1.1;datacom01
BR-RJ-RIO-EDGE-01;10.100.2.1;huawei01
# LAB-ELEMENT;10.100.99.1;cisco02  <-- Commented out
```

### `config/commands.cfg` (CLI Commands)
Defines the sequence of `show` commands dispatched per profile:
- **Syntax:** `ProfileKey;CLI_Command`

```text
# Cisco IOS / IOS-XR
cisco02;terminal length 0
cisco02;show version
cisco02;show ip interface brief
cisco02;show lldp neighbors detail

# Datacom DmOS
datacom01;show system
datacom01;show interface brief
datacom01;show lldp remote-systems

# Huawei VRP
huawei01;screen-length 0 temporary
huawei01;display version
huawei01;display interface brief
huawei01;display lldp neighbor brief
```

---

## 🗂️ Modular JSON Domain Files

### `config/extractor.json` (Polling Engine)
Controls concurrent thread pooling, command pacing, and recursive discovery:

```json
{
  "workers": 30,
  "command_timeout": 35.0,
  "per_command_delay": 0.35,
  "connect_timeout": 15.0,
  "discovery": {
    "default_hops": 2,
    "max_hops": 5,
    "preferred_management_subnets": [
      "10.0.0.0/8",
      "172.16.0.0/12"
    ]
  }
}
```

### `config/ssh.json` (SSH & Protocol Layer)
Manages SSH cryptographic negotiation, shell banners, and terminal pager markers:

```json
{
  "auth_timeout": 20.0,
  "banner_timeout": 20.0,
  "retries": 2,
  "retry_delay": 3.0,
  "keepalive_interval": 15,
  "pager_markers": [
    "--More--",
    "---- More ----",
    "<--- More --->",
    "Press any key to continue"
  ],
  "prompt_regex": "[#>$]\\s*$"
}
```

### `config/network.json` (Topology & Hierarchy)
Defines network hierarchy tiers, link speed inferences, transceiver classifications, and Draw.io visual colors:

```json
{
  "routing_hierarchy": {
    "tiers": ["CORE", "AGGREGATION", "METRO", "ACCESS", "EDGE", "PEERING"]
  },
  "tier_metadata": {
    "CORE": { "rank": 1, "color": "#ef4444", "shape": "hexagon" },
    "AGGREGATION": { "rank": 2, "color": "#f59e0b", "shape": "square" },
    "METRO": { "rank": 3, "color": "#06b6d4", "shape": "roundrectangle" },
    "ACCESS": { "rank": 4, "color": "#10b981", "shape": "ellipse" }
  },
  "interface_speed_inference": {
    "^TenGigE|^Ten-Gigabit|^XGigabitEthernet": 10000,
    "^HundredGigE|^100GE": 100000,
    "^FortyGigE|^40GE": 40000
  },
  "speed_colors": {
    "100G": "#ef4444",
    "40G": "#f59e0b",
    "10G": "#06b6d4",
    "1G": "#10b981"
  }
}
```

### `config/ping.json` (ICMP & SLA Thresholds)
Configures ICMP sweep parameters, SLA degradation coloring, and architecture matrix rules:

```json
{
  "mode": "selective",
  "packet_count": 5,
  "packet_size": 64,
  "timeout": 2.0,
  "canvas_sla_thresholds": {
    "latency_excellent_ms": 10.0,
    "latency_good_ms": 30.0,
    "latency_warning_ms": 60.0,
    "loss_warning_pct": 2.0,
    "loss_critical_pct": 10.0
  },
  "architecture_matrix": {
    "CORE": ["CORE", "AGGREGATION", "PEERING"],
    "AGGREGATION": ["CORE", "AGGREGATION", "METRO"],
    "METRO": ["AGGREGATION", "ACCESS"],
    "ACCESS": ["METRO"]
  }
}
```

### `config/storage.json` (Database & Retention)
Configures persistence backend modes, SQLite relational parameters, and automated sliding-window pruning:

```json
{
  "mode": "hybrid",
  "database_path": "infos/ndx_telemetry.db",
  "wal_mode": true,
  "cache_size_mb": 64,
  "retention": {
    "global": {
      "max_collections": 30,
      "max_days": 30
    },
    "ping_history": {
      "auto_purge_out_of_scope": true
    },
    "components": {
      "collect": { "max_collections": 30, "max_days": 30 },
      "resume": { "max_collections": 30, "max_days": 30 },
      "connections": { "max_collections": 30, "max_days": 30 }
    }
  }
}
```

---

## 🔄 Deep-Merge Precedence & Backward Compatibility

The configuration loader (`core/utils_shared.py`) enforces deterministic deep-merge precedence:

1. **Domain-Specific Files (`config/*.json`):** If present, individual domain files (`extractor.json`, `ssh.json`, etc.) take top precedence.
2. **Legacy `config/settings.json`:** If legacy keys exist in `settings.json` or a custom file passed via `--settings`, they are safely deep-merged.
3. **Internal Hardcoded Defaults:** Any omitted keys seamlessly fall back to safe built-in defaults.

---

## 🧪 Validating Configuration Integrity

Run the built-in configuration audit tool before deploying new changes to production:

```bash
python3 tools/test_modular_configs.py
```
This tests JSON syntax, key types, range validation, and verify backward compatibility.
