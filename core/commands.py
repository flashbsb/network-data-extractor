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

# Load Global Settings once
json_config = {}
if os.path.exists("config/settings.json"):
    try:
        with open("config/settings.json", "r") as f:
            json_config = json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load config/settings.json: {e}")

ssh_cfg = json_config.get("ssh", {})
SSH_TIMEOUT = ssh_cfg.get("timeout", 10)
CMD_DELAY = ssh_cfg.get("delay_between_commands", 5)
extractor_cfg = json_config.get("extractor", {})
LOG_LEVEL = extractor_cfg.get("log_level", "INFO").upper()


def read_elements(path):
    elements = []
    if not os.path.isfile(path):
        logging.error(f"Element file not found: {path}")
        sys.exit(1)

    with open(path, 'r') as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(';')
            if len(parts) != 3:
                logging.warning(f"Invalid line {lineno} in {path} (Expected format: hostname;ip;command_key): {line}")
                continue
            elements.append(dict(zip(['hostname', 'ip', 'cmd_key'], parts)))
    return elements


def read_commands(path):
    commands = {}
    if not os.path.isfile(path):
        logging.error(f"Commands file not found: {path}")
        sys.exit(1)

    with open(path, 'r') as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(';', 1)
            if len(parts) != 2:
                logging.warning(f"Invalid line {lineno} in {path}: {line}")
                continue
            key, cmd = parts
            commands.setdefault(key, []).append(cmd)
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
    paginators = [
        'terminal length 0',      # Cisco IOS / IOS-XE
        'terminal pager 0',       # Datacom / DmOS / Huawei
        'screen-length 0 disable' # HP / H3C / Datacom Legacy
    ]
    for p_cmd in paginators:
        shell.send(p_cmd + '\n')
        time.sleep(0.5)

    # Flush the pager command echos
    while shell.recv_ready():
        shell.recv(65535)

    output_map = {}
    for cmd in cmds:
        shell.send(cmd + '\n')

        buff = b''
        timeout_limit = 20  # Maximum seconds to wait total per command
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

    def process_element(elem):
        nonlocal counter
        nonlocal files_written
        host = elem['hostname']
        ip = elem['ip']
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Support multiple IPs and cmd_keys joined by '|'
        ip_list = elem['ip'].split('|')
        cmd_key_list = elem['cmd_key'].split('|')
        success = False
        
        timestamp = datetime.datetime.now().strftime('%d%m%y%H%M%S')
        
        for current_ip in ip_list:
            if success: break
            for current_key in cmd_key_list:
                cmds = commands_map.get(current_key)
                if not cmds:
                    logging.warning(f"No commands found for key '{current_key}' on element '{host}'")
                    continue
                    
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
                    client.close()
                    
                    # Save files
                    for cmd, out in outputs.items():
                        fname = f"{host}.{timestamp}.{sanitize_filename(cmd)}.txt"
                        try:
                            with open(os.path.join(args.outdir, fname), 'w') as f:
                                f.write(f"# Host: {host}\n# IP: {current_ip}\n# Command: {cmd}\n# Date: {timestamp}\n\n")
                                f.write(out)
                            with files_written_lock:
                                files_written += 1
                        except Exception as e:
                            logging.error(f"Error saving '{fname}': {e}")
                    
                    # Log the successful key for element_status.py to consume.
                    # IMPORTANT: Must be written to outdir (collect_dir), because
                    # element_status.py reads it from collect_dir (not resumedir).
                    success_keys_file = os.path.join(args.outdir, "successful_keys.csv")
                    with files_written_lock:
                        with open(success_keys_file, 'a') as skf:
                            skf.write(f"{host};{current_ip};{current_key}\n")

                    success = True
                    logging.info(f"Session finished for {host} using IP {current_ip} and key '{current_key}'")
                    break # Exit the key fallback loop
                    
                except Exception as e:
                    logging.warning(f"Connection/Execution failed for {host} at {current_ip} with key '{current_key}': {e}")
                    try: client.close()
                    except Exception: pass
                    continue

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
