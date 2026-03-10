# Changelog

All notable changes to the **Network Data Extractor** project will be documented in this file.
 
## [1.36.0] - 2026-03-10
### Added
- **Discovery Intelligence**: The discovery process now distinguishes between "Success" and "Discovery" states.
    - Nodes that failed to connect in one hop can be retried in the next hop if **new management IPs** are found.
    - Nodes already successfully connected (`successful_keys.csv`) are automatically skipped to avoid redundant work.
- **Cumulative Reporting**: The `discovered_elements.csv` report is now cumulative across all hops, aggregating all unique IPs and discovery sources found during the entire run.
- **Improved Deduplication**: Original seed nodes (Hop 0) are strictly protected and never re-added to discovery, ensuring a clean "delta" output.
- **Source Aggregation**: Multiple sources for the same discovered node are consolidated in the final reports.

## [1.35.0] - 2026-03-09
### Added
- **Discovery Source Tracking**: The Discovery process now tracks which node(s) reported a specific neighbor. 
- **New CSV Column**: Added `discovered_by` to the `discovered_elements.csv` report in the `resume/` directory.
### Fixed
- **Robust IP Extraction**: Refined the LLDP parser's regex to be more robust with variations in indentation and labels for management addresses (`IPv4 address`, `IP address`, `IP`, `IPv4`).
- **IP Aggregation**: Improved the logic to correctly aggregate multiple management IPs for the same node even when discovered from multiple different sources.
- **Reporting Consistency**: Internal sorting of IPs and sources in the final reports for better auditability.

## [1.34.1] - 2026-03-09
### Fixed
- **Clean Output (Discovery)**: The orchestrator now skips the creation of the `connections` folder when running in `--discovery` mode, as it is non-essential.
- **Intermediate File Management**: Discovery hop files (`discovery_hop_X.elements.cfg`) are now stored within the `resume/` subdirectory instead of the output root, keeping the top-level cleaner.
### Added
- **Hostname Formatting**: Added `hostname_format` setting to `settings.json` (options: `simple`, `fqdn`). This allows controlling whether discovered nodes use their short names or full domain names (default is `simple`).

## [1.34.0] - 2026-03-09
### Changed
- **Relocated Success Reports**: Moved `successful_keys.csv` from the raw data directory (`collect/`) to the summary directory (`resume/`) to keep `collect/` exclusively for raw command outputs.
- **Improved Discovery Reporting**: `discovery.py` now generates a structured `discovered_elements.csv` report in the `resume/` directory, detailing hostnames, discovered IPs, and fallback keys for each hop.

## [1.33.1] - 2026-03-09
### Fixed
- **Hostname Normalization**: Implemented `normalize_hostname` in `discovery.py` to correctly deduplicate FQDN vs short hostnames during discovery.
- **Robust IP Extraction**: Improved the LLDP parser to capture management IPs across different indentation levels and labels (e.g., "Management Addresses" block).
- **Multi-IP Aggregation**: Discovery now aggregates all reachable IPs found for a single node, ensuring better fallback availability.

## [1.33.0] - 2026-03-09
### Added
- **Multi-IP Discovery Support**: The discovery process now exports all valid IPs found for a node (separated by `|`). The orchestrator then attempts to connect to each IP sequentially until a successful session is established. This significantly increases discovery success rates by trying alternative interfaces (e.g., physical vs. loopback) if the primary one fails.

## [1.32.0] - 2026-03-09
### Added
- **Discovery Optimization Mode**: When `--discovery` is enabled, the orchestrator now enters a "Discovery-Focus" mode. It automatically skips all non-essential parsers, consolidation scripts, and topology mapping, executing only `core/commands.py`, `parsers/show.lldp.neighbors.detail.py`, and `core/element_status.py`. This significantly speeds up multi-hop recursive discovery.

## [1.31.1] - 2026-03-09
### Added
- **Persistent Interactive Authentication**: The orchestrator now prompts for the SSH password once at the start of execution and reuses it for all discovery hops, preventing multiple re-prompts.

### Fixed
- **Discovery I/O Error**: Fixed a bug that triggered "I/O operation on closed file" when writing logs for discovery sub-processes.
- **Custom Settings Support**: Refactored `discovery.py`, `element_status.py`, and `interface2connection.py` to respect the `--settings` CLI argument passed to the orchestrator.

## [1.31.0] - 2026-03-09
### Added
- **Output Compression**: Added a feature to automatically compress output folders (`collect/`, `log/`) into `.zip`, `.tar`, or `.gztar` archives at the end of the execution, saving significant disk space.
- **Dependency Validation**: Implemented a pre-execution check to verify if the chosen compression format is supported by the environment.
- **Improved install script**: Updated `installdep.sh` to include `zip` and `tar` packages.
- **Improved Discovery Logic**: Fixed I/O errors and ensured custom settings are respected globally.

## [1.30.1] - 2026-03-09
### Fixed
- **Missing CSV Import**: Restored `import csv` in the main orchestrator, fixing a `NameError` during final report generation.
- **Consolidated Parser Arguments**: Refactored the consolidation loop to correctly map specific CLI arguments (`--outdir` vs `--resume_dir`) for each sub-script, resolving failures in `system_asset.py`, `transceiver_matrix.py`, and others.
- **Argument Dependencies**: Improved `argparse` logic to prevent conflicting flags (e.g., `--discovery` with `--offline`) and refined the `--help` output with contextual groupings.

## [1.30.0] - 2026-03-09
### Added
- **Recursive Network Discovery (`--discovery`)**: Implemented multi-hop recursive crawling. The script now parses LLDP neighbors at the end of each cycle and generates a new target list for the next hop.
- **Management IP Election Logic**: Intelligent IP selection for discovered neighbors. Prioritizes configured `preferred_management_subnets` (loopbacks/mgmt) and falls back to other reachable IPs.
- **Authentication Fallback (Multi-Key Support)**: Support for multiple `cmd_keys` separated by pipes (e.g., `cisco_ios|datacom_dmos`). Elements are tried against these keys sequentially until success.
- **Success Key Reporting**: Added `successful_keys.csv` and a new `working_key` column in `status.elements.csv` to simplify inventory cleanup by identifying exactly which command profile worked for each device.
- **Configurable Discovery Hops**: Added `--hops` CLI argument to control the depth of recursive crawling.

### Fixed
- **Duplicate Detection**: Refined to skip elements by both IP and Hostname, preventing redundant processing of multi-homed routers.
- **Timestamp Consistency**: Fixed a bug in `core/commands.py` where the timestamp was not refreshed within the thread worker, causing file collision risks.

## [1.28.7] - 2026-03-06
### Fixed
- **Topology Audit Logging**: Fixed a bug where `core/topology_checker.py` was generating an empty log file. Added verbose output to the script so that audit results and isolated node lists are correctly captured by the orchestrator.

## [1.28.6] - 2026-03-06
### Fixed
- **Comprehensive Audit of Skip Logic**: Performed a full validation of all `check_data_presence` rules. 
- **Transceiver Matrix Detection**: Corrected patterns for `transceiver_matrix.py` to include Datacom-specific `hardware-status` and Cisco's `inventory.details` filenames, which were previously being ignored.
- **Subcomponents Detection**: Expanded detection patterns to ensure consistency for both vendors.

## [1.28.5] - 2026-03-06
### Fixed
- **Parser Skip Logic**: Fixed a bug where `license_matrix.py` was being skipped due to a mismatch in filename patterns (`*.show.license.txt` vs the actual `*.show.license.summary.txt` or `feature.txt`).
- **Topology Check Skip**: Fixed a path error in the skip logic for `core/topology_checker.py`, which was looking for the connections CSV in the wrong directory.

## [1.28.4] - 2026-03-06
### Fixed
- **UnboundLocalError in Commands**: Fixed a scoping bug introduced in 1.28.3 where `commands.py` crashed silently during thread execution due to the `files_written` variable missing a `nonlocal` declaration, resulting in false 100 exit codes even when files were successfully generated.

## [1.28.3] - 2026-03-06
### Added
- **Offline Processing (`--offline`)**: Added the ability to skip active SSH polling and reprocess existing `collect/` folders directly to generate updated CSVs and topology maps without logging into the equipment again.

### Fixed
- **Empty Collection Handling**: The orchestrator now correctly stops execution if `core/commands.py` fails to collect any files (exit code 100).
- **Silent Parser Success**: Implemented smart data presence checks before running parsers. If the required raw `collect/*.txt` files are missing, the orchestrator skips the parser (`[SKIPPED - NO DATA]`) instead of executing it and reporting a false `[SUCCESS]`.
- **Force Execution**: Added a `--force` flag to bypass the new missing-data safeguards if needed by legacy automation pipelines.

## [1.28.2] - 2026-03-05
- **Orchestration:** Corrected script categorization logic that was still allowing the BGP parser to run in the atomic `show.*` loop without mandatory arguments.


## [1.28.1] - 2026-03-05
### Fixed
- **BGP Parser:** Fixed `IndentationError` in `parsers/show.bgp.vpnv4.unicast.all.summary.py`.
- **LLDP Consistency Report:** Fixed column name mismatch (`local_interface` vs `local_intf`) that caused empty interface columns and false 'EMPTY' alerts.
- **Orchestration Consolidation:** Prevented consolidation scripts from running twice (generic loop vs specialized end-pipe) to avoid argument mismatch errors.
- **Improved LLDP Matching:** Added ignore-self and FQDN normalization to the LLDP auditor.


## [1.28.0] - 2026-03-05
### Added
- **Service Inventory Auto-Extraction:** `parsers/generate_service_inventory.py` to extract clients, speeds, circuits, and services directly from interface descriptions.
- **BGP Logical Peering Matrix:** `parsers/show.bgp.vpnv4.unicast.all.summary.py` to map BGP neighbors, AS Numbers, and prefixes.
- **L2 LLDP Consistency Auditor:** `core/lldp_consistency_checker.py` to cross-reference configured interface descriptions against live LLDP discovery.
- **Certificate Auth / Non-Interactive Executions:** Added `--user`, `--password`, and `--key` flag support to `network-data-extractor.py` and `core/commands.py` to allow execution by CI/CD pipelines without terminal prompts.
- **Terminal Secure Clear:** Added `os.system("clear")` to prevent `--password` CLI parameters from remaining visible on-screen during execution.

### Fixed
- Addressed ASR9k Smart Licensing parsing bug in `parsers/license_matrix.py` where terminal headers were leaking into CSV rows.

## [1.27.0] - 2026-03-04
### Added
- **Multi-vendor Terminal Pager Support:** Dynamic `terminal pager 0`, `screen-length 0 disable` injection for Huawei, Datacom, HP, and Cisco.
- **Smart Regex Link Discovery:** Moved away from rigid 3-column `elements.cfg` layout to a dynamic Regex parser that finds equipment hostnames anywhere inside an interface description string.
- **Hardware Module Expansion:** Created matrices for Optical Transceivers (`transceiver_matrix.py`) and generic chassis modules (`subcomponents.py`).
- **Software Licensing Auditor:** Created `license_matrix.py`.
- **System Asset Global View:** Created `system_asset.py` to compile Model, Serial, MAC Base, and Firmware versions across the fleet.

## [1.26.0] - 2026-03-03
### Changed
- **Architecture Paradigms:** Migrated hardcoded application settings (like regex rules, ignored prefixes, SSH delays) into an externalized `config/settings.json` file.
- **Orchestrator UX:** Added the Interactive Configuration Wizard to the start of `network-data-extractor.py`.

## [1.25.0] - 2026-02-27
### Changed
- Improved formatting and output clarity of the terminal execution logs.

## [1.24.0]
- Refactored core topology connection generation code.

## [1.23.0]
- Added element status reporting metrics.

## [1.22.0]
- Stabilized LLDP data polling components.

## [1.11.0] to [1.21.0]
- Continuous development cycle adding various parsing utilities and core orchestrator stabilization features.

## [1.10.0]
- Initial functional beta releases.

## [1.01.0]
- First commit. Extractor prototype.
