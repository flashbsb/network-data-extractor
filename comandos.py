import paramiko
import getpass
import logging
import datetime
import os
import sys
import time
import concurrent.futures

# v1.1

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def read_elementos(path):
    elementos = []
    if not os.path.isfile(path):
        logging.error(f"Arquivo de elementos nao encontrado: {path}")
        sys.exit(1)

    with open(path, 'r') as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(';')
            if len(parts) != 4:
                logging.warning(f"Linha {lineno} em {path} invalida: {line}")
                continue
            elementos.append(dict(zip(['hostname', 'ip', 'modelo', 'cmd_key'], parts)))
    return elementos


def read_comandos(path):
    comandos = {}
    if not os.path.isfile(path):
        logging.error(f"Arquivo de comandos nao encontrado: {path}")
        sys.exit(1)

    with open(path, 'r') as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(';', 1)
            if len(parts) != 2:
                logging.warning(f"Linha {lineno} em {path} invalida: {line}")
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
        logging.info(f"Enviando comando: {cmd}")
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
    parser.add_argument("--threads", type=int, default=10, help="Numero de conexoes simultaneas")
    args = parser.parse_args()

    elementos = read_elementos('elementos.cfg')
    comandos_map = read_comandos('comandos.cfg')

    user = input('Usuário SSH: ')
    password = getpass.getpass('Senha SSH: ')

    if not elementos:
        logging.error('Nenhum elemento valido  encontrado.')
        sys.exit(1)

    def process_element(elem):
        host = elem['hostname']
        ip = elem['ip']
        key = elem['cmd_key']
        cmds = comandos_map.get(key)
        if not cmds:
            logging.warning(f"Nenhum comando para chave '{key}' no elemento '{host}'")
            return

        timestamp = datetime.datetime.now().strftime('%d%m%y%H%M%S')
        logging.info(f"Conectando em {host} ({ip}) chave '{key}'")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(ip, username=user, password=password, timeout=10, look_for_keys=False)
        except Exception as e:
            logging.error(f"Falha na conexao do {host}: {e}")
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
                logging.info(f"Arquivo gerado: {fname}")
            except Exception as e:
                logging.error(f"Erro ao gravar '{fname}': {e}")

        logging.info(f"Sessao finnalizada em {host}\n")

    # Inicia a thread pool com o numero de threads especificado
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
        executor.map(process_element, elementos)

if __name__ == '__main__':
    main()
