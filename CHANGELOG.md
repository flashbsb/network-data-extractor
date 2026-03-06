# Changelog

All notable changes to the **Network Data Extractor** project will be documented in this file.

## [1.28.3] - 2026-03-06
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
