import paramiko
import getpass
import logging
import datetime
import os
import sys
import time
import concurrent.futures
import json
import argparse

# Logging will be configured in main()

# Load Global Settings once.
# Path is derived from __file__ so the file is found regardless of the
# current working directory from which commands.py is invoked.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SETTINGS_PATH = os.path.join(_SCRIPT_DIR, "..", "config", "settings.json")
_SETTINGS_PATH = os.path.normpath(_SETTINGS_PATH)

json_config = {}
if os.path.exists(_SETTINGS_PATH):
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            json_config = json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load settings.json ({_SETTINGS_PATH}): {e}")

ssh_cfg = json_config.get("ssh", {})
SSH_TIMEOUT = ssh_cfg.get("timeout", 10)
CMD_DELAY = ssh_cfg.get("delay_between_commands", 5)
STRICT_HOST_KEY_CHECKING = ssh_cfg.get("strict_host_key_checking", False)
extractor_cfg = json_config.get("extractor", {})
LOG_LEVEL = extractor_cfg.get("log_level", "INFO").upper()

PAGER_DISABLE_COMMANDS = ssh_cfg.get("pager_disable_commands", ["terminal length 0", "terminal pager 0", "screen-length 0 disable"])
COMMAND_TIMEOUT = ssh_cfg.get("command_timeout", 20)


def read_elements(path):
    elements = []
    if not os.path.isfile(path):
        logging.error(f"Element file not found: {path}")
        sys.exit(1)

    with open(path, 'r', encoding='utf-8') as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(';')
            if len(parts) < 3:
                logging.warning(f"Invalid line {lineno} in {path} (Expected format: hostname;ip;command_key): {line}")
                continue
            elements.append({
                'hostname': parts[0].strip(),
                'ip': parts[1].strip(),
                'cmd_key': parts[2].strip()
            })
    return elements


def read_commands(path):
    commands = {}
    if not os.path.isfile(path):
        logging.error(f"Commands file not found: {path}")
        sys.exit(1)

    with open(path, 'r', encoding='utf-8') as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(';', 1)
            if len(parts) != 2:
                logging.warning(f"Invalid line {lineno} in {path}: {line}")
                continue
            key, cmd = parts
            commands.setdefault(key.strip(), []).append(cmd.strip())
    return commands


def sanitize_filename(s):
    sanitized = s.replace(' ', '.')
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        sanitized = sanitized.replace(ch, '')
    return sanitized[:100]


def execute_commands_shell(client, cmds):
    import re
    # Matches CLI prompts like: ROUTER#, ROUTER>, RP/0/RSP0/CPU0:ROUTER#, etc.
    PROMPT_RE = re.compile(r'[A-Za-z0-9_\-\.\:\/]+[#>]\s*$')

    shell = client.invoke_shell()
    time.sleep(1)
    shell.recv(1000)  # clear banner

    # Disable pagination (Universal Shotgun Strategy)
    for p_cmd in PAGER_DISABLE_COMMANDS:
        shell.send(p_cmd + '\n')
        time.sleep(0.5)

    # Flush the pager command echos
    while shell.recv_ready():
        shell.recv(65535)

    output_map = {}
    for cmd in cmds:
        shell.send(cmd + '\n')

        buff = b''
        timeout_limit = COMMAND_TIMEOUT  # Maximum seconds to wait total per command
        start_time = time.time()
        last_recv_time = time.time()

        while True:
            # Hard timeout: always bail after timeout_limit seconds
            if time.time() - start_time > timeout_limit:
                break

            if shell.recv_ready():
                chunk = shell.recv(65535)
                if chunk:
                    buff += chunk
                    last_recv_time = time.time()

                    text_chunk = chunk.decode('utf-8', errors='ignore').lower()

                    # Handle mid-output pagination markers
                    if '--more--' in text_chunk or '---- more' in text_chunk or 'press any key' in text_chunk:
                        shell.send(' ')  # Send Spacebar to continue
                        time.sleep(0.1)
                        continue

                    # PERF: prompt detected — output is complete, no need to wait CMD_DELAY
                    tail = buff.decode('utf-8', errors='ignore').rstrip()
                    last_line = tail.split('\n')[-1] if tail else ''
                    if PROMPT_RE.search(last_line):
                        break
            else:
                # Idle fallback: if no data for CMD_DELAY seconds, assume output finished
                if time.time() - last_recv_time > CMD_DELAY:
                    break
                time.sleep(0.1)

        output_map[cmd] = buff.decode('utf-8', errors='ignore')
    shell.close()
    return output_map


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default=".")
    parser.add_argument("--logdir", default=".")
    parser.add_argument("--threads", type=int, default=20, help="Number of concurrent connections")
    parser.add_argument("--elements", type=str, default="config/elements.cfg", help="Input file containing the list of elements")
    parser.add_argument("--commands", type=str, default="config/commands.cfg", help="Input file containing the list of commands")
    parser.add_argument("--randomize", action="store_true", default=True, help="Randomize the connection order (default: True)")
    parser.add_argument("--resumedir", help="Directory for consolidated/summary reports (e.g. successful_keys.csv)")
    parser.add_argument("--no-randomize", dest="randomize", action="store_false", help="Keep the connection order exactly as in the elements file")
    parser.add_argument("--run-id", "--run_id", dest="run_id", default=None, help="Extraction run identifier")
    parser.add_argument("--outbase", default=None, help="Root directory for outputs")
    parser.add_argument("--storage-mode", "--storage_mode", dest="storage_mode", default=None, help="Storage persistence mode override")
    parser.add_argument("--database-path", "--database_path", dest="database_path", default=None, help="Explicit path to database")
    args = parser.parse_args()

    log_file = os.path.join(args.logdir, 'commands.log')
    numeric_level = getattr(logging, LOG_LEVEL, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[logging.FileHandler(log_file, mode='a', encoding='utf-8')]
    )
    logging.getLogger("paramiko").setLevel(logging.WARNING)

    elements = read_elements(args.elements)
    commands_map = read_commands(args.commands)

    # Check if credentials were provided via environment variables (Non-interactive mode)
    env_user = os.environ.get('NDX_SSH_USER')
    env_pass = os.environ.get('NDX_SSH_PASS')
    env_key  = os.environ.get('NDX_SSH_KEY')
    
    if env_user:
        logging.info("Using SSH username provided via arguments/environment.")
        user = env_user
    else:
        user = input('SSH Worker User: ')
        
    password = None
    if env_key:
        logging.info(f"Using explicit SSH key provided via arguments: {env_key}")
    elif env_pass is not None:
        logging.info("Using SSH password provided via environment.")
        password = env_pass
    else:
        password = getpass.getpass('SSH Password (leave blank to use local SSH Agent/Keys): ')

    if not elements:
        logging.error('No valid elements found.')
        sys.exit(1)

    if args.randomize:
        import random
        random.shuffle(elements)
        logging.info("Randomized the connection sequence.")

    import threading
    total_elements = len(elements)
    pad = len(str(total_elements))
    counter = 0
    counter_lock = threading.Lock()
    files_written = 0
    files_written_lock = threading.Lock()

    # Storage Abstraction Layer initialization
    storage_mgr = None
    if args.run_id:
        try:
            proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if proj_root not in sys.path:
                sys.path.insert(0, proj_root)
            from core.storage.manager import StorageManager
            resolved_outbase = args.outbase or os.path.dirname(os.path.dirname(os.path.abspath(args.outdir)))
            storage_mgr = StorageManager.from_settings(
                outbase=resolved_outbase,
                custom_db_path=args.database_path,
                custom_mode=args.storage_mode,
            )
            if storage_mgr.is_db_enabled():
                logging.info(f"StorageManager initialized for commands.py: mode={storage_mgr.get_mode()} (DB enabled)")
        except Exception as e:
            logging.warning(f"Could not initialize StorageManager in commands.py: {e}")

    save_fs = (storage_mgr is None) or storage_mgr.is_files_enabled() or (storage_mgr.get_mode() == "db_only")
    save_db = (storage_mgr is not None) and storage_mgr.is_db_enabled()

    def process_element(elem):
        nonlocal counter
        nonlocal files_written
        host = elem['hostname']
        
        # Support multiple IPs and cmd_keys joined by '|'
        ip_list = elem['ip'].split('|')
        cmd_key_list = elem['cmd_key'].split('|')
        success = False
        
        timestamp = datetime.datetime.now().strftime('%d%m%y%H%M%S')
        
        for current_ip in ip_list:
            if success:
                break
            for current_key in cmd_key_list:
                cmds = commands_map.get(current_key)
                if not cmds:
                    logging.warning(f"No commands found for key '{current_key}' on element '{host}'")
                    continue

                client = paramiko.SSHClient()
                if STRICT_HOST_KEY_CHECKING:
                    client.load_system_host_keys()
                    client.set_missing_host_key_policy(paramiko.RejectPolicy())
                else:
                    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    
                try:
                    connect_kwargs = {
                        "username": user,
                        "timeout": SSH_TIMEOUT,
                        "look_for_keys": False,
                        "allow_agent": False
                    }
                    if env_key:
                        connect_kwargs['key_filename'] = env_key
                    elif password:
                        connect_kwargs['password'] = password
                    else:
                        connect_kwargs['look_for_keys'] = True
                        connect_kwargs['allow_agent'] = True
                        
                    client.connect(current_ip, **connect_kwargs)
                    
                    # If we reached here, connection worked. Now try to execute.
                    outputs = execute_commands_shell(client, cmds)
                    
                    # Save files (Filesystem Driver)
                    for cmd, out in outputs.items():
                        if save_fs:
                            fname = f"{host}.{timestamp}.{sanitize_filename(cmd)}.txt"
                            try:
                                with open(os.path.join(args.outdir, fname), 'w', encoding='utf-8') as f:
                                    f.write(f"# Host: {host}\n# IP: {current_ip}\n# Command: {cmd}\n# Date: {timestamp}\n\n")
                                    f.write(out)
                                with files_written_lock:
                                    files_written += 1
                            except Exception as e:
                                logging.error(f"Error saving '{fname}': {e}")

                        # Stream immediately to Database (fail-open)
                        if save_db:
                            try:
                                cmd_dt = datetime.datetime.strptime(timestamp, '%d%m%y%H%M%S')
                            except Exception:
                                cmd_dt = datetime.datetime.now()
                            try:
                                storage_mgr.save_raw_collection(
                                    run_id=args.run_id,
                                    hostname=host,
                                    ip=current_ip,
                                    command=cmd,
                                    raw_output=out,
                                    collected_at=cmd_dt,
                                )
                                if not save_fs:
                                    with files_written_lock:
                                        files_written += 1
                            except Exception as e:
                                logging.warning(f"Error persisting raw collection to DB for {host} {cmd}: {e}")
                    
                    # Log the successful key for element_status.py to consume.
                    # IMPORTANT: Must be written to outdir (collect_dir), because
                    # element_status.py reads it from collect_dir (not resumedir).
                    if save_fs:
                        success_keys_file = os.path.join(args.outdir, "successful_keys.csv")
                        with files_written_lock:
                            with open(success_keys_file, 'a', encoding='utf-8') as skf:
                                skf.write(f"{host};{current_ip};{current_key}\n")

                    if save_db:
                        try:
                            storage_mgr.save_successful_key(
                                run_id=args.run_id,
                                hostname=host,
                                ip=current_ip,
                                key=current_key,
                            )
                        except Exception as e:
                            logging.warning(f"Error saving successful key to DB for {host}: {e}")

                    success = True
                    logging.info(f"Session finished for {host} using IP {current_ip} and key '{current_key}'")
                    break # Exit the key fallback loop
                    
                except Exception as e:
                    logging.warning(f"Connection/Execution failed for {host} at {current_ip} with key '{current_key}': {e}")
                    continue
                finally:
                    try:
                        client.close()
                    except Exception:
                        pass

        with counter_lock:
            counter += 1
            curr = counter
            
        if success:
            print(f"  [{curr:>{pad}}/{total_elements}] [+] Collected: {host}")
        else:
            print(f"  [{curr:>{pad}}/{total_elements}] [-] Failed: {host} (Tried {len(ip_list)} IPs, {len(cmd_key_list)} keys)")

        # logging.info(f"Session finished for {host}\n")

    # Start the thread pool with the specified number of threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
        executor.map(process_element, elements)

    if files_written == 0:
        logging.error("No data files were written. Collection failed or no elements responded.")
        sys.exit(100)

if __name__ == '__main__':
    main()
