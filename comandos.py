import paramiko
import getpass
import logging
import datetime
import os
import sys
import time
import concurrent.futures

# v1.1

# Logging will be configured in main()


def read_elementos(path):
    elementos = []
    if not os.path.isfile(path):
        logging.error(f"Element file not found: {path}")
        sys.exit(1)

    with open(path, 'r') as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(';')
            if len(parts) != 4:
                logging.warning(f"Invalid line {lineno} in {path}: {line}")
                continue
            elementos.append(dict(zip(['hostname', 'ip', 'modelo', 'cmd_key'], parts)))
    return elementos


def read_comandos(path):
    comandos = {}
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
            comandos.setdefault(key, []).append(cmd)
    return comandos


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
        # logging.info(f"Enviando comando: {cmd}") # Suppressed
        shell.send(cmd + '\n')
        time.sleep(5)
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
    parser.add_argument("--threads", type=int, default=10, help="Numero de conexoes simultaneas")
    args = parser.parse_args()

    log_file = os.path.join(args.logdir, 'comandos.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[logging.FileHandler(log_file, mode='a', encoding='utf-8')]
    )
    logging.getLogger("paramiko").setLevel(logging.WARNING)

    elementos = read_elementos('elementos.cfg')
    comandos_map = read_comandos('comandos.cfg')

    user = input('SSH Worker User: ')
    password = getpass.getpass('SSH Password: ')

    if not elementos:
        logging.error('No valid elements found.')
        sys.exit(1)

    import threading
    total_elements = len(elementos)
    pad = len(str(total_elements))
    counter = 0
    counter_lock = threading.Lock()

    def process_element(elem):
        nonlocal counter
        host = elem['hostname']
        ip = elem['ip']
        key = elem['cmd_key']
        cmds = comandos_map.get(key)
        if not cmds:
            logging.warning(f"No commands found for key '{key}' on element '{host}'")
            with counter_lock:
                counter += 1
                curr = counter
            print(f"  [{curr:>{pad}}/{total_elements}] [-] No cmds found: {host}")
            return

        timestamp = datetime.datetime.now().strftime('%d%m%y%H%M%S')
        logging.info(f"Conectando em {host} ({ip}) chave '{key}'")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(ip, username=user, password=password, timeout=10, look_for_keys=False)
        except Exception as e:
            logging.error(f"Connection failed for {host}: {e}")
            with counter_lock:
                counter += 1
                curr = counter
            print(f"  [{curr:>{pad}}/{total_elements}] [-] Connection failed: {host} (See log for details)")
            return

        outputs = execute_commands_shell(client, cmds)
        client.close()

        # Grava arquivos
        for cmd, out in outputs.items():
            fname = f"{host}.{timestamp}.{sanitize_filename(cmd)}.txt"
            try:
                with open(os.path.join(args.outdir, fname), 'w') as f:
                    f.write(f"# Host: {host}\n# IP: {ip}\n# Comando: {cmd}\n# Data: {timestamp}\n\n")
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

    # Inicia a thread pool com o numero de threads especificado
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
        executor.map(process_element, elementos)

if __name__ == '__main__':
    main()
