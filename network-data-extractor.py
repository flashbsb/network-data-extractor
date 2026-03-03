#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
           NETWORK DATA EXTRACTOR ORCHESTRATOR           
============================================================
Version : 1.14.1
Date    : 2026-03-03
Author  : flashbsb (and contributors)

Changelog:
 - Removed unused 3rd column from elements.cfg
 - Refactored Topology Aggregation (interface2connection)
 - Enforced strict KeyboardInterrupt graceful exits
============================================================

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
from datetime import datetime
from glob import glob

# ANSI Colors
C_GREEN = '\033[92m'
C_RED = '\033[91m'
C_CYAN = '\033[96m'
C_RESET = '\033[0m'

# Auto-discover parsers
parsers_show = sorted(glob("parsers/show.*.py"))
parsers_others = sorted([p for p in glob("parsers/*.py") if p not in parsers_show])

SCRIPTS = ["core/commands.py"] + parsers_show + parsers_others

description = """
Main Extractor Orchestrator

This script automates the execution of multiple data collection and parsing
scripts against network elements defined in 'config/elements.cfg', using the
commands outlined in 'config/commands.cfg'.

Workflow:
  1. Prompts for SSH credentials interactively.
  2. Executes 'core/commands.py' concurrently to gather raw CLI outputs into '<outbase>/YYYYMMDD_HHMMSS/collect/'.
  3. Sequentially process all parsing scripts (parsers/*.py) to generate CSV structures into '<outbase>/YYYYMMDD_HHMMSS/resume/'.
  4. Finally runs 'core/interface2connection.py' to map the physical topology connections.
  5. All execution logs are silently stored in '<outbase>/YYYYMMDD_HHMMSS/log/'.
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

parser.add_argument("--threads", type=int, default=def_threads, help=f"Number of concurrent SSH sessions for commands.py (default: {def_threads})")
parser.add_argument("--outbase", type=str, default=def_outbase, help=f"Root directory base to save timestamps/logs/CSVs folders (default: {def_outbase})")
parser.add_argument("--elements", type=str, default=def_elements, help=f"Input file containing the list of elements (default: {def_elements})")
parser.add_argument("--commands", type=str, default=def_commands, help=f"Input file containing the list of commands (default: {def_commands})")
parser.add_argument("--randomize", action="store_true", default=def_randomize, help=f"Randomize the connection order in commands.py (default: {def_randomize})")
parser.add_argument("--no-randomize", dest="randomize", action="store_false", help="Keep connection order sequential")
parser.add_argument("--skip-wizard", action="store_true", help="Skip the configuration confirmation prompt")
args = parser.parse_args()

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
print("Version : 1.14.1")
print(f"Date    : {datetime.now().strftime('%Y-%m-%d')}")
print("Author  : flashbsb (and contributors)")
print("")
print("Changelog:")
print(" - Removed unused 3rd column from elements.cfg")
print(" - Refactored Topology Aggregation (interface2connection)")
print(" - Enforced strict KeyboardInterrupt graceful exits")
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
            # Let standard bounds stay active for user password inputs
            script_start_time = datetime.now()
            rc = subprocess.run(cmd)
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

end_time = datetime.now()
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
