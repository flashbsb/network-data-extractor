#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_scripts_sequencia.py

Behavior:
 - Does not prompt for credentials initially.
 - When reaching comandos.py, executes INTERACTIVELY (stdin/tty connected)
   so you can directly type username/password.
 - For other scripts, executes and streams the output in real-time
   while saving logs to <script>.txt.
 - Ultimately generates ../infos/DDMMYYYY and ../consolidado/DDMMYYYY and moves .txt/.csv.
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

SCRIPTS = [
    "commands.py",
    "show.interfaces.py",
    "show.interfaces.status.py",
    "show.inventory.details.py",
    "show.inventory.py",
    "show.platform.py",
    "show.system.py",
    "show.version.py",
    "show.firmware.py",
    "show.hardware-status.transceiver.py",
    "show.hardware-status.transceivers.detail.py",
    "generate_max_speed_interfaces.py",
    "show.lldp.neighbors.detail.py",
]

description = """
Main Extractor Orchestrator

This script automates the execution of multiple data collection and parsing
scripts against network elements defined in 'elements.cfg', using the
commands outlined in 'commands.cfg'.

Workflow:
  1. Prompts for SSH credentials interactively.
  2. Executes 'commands.py' concurrently to gather raw CLI outputs into '<outbase>/YYYYMMDD_HHMMSS/collect/'.
  3. Sequentially process all parsing scripts (show.*.py) to generate CSV structures into '<outbase>/YYYYMMDD_HHMMSS/resume/'.
  4. Finally runs 'interface2connection.py' to map the physical topology connections.
  5. All execution logs are silently stored in '<outbase>/YYYYMMDD_HHMMSS/log/'.
"""

parser = argparse.ArgumentParser(
    description=description,
    formatter_class=argparse.RawTextHelpFormatter
)
parser.add_argument("--threads", type=int, default=10, help="Number of concurrent SSH sessions for commands.py (default: 10)")
parser.add_argument("--outbase", type=str, default="infos", help="Root directory base to save timestamps/logs/CSVs folders (default: infos/)")
parser.add_argument("--elements", type=str, default="elements.cfg", help="Input file containing the list of elements (default: elements.cfg)")
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
print(f"{C_CYAN}--- Network Data Extractor Orchestrator ---{C_RESET}")
print(f"Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Output Root: {TIMESTAMP_DIR}\n")
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
    script_path = os.path.join(cwd, script)
    if not os.path.isfile(script_path):
        print(f"{step_prefix} {C_RED}[SKIPPED - NOT FOUND]{C_RESET}")
        log_orchestrator(f"Skipped {script}: File not found")
        continue

    log_orchestrator(f"Executing {script}...")

    cmd = [sys.executable, script_path]

    if script == "commands.py":
        cmd.extend(["--outdir", COLLECT_DIR, "--logdir", LOG_DIR, "--threads", str(args.threads), "--elements", args.elements])
        print(f">>> {C_CYAN}commands.py{C_RESET} is running. Extracted data goes to: collect/")
        try:
            # Let standard bounds stay active for user password inputs
            script_start_time = datetime.now()
            rc = subprocess.run(cmd)
            script_duration = (datetime.now() - script_start_time).total_seconds()
            
            status_text = f"{C_GREEN}[SUCCESS]{C_RESET}" if rc.returncode == 0 else f"{C_RED}[FAILED ]{C_RESET}"
            log_orchestrator(f"{script} Finished. Return Code: {rc.returncode}")
            print(f"{step_prefix} {status_text} ({script_duration:5.1f}s)")
        except KeyboardInterrupt:
            print(f"{step_prefix} {C_RED}[INTERRUPTED]{C_RESET}")
        except Exception as e:
            log_orchestrator(f"{script} Error: {e}")
            print(f"{step_prefix} {C_RED}[ERROR]{C_RESET}")
    else:
        cmd.extend(["--outdir", RESUME_DIR, "--indir", COLLECT_DIR])
        # Scripts output real-time to std and file automatically
        safe_name = script.replace(".py", "")
        out_file_name = os.path.join(LOG_DIR, f"{safe_name}.log")
        # Initialize execution header
        try:
            with open(out_file_name, "w", encoding="utf-8") as fh:
                fh.write(f"COMMAND: {' '.join(cmd)}\n")
                fh.write("START: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n")
        except Exception as e:
            log_orchestrator(f"Warning: unable to create log for {script}: {e}")
            out_file_name = None

        script_start_time = datetime.now()
        rc = run_and_stream_capture(cmd, env=None, out_path=out_file_name)
        script_end_time = datetime.now()
        script_duration = (script_end_time - script_start_time).total_seconds()
        log_orchestrator(f"{script} Finished. Return Code: {rc}. Duration: {script_duration:.2f}s")
        
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
step_prefix_conn = f"[**/**] {'interface2connection.py':40s}"
script_interface2conn = os.path.join(cwd, "interface2connection.py")

log_orchestrator(f"Executing interface2connection.py...")

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

sys.exit(0)
