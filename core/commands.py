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
    except:
        pass

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
    shell = client.invoke_shell()
    time.sleep(1)
    shell.recv(1000)  # clear banner
    # Disable pagination
    shell.send('terminal length 0\n')
    time.sleep(1)
    shell.recv(1000)

    output_map = {}
    for cmd in cmds:
        # logging.info(f"Sending command: {cmd}") # Suppressed
        shell.send(cmd + '\n')
        time.sleep(CMD_DELAY)
        buff = b''
        while shell.recv_ready():
            buff += shell.recv(65535)
            time.sleep(0.5)
        output_map[cmd] = buff.decode('utf-8', errors='ignore')
    shell.close()
    return output_map


import argparse
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default=".")
    parser.add_argument("--logdir", default=".")
    parser.add_argument("--threads", type=int, default=20, help="Number of concurrent connections")
    parser.add_argument("--elements", type=str, default="config/elements.cfg", help="Input file containing the list of elements")
    parser.add_argument("--commands", type=str, default="config/commands.cfg", help="Input file containing the list of commands")
    parser.add_argument("--randomize", action="store_true", default=True, help="Randomize the connection order (default: True)")
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

    user = input('SSH Worker User: ')
    password = getpass.getpass('SSH Password: ')

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

    def process_element(elem):
        nonlocal counter
        host = elem['hostname']
        ip = elem['ip']
        key = elem['cmd_key']
        cmds = commands_map.get(key)
        if not cmds:
            logging.warning(f"No commands found for key '{key}' on element '{host}'")
            with counter_lock:
                counter += 1
                curr = counter
            print(f"  [{curr:>{pad}}/{total_elements}] [-] No cmds found: {host}")
            return

        timestamp = datetime.datetime.now().strftime('%d%m%y%H%M%S')
        logging.info(f"Connecting to {host} ({ip}) key '{key}'")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(ip, username=user, password=password, timeout=SSH_TIMEOUT, look_for_keys=False)
        except Exception as e:
            logging.error(f"Connection failed for {host}: {e}")
            with counter_lock:
                counter += 1
                curr = counter
            print(f"  [{curr:>{pad}}/{total_elements}] [-] Connection failed: {host} (See log for details)")
            return

        outputs = execute_commands_shell(client, cmds)
        client.close()

        # Save files
        for cmd, out in outputs.items():
            fname = f"{host}.{timestamp}.{sanitize_filename(cmd)}.txt"
            try:
                with open(os.path.join(args.outdir, fname), 'w') as f:
                    f.write(f"# Host: {host}\n# IP: {ip}\n# Command: {cmd}\n# Date: {timestamp}\n\n")
                    f.write(out)
                # Omit verbose logging of every single file generated to preserve terminal UX
            except Exception as e:
                logging.error(f"Error saving '{fname}': {e}")

        logging.info(f"Session finished for {host}")
        with counter_lock:
            counter += 1
            curr = counter
        print(f"  [{curr:>{pad}}/{total_elements}] [+] Collected: {host}")

        # logging.info(f"Session finished for {host}\n")

    # Start the thread pool with the specified number of threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
        executor.map(process_element, elements)

if __name__ == '__main__':
    main()
