# Changelog

All notable changes to the **Network Data Extractor** project will be documented in this file.

## [1.66.0] - 2026-06-30
### Added
- **Inter-Dashboard Context Menus**: Introduced context menus triggered on connection/interface cell clicks across Global Inventory connection lists, interface lists, and heatmap cells. They list contextual links to P2P latency history, route analysis (Dijkstra), inventory details, and drift comparisons.
- **Unified Parameter Routing**: Implemented dynamic parameter parsing and pre-filling using URL parameters (`run`, `origin`, `dest`, `device`, `interface`, `focus`) across all dashboards, enabling operators to seamlessly jump between telemetry details.
- **Decoupled Input Pre-filling**: Pre-filled search and autocomplete fields in Dijkstra Path Analysis and SLA P2P History independently when single parameters are found.
- **Draw.io Node Highlighting**: Enabled automated search and highlight triggers inside Draw.io topology frame using Native Draw.io search integration.
- **Self-Disabling Optional Integrations**: Implemented live file checking using HEAD request validation, disabling links to Drift Analysis dynamically inside the Global Inventory context menu if comparison files do not exist.

## [1.65.0] - 2026-06-26
### Added
- **Interface Timeline Tracker**: Introduced a new analysis tab inside the Drift Analyzer dashboard (`diff/index.html`) that allows tracking the historical state changes of a single physical/logical interface. It features:
  - Autocomplete lists for network elements and their corresponding interfaces, loaded dynamically from the latest snapshot.
  - Custom date range selection.
  - Interactive vertical timeline showing baseline states and chronological events (`ADDED`, `REMOVED`, `MODIFIED`).
  - Search/filter capability to narrow down timeline details in real-time.

## [1.64.1] - 2026-06-26
### Fixed
- **Python Import Paths (sys.path)**: Appended project root directory to `sys.path` dynamically inside `core/discovery.py`, `core/element_status.py`, and `core/interface2connection.py` to fix `ModuleNotFoundError: No module named 'core'` when execution is triggered inside subprocesses.

## [1.64.0] - 2026-06-26
### Added
- **SSH Strict Host Key Checking option**: Added `"strict_host_key_checking"` setting inside the `"ssh"` configuration block in `settings.json` and implemented key policy validation in `commands.py` to reject unknown hosts when enabled.
- **Shared Utility Module**: Introduced `core/utils_shared.py` to consolidate configurations loading (`load_settings`) and hostname normalization (`normalize_hostname`), reducing code duplication across `discovery.py`, `interface2connection.py`, and `element_status.py`.

### Fixed
- **Parser Processed Counter Bug**: Fixed a logic bug across 5 parsers (`show.firmware.py`, `show.system.py`, `show.platform.py`, `show.version.py`, `show.interfaces.status.py`) where the `"processed"` count was initialized but never incremented inside the file loop, which previously always reported "0" parsed nodes.
- **Exception Variable NameError**: Fixed a `NameError` bug in `core/root_portal_engine.py` by catching the exception as `e` and formatting it correctly in an f-string.
- **Robust File Ingestion**: Guarded `open()` calls in `parsers/generate_max_speed_interfaces.py` using `os.path.exists()` checks to prevent orchestrator crashes when files are missing.
- **Source Comments English Translation**: Translated all legacy Portuguese comments to English in `show.inventory.py`, `show.inventory.details.py`, `show.firmware.py`, and `core/ping_matrix.py`, conforming to strict English coding guidelines.

## [1.63.0] - 2026-06-23
### Added
- **Configuration-Driven Dijkstra Routing Hierarchy**: Added a `"routing_hierarchy"` block inside `config/settings.json` to define naming prefixes and ranks representing `METRO` (1), `EDGE` (2), `CORE_AGG` (3), `CORE` (4), `PEERING` (5), and `ROUTER_REFLECTOR` (6).
- **Pre-computed Device Ranks**: Modified `core/inventory_engine.py` to parse hierarchy settings and calculate unique device ranks on the Python backend, embedding them inside the JS snapshot payloads to bypass browser CORS constraints.
- **Backbone Routing Constraints**: Implemented 4 key routing constraints in `templates/ping-matrix/path.html` Dijkstra path analysis:
  - **Valley-Free Constraint**: Heavily penalizes paths descending in rank and then ascending (e.g. Core ➔ Edge ➔ Core).
  - **Metro-to-Metro Transit Penalty**: Restricts transit traffic between multiple METRO switches, forcing paths up to the EDGE level.
  - **Peering & Route Reflector Transit Penalty**: Bypasses `PEERING` (`RTPR` / Rank 5) and `ROUTER_REFLECTOR` (`RTRR` / Rank 6) nodes as intermediate transit hops unless they are the designated source or destination.
  - **Level-Skipping Penalty**: Penalizes direct hops that skip intermediate hierarchy levels to favor standard progressive routes.
- **Shortest Hop Sorting**: Ordered calculated Dijkstra paths by hop count (ascending) to guarantee that the path with the fewest hops is selected and visualized by default in the UI.

## [1.62.0] - 2026-06-19
### Added
- **Global English Translation**: Translated all user-facing interface text, buttons, loading screens, and fallbacks inside the Draw.io Topology Viewer (`topology/index.html`) and manifest cataloguer (`core/topology_engine.py`) to English.
- **Source Code Comments Cleanup**: Replaced Portuguese code-level and HTML comments with English equivalents across the main orchestrator (`network-data-extractor.py`) and templates (`history.html`, `path.html`).
- **Draw.io Layer & Navigation Controls**: Appended `layers=1` and `nav=1` URL parameters to the embedded diagrams.net iframe inside the topology portal ([core/topology_engine.py](file:///home/flashbsb/projetos/network-data-extractor/core/topology_engine.py)) to allow NOC operators to show/hide specific layers (such as background maps) and use pan/zoom navigation controls directly inside the web browser.

### Verified
- **Terminal Consistencies**: Conducted an end-to-end audit verifying that all console output, interactive configuration prompts, and command line validation warnings are exclusively printed in English.

## [1.61.0] - 2026-06-18
### Added
- **Topology Sync Integration (Flowchart Update)**: Added detailed representation of the `--topology` workflow mapping and topological index engine synchronisation to the core README.
- **Dijkstra Route Analysis Summary**: Added automatic summation of individual hop mean latencies, presenting a dynamic "Total Path Latency" calculation inside the Dijkstra Route analytical card.
- **Dynamic Snapshot Text Search**: Replaced the static selection dropdown in Route Analysis (`path.html`) with a dynamic autocomplete text input associated with an HTML5 `<datalist>` to support searching snapshots by ID or dates.
- **CSV Data Export (Drift & Ping Heatmap)**: Added client-side Javascript CSV export functionality in both the Drift Analyzer (`diff/index.html`) and Snapshots & Heatmaps (`ping_matrix.html`) allowing NOC operators to immediately download current filtered results.
- **Action Filters Split**: Replaced the unified filter cleanup actions with dedicated "Clear All" (reset text inputs and uncheck options) and "Select All" (check all items) buttons.
- **Circuit SLA History Redesign**: Moved and restructured the global network health metrics (Recent Anomalies, Top 10 Worst, Degradation Trend, and Instability) to a full-width bottom section on the SLA dashboard (`history.html`), isolating the circuit-specific tracking at the top to reduce layout confusion. Added metric legends.

### Changed
- **Default Drift Selection**: Adjusted initial page load logic of the Drift Analyzer to auto-select the two most recent network snapshots instead of the oldest and newest.
- **Horizontal Filter Alignment**: Restructured selection filters (Admin and Oper) inside the Global Inventory dashboard to render horizontally side-by-side using CSS flex-wrap layout rules, significantly saving vertical dashboard space.
- **Card Centralisation**: Enhanced root navigation portal aesthetics by centralising descriptions, statuses, and icons inside the Global Inventory, Drift Analyzer, Network Topology, and Ping Monitoring cards, ordering the Topology card to the bottom.
- **Lateral Navigation Labels**: Renamed left navigation drawer actions from "Menu" or "Drift Analyzer" to "HISTORY" inside the Ping Matrix and Master Index files.

## [1.60.0] - 2026-06-03
### Added
- **Dynamic Datalist Autocomplete**: Replaced the static selection dropdowns in both the Ping History (`history.html`) and Dijkstra Route Analysis (`path.html`) dashboards with text inputs connected to HTML5 `<datalist>` elements. This provides instant dynamic filtering, handles large lists without browser lag, supports native keyboard navigation, and runs CORS-free.
- **Dijkstra Route Analysis**: Added a path simulator inside the Ping Matrix workspace (`path.html`) using Dijkstra's algorithm to compute shortest paths between nodes based on real-time latency and packet loss.
- **Ping History Telemetry**: Introduced a telemetry dashboard (`history.html`) to visualize and analyze historical ping metrics (latency, jitter, packet loss, and node availability) over time.
- **Project Requirements**: Added a `requirements.txt` file listing python dependencies (`pandas` and `paramiko`) to standardize environment setups.

### Changed
- **Unified Portal Headers**: Harmonized navigation styling across all sub-workspaces, introducing a "Network Portal" back-navigation link in the top-right corner.
- **Iframe Navigation Handling**: Implemented a responsive check (`window.self !== window.top`) in the master templates to dynamically hide duplicate portal buttons when a sub-dashboard is loaded inside the Root Navigation iframe.

### Fixed
- **Network Drift Layout Overlap**: Corrected absolute overlay positions, padding, and sidebar toggle behaviors in the Drift Analyzer (`diff/index.html`) to prevent the header navigation links from being clipped or blocked.

## [1.59.0] - 2026-05-21
### Added
- **Root Navigation Portal**: Developed a central, interactive `index.html` hub that is automatically generated at the root of the `--outbase` directory. It actively detects and bridges access to the Diff, Inventory, and Ping Matrix workspaces in a highly polished, NOC-focused dark mode interface.
- **Dynamic Portal Links**: The Root Portal uses strictly relative paths and automatically provides actionable commands to the user if a specific workspace hasn't been generated yet (e.g., `Run with --diff`).

## [1.58.5] - 2026-05-15
### Changed
- **Documentation**: Updated `README.md` flowchart and help texts to accurately reflect current `--rebuild-ping-index` functionality and correct portal paths.
- **Version Alignment**: Harmonized application internal versions and banners.

## [1.58.0] - 2026-05-14
### Added
- **Admin State vs Oper Protocol Separation**: Deeply decoupled the interface tracking on the Inventory Dashboard. Checkbox filters and main dashboard metrics now differentiate between Administrative intent (`Admin UP`/`Admin DOWN`) and actual physical/logical line status (`Oper UP`/`Oper DOWN`).
- **Fault Tracking Card**: Added a dedicated, highlighted metrics card ("FAULTS") specifically engineered to intercept critical failure conditions: `Admin UP` (Port enabled) paired with `Oper DOWN` (Link lost). This dramatically accelerates NOC troubleshooting workflows.

## [1.57.0] - 2026-05-14
### Added
- **Dynamic CSV Export**: The Inventory Dashboard now features a local CSV export button (`📥 Export CSV`) that dynamically downloads the currently active table (Interfaces or Topology) while fully respecting applied logic filters.
- **Advanced Inventory Search**: Integrated a powerful logical search engine supporting `AND` (semicolon/space), `OR` (pipe/comma), and `NOT` (minus/exclamation) syntax directly into the dashboard.
- **Reactive Metric Cards**: The main summary cards (Total Interfaces, Links, Devices, etc.) now instantly recalculate their values in real-time as search filters are typed.

### Fixed
- **Subinterface Phantom Capacity Bug**: Restructured the phase 3 deduplication engine in `core/interface2connection.py`. The algorithm now aggressively strips subinterface demarcations (`.\d+$`), collapsing multiple logical definitions over the same physical port into a single correct connection, thus displaying the accurate physical capacity (e.g., 1x 1G instead of 1x 1G + 1x 100M).
- **Responsive Layout**: Forced strict `100vw` layout rules and flexbox zero-minimum bounds (`min-width: 0`) to prevent large tables from ignoring their horizontal overflow containers and pushing the main dashboard layout out of screen.

## [1.56.0] - 2026-05-14
### Added
- **Global Inventory Dashboard (`--inventory`)**: Added a new offline execution mode that scans previous historical collections (`infos/`) and builds a cumulative HTML dashboard. It features an interactive UI for visualizing the complete network Interface List and Topology Links across different execution dates.
- **Automated Inventory Extraction**: The main orchestrator now automatically invokes the Inventory Engine at the end of every successful standard SSH extraction, keeping the global dashboard permanently up-to-date without user intervention.
- **CORS-Free Dynamic Loading**: Implemented a JS-payload wrapping mechanism for the Inventory Dashboard, completely bypassing browser CORS restrictions for local `file:///` viewing without a web server.


## [1.55.0] - 2026-05-04
### Added
- **Universal Offline Architecture**: `core/ping_matrix.py` now supports the `--offline` flag. It can bypass SSH entirely, reading cached `.txt` ICMP responses from a previous extraction to instantly regenerate the High-Performance Dashboard and CSVs.
- **Strict Mode B/E Gatekeeper**: Explicit runtime blocks preventing logical impossibilities, such as combining `--offline` with `--discovery` or `--diff`.

## [1.54.0] - 2026-05-04
### Added
- **Advanced Drift Filters**: Replaced the basic drift filter with a multi-valued checkbox engine allowing users to selectively display interface changes by Changed Fields (Description, Admin, Protocol, Bandwidth) and Current State (UP, DOWN, OTHER). 
- **Negative Text Search**: Added an "Exclude" text box in the Drift Analyzer to quickly hide specific interfaces (e.g. "loopback") from the audit panel.
- **Smart UI Rendering**: The comparison table now dynamically masks field changes that are unchecked in the filters, lowering visual noise while preserving structural accuracy.

### Changed
- **Premium Layout UX**: The Master Index lateral panel is now fully collapsible, guaranteeing 100% table width visibility. 
- **Time/Date Clarity**: Snapshot UNIX IDs have been converted to human-readable `DD/MM/YYYY HH:MM:SS` format within the side menu.
- **Auto-Compare Mode**: The Drift Analyzer now auto-selects the oldest and newest snapshots upon loading, bypassing manual clicks.

## [1.53.0] - 2026-04-29
### Added
- **Network Drift Analysis (Snapshot Comparison)**: The Master Index now features an advanced comparison engine. Users can select any two historical collections and instantly visualize differences in interface states, speeds, and administrative statuses.
- **Dynamic JSON Data Export**: The `show.interfaces.py` parser now generates a comprehensive `interfaces_all.json` payload for every run, enabling near-instant client-side differential analysis.
- **Advanced Drift Filters**: The comparison dashboard includes specialized filters for Element names, Change Types (Added/Removed/Modified), Status Transitions (Up/Down, Admin Up/Down), and Speed changes (Increased/Decreased bandwidth).
- **Premium Comparison UI**: Integrated a high-performance comparison overlay with real-time statistics (Total Changes, New Elements, Removed Links, Status Drift) and a highlighted difference table.

### Changed
- **Master Index Upgrade**: Refactored the dashboard sidebar to support multi-selection (checkboxes) and added a dedicated "Compare Selected" action footer.

## [1.52.0] - 2026-04-27
### Added
- **Maintenance Mode (`--rebuild-ping-index`)**: Added a dedicated flag to synchronize and update the Master Index without running new ping tests. This allows users to instantly clean up deleted folders or update the dashboard portal in milliseconds.
- **Improved Code Architecture**: Refactored the core logic to separate portal generation from execution, enabling faster maintenance and better error handling for "ghost" directories.

## [1.51.0] - 2026-04-27
### Added
- **Collapsible Master Index Sidebar**: The Master Index now features a modern, smooth-transition collapsible sidebar. By default, the sidebar is collapsed to maximize the dashboard's screen real estate, providing a cleaner and more focused monitoring experience.
- **Floating Navigation Toggle**: A stylish floating hamburger button at the top-left allows users to quickly expand the index to switch between different matrix execution runs.

## [1.50.2] - 2026-04-27
### Fixed
- **Redundant File Cleanup**: Restored strict adherence to the `--ping-format` flag. If the user requests only `html`, the script no longer generates auxiliary `.json` or `.csv` files, keeping the output directory clean.
- **Resilient Master Index Extraction**: Enhanced the orchestrator's data extraction logic to reliably pull metadata directly from the interactive HTML files using a robust Regex pattern, ensuring the Master Index stays updated even without standalone JSON files.

## [1.50.0] - 2026-04-27
### Added
- **Quadrant-Aware Smart Tooltip**: Replaced the HUD panel with a new, highly intelligent floating tooltip. It uses a **Quadrant Logic Algorithm**: if the mouse is in the bottom-right of the screen, the tooltip appears to the top-left, and vice-versa. This ensures the tooltip always "aims" towards the center of the viewport where there is the most available space.
- **Bidirectional Clamping**: Added a secondary mathematical safety layer that clamps the tooltip position at least 10px away from all 4 viewport edges, making it physically impossible to be cut off by iframe boundaries or screen edges.
- **Improved Contrast**: Enhanced the tooltip styling with high-contrast glassmorphism (`backdrop-filter`) and optimized text colors for better readability against the dark dashboard background.

## [1.49.0] - 2026-04-27
### Changed
- **NOC Heads-Up Display (HUD)**: Completely abandoned the "mouse-following floating tooltip" paradigm in favor of a fixed **Inspection Panel (HUD)** at the bottom-right of the screen. This is a definitive UX upgrade for NOC operations that guarantees 100% visibility of routing details without any clipping, iframe border conflicts, or coordinate miscalculations. Hovering over any matrix cell instantly populates the fixed panel with cross-information without blocking the user's view of adjacent matrix cells.

## [1.48.1] - 2026-04-27
### Fixed
- **Iframe Rendering Bug**: Switched tooltip positioning from `fixed` to `absolute`. This resolves a browser compositing bug where `position: fixed` elements inside an iframe could be visually clipped or shifted if the parent window uses CSS Flexbox with `overflow: hidden` (like the Master Index dashboard layout).

## [1.48.0] - 2026-04-27
### Fixed
- **Fluid Dynamic Tooltips**: Completely refactored the Ping Matrix tooltip logic. Tooltips now dynamically follow the mouse cursor (`onmousemove`) instead of locking to the entrance point of the cell. Implemented absolute mathematical failsafes (`Math.max(10, ...)`) to guarantee that tooltips will **never** be rendered off-screen (top/left) or cause overflow cuts, regardless of the matrix size or viewport constraints.
 
## [1.47.0] - 2026-04-27
### Added
- **Global Reset Filter**: Added a new "Reset Filters" button in the Ping Matrix Dashboard to instantly clear all active filters (Severity, Origin/Destination, Direction, Metrics) and restore the matrix to its full state.
- **Master Index Tooltips**: Added hover descriptions to the health badges (OK, W, C, D) in the Master Index sidebar to help new users identify status levels.

### Fixed
- **Smart Tooltip Positioning**: Implemented edge-aware tooltip logic. Details will now automatically align left/right at the screen edges and appear above the cell for the bottom-most rows, preventing information from being cut off.
- **NOC-Ready Filtering**: Changed the severity filter behavior from "dimming" to "hiding". When a filter (e.g., Asymmetry) is selected, healthy connections are now completely removed from the view instead of being shown with low opacity, creating a significantly cleaner interface for large networks.

## [1.46.0] - 2026-04-24
### Added
- **Single File Dashboard (Portable)**: The `ping_matrix_dashboard.html` now fully embeds the JSON data payload at generation time, replacing asynchronous HTTP `fetch()` logic. This allows the dashboard to be perfectly portable and executable entirely offline (e.g. sent via email or USB) without triggering browser CORS security blockers.
- **Master Index Portal**: The Orchestrator now generates a dynamic `index.html` at the root of the output directory (e.g., `/infos/index.html`) after every Ping Matrix execution. This portal features a left-side navigation sidebar displaying the chronological history of all matrix executions, allowing users to quickly switch between interactive dashboards using an embedded `iframe`.

### Fixed
- **Iframe Visibility (Master Index)**: Refactored CSS to use absolute positioning on the dashboard iframe, ensuring it fills 100% of the viewport and resolves content cutoff issues on specific resolutions.
- **Visual Cleanup**: Removed legacy "2.0" versioning string from the Ping Matrix Dashboard header for a cleaner, unified UI.
- **Metadata Fallback**: Implemented a Regex-based JSON extractor for the Master Index, allowing it to index historical runs even when the standalone `.json` file is missing, by mining the embedded payload directly from the HTML source.
- **Python Indentation**: Fixed a syntax error in the orchestrator's index generation logic.

## [1.45.0] - 2026-04-24
### Added
- **Audit Trail (Execution Metrics)**: The JSON metadata now permanently captures the exact execution scope (`total origins`, `total pings`, `threads`) and the real duration taken by the ICMP Motor (`actual duration vs estimated duration`).
- **Dashboard Audit Header**: The HTML Dashboard now automatically reads the execution metrics and generates a professional, printable Audit Header displaying the execution parameters below the main title.

### Fixed
- **Analytics Empty States**: Refactored the internal filtering of the Ping Matrix Advanced Analytics. Panels like "Most Isolated Nodes" or "Highest Packet Loss" will no longer display healthy routes as false-positives when the entire network is 100% operational, returning clean text strings instead (e.g., "All nodes are 100% reachable!").

## [1.44.0] - 2026-04-24
### Added
- **Multi-Value Search Engine**: Origin and Destination text filters in Ping Matrix Dashboard now support multiple parallel queries separated by semicolons (`eg. bsa; gti`).
- **Advanced Predictive Engine**: The Orchestrator now pre-calculates and displays a complete `Ping Matrix Execution Plan` in the terminal before triggering threads, estimating time based on network overhead and local latency.
- **Top 5 Asymmetric Routes**: Analytics Panel now automatically calculates and flags route deviations ($|A \rightarrow B - B \rightarrow A|$) highlighting massive path discrepancies.
- **Top 5 High Packet Loss**: Analytics Panel now ranks actively degrading links that have not yet failed completely ($1\%$ to $99\%$ loss).
- **Most Isolated Nodes**: Ping Extractor script now calculates a `Reachability Score` for each router in the backend and displays the most blackholed origins in the HTML dashboard.
- **Global Network Health**: JSON metadata now carries total counters for `Healthy`, `Warning`, `Critical`, and `Dead` links, protecting browser CPU by executing aggregations in Python.

### Changed
- **Responsive Analytics CSS**: Rewrote the `.analytics-content` as a flex-wrap container with `min-width` parameters for `.analytics-card`, allowing the new 5 sub-reports to stack gracefully on smaller screens without horizontal scrolling issues.
## [1.42.0] - 2026-04-23
### Added
- **Ping Matrix Accelerator**: Implemented an override in ICMP Ping module that ignores excessive system delays configured in `settings.json`, reducing the ping collection time significantly.
- **Selective Discovery Filtering**: Added the `--filter` parameter to `ping_matrix.py` enabling filtering nodes by prefix strings through Inclusion (`in:`) or Exclusion (`rn:`).
- **Console Feedback in Matrix Mode**: Added granular visual progress feedback (`.`) during matrix execution to avoid freezing impression on large node counts.

### Changed
- **Ping Matrix Dashboard 2.0 (HTML)**: Complete redesign of the Ping Matrix UI transforming it into a high-performance NOC-ready Dashboard.
- **Glassmorphism Aesthetics**: Introduced Neon glow, modern typography (Inter/Outfit), and dark-mode by default.
- **SPA Local Support**: Refactored dashboard to ingest static JSON gracefully via JS Fetch and Drag&Drop, avoiding CORS limitations on local environments.
- **Collapsible Panels (Sanfonas)**: Refactored the advanced metrics panel (Top latency/jitter) and Legends into space-saving expandable components.
- **Dynamic Multi-Value Filters**: Destroyed the monolithic `<select>` dropdowns and replaced them with Checkboxes/Toggles for Perspective, Path Metrics, and Severities (`Critical`, `Loss`, `Jitter`, `Asym`, `Healthy`).
- **Dimming Mechanics**: Refactored Severity parsing (`checkCond()`) to support combinatorial combinatorial OR filters, dynamically isolating the filtered conditions while muting irrelevant connections with opacity changes.
## [1.37.0] - 2026-03-10
### Added
- **Smart Success IP Pruning**: The cumulative discovery report (`discovered_elements.csv`) now favors successful connections. If a node is successfully reached, all unsuccessful "candidate" IPs for that node are automatically pruned from the final report.
- **Improved Source Tracking**: Sources are now aggregated cumulatively across all discovery hops.
### Changed
- **Mandatory Final Consolidation**: The orchestrator now runs a final discovery process after the hop loop finishes. This ensures that LLDP data collected from nodes in the very last hop is processed and integrated into the final CSV reports.

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
