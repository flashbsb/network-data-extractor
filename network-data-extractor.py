#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
           NETWORK DATA EXTRACTOR ORCHESTRATOR           
============================================================
Version : 1.30.0
Date    : 2026-03-09
Author  : flashbsb (and contributors)

Behavior:
 - Does not prompt for credentials initially.
 - When reaching commands.py, executes INTERACTIVELY (stdin/tty connected).
 - For other scripts, executes and streams the output in real-time.
 - Ultimately generates ../infos/DDMMYYYY and consolidates .txt/.csv.
"""

import subprocess
import sys
import os
import shutil
import argparse
import json
import csv
from datetime import datetime
from glob import glob

APP_VERSION = "1.31.0"
APP_DATE = "2026-03-09"

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

Workflow:
  1. Prompts for SSH credentials interactively.
  2. Executes 'core/commands.py' concurrently to gather raw CLI outputs into '<outbase>/YYYYMMDD_HHMMSS/collect/'.
  3. Sequentially process all parsing scripts (parsers/*.py) to generate CSV structures into '<outbase>/YYYYMMDD_HHMMSS/resume/'.
  4. Runs 'core/element_status.py' to generate 'status.elements.csv' inside 'collect/'.
  5. Finally runs 'core/interface2connection.py' to map the physical topology connections.
  6. All execution logs are silently stored in '<outbase>/YYYYMMDD_HHMMSS/log/'.
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

group_ext = parser.add_argument_group("Extraction & Path Settings (ignored in --offline)")
group_ext.add_argument("--settings", type=str, default="config/settings.json", help="Path to JSON settings file (default: config/settings.json)")
group_ext.add_argument("--threads", type=int, default=def_threads, help=f"Number of concurrent SSH sessions (default: {def_threads})")
group_ext.add_argument("--outbase", type=str, default=def_outbase, help=f"Root directory for outputs (default: {def_outbase})")
group_ext.add_argument("--elements", type=str, default=def_elements, help=f"Input elements file (default: {def_elements})")
group_ext.add_argument("--commands", type=str, default=def_commands, help=f"Input commands file (default: {def_commands})")
group_ext.add_argument("--randomize", action="store_true", default=def_randomize, help=f"Randomize connection order (default: {def_randomize})")
group_ext.add_argument("--no-randomize", dest="randomize", action="store_false", help="Keep connection order sequential")

group_auth = parser.add_argument_group("Authentication (ignored in --offline)")
group_auth.add_argument("--user", type=str, help="SSH Username (required for automated auth)")
auth_me = group_auth.add_mutually_exclusive_group()
auth_me.add_argument("--password", type=str, help="[INSECURE] SSH Password (requires --user)")
auth_me.add_argument("--key", type=str, help="Path to SSH Private Key (requires --user)")

group_mode = parser.add_argument_group("Execution Modes")
group_mode.add_argument("--skip-wizard", action="store_true", help="Skip configuration confirmation prompt")
group_mode.add_argument("--force", action="store_true", help="Force execution even if collection fails")
group_mode.add_argument("--offline", type=str, metavar="DIR", help="Process existing data in DIR (skips discovery/SSH)")

group_disco = parser.add_argument_group("Discovery Options (ignored in --offline)")
group_disco.add_argument("--discovery", action="store_true", help="Enable recursive discovery via LLDP neighbors")
group_disco.add_argument("--hops", type=int, help="Number of recursive hops (requires --discovery)")

args = parser.parse_args()

# --- ARGUMENT VALIDATION & LOGIC ---

# 1. Offline Mode Overrides
if args.offline:
    if args.discovery:
        print(f"{C_YELLOW}Warning: --discovery is ignored in --offline mode.{C_RESET}")
        args.discovery = False
    args.hops = 0
    # Values like threads, randomize, user, etc. are naturally ignored by the flow
else:
    # 2. Hops logic (only if NOT offline)
    if args.discovery:
        if args.hops is None:
            args.hops = discovery_cfg.get("default_hops", 3)
    else:
        args.hops = 0

# 3. Authentication logical dependency
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
known_elements_chain = [args.elements]
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
                
            cmd.extend(["--outdir", COLLECT_DIR, "--logdir", LOG_DIR, "--threads", str(args.threads), "--elements", current_elements_file, "--commands", args.commands])
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
                if args.password: cmd_env["NDX_SSH_PASS"] = args.password
                if args.key: cmd_env["NDX_SSH_KEY"] = args.key
                
                rc = subprocess.run(cmd, env=cmd_env)
                script_duration = (datetime.now() - script_start_time).total_seconds()
                
                status_text = f"{C_GREEN}[SUCCESS]{C_RESET}" if rc.returncode == 0 else f"{C_RED}[FAILED ]{C_RESET}"
                log_orchestrator(f"{script_name} Finished. Return Code: {rc.returncode}")
                print(f"{step_prefix} {status_text} ({script_duration:5.1f}s)")
                
                if rc.returncode == 100 and not args.force:
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
            cmd.extend(["--collect_dir", COLLECT_DIR, "--resume_dir", RESUME_DIR, "--elements_cfg", args.elements, "--settings", args.settings])
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
    print(f"\n{C_CYAN}--- Final Topology Mapping ---{C_RESET}")
    scripts_final = ["core/interface2connection.py", "core/topology_checker.py"]
    isolated_count = 0
    for s_rel in scripts_final:
        s_name = os.path.basename(s_rel)
        s_abs = os.path.join(cwd, s_rel)

        if not os.path.isfile(s_abs):
            print(f"[*] {s_name:40s} {C_RED}[SKIPPED - NOT FOUND]{C_RESET}")
            log_orchestrator(f"Skipped {s_name}: File not found at {s_abs}")
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
        disco_out = os.path.join(TIMESTAMP_DIR, disco_fname)
        
        # Pass ALL known elements files to the skip list
        elements_skip_str = ",".join(known_elements_chain)
        cmd_disco = [sys.executable, disco_script, "--resume_dir", RESUME_DIR, "--elements_cfg", elements_skip_str, "--outdir", TIMESTAMP_DIR, "--out_filename", disco_fname, "--settings", args.settings]
        
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
    
    break # Exit the while loop if no discovery or no more hops

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
print(f"Total processing time: {hours:02d}:{minutes:02d}:{seconds:02d}")

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
