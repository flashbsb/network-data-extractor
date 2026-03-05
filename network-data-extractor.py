#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
           NETWORK DATA EXTRACTOR ORCHESTRATOR           
============================================================
Version : 1.28.2
Date    : 2026-03-05
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
import csv
from datetime import datetime
from glob import glob

APP_VERSION = "1.28.2"
APP_DATE = "2026-03-05"

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

parser = argparse.ArgumentParser(
    description=description,
    formatter_class=argparse.RawTextHelpFormatter
)

import json
json_config = {}
if os.path.exists("config/settings.json"):
    try:
        with open("config/settings.json", "r") as f:
            json_config = json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load config/settings.json: {e}")

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

parser.add_argument("--threads", type=int, default=def_threads, help=f"Number of concurrent SSH sessions for commands.py (default: {def_threads})")
parser.add_argument("--outbase", type=str, default=def_outbase, help=f"Root directory base to save timestamps/logs/CSVs folders (default: {def_outbase})")
parser.add_argument("--elements", type=str, default=def_elements, help=f"Input file containing the list of elements (default: {def_elements})")
parser.add_argument("--commands", type=str, default=def_commands, help=f"Input file containing the list of commands (default: {def_commands})")
parser.add_argument("--randomize", action="store_true", default=def_randomize, help=f"Randomize the connection order in commands.py (default: {def_randomize})")
parser.add_argument("--no-randomize", dest="randomize", action="store_false", help="Keep connection order sequential")
parser.add_argument("--skip-wizard", action="store_true", help="Skip the configuration confirmation prompt")
parser.add_argument("--user", type=str, help="SSH Username (if provided, skips interactive prompt)")
parser.add_argument("--password", type=str, help="[WARNING: Insecure for terminal] SSH Password. Use only for automated CRON/CI execution. Consider certificate auth instead.")
parser.add_argument("--key", type=str, help="Path to SSH Private Key (Certificate) for passwordless authentication")
args = parser.parse_args()

# Clear the screen if a plaintext password was passed via CLI to hide it from terminal history
if args.password:
    os.system('clear' if os.name == 'posix' else 'cls')

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

    cmd = [sys.executable, script_path]

    if script_name == "commands.py":
        cmd.extend(["--outdir", COLLECT_DIR, "--logdir", LOG_DIR, "--threads", str(args.threads), "--elements", args.elements, "--commands", args.commands])
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
        except KeyboardInterrupt:
            print(f"{step_prefix} {C_RED}[INTERRUPTED]{C_RESET}")
            log_orchestrator("Orchestrator interrupted by user during commands.py")
            sys.exit(130)
        except Exception as e:
            log_orchestrator(f"{script_name} Error: {e}")
            print(f"{step_prefix} {C_RED}[ERROR]{C_RESET}")
    elif script_name == "element_status.py":
        cmd.extend(["--collect_dir", COLLECT_DIR, "--resume_dir", RESUME_DIR, "--elements_cfg", args.elements])
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

print("\n" + "-" * 60)
step_prefix_sys = f"[**/**] {'parsers/system_asset.py':40s}"
script_sysasset = os.path.join(cwd, "parsers", "system_asset.py")

if os.path.isfile(script_sysasset):
    log_orchestrator(f"Executing parsers/system_asset.py...")
    cmd_sys = [sys.executable, script_sysasset, "--collect_dir", COLLECT_DIR, "--resume_dir", RESUME_DIR]
    sys_log = os.path.join(LOG_DIR, "system_asset.log")
    
    sys_start = datetime.now()
    rc_sys = run_and_stream_capture(cmd_sys, env=None, out_path=sys_log)
    sys_duration = (datetime.now() - sys_start).total_seconds()
    status_sys = "SUCCESS" if rc_sys == 0 else "FAILURE/WARNING"
    status_text_sys = f"{C_GREEN}[SUCCESS]{C_RESET}" if rc_sys == 0 else f"{C_RED}[FAILED ]{C_RESET}"
    
    with open(sys_log, "a", encoding="utf-8") as fh:
        fh.write(f"\n\n--- EXECUTION SUMMARY ---\n")
        fh.write(f"FINAL STATUS: {status_sys} (Return Code: {rc_sys})\n")
        fh.write(f"PROCESSING TIME: {sys_duration:.2f} seconds\n")
        fh.write("END: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
        
    print(f"{step_prefix_sys} {status_text_sys} ({sys_duration:5.1f}s)")
    if rc_sys != 0:
         print(f"    └─> {C_RED}Check log/system_asset.log for details.{C_RESET}")
else:
    print(f"{step_prefix_sys} {C_RED}[SKIPPED - NOT FOUND]{C_RESET}")
    log_orchestrator(f"WARNING: {script_sysasset} not found, skipping hook.")

# ----------------- AXIS 11: Optical Health Matrix -----------------
print("\n" + "-" * 60)
step_prefix_optics = f"[**/**] {'parsers/transceiver_matrix.py':40s}"
script_optics = os.path.join(cwd, "parsers", "transceiver_matrix.py")

if os.path.isfile(script_optics):
    log_orchestrator(f"Executing parsers/transceiver_matrix.py...")
    cmd_optics = [sys.executable, script_optics, "--collect_dir", COLLECT_DIR, "--resume_dir", RESUME_DIR]
    optics_log = os.path.join(LOG_DIR, "transceiver_matrix.log")
    
    optics_start = datetime.now()
    rc_optics = run_and_stream_capture(cmd_optics, env=None, out_path=optics_log)
    optics_duration = (datetime.now() - optics_start).total_seconds()
    status_optics = "SUCCESS" if rc_optics == 0 else "FAILURE/WARNING"
    status_text_optics = f"{C_GREEN}[SUCCESS]{C_RESET}" if rc_optics == 0 else f"{C_RED}[FAILED ]{C_RESET}"
    
    with open(optics_log, "a", encoding="utf-8") as fh:
        fh.write(f"\n\n--- EXECUTION SUMMARY ---\n")
        fh.write(f"FINAL STATUS: {status_optics} (Return Code: {rc_optics})\n")
        fh.write(f"PROCESSING TIME: {optics_duration:.2f} seconds\n")
        fh.write("END: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
        
    print(f"{step_prefix_optics} {status_text_optics} ({optics_duration:5.1f}s)")
    if rc_optics != 0:
         print(f"    └─> {C_RED}Check log/transceiver_matrix.log for details.{C_RESET}")
else:
    print(f"{step_prefix_optics} {C_RED}[SKIPPED - NOT FOUND]{C_RESET}")
    log_orchestrator(f"WARNING: {script_optics} not found, skipping hook.")

# ----------------- AXIS 14: Port Census Matrix -----------------
print("\n" + "-" * 60)
step_prefix_census = f"[**/**] {'parsers/port_census.py':40s}"
script_census = os.path.join(cwd, "parsers", "port_census.py")

if os.path.isfile(script_census):
    log_orchestrator(f"Executing parsers/port_census.py...")
    cmd_census = [sys.executable, script_census, "--resume_dir", RESUME_DIR, "--outdir", RESUME_DIR]
    census_log = os.path.join(LOG_DIR, "port_census.log")
    
    census_start = datetime.now()
    rc_census = run_and_stream_capture(cmd_census, env=None, out_path=census_log)
    census_duration = (datetime.now() - census_start).total_seconds()
    status_census = "SUCCESS" if rc_census == 0 else "FAILURE/WARNING"
    status_text_census = f"{C_GREEN}[SUCCESS]{C_RESET}" if rc_census == 0 else f"{C_RED}[FAILED ]{C_RESET}"
    
    with open(census_log, "a", encoding="utf-8") as fh:
        fh.write(f"\n\n--- EXECUTION SUMMARY ---\n")
        fh.write(f"FINAL STATUS: {status_census} (Return Code: {rc_census})\n")
        fh.write(f"PROCESSING TIME: {census_duration:.2f} seconds\n")
        fh.write("END: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
        
    print(f"{step_prefix_census} {status_text_census} ({census_duration:5.1f}s)")
    if rc_census != 0:
         print(f"    └─> {C_RED}Check log/port_census.log for details.{C_RESET}")
else:
    print(f"{step_prefix_census} {C_RED}[SKIPPED - NOT FOUND]{C_RESET}")
    log_orchestrator(f"WARNING: {script_census} not found, skipping hook.")

# ----------------- AXIS 12: Subcomponents Matrix -----------------
print("\n" + "-" * 60)
step_prefix_subc = f"[**/**] {'parsers/subcomponents.py':40s}"
script_subc = os.path.join(cwd, "parsers", "subcomponents.py")

if os.path.isfile(script_subc):
    log_orchestrator(f"Executing parsers/subcomponents.py...")
    cmd_subc = [sys.executable, script_subc, "--collect_dir", COLLECT_DIR, "--outdir", RESUME_DIR]
    subc_log = os.path.join(LOG_DIR, "subcomponents.log")
    
    subc_start = datetime.now()
    rc_subc = run_and_stream_capture(cmd_subc, env=None, out_path=subc_log)
    subc_duration = (datetime.now() - subc_start).total_seconds()
    status_subc = "SUCCESS" if rc_subc == 0 else "FAILURE/WARNING"
    status_text_subc = f"{C_GREEN}[SUCCESS]{C_RESET}" if rc_subc == 0 else f"{C_RED}[FAILED ]{C_RESET}"
    
    with open(subc_log, "a", encoding="utf-8") as fh:
        fh.write(f"\n\n--- EXECUTION SUMMARY ---\n")
        fh.write(f"FINAL STATUS: {status_subc} (Return Code: {rc_subc})\n")
        fh.write(f"PROCESSING TIME: {subc_duration:.2f} seconds\n")
        fh.write("END: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
        
    print(f"{step_prefix_subc} {status_text_subc} ({subc_duration:5.1f}s)")
    if rc_subc != 0:
         print(f"    └─> {C_RED}Check log/subcomponents.log for details.{C_RESET}")
else:
    print(f"{step_prefix_subc} {C_RED}[SKIPPED - NOT FOUND]{C_RESET}")
    log_orchestrator(f"WARNING: {script_subc} not found, skipping hook.")

# ----------------- AXIS 13: Software Licensing Matrix -----------------
print("\n" + "-" * 60)
step_prefix_lic = f"[**/**] {'parsers/license_matrix.py':40s}"
script_lic = os.path.join(cwd, "parsers", "license_matrix.py")

if os.path.isfile(script_lic):
    log_orchestrator(f"Executing parsers/license_matrix.py...")
    cmd_lic = [sys.executable, script_lic, "--collect_dir", COLLECT_DIR, "--outdir", RESUME_DIR]
    lic_log = os.path.join(LOG_DIR, "license_matrix.log")
    
    lic_start = datetime.now()
    rc_lic = run_and_stream_capture(cmd_lic, env=None, out_path=lic_log)
    lic_duration = (datetime.now() - lic_start).total_seconds()
    status_lic = "SUCCESS" if rc_lic == 0 else "FAILURE/WARNING"
    status_text_lic = f"{C_GREEN}[SUCCESS]{C_RESET}" if rc_lic == 0 else f"{C_RED}[FAILED ]{C_RESET}"
    
    with open(lic_log, "a", encoding="utf-8") as fh:
        fh.write(f"\n\n--- EXECUTION SUMMARY ---\n")
        fh.write(f"FINAL STATUS: {status_lic} (Return Code: {rc_lic})\n")
        fh.write(f"PROCESSING TIME: {lic_duration:.2f} seconds\n")
        fh.write("END: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
        
    print(f"{step_prefix_lic} {status_text_lic} ({lic_duration:5.1f}s)")
    if rc_lic != 0:
         print(f"    └─> {C_RED}Check log/license_matrix.log for details.{C_RESET}")
else:
    print(f"{step_prefix_lic} {C_RED}[SKIPPED - NOT FOUND]{C_RESET}")
    log_orchestrator(f"WARNING: {script_lic} not found, skipping hook.")

# ----------------- AXIS 14: Service Inventory Extractor -----------------
print("\n" + "-" * 60)
step_prefix_srv = f"[**/**] {'parsers/generate_service_inventory.py':40s}"
script_srv = os.path.join(cwd, "parsers", "generate_service_inventory.py")

if os.path.isfile(script_srv):
    log_orchestrator(f"Executing parsers/generate_service_inventory.py...")
    cmd_srv = [sys.executable, script_srv, "--resume_dir", RESUME_DIR]
    srv_log = os.path.join(LOG_DIR, "generate_service_inventory.log")
    
    srv_start = datetime.now()
    rc_srv = run_and_stream_capture(cmd_srv, env=None, out_path=srv_log)
    srv_duration = (datetime.now() - srv_start).total_seconds()
    
    status_srv = "SUCCESS" if rc_srv == 0 else "FAILURE/WARNING"
    status_text_srv = f"{C_GREEN}[SUCCESS]{C_RESET}" if rc_srv == 0 else f"{C_RED}[FAILED ]{C_RESET}"
    print(f"{step_prefix_srv} {status_text_srv} ({srv_duration:5.1f}s)")
else:
    print(f"{step_prefix_srv} {C_RED}[SKIPPED - NOT FOUND]{C_RESET}")

# ----------------- AXIS 15: BGP Logical Peering Matrix -----------------
print("\n" + "-" * 60)
step_prefix_bgp = f"[**/**] {'parsers/show.bgp.vpnv4.unicast.all.summary.py':40s}"
script_bgp = os.path.join(cwd, "parsers", "show.bgp.vpnv4.unicast.all.summary.py")

if os.path.isfile(script_bgp):
    log_orchestrator(f"Executing parsers/show.bgp.vpnv4.unicast.all.summary.py...")
    cmd_bgp = [sys.executable, script_bgp, "--collect_dir", COLLECT_DIR, "--outdir", RESUME_DIR]
    bgp_log = os.path.join(LOG_DIR, "show.bgp.vpnv4.unicast.all.summary.log")
    
    bgp_start = datetime.now()
    rc_bgp = run_and_stream_capture(cmd_bgp, env=None, out_path=bgp_log)
    bgp_duration = (datetime.now() - bgp_start).total_seconds()
    
    status_bgp = "SUCCESS" if rc_bgp == 0 else "FAILURE/WARNING"
    status_text_bgp = f"{C_GREEN}[SUCCESS]{C_RESET}" if rc_bgp == 0 else f"{C_RED}[FAILED ]{C_RESET}"
    print(f"{step_prefix_bgp} {status_text_bgp} ({bgp_duration:5.1f}s)")
else:
    print(f"{step_prefix_bgp} {C_RED}[SKIPPED - NOT FOUND]{C_RESET}")

# ----------------- AXIS 16: LLDP Consistency Cross-Reference -----------------
print("\n" + "-" * 60)
step_prefix_lldpchk = f"[**/**] {'core/lldp_consistency_checker.py':40s}"
script_lldpchk = os.path.join(cwd, "core", "lldp_consistency_checker.py")

if os.path.isfile(script_lldpchk):
    log_orchestrator(f"Executing core/lldp_consistency_checker.py...")
    cmd_lldpchk = [sys.executable, script_lldpchk, "--resume_dir", RESUME_DIR]
    lldpchk_log = os.path.join(LOG_DIR, "lldp_mismatch.log")
    
    lldpchk_start = datetime.now()
    rc_lldpchk = run_and_stream_capture(cmd_lldpchk, env=None, out_path=lldpchk_log)
    lldpchk_duration = (datetime.now() - lldpchk_start).total_seconds()
    
    status_lldpchk = "SUCCESS" if rc_lldpchk == 0 else "FAILURE/WARNING"
    status_text_lldpchk = f"{C_GREEN}[SUCCESS]{C_RESET}" if rc_lldpchk == 0 else f"{C_RED}[FAILED ]{C_RESET}"
    print(f"{step_prefix_lldpchk} {status_text_lldpchk} ({lldpchk_duration:5.1f}s)")
else:
    print(f"{step_prefix_lldpchk} {C_RED}[SKIPPED - NOT FOUND]{C_RESET}")

# ------------------------------------------------------------------

print("\n" + "-" * 60)
step_prefix_conn = f"[**/**] {'core/interface2connection.py':40s}"
script_interface2conn = os.path.join(cwd, "core", "interface2connection.py")

log_orchestrator(f"Executing core/interface2connection.py...")

if os.path.isfile(script_interface2conn):
    try:
        cmd_conn = [sys.executable, script_interface2conn, "--input", RESUME_DIR, "--output", CONNECTIONS_DIR]
        conn_log = os.path.join(LOG_DIR, "interface2connection.log")
        conn_start = datetime.now()
        rc_conn = run_and_stream_capture(cmd_conn, env=None, out_path=conn_log)
        conn_duration = (datetime.now() - conn_start).total_seconds()
        status_conn = "SUCCESS" if rc_conn == 0 else "FAILURE/WARNING"
        status_text_conn = f"{C_GREEN}[SUCCESS]{C_RESET}" if rc_conn == 0 else f"{C_RED}[FAILED ]{C_RESET}"
        
        # Append summary block to connections log as well
        with open(conn_log, "a", encoding="utf-8") as fh:
            fh.write(f"\n\n--- EXECUTION SUMMARY ---\n")
            fh.write(f"FINAL STATUS: {status_conn} (Return Code: {rc_conn})\n")
            fh.write(f"PROCESSING TIME: {conn_duration:.2f} seconds\n")
            fh.write("END: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
            
        print(f"{step_prefix_conn} {status_text_conn} ({conn_duration:5.1f}s)")
        if rc_conn != 0:
             print(f"    └─> {C_RED}Check log/interface2connection.log for details.{C_RESET}")
    except Exception as e:
        print(f"{step_prefix_conn} {C_RED}[CRASHED]{C_RESET}")
        log_orchestrator(f"FATAL ERROR: Failed to execute interface2connection: {e}")
else:
    print(f"{step_prefix_conn} {C_RED}[SKIPPED - NOT FOUND]{C_RESET}")
    log_orchestrator(f"WARNING: {script_interface2conn} not found, skipping hook.")

print("\n" + "-" * 60)
step_prefix_check = f"[**/**] {'core/topology_checker.py':40s}"
script_topocheck = os.path.join(cwd, "core", "topology_checker.py")
isolated_count = 0

if os.path.isfile(script_topocheck):
    log_orchestrator(f"Executing core/topology_checker.py...")
    cmd_check = [sys.executable, script_topocheck, "--resume_dir", RESUME_DIR, "--connections_dir", CONNECTIONS_DIR]
    check_log = os.path.join(LOG_DIR, "topology_checker.log")
    
    check_start = datetime.now()
    rc_check = run_and_stream_capture(cmd_check, env=None, out_path=check_log)
    check_duration = (datetime.now() - check_start).total_seconds()
    
    if rc_check == 50:
        print(f"{step_prefix_check} {C_YELLOW}[WARNING]{C_RESET} ({check_duration:5.1f}s)")
        print(f"    └─> {C_YELLOW}Isolated node(s) detected. Check audit logs.{C_RESET}")
        isolated_csv_path = os.path.join(RESUME_DIR, "topology_warnings.isolated.csv")
        if os.path.isfile(isolated_csv_path):
            with open(isolated_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=';')
                isolated_count = sum(1 for _ in reader)
    elif rc_check == 0:
        print(f"{step_prefix_check} {C_GREEN}[SUCCESS]{C_RESET} ({check_duration:5.1f}s)")
    else:
        print(f"{step_prefix_check} {C_RED}[FAILED ]{C_RESET} ({check_duration:5.1f}s)")
else:
    print(f"{step_prefix_check} {C_RED}[SKIPPED - NOT FOUND]{C_RESET}")
    log_orchestrator(f"WARNING: {script_topocheck} not found, skipping isolation check.")

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

print(f"\n{C_CYAN}All tasks completed. For updates and new versions, visit:{C_RESET}")
print(f"{C_CYAN}https://github.com/flashbsb/network-data-extractor{C_RESET}\n")

sys.exit(0)
