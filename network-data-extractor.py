#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 
============================================================
           NETWORK DATA EXTRACTOR ORCHESTRATOR           
============================================================
 Version : 1.55.0
 Date    : 2026-05-04
 Author  : flashbsb (and contributors)

"""

import subprocess
import sys
import os
import shutil
import argparse
import json
import csv
import getpass
from datetime import datetime
from glob import glob

APP_VERSION = "1.55.0"
APP_DATE = "2026-05-04"

# ANSI Colors
C_GREEN = '\033[92m'
C_RED = '\033[91m'
C_CYAN = '\033[96m'
C_YELLOW = '\033[93m'
C_RESET = '\033[0m'

# Exclude scripts that are manually called later in specialized 'consolidation' blocks to avoid double execution with wrong args
consolidation_scripts = [
    "parsers/generate_max_speed_interfaces.py",
    "parsers/generate_service_inventory.py",
    "parsers/license_matrix.py",
    "parsers/port_census.py",
    "parsers/subcomponents.py",
    "parsers/system_asset.py",
    "parsers/transceiver_matrix.py",
    "parsers/show.bgp.vpnv4.unicast.all.summary.py"
]
parsers_show = sorted([p for p in glob("parsers/show.*.py") if p not in consolidation_scripts])
parsers_others = sorted([p for p in glob("parsers/*.py") if p not in parsers_show and p not in consolidation_scripts])

SCRIPTS = ["core/commands.py"] + parsers_show + parsers_others + ["core/element_status.py"]

description = """
Main Extractor Orchestrator

This script automates the execution of multiple data collection and parsing
scripts against network elements defined in 'config/elements.cfg', using the
commands outlined in 'config/commands.cfg'.

Workflow Options:
  [A] Standard Extraction Mode:
      1. Validates SSH credentials interactively or via flags.
      2. Concurrently gathers raw CLI outputs into '<outbase>/YYYYMMDD_HHMMSS/collect/'.
      3. Process parsing scripts sequentially to generate CSV structures.
      4. Executes network health, isolation checks, and physical topology mapping.

  [B] Ping Matrix Mode (--ping-matrix):
      1. Bypasses regular SSH scraping.
      2. Tests ICMP reachability from all configured origins to all destinations.
      3. Generates statistical analysis and builds a High-Performance HTML/JSON Dashboard.

  [C] Discovery Mode (--discovery):
      1. Follows Standard Mode but iterates continuously over LLDP neighbors.
      2. Discovers missing routers and creates a new pool file iteratively automatically.

  [D] Drift Analysis Mode (--diff):
      1. Operates offline without querying devices.
      2. Compares two snapshot collections to detect configuration drift.
      3. Generates an interactive High-Performance HTML Dashboard with advanced filters.
"""

# --- PRE-PARSING TO LOAD SETTINGS ---
pre_parser = argparse.ArgumentParser(add_help=False)
pre_parser.add_argument("--settings", type=str, default="config/settings.json")
pre_args, _ = pre_known = pre_parser.parse_known_args()

json_config = {}
if os.path.exists(pre_args.settings):
    try:
        with open(pre_args.settings, "r") as f:
            json_config = json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load {pre_args.settings}: {e}")

extractor_cfg = json_config.get("extractor", {})
def_threads = extractor_cfg.get("threads", 20)
def_outbase = extractor_cfg.get("output_base_dir", "infos")
def_elements = extractor_cfg.get("elements_file", "config/elements.cfg")
def_commands = extractor_cfg.get("commands_file", "config/commands.cfg")
def_randomize = extractor_cfg.get("randomize_order", True)

ssh_cfg = json_config.get("ssh", {})
SSH_TIMEOUT = ssh_cfg.get("timeout", 10)
CMD_DELAY = ssh_cfg.get("delay_between_commands", 5)

topology_cfg = json_config.get("topology", {})
IGNORE_VIRTUAL_PREFIXES = topology_cfg.get("ignore_virtual_prefixes", [])
NEIGHBOR_PREFIXES = topology_cfg.get("neighbor_regex_prefixes", [])

discovery_cfg = json_config.get("discovery", {})
IGNORE_NEW_PREFIXES = discovery_cfg.get("ignore_new_prefixes", [])

# --- MAIN ARGUMENT PARSING ---
parser = argparse.ArgumentParser(
    description=description,
    formatter_class=argparse.RawTextHelpFormatter
)

group_global = parser.add_argument_group("Global Settings")
group_global.add_argument("--settings", type=str, default="config/settings.json", help="Path to JSON settings file (default: config/settings.json)")
group_global.add_argument("--outbase", type=str, default=def_outbase, help=f"Root directory for outputs (default: {def_outbase})")
group_global.add_argument("--skip-wizard", action="store_true", help="Skip configuration confirmation prompt")
group_global.add_argument("--force", action="store_true", help="Force execution even if collection fails (ignored in --ping-matrix/--diff)")

group_auth = parser.add_argument_group("Authentication (ignored in --offline/--diff)")
group_auth.add_argument("--user", type=str, help="SSH Username (required for automated auth)")
auth_me = group_auth.add_mutually_exclusive_group()
auth_me.add_argument("--password", type=str, help="[INSECURE] SSH Password (requires --user)")
auth_me.add_argument("--key", type=str, help="Path to SSH Private Key (requires --user)")

group_a = parser.add_argument_group("Mode A: Standard Extraction (Default)")
group_a.add_argument("--elements", type=str, default=def_elements, help=f"Input elements file (default: {def_elements})")
group_a.add_argument("--commands", type=str, default=def_commands, help=f"Input commands file (default: {def_commands})")
group_a.add_argument("--threads", type=int, default=def_threads, help=f"Number of concurrent SSH sessions (default: {def_threads})")
group_a.add_argument("--randomize", action="store_true", default=def_randomize, help=f"Randomize connection order (default: {def_randomize})")
group_a.add_argument("--no-randomize", dest="randomize", action="store_false", help="Keep connection order sequential")
group_a.add_argument("--filter", type=str, help="Filter elements by prefix (e.g. 'in:RT1;RT2' to include, 'rn:RT1;RT2' to exclude)")

group_b = parser.add_argument_group("Mode B: Ping Matrix")
group_b.add_argument("--ping-matrix", action="store_true", help="Omit regular tests and execute ICMP Ping Matrix")
group_b.add_argument("--ping-commands", type=str, default="config/commands.icmp.cfg", help="(requires --ping-matrix) Input ICMP commands file (default: config/commands.icmp.cfg)")
group_b.add_argument("--ping-format", type=str, default="csv", help="(requires --ping-matrix) Output format: csv, json, html (comma-separated)")

group_c = parser.add_argument_group("Mode C: Discovery")
group_c.add_argument("--discovery", action="store_true", help="Enable recursive discovery via LLDP neighbors")
group_c.add_argument("--hops", type=int, help="(requires --discovery) Number of recursive hops to perform")

group_d = parser.add_argument_group("Mode D: Drift Analysis")
group_d.add_argument("--diff", type=str, nargs='?', const='DEFAULT', help="Build Network Drift Workspace in 'diff/' folder. Optional: provide path to collections.")

group_e = parser.add_argument_group("Mode E: Offline Processing")
group_e.add_argument("--offline", type=str, metavar="DIR", help="Process existing data in DIR (Incompatible with --discovery/--diff)")

args = parser.parse_args()

# --- STRICT ARGUMENT VALIDATION & GATEKEEPER ---

# 1. Mode B: Ping Matrix Validations
if args.ping_matrix:
    ignored_pm_flags = []
    if args.force: ignored_pm_flags.append("--force")
    if ignored_pm_flags:
        print(f"{C_YELLOW}Warning: The following flags are ignored in Ping Matrix mode (--ping-matrix): {', '.join(ignored_pm_flags)}{C_RESET}")

if not args.ping_matrix:
    if args.ping_commands != "config/commands.icmp.cfg":
        print(f"{C_RED}ERROR: --ping-commands can only be used with --ping-matrix.{C_RESET}")
        sys.exit(1)
    if args.ping_format != "csv":
        print(f"{C_RED}ERROR: --ping-format can only be used with --ping-matrix.{C_RESET}")
        sys.exit(1)

# 2. Mode C: Discovery Validations
if not args.discovery:
    if args.hops is not None:
        print(f"{C_RED}ERROR: --hops can only be used with --discovery.{C_RESET}")
        sys.exit(1)
if args.discovery and args.ping_matrix:
    print(f"{C_RED}ERROR: --discovery and --ping-matrix are mutually exclusive.{C_RESET}")
    sys.exit(1)

# 3. Mode E: Offline Processing Validations (Pre-Checks)
if args.offline:
    if args.discovery:
        print(f"{C_RED}ERROR: --offline and --discovery are mutually exclusive.{C_RESET}")
        sys.exit(1)
    if args.diff:
        print(f"{C_RED}ERROR: --offline and --diff are mutually exclusive.{C_RESET}")
        sys.exit(1)

# 4. Mode D: Drift Analysis Validations
if args.diff:
    ignored_flags = []
    if args.user: ignored_flags.append("--user")
    if args.password: ignored_flags.append("--password")
    if args.key: ignored_flags.append("--key")
    if args.ping_matrix: ignored_flags.append("--ping-matrix")
    if args.discovery: ignored_flags.append("--discovery")
    if args.force: ignored_flags.append("--force")
    if args.threads != def_threads: ignored_flags.append("--threads")
    
    if ignored_flags:
        print(f"{C_YELLOW}Warning: The following flags are ignored in Drift Analysis mode (--diff): {', '.join(ignored_flags)}{C_RESET}")
    
    print(f"\n{C_CYAN}--- Network Drift Workspace: Initialization ---{C_RESET}")
    from core.diff_engine import DiffEngine
    base_path = args.outbase if args.diff == 'DEFAULT' else args.diff
    engine = DiffEngine(base_path)
    engine.run()
    sys.exit(0)

# 5. Hops Logic
if args.offline:
    args.hops = 0
else:
    # 5. Hops logic (only if NOT offline)
    if args.discovery:
        if args.hops is None:
            args.hops = discovery_cfg.get("default_hops", 3)
    else:
        args.hops = 0

# 6. Authentication logical dependency
if not args.offline and not args.password and not args.key:
    # If we are going to run commands.py or ping_matrix.py, ask for password once here
    # so we can reuse it for all discovery hops and prevent multiple interactive prompts.
    try:
        args.password = getpass.getpass('SSH Password (leave blank to use local SSH Agent/Keys): ')
    except EOFError:
        args.password = ""
    except KeyboardInterrupt:
        print(f"\n{C_RED}Execution cancelled by user.{C_RESET}")
        sys.exit(130)

if (args.password or args.key) and not args.user:
    print(f"{C_YELLOW}Warning: Automated authentication works best when --user is also provided.{C_RESET}")

# 4. Clear screen for password security
if args.password:
    os.system('clear' if os.name == 'posix' else 'cls')

# --- COMPRESSION VALIDATION ---
comp_cfg = json_config.get("compression", {})
if comp_cfg.get("enabled", False):
    comp_format = comp_cfg.get("format", "zip")
    supported_formats = [f[0] for f in shutil.get_archive_formats()]
    if comp_format not in supported_formats:
        print(f"{C_RED}ERROR: Compression format '{comp_format}' is not supported in this environment.{C_RESET}")
        print(f"Supported formats: {', '.join(supported_formats)}")
        print(f"{C_YELLOW}Disabling compression to prevent execution failure.{C_RESET}\n")
        comp_cfg["enabled"] = False
        json_config["compression"] = comp_cfg

if args.offline:
    TIMESTAMP_DIR = os.path.abspath(args.offline)
    if not os.path.isdir(TIMESTAMP_DIR):
        print(f"{C_RED}ERROR: Offline directory '{args.offline}' not found.{C_RESET}")
        sys.exit(1)
        
    LOG_DIR = os.path.join(TIMESTAMP_DIR, "log")
    COLLECT_DIR = os.path.join(TIMESTAMP_DIR, "collect")
    RESUME_DIR = os.path.join(TIMESTAMP_DIR, "resume")
    CONNECTIONS_DIR = os.path.join(TIMESTAMP_DIR, "connections")

    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(COLLECT_DIR, exist_ok=True)
    os.makedirs(RESUME_DIR, exist_ok=True)
    os.makedirs(CONNECTIONS_DIR, exist_ok=True)

    orchestrator_log = os.path.join(LOG_DIR, "orchestrator.log")
    def log_orchestrator(msg):
        with open(orchestrator_log, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

    start_time = datetime.now()
    log_orchestrator(f"Offline Processing Started. Target Root: {TIMESTAMP_DIR}")
    print(f"{C_CYAN}")
    print("============================================================")
    print("           NETWORK DATA EXTRACTOR ORCHESTRATOR           ")
    print("============================================================")
    print(f"Version : {APP_VERSION}")
    print(f"Date    : {APP_DATE}")
    print("============================================================")
    print(f"{C_RESET}")
    print(f"Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')} {C_YELLOW}(OFFLINE MODE){C_RESET}")
    print(f"Target Root: {TIMESTAMP_DIR}\n")
    print(f"{C_CYAN}----------------------------------------{C_RESET}")
    print(f"Offline processing initializing...")
    print("")

else:
    DIR_SUFFIX = datetime.now().strftime("%Y%m%d_%H%M%S")
    TIMESTAMP_DIR = os.path.abspath(os.path.join(args.outbase, DIR_SUFFIX))
    LOG_DIR = os.path.join(TIMESTAMP_DIR, "log")
    COLLECT_DIR = os.path.join(TIMESTAMP_DIR, "collect")
    RESUME_DIR = os.path.join(TIMESTAMP_DIR, "resume")
    CONNECTIONS_DIR = os.path.join(TIMESTAMP_DIR, "connections")

    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(COLLECT_DIR, exist_ok=True)
    os.makedirs(RESUME_DIR, exist_ok=True)
    if not args.discovery and not args.ping_matrix:
        os.makedirs(CONNECTIONS_DIR, exist_ok=True)

    orchestrator_log = os.path.join(LOG_DIR, "orchestrator.log")
    def log_orchestrator(msg):
        with open(orchestrator_log, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

    start_time = datetime.now()
    log_orchestrator(f"Extraction Started. Output Root: {TIMESTAMP_DIR}")
    print(f"{C_CYAN}")
    print("============================================================")
    print("           NETWORK DATA EXTRACTOR ORCHESTRATOR           ")
    print("============================================================")
    print(f"Version : {APP_VERSION}")
    print(f"Date    : {APP_DATE}")
    print("============================================================")
    print(f"{C_RESET}")
    print(f"Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Output Root: {TIMESTAMP_DIR}\n")

    if not args.skip_wizard:
        print(f"{C_CYAN}--- Interactive Configuration Wizard ---{C_RESET}")
        print(f"Loaded {C_GREEN}config/settings.json{C_RESET} defaults:")
        print(f"  * Threads          : {args.threads}")
        print(f"  * Extractor Base   : {args.outbase}")
        print(f"  * Elements File    : {args.elements}")
        print(f"  * Filter           : {args.filter if args.filter else 'None'}")
        print(f"  * Commands File    : {args.commands}")
        print(f"  * Randomize Order  : {args.randomize}")
        print(f"  * SSH Timeout      : {SSH_TIMEOUT}s")
        print(f"  * Command Delay    : {CMD_DELAY}s")
        print(f"  * Ignored Virtuals : {len(IGNORE_VIRTUAL_PREFIXES)} prefixes defined")
        print(f"  * Neighbor Matches : {len(NEIGHBOR_PREFIXES)} patterns defined")
        print(f"  * Ignored Discover : {len(IGNORE_NEW_PREFIXES)} prefixes defined")
        print(f"{C_CYAN}----------------------------------------{C_RESET}")
        
        try:
            use_defaults = input("Use these default configurations? [Y/n]: ").strip().lower()
            if use_defaults not in ['n', 'no', 'false', '0']:
                print("Accepting defaults. Skipping granular setup...\n")
            else:
                print("\nPress [ENTER] to accept the [] default value, or type a new value.")
                # Prompt for Threads
                inp_threads = input(f"  * Threads          [{args.threads}]: ").strip()
                if inp_threads: args.threads = int(inp_threads)
                
                # Prompt for Extractor Base
                inp_outbase = input(f"  * Extractor Base   [{args.outbase}]: ").strip()
                if inp_outbase: args.outbase = inp_outbase
                
                # Prompt for Elements File
                inp_elements = input(f"  * Elements File    [{args.elements}]: ").strip()
                if inp_elements: args.elements = inp_elements
                
                # Prompt for Commands File
                inp_commands = input(f"  * Commands File    [{args.commands}]: ").strip()
                if inp_commands: args.commands = inp_commands

                # Prompt for Filter
                inp_filter = input(f"  * Filter Mode      [{args.filter if args.filter else 'None'}]: ").strip()
                if inp_filter: 
                    if inp_filter.lower() == 'none': args.filter = None
                    else: args.filter = inp_filter
                
                # Prompt for Randomize
                inp_rand = input(f"  * Randomize Order  [{args.randomize}] (y/n): ").strip().lower()
                if inp_rand in ['y', 'yes', 'true', '1']:
                    args.randomize = True
                elif inp_rand in ['n', 'no', 'false', '0']:
                    args.randomize = False

                # Prompt for SSH Timeout
                inp_ssh_time = input(f"  * SSH Timeout      [{SSH_TIMEOUT}]: ").strip()
                if inp_ssh_time: 
                    SSH_TIMEOUT = int(inp_ssh_time)
                    json_config['ssh']['timeout'] = SSH_TIMEOUT
                    
                # Prompt for Command Delay
                inp_cmd_delay = input(f"  * Command Delay    [{CMD_DELAY}]: ").strip()
                if inp_cmd_delay: 
                    CMD_DELAY = int(inp_cmd_delay)
                    json_config['ssh']['delay_between_commands'] = CMD_DELAY
                    
                # Persist interactive changes back to settings.json purely for child scripts to read
                try:
                    with open("config/settings.json", "w") as f:
                        json.dump(json_config, f, indent=4)
                except Exception as e:
                    print(f"Warning: Could not save interactive overrides to settings.json: {e}")
                
        except KeyboardInterrupt:
            print("\nAborted by user.")
            sys.exit(130)
        
        # Re-evaluate TIMESTAMP_DIR just in case Outbase changed
        TIMESTAMP_DIR = os.path.abspath(os.path.join(args.outbase, DIR_SUFFIX))
        LOG_DIR = os.path.join(TIMESTAMP_DIR, "log")
        COLLECT_DIR = os.path.join(TIMESTAMP_DIR, "collect")
        RESUME_DIR = os.path.join(TIMESTAMP_DIR, "resume")
        CONNECTIONS_DIR = os.path.join(TIMESTAMP_DIR, "connections")

        os.makedirs(LOG_DIR, exist_ok=True)
        os.makedirs(COLLECT_DIR, exist_ok=True)
        os.makedirs(RESUME_DIR, exist_ok=True)
        if not args.ping_matrix:
            os.makedirs(CONNECTIONS_DIR, exist_ok=True)
        
        print(f"{C_CYAN}----------------------------------------{C_RESET}")
        print(f"Extraction initializing...")
        print("")

cwd = os.getcwd()


def run_and_stream_capture(cmd, env=None, out_path=None):
    """
    Executes cmd (list) and:
     - streams stdout+stderr SILENTLY to out_path log file (no terminal echo)
    Returns returncode.
    """
    # Open output file if needed
    out_file = None
    if out_path:
        out_file = open(out_path, "w", encoding="utf-8", errors="replace")

    # Start process overriding standard buffers
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, bufsize=1, universal_newlines=True)

    try:
        # Stream read bounds in real-time
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                # log to file (no sys.stdout.write to prevent terminal noise)
                if out_file:
                    out_file.write(line)
                    out_file.flush()
    except KeyboardInterrupt:
        print("\nInterrupted by user. Killing child process.")
        proc.kill()
        proc.wait()
        if out_file:
            out_file.close()
        return 130
    finally:
        # Ensures clean teardown
        proc.stdout.close()

    rc = proc.wait()
    if out_file:
        out_file.close()
    return rc


def check_data_presence(script_path, collect_dir, resume_dir):
    """Returns True if there is data for the script to process."""
    script_name = os.path.basename(script_path)
    
    if script_name == "commands.py": 
        return True
        
    if script_name.startswith("show."):
         # parsers/show.X.py -> *.show.X.txt
         cmd_part = script_name.replace(".py", "")
         return len(glob(os.path.join(collect_dir, f"*.{cmd_part}.txt"))) > 0

    if script_name == "system_asset.py":
        # system_asset.py parses Datacom show system, and Cisco show version / show platform
        return any(len(glob(os.path.join(collect_dir, pat))) > 0 for pat in ["*.show.system.txt", "*.show.version.txt", "*.show.platform.txt"])

    if script_name == "transceiver_matrix.py":
        # transceiver_matrix.py parses Datacom hardware-status AND Cisco inventory/inventory details
        return any(len(glob(os.path.join(collect_dir, pat))) > 0 for pat in [
            "*.show.hardware-status.transceivers.detail.txt",
            "*.show.inventory.details.txt", 
            "*.show.inventory.txt"
        ])

    if script_name == "subcomponents.py":
        # subcomponents.py parses show inventory
        return any(len(glob(os.path.join(collect_dir, pat))) > 0 for pat in ["*.show.inventory.txt", "*.show.inventory.details.txt"])

    if script_name == "license_matrix.py":
        return any(len(glob(os.path.join(collect_dir, pat))) > 0 for pat in ["*.show.license.summary.txt", "*.show.license.feature.txt", "*.show.license.txt"])

    if script_name == "port_census.py":
        return os.path.isfile(os.path.join(resume_dir, "interfaces_all.csv"))

    if script_name == "generate_service_inventory.py":
        return os.path.isfile(os.path.join(resume_dir, "show_lldp_neighbors_detail_all.csv"))

    if script_name == "lldp_consistency_checker.py":
         return os.path.isfile(os.path.join(resume_dir, "show_lldp_neighbors_detail_all.csv"))

    if script_name == "interface2connection.py":
         return os.path.isfile(os.path.join(resume_dir, "interfaces_all.csv"))

    if script_name == "topology_checker.py":
         # Check in the connections directory, which is a sibling to resume
         conn_dir = os.path.join(os.path.dirname(resume_dir), "connections")
         return os.path.isfile(os.path.join(conn_dir, "topology.connections.csv"))
    
    if script_name == "element_status.py":
         return len(glob(os.path.join(collect_dir, "*.txt"))) > 0

    return True


# --- EXECUTION ENGINE ---
current_elements_file = args.elements

if getattr(args, 'filter', None):
    log_orchestrator(f"Applying filter: {args.filter} to {args.elements}")
    mode = "in"
    f_str = args.filter.strip()
    
    if f_str.startswith("rn:"):
        mode = "rn"
        f_str = f_str[3:]
    elif f_str.startswith("in:"):
        mode = "in"
        f_str = f_str[3:]
    else:
        # Default to 'in' if omitted as per user request
        mode = "in"
        
    patterns = [p for p in f_str.split(';') if p]
    filtered_file = os.path.join(TIMESTAMP_DIR, "filtered_elements.cfg")
    keep_count = drop_count = 0
    
    try:
        with open(args.elements, 'r', encoding='utf-8') as fin, open(filtered_file, 'w', encoding='utf-8') as fout:
            for line in fin:
                ln = line.strip()
                if not ln or ln.startswith('#'):
                    fout.write(line)
                    continue
                
                hostname = ln.split(';')[0]
                match = any(hostname.startswith(p) for p in patterns)
                
                keep = match if mode == "in" else not match
                    
                if keep:
                    fout.write(line)
                    keep_count += 1
                else:
                    drop_count += 1
                    
        print(f"{C_CYAN}>>> FILTER APPLIED: {mode.upper()} {patterns} <<<{C_RESET}")
        print(f"Elements kept: {C_GREEN}{keep_count}{C_RESET} | Dropped: {C_YELLOW}{drop_count}{C_RESET}\n")
        log_orchestrator(f"Filter applied. Kept: {keep_count}, Dropped: {drop_count}")
        current_elements_file = filtered_file
        
    except Exception as e:
        print(f"{C_RED}Error applying filter: {e}{C_RESET}")
        log_orchestrator(f"Error applying filter: {e}")

known_elements_chain = [current_elements_file]
current_hop = 0
max_hops = args.hops if args.discovery else 0

# Define consolidation scripts to be run after each full parsing cycle
consolidation_scripts = [
    "parsers/system_asset.py",
    "parsers/transceiver_matrix.py",
    "parsers/port_census.py",
    "parsers/subcomponents.py",
    "parsers/license_matrix.py",
    "parsers/generate_service_inventory.py",
    "parsers/show.bgp.vpnv4.unicast.all.summary.py",
    "core/lldp_consistency_checker.py"
]

# When discovery is active, we focus ONLY on essential scripts to map the network faster.
if args.ping_matrix:
    # Exclusive Ping Matrix runner
    SCRIPTS = ["core/ping_matrix.py"]
    consolidation_scripts = []
elif args.discovery:
    # Whitelist of scripts needed for discovery
    discovery_essential = [
        "core/commands.py",
        "parsers/show.lldp.neighbors.detail.py",
        "core/element_status.py"
    ]
    SCRIPTS = [s for s in SCRIPTS if s in discovery_essential]
    consolidation_scripts = [] # Skip all consolidation during discovery hops

while True:
    log_orchestrator(f"--- STARTING HOP {current_hop} (Elements: {current_elements_file}) ---")
    if current_hop > 0:
        print(f"\n{C_CYAN}>>> DISCOVERY HOP {current_hop}/{max_hops} <<<{C_RESET}")
        print(f"Targeting: {current_elements_file}\n")

    total_scripts = len(SCRIPTS)
    for i, script in enumerate(SCRIPTS, start=1):
        step_prefix = f"[{i:2d}/{total_scripts:2d}] {script:40s}"
        # Determine script display name and path
        script_name = os.path.basename(script)
        script_path = os.path.join(cwd, script)
        
        if not os.path.isfile(script_path):
            print(f"{step_prefix} {C_RED}[SKIPPED - NOT FOUND]{C_RESET}")
            log_orchestrator(f"Skipped {script_name}: File not found at {script_path}")
            continue

        log_orchestrator(f"Executing {script_name}...")

        if not args.force and not check_data_presence(script, COLLECT_DIR, RESUME_DIR):
            print(f"{step_prefix} {C_YELLOW}[SKIPPED - NO DATA]{C_RESET}")
            log_orchestrator(f"Skipped {script_name}: No data found in collect/ to process.")
            continue

        cmd = [sys.executable, script_path]

        if script_name == "commands.py":
            if args.offline:
                print(f"{step_prefix} {C_YELLOW}[SKIPPED - OFFLINE MODE]{C_RESET}")
                log_orchestrator(f"Skipped {script_name}: Running in offline mode.")
                continue
                
            cmd.extend(["--outdir", COLLECT_DIR, "--resumedir", RESUME_DIR, "--logdir", LOG_DIR, "--threads", str(args.threads), "--elements", current_elements_file, "--commands", args.commands])
            if args.randomize:
                cmd.append("--randomize")
            else:
                cmd.append("--no-randomize")
            print(f">>> {C_CYAN}core/commands.py{C_RESET} is running. Extracted data goes to: collect/")
            try:
                # Let standard bounds stay active for user password inputs, but pass our modified env
                script_start_time = datetime.now()
                
                # Setup environment for this subprocess specifically
                cmd_env = os.environ.copy()
                cmd_env["PYTHONIOENCODING"] = "utf-8"
                if args.user: cmd_env["NDX_SSH_USER"] = args.user
                if args.password is not None: cmd_env["NDX_SSH_PASS"] = args.password
                if args.key: cmd_env["NDX_SSH_KEY"] = args.key
                
                rc = subprocess.run(cmd, env=cmd_env)
                script_duration = (datetime.now() - script_start_time).total_seconds()
                
                status_text = f"{C_GREEN}[SUCCESS]{C_RESET}" if rc.returncode == 0 else f"{C_RED}[FAILED ]{C_RESET}"
                log_orchestrator(f"{script_name} Finished. Return Code: {rc.returncode}")
                print(f"{step_prefix} {status_text} ({script_duration:5.1f}s)")
                
                if rc.returncode == 100 and not args.force:
                    if args.discovery and current_hop > 0:
                        print(f"\n{C_YELLOW}WARNING: No data collected in Hop {current_hop}. Stopping recursion but proceeding to consolidation.{C_RESET}")
                        log_orchestrator(f"Discovery hop {current_hop} failed to collect data. Breaking recursion.")
                        break # Break the discovery while loop
                    else:
                        print(f"\n{C_RED}ERROR: No data collected from any element. Stopping here.{C_RESET}")
                        print(f"Check {LOG_DIR}/commands.log for connection details.")
                        log_orchestrator("Stopping orchestrator: No data collected.")
                        sys.exit(100)
            except KeyboardInterrupt:
                print(f"{step_prefix} {C_RED}[INTERRUPTED]{C_RESET}")
                log_orchestrator("Orchestrator interrupted by user during commands.py")
                sys.exit(130)
            except Exception as e:
                log_orchestrator(f"{script_name} Error: {e}")
                print(f"{step_prefix} {C_RED}[ERROR]{C_RESET}")
        elif script_name == "element_status.py":
            cmd.extend(["--collect_dir", COLLECT_DIR, "--resume_dir", RESUME_DIR, "--elements_cfg", current_elements_file, "--settings", args.settings])
            safe_name = "element_status"
            out_file_name = os.path.join(LOG_DIR, f"{safe_name}.log")
            
            try:
                with open(out_file_name, "w", encoding="utf-8") as fh:
                    fh.write(f"COMMAND: {' '.join(cmd)}\n")
                    fh.write("START: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n")
            except:
                out_file_name = None

            script_start_time = datetime.now()
            rc = run_and_stream_capture(cmd, env=None, out_path=out_file_name)
            if rc == 130:
                log_orchestrator(f"Orchestrator interrupted by user during {script_name}")
                sys.exit(130)
                
            script_duration = (datetime.now() - script_start_time).total_seconds()
            log_orchestrator(f"{script_name} Finished. Return Code: {rc}")
            
            status_text = f"{C_GREEN}[SUCCESS]{C_RESET}" if rc == 0 else f"{C_RED}[FAILED ]{C_RESET}"
            print(f"{step_prefix} {status_text} ({script_duration:5.1f}s)")
            if rc != 0:
                 print(f"    └─> {C_RED}Check log/{safe_name}.log for details.{C_RESET}")
        elif script_name == "ping_matrix.py":
            cmd.extend(["--collect_dir", COLLECT_DIR, "--resume_dir", RESUME_DIR, "--logdir", LOG_DIR, "--elements_cfg", current_elements_file, "--settings", args.settings, "--ping_commands", args.ping_commands, "--ping_format", args.ping_format])
            if args.offline:
                cmd.append("--offline_mode")
            safe_name = "ping_matrix"
            out_file_name = os.path.join(LOG_DIR, f"{safe_name}.log")
            
            # Repassar environment auth info to ping_matrix similarly to commands.py
            cmd_env = os.environ.copy()
            if args.user: cmd_env["NDX_SSH_USER"] = args.user
            if args.password is not None: cmd_env["NDX_SSH_PASS"] = args.password
            if args.key: cmd_env["NDX_SSH_KEY"] = args.key
            
            print(f">>> {C_CYAN}core/ping_matrix.py{C_RESET} is running ICMP multithreading test.")
            script_start_time = datetime.now()
            rc_ping = subprocess.run(cmd, env=cmd_env)
            script_duration = (datetime.now() - script_start_time).total_seconds()
            status_text = f"{C_GREEN}[SUCCESS]{C_RESET}" if rc_ping.returncode == 0 else f"{C_RED}[FAILED ]{C_RESET}"
            log_orchestrator(f"{script_name} Finished. Return Code: {rc_ping.returncode}")
            print(f"{step_prefix} {status_text} ({script_duration:5.1f}s)")
            
        else:
            cmd.extend(["--outdir", RESUME_DIR, "--indir", COLLECT_DIR])
            # Scripts output real-time to std and file automatically
            safe_name = script_name.replace(".py", "")
            out_file_name = os.path.join(LOG_DIR, f"{safe_name}.log")
            # Initialize execution header
            try:
                with open(out_file_name, "w", encoding="utf-8") as fh:
                    fh.write(f"COMMAND: {' '.join(cmd)}\n")
                    fh.write("START: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n")
            except Exception as e:
                log_orchestrator(f"Warning: unable to create log for {script_name}: {e}")
                out_file_name = None

            script_start_time = datetime.now()
            rc = run_and_stream_capture(cmd, env=None, out_path=out_file_name)
            if rc == 130:
                log_orchestrator(f"Orchestrator interrupted by user during {script_name}")
                sys.exit(130)
                
            script_end_time = datetime.now()
            script_duration = (script_end_time - script_start_time).total_seconds()
            log_orchestrator(f"{script_name} Finished. Return Code: {rc}. Duration: {script_duration:.2f}s")
            
            status = "SUCCESS" if rc == 0 else "FAILURE/WARNING"
            status_text = f"{C_GREEN}[SUCCESS]{C_RESET}" if rc == 0 else f"{C_RED}[FAILED ]{C_RESET}"

            # After finishing, append summary block to the file
            if out_file_name:
                try:
                    with open(out_file_name, "a", encoding="utf-8") as fh:
                        fh.write(f"\n\n--- EXECUTION SUMMARY ---\n")
                        fh.write(f"FINAL STATUS: {status} (Return Code: {rc})\n")
                        fh.write(f"PROCESSING TIME: {script_duration:.2f} seconds\n")
                        fh.write("END: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
                except Exception as e:
                    pass # Silently drop missing summary lines instead of breaking terminal display

            print(f"{step_prefix} {status_text} ({script_duration:5.1f}s)")
            if rc != 0:
                 print(f"    └─> {C_RED}Check log/orchestrator.log or log/{safe_name}.log for details.{C_RESET}")

    # Specialized consolidation scripts
    if not args.ping_matrix:
        print(f"\n{C_CYAN}--- Consolidating Parsers ---{C_RESET}")
    for script_rel in consolidation_scripts:
        script_name = os.path.basename(script_rel)
        script_abs = os.path.join(cwd, script_rel)
        
        if not os.path.isfile(script_abs):
            print(f"[*] {script_name:40s} {C_RED}[SKIPPED - NOT FOUND]{C_RESET}")
            log_orchestrator(f"Skipped {script_name}: File not found at {script_abs}")
            continue
        
        if not args.force and not check_data_presence(script_rel, COLLECT_DIR, RESUME_DIR):
            print(f"[*] {script_name:40s} {C_YELLOW}[SKIPPED - NO DATA]{C_RESET}")
            log_orchestrator(f"Skipped {script_name}: No data found to process.")
            continue
        
        log_orchestrator(f"Executing {script_name}...")
        
        # Determine specific arguments for each consolidation script
        if script_name in ["generate_service_inventory.py", "lldp_consistency_checker.py"]:
            cmd = [sys.executable, script_abs, "--resume_dir", RESUME_DIR]
        elif script_name in ["subcomponents.py", "license_matrix.py", "show.bgp.vpnv4.unicast.all.summary.py"]:
            cmd = [sys.executable, script_abs, "--collect_dir", COLLECT_DIR, "--outdir", RESUME_DIR]
        elif script_name == "port_census.py":
            cmd = [sys.executable, script_abs, "--resume_dir", RESUME_DIR, "--outdir", RESUME_DIR]
        else:
            # system_asset.py and transceiver_matrix.py use --collect_dir and --resume_dir
            cmd = [sys.executable, script_abs, "--collect_dir", COLLECT_DIR, "--resume_dir", RESUME_DIR]

        out_log = os.path.join(LOG_DIR, f"{script_name.replace('.py','')}.log")
        
        script_start_time = datetime.now()
        rc = run_and_stream_capture(cmd, out_path=out_log)
        script_duration = (datetime.now() - script_start_time).total_seconds()
        
        status = f"{C_GREEN}[SUCCESS]{C_RESET}" if rc == 0 else f"{C_RED}[FAILED ]{C_RESET}"
        print(f"[*] {script_name:40s} {status} ({script_duration:5.1f}s)")
        if rc != 0:
            print(f"    └─> {C_RED}Check log/{script_name.replace('.py','')}.log for details.{C_RESET}")
        log_orchestrator(f"{script_name} Finished. Return Code: {rc}. Duration: {script_duration:.2f}s")


    # Final Topology Mapping
    if not args.ping_matrix:
        print(f"\n{C_CYAN}--- Final Topology Mapping ---{C_RESET}")
        scripts_final = ["core/interface2connection.py", "core/topology_checker.py"]
    else:
        scripts_final = []
    isolated_count = 0
    for s_rel in scripts_final:
        s_name = os.path.basename(s_rel)
        s_abs = os.path.join(cwd, s_rel)

        if not os.path.isfile(s_abs):
            print(f"[*] {s_name:40s} {C_RED}[SKIPPED - NOT FOUND]{C_RESET}")
            log_orchestrator(f"Skipped {s_name}: File not found at {s_abs}")
            continue
        
        if args.discovery:
            # Skip topology mapping during discovery hops to maximize speed
            continue

        if not args.force and not check_data_presence(s_rel, COLLECT_DIR, RESUME_DIR):
            print(f"[*] {s_name:40s} {C_YELLOW}[SKIPPED - NO DATA]{C_RESET}")
            log_orchestrator(f"Skipped {s_name}: No data found to process.")
            continue

        log_orchestrator(f"Executing {s_name}...")
        cmd = [sys.executable, s_abs]
        out_log = os.path.join(LOG_DIR, f"{s_name.replace('.py','')}.log")

        if s_name == "interface2connection.py":
            cmd.extend(["--input", RESUME_DIR, "--output", CONNECTIONS_DIR])
        elif s_name == "topology_checker.py":
            cmd.extend(["--resume_dir", RESUME_DIR, "--connections_dir", CONNECTIONS_DIR])
        
        script_start_time = datetime.now()
        rc = run_and_stream_capture(cmd, out_path=out_log)
        script_duration = (datetime.now() - script_start_time).total_seconds()

        if s_name == "topology_checker.py" and rc == 50:
            print(f"[*] {s_name:40s} {C_YELLOW}[WARNING]{C_RESET} ({script_duration:5.1f}s)")
            print(f"    └─> {C_YELLOW}Isolated node(s) detected. Check audit logs.{C_RESET}")
            isolated_csv_path = os.path.join(RESUME_DIR, "topology_warnings.isolated.csv")
            if os.path.isfile(isolated_csv_path):
                with open(isolated_csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f, delimiter=';')
                    isolated_count = sum(1 for _ in reader)
        else:
            status = f"{C_GREEN}[SUCCESS]{C_RESET}" if rc == 0 else f"{C_RED}[FAILED ]{C_RESET}"
            print(f"[*] {s_name:40s} {status} ({script_duration:5.1f}s)")
            if rc != 0:
                print(f"    └─> {C_RED}Check log/{s_name.replace('.py','')}.log for details.{C_RESET}")
        log_orchestrator(f"{s_name} Finished. Return Code: {rc}. Duration: {script_duration:.2f}s")


    # DISCOVERY HOOK
    if args.discovery and current_hop < max_hops:
        print(f"\n{C_YELLOW}--- Running Discovery (Hop {current_hop+1}/{max_hops}) ---{C_RESET}")
        log_orchestrator(f"Running discovery for hop {current_hop+1}")
        disco_script = os.path.join(cwd, "core", "discovery.py")
        disco_fname = f"discovery_hop_{current_hop+1}.elements.cfg"
        disco_out = os.path.join(RESUME_DIR, disco_fname)
        
        # Pass ALL known elements files to the skip list, but also keep the ORIGINAL SEEDS separate
        elements_skip_str = ",".join(known_elements_chain)
        success_keys_path = os.path.join(RESUME_DIR, "successful_keys.csv")
        cmd_disco = [
            sys.executable, disco_script, 
            "--resume_dir", RESUME_DIR, 
            "--resumedir", RESUME_DIR, 
            "--elements_cfg", elements_skip_str, 
            "--seeds_cfg", args.elements,
            "--successful_keys", success_keys_path,
            "--outdir", RESUME_DIR, 
            "--out_filename", disco_fname, 
            "--settings", args.settings
        ]
        
        disco_log_path = os.path.join(LOG_DIR, f"discovery_hop_{current_hop+1}.log")
        
        try:
            disco_start_time = datetime.now()
            with open(disco_log_path, "w", encoding="utf-8") as fh:
                fh.write(f"COMMAND: {' '.join(cmd_disco)}\n")
                fh.write("START: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n")
                fh.flush() # Ensure header is written before subprocess starts
                
                rc_disco = subprocess.run(cmd_disco, stdout=fh, stderr=fh, text=True)
            
            disco_duration = (datetime.now() - disco_start_time).total_seconds()
            
            with open(disco_log_path, "a", encoding="utf-8") as fh:
                fh.write(f"\n\n--- EXECUTION SUMMARY ---\n")
                fh.write(f"FINAL STATUS: {'SUCCESS' if rc_disco.returncode == 0 else 'FAILURE/WARNING'} (Return Code: {rc_disco.returncode})\n")
                fh.write(f"PROCESSING TIME: {disco_duration:.2f} seconds\n")
                fh.write("END: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")

        except Exception as e:
            log_orchestrator(f"Discovery script execution failed: {e}")
            rc_disco = type('obj', (object,), {'returncode' : 1})() # Mock a failed result
            disco_duration = 0

        log_orchestrator(f"Discovery script finished. Return Code: {rc_disco.returncode}. Output: {disco_out}")
        
        if rc_disco.returncode == 0 and os.path.isfile(disco_out):
            # Check if it has any new elements (non-comment lines)
            has_new = False
            with open(disco_out, 'r') as f:
                for line in f:
                    if line.strip() and not line.strip().startswith('#'):
                        has_new = True
                        break
            
            if has_new:
                known_elements_chain.append(disco_out)
                current_elements_file = disco_out
                current_hop += 1
                log_orchestrator(f"Discovery found new elements. Advancing to hop {current_hop}")
                print(f"{C_GREEN}Discovery found new elements. Advancing to hop {current_hop}.{C_RESET}")
                continue # Next iteration of the while loop
            else:
                print(f"{C_YELLOW}No new elements discovered. Ending recursion.{C_RESET}")
                log_orchestrator("No new elements discovered. Ending recursion.")
        else:
            print(f"{C_RED}Discovery script failed or no new elements file generated. Ending recursion.{C_RESET}")
            log_orchestrator("Discovery script failed or no new elements file generated. Ending recursion.")
    
    # FINAL DISCOVERY RUN (to process LLDP data from the VERY LAST hop)
    if args.discovery:
        print(f"\n{C_YELLOW}--- Final Discovery Consolidation ---{C_RESET}")
        log_orchestrator("Running final discovery consolidation")
        
        elements_skip_str = ",".join(known_elements_chain)
        success_keys_path = os.path.join(RESUME_DIR, "successful_keys.csv")
        # We don't need a new .elements.cfg here, just updating the CSV report
        cmd_final_disco = [
            sys.executable, disco_script, 
            "--resume_dir", RESUME_DIR, 
            "--resumedir", RESUME_DIR, 
            "--elements_cfg", elements_skip_str, 
            "--seeds_cfg", args.elements,
            "--successful_keys", success_keys_path,
            "--outdir", RESUME_DIR, 
            "--out_filename", "final_discovery_run.tmp",
            "--settings", args.settings
        ]
        subprocess.run(cmd_final_disco, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(os.path.join(RESUME_DIR, "final_discovery_run.tmp")):
            os.remove(os.path.join(RESUME_DIR, "final_discovery_run.tmp"))

    break # Exit the while loop

print(f"\n{C_GREEN}============================================================{C_RESET}")
print(f"Final Execution Finished. Output in: {TIMESTAMP_DIR}")
print(f"Duration: {(datetime.now()-start_time).total_seconds():.1f}s")
print(f"{C_GREEN}============================================================{C_RESET}")

end_time = datetime.now()

# --- CONSOLIDATION RUN SUMMARY ---
status_csv_path = os.path.join(RESUME_DIR, "status.elements.csv")
ok_count = 0
fail_count = 0
new_count = 0
if os.path.isfile(status_csv_path):
    with open(status_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            st = row.get("status", "")
            if st == "ok": ok_count += 1
            elif st == "fail": fail_count += 1
            elif st == "new": new_count += 1

print("\n" + "=" * 60)
if args.ping_matrix:
    print(f"{C_CYAN}                PING MATRIX SUMMARY{C_RESET}")
    print("=" * 60)
    print(f"  * Mode             : Origin x Destination Pings")
    print(f"  └─> View Matrix in : resume/ping_matrix_list.csv")
else:
    print(f"{C_CYAN}                CONSOLIDATION SUMMARY{C_RESET}")
    print("=" * 60)
    print(f"  * Collected (OK)   : {C_GREEN}{ok_count}{C_RESET} elements")
    print(f"  * Failed (FAIL)    : {C_RED}{fail_count}{C_RESET} elements")
    print(f"  * Discovered (NEW) : {C_YELLOW}{new_count}{C_RESET} elements")
    if isolated_count > 0:
        print(f"  * Topology Iso.    : {C_YELLOW}{isolated_count} WARNINGS{C_RESET} (missing from LLDP map)")
    print("  └─> View full report in: resume/status.elements.csv")
    if isolated_count > 0:
        print("  └─> View isolation in  : resume/topology_warnings.isolated.csv")
print("=" * 60)

log_orchestrator("Extraction Ended")
print("\n" + "-" * 60)
print("End:", end_time.strftime("%Y-%m-%d %H:%M:%S"))

duration = end_time - start_time
total_seconds = int(duration.total_seconds())
hours = total_seconds // 3600
minutes = (total_seconds % 3600) // 60
seconds = total_seconds % 60
# --- MASTER INDEX DASHBOARD ---
def generate_master_dashboard(outbase):
    import re
    index_path = os.path.join(outbase, "index.html")
    directories = glob(os.path.join(outbase, "20*_*"))
    directories.sort(reverse=True)
    
    runs = []
    for d in directories:
        basename = os.path.basename(d)
        json_file = os.path.join(d, "resume", "ping_matrix_list.json")
        html_file = os.path.join(d, "resume", "ping_matrix_dashboard.html")
        
        if os.path.isfile(html_file) and os.path.isfile(json_file):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Filter out empty or partial runs without valid data
                if not data.get("data") or len(data.get("data", [])) == 0:
                    continue
                
                metadata = data.get("metadata", {})
                health = metadata.get("network_health", {})
                node_count = metadata.get("nodes_connected", 0)
                
                # Derive display date from folder name
                try:
                    dt_label = f"{basename[:4]}-{basename[4:6]}-{basename[6:8]} {basename[9:11]}:{basename[11:13]}:{basename[13:15]}"
                except:
                    dt_label = basename
                
                runs.append({
                    "id": basename,
                    "label": dt_label,
                    "nodes": node_count,
                    "healthy": health.get("healthy", 0),
                    "warn": health.get("warning", 0),
                    "crit": health.get("critical", 0),
                    "dead": health.get("dead", 0),
                    "path": f"{basename}/resume/ping_matrix_dashboard.html"
                })
            except:
                continue

    if not runs:
        return

    # Sort runs by ID descending (newest first)
    runs.sort(key=lambda x: x["id"], reverse=True)

    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Ping Matrix Master Index</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@400;600;800&display=swap" rel="stylesheet">
    <style>
        body { margin: 0; padding: 0; font-family: 'Inter', sans-serif; display: flex; height: 100vh; background: #020617; color: #e2e8f0; overflow: hidden; }
        
        /* Sidebar */
        .sidebar { 
            width: 320px; min-width: 320px;
            background: #0f172a; 
            border-right: 1px solid rgba(255,255,255,0.05); 
            display: flex; flex-direction: column;
            box-shadow: 10px 0 30px rgba(0,0,0,0.5);
            z-index: 10;
        }
        .sidebar-header {
            padding: 25px 20px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .sidebar-header h1 {
            font-family: 'Outfit', sans-serif;
            font-size: 22px; font-weight: 800; margin: 0;
            background: linear-gradient(90deg, #38bdf8, #818cf8);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        .sidebar-header p { font-size: 11px; color: #64748b; margin: 5px 0 0 0; text-transform: uppercase; letter-spacing: 1px; font-weight: 600; }
        
        .run-list { flex-grow: 1; overflow-y: auto; padding: 15px 12px; }
        .run-list::-webkit-scrollbar { width: 4px; }
        .run-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 10px; }
        
        .run-item {
            padding: 16px; margin-bottom: 12px;
            background: rgba(30, 41, 59, 0.4);
            border: 1px solid rgba(255,255,255,0.03);
            border-radius: 12px; cursor: pointer;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            border-left: 4px solid transparent;
        }
        .run-item:hover {
            background: rgba(30, 41, 59, 0.7);
            transform: translateX(4px);
            border-color: rgba(56,189,248,0.3);
        }
        .run-item.active {
            background: rgba(30, 41, 59, 1);
            border-left-color: #38bdf8;
            box-shadow: 0 8px 25px rgba(0,0,0,0.4);
            border-color: rgba(56,189,248,0.2);
        }
        
        .run-item .date { font-size: 14px; font-weight: 700; color: #f1f5f9; margin-bottom: 10px; font-family: 'Outfit', sans-serif; display: flex; align-items: center; gap: 8px; }
        .run-item .stats { display: flex; gap: 10px; align-items: center; margin-top: 5px; }
        .stat-group { display: flex; align-items: center; gap: 4px; }
        .stat-dot { width: 7px; height: 7px; border-radius: 50%; }
        .stat-val { font-size: 12px; color: #94a3b8; font-weight: 600; }
        
        .nodes-badge {
            position: absolute; top: 16px; right: 16px;
            font-size: 10px; padding: 2px 8px; border-radius: 6px;
            background: rgba(56,189,248,0.1); color: #38bdf8;
            border: 1px solid rgba(56,189,248,0.2);
            font-weight: 700;
        }
        
        /* Main View */
        .main-content { flex-grow: 1; position: relative; background: #020617; display: flex; flex-direction: column; }
        #viewer { width: 100%; height: 100%; border: none; }
        
        #placeholder {
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            text-align: center; transition: opacity 0.3s ease;
        }
        #placeholder h2 { font-family: 'Outfit', sans-serif; font-size: 28px; margin-bottom: 10px; color: #1e293b; }
        #placeholder p { color: #0f172a; font-weight: 600; }
        
        .footer-logo {
            padding: 15px; text-align: center; font-size: 11px; color: #334155;
            border-top: 1px solid rgba(255,255,255,0.03);
        }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="sidebar-header">
            <h1>📡 Ping Matrix</h1>
            <p>Historical Analysis Portal</p>
        </div>
        <div class="run-list">
"""
    for r in runs:
        html += f"""
            <div class="run-item" onclick="loadRun('{r['path']}', this)">
                <div class="nodes-badge">{r['nodes']} Nodes</div>
                <div class="date">📅 {r['label']}</div>
                <div class="stats">
                    <div class="stat-group" title="Healthy"><span class="stat-dot" style="background:#4ade80"></span><span class="stat-val">{r['healthy']}</span></div>
                    <div class="stat-group" title="Warning"><span class="stat-dot" style="background:#fbbf24"></span><span class="stat-val">{r['warn']}</span></div>
                    <div class="stat-group" title="Critical"><span class="stat-dot" style="background:#f87171"></span><span class="stat-val">{r['crit']}</span></div>
                    <div class="stat-group" title="Dead"><span class="stat-dot" style="background:#475569"></span><span class="stat-val">{r['dead']}</span></div>
                </div>
            </div>"""

    html += """
        </div>
        <div class="footer-logo">
            Powered by <strong>network-data-extractor</strong>
        </div>
    </div>
    <div class="main-content">
        <iframe id="viewer" src="about:blank"></iframe>
        <div id="placeholder">
            <h2>No run selected</h2>
            <p>Select a historical run from the sidebar to view the dashboard</p>
        </div>
    </div>
    
    <script>
        function loadRun(path, el) {
            document.getElementById('viewer').src = path;
            document.getElementById('placeholder').style.display = 'none';
            document.querySelectorAll('.run-item').forEach(item => item.classList.remove('active'));
            if(el) el.classList.add('active');
        }
        
        // Auto-load first run
        window.onload = () => {
            const first = document.querySelector('.run-item');
            if (first) {
                // Small delay to ensure styles are ready
                setTimeout(() => first.click(), 100);
            }
        };
    </script>
</body>
</html>
"""
    try:
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"\n{C_CYAN}--- Master Index Generated ---{C_RESET}")
        print(f"[*] Portal available at: {index_path}")
    except Exception as e:
        print(f"\n{C_RED}[!] Failed to generate Master Index: {e}{C_RESET}")

if args.ping_matrix:
    generate_master_dashboard(os.path.dirname(TIMESTAMP_DIR))

# --- OUTPUT COMPRESSION ---
comp_cfg = json_config.get("compression", {})
if comp_cfg.get("enabled", False):
    print(f"\n{C_CYAN}--- Minimizing Output (Compression) ---{C_RESET}")
    folders_to_compress = comp_cfg.get("folders", ["collect", "log"])
    comp_format = comp_cfg.get("format", "zip")
    delete_orig = comp_cfg.get("delete_after_compression", True)
    
    for f_name in folders_to_compress:
        f_dir = os.path.join(TIMESTAMP_DIR, f_name)
        if os.path.isdir(f_dir):
            print(f"[*] Compressing {f_name:20s} -> {f_name}.{comp_format}...", end="", flush=True)
            try:
                # shutil.make_archive(base_name, format, root_dir)
                archive_path = os.path.join(TIMESTAMP_DIR, f_name)
                shutil.make_archive(archive_path, comp_format, f_dir)
                print(f" {C_GREEN}[DONE]{C_RESET}")
                
                if delete_orig:
                    shutil.rmtree(f_dir)
            except Exception as e:
                print(f" {C_RED}[FAILED]{C_RESET}: {e}")
                log_orchestrator(f"Compression failed for {f_name}: {e}")

print(f"\n{C_CYAN}🔗 Repository - Follow on GitHub for new versions and updates{C_RESET}")
print(f"\n{C_GREEN}Generate topologies dynamically{C_RESET}")
print("https://github.com/flashbsb/network-topology-generator")
print(f"\n{C_GREEN}Execute massive commands simply and generate connection information between network elements{C_RESET}")
print("https://github.com/flashbsb/network-data-extractor")
print(f"\n{C_GREEN}Dimension backbone topologies for testing:{C_RESET}")
print("https://github.com/flashbsb/backbone-network-topology-generator\n")

sys.exit(0)
