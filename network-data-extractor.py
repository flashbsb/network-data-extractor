#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_scripts_sequencia.py

Comportamento:
 - Nao pergunta credenciais no inicio.
 - Quando chegar em comandos.py, executa INTERATIVAMENTE (stdin/tty conectados)
   para que voce digite usuario/senha diretamente.
 - Para os outros scripts, executa e mostra a saida em tempo real na tela
   e tambem grava cada saida em <script>.txt.
 - Ao final, cria ../infos/DDMMYYYY e ../consolidado/DDMMYYYY e move .txt/.csv.
"""

import subprocess
import sys
import os
import shutil
import argparse
from datetime import datetime
from glob import glob

SCRIPTS = [
    "comandos.py",
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
    "gerar_max_speed_interfaces.py",
    "show.lldp.neighbors.detail.py",
]

parser = argparse.ArgumentParser(description="Principal extrator")
parser.add_argument("--threads", type=int, default=10, help="Numero de conexoes simultaneas para comandos.py")
parser.add_argument("--outbase", type=str, default="infos", help="Pasta raiz base para o timestamp (default: infos/)")
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

start_time = datetime.now()
print("Inicio:", start_time.strftime("%Y-%m-%d %H:%M:%S"))
print("Diretorio atual:", os.getcwd())
cwd = os.getcwd()


def run_and_stream_capture(cmd, env=None, out_path=None):
    """
    Executa cmd (lista) e:
     - streama stdout+stderr para a tela em tempo real
     - grava a mesma saida em out_path (se fornecido)
    Retorna returncode.
    """
    # Abre arquivo de saida se necessario
    out_file = None
    if out_path:
        out_file = open(out_path, "w", encoding="utf-8", errors="replace")

    # Inicia processo com stdout PIPE e stderr para STDOUT
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env, bufsize=1, universal_newlines=True)

    try:
        # Le e escreve linha a linha para ter saida em tempo real
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                sys.stdout.write(line)
                sys.stdout.flush()
                # grava no arquivo
                if out_file:
                    out_file.write(line)
                    out_file.flush()
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuario. Matando processo filho.")
        proc.kill()
        proc.wait()
        if out_file:
            out_file.close()
        return 130
    finally:
        # garante que entramos aqui quando terminar
        proc.stdout.close()

    rc = proc.wait()
    if out_file:
        out_file.close()
    return rc


for script in SCRIPTS:
    print("\n" + "=" * 60)
    print(f"Executando processo: {script}")
    script_path = os.path.join(cwd, script)
    if not os.path.isfile(script_path):
        print(f"Aviso: Opcional extra {script} nao econtrado. Pulando etapa.")
        continue

    cmd = [sys.executable, script_path]

    # Se for comandos.py -> executar INTERATIVAMENTE (stdin/tty conectado)
    if script == "comandos.py":
        cmd.extend(["--outdir", COLLECT_DIR, "--threads", str(args.threads)])
        print(f"    --> Coletando dados crus e enviando para: {COLLECT_DIR}")
        print(">>> comandos.py sera executado de forma INTERATIVA. Pressione Ctrl+C para pular ou digite credenciais.")
        try:
            # Não capturamos aqui; deixamos a interação no terminal para o usuario
            rc = subprocess.run(cmd)
            # se o comando gerar arquivos por host, eles ja ficaram no cwd
            print(f"[{script}] Finalizado com codigo de retorno: {rc.returncode}")
        except KeyboardInterrupt:
            print(f"\n[{script}] Interrompido pelo usuario.")
        except Exception as e:
            print(f"Erro ao executar {script} interativamente: {e}")
    else:
        cmd.extend(["--outdir", RESUME_DIR, "--indir", COLLECT_DIR])
        print(f"    --> Analisando de: {COLLECT_DIR}  |  Enviando para: {RESUME_DIR}")
        # Para scripts nao interativos, executa e grava saida em <script>.log enquanto mostra na tela
        safe_name = script.replace(".py", "")
        out_file_name = os.path.join(LOG_DIR, f"{safe_name}.log")
        # Escreve um cabeçalho no arquivo antes de rodar
        try:
            with open(out_file_name, "w", encoding="utf-8") as fh:
                fh.write(f"COMANDO: {' '.join(cmd)}\n")
                fh.write("INICIO: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n")
        except Exception as e:
            print("Aviso: nao foi possivel criar arquivo de log inicial:", e)
            out_file_name = None

        rc = run_and_stream_capture(cmd, env=None, out_path=out_file_name)

        # apos termino, grava retorno e hora final no arquivo
        if out_file_name:
            try:
                with open(out_file_name, "a", encoding="utf-8") as fh:
                    fh.write("\n\nRETURNCODE: " + str(rc) + "\n")
                    fh.write("FIM: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n")
            except Exception as e:
                print("Aviso: falha ao atualizar arquivo de log:", e)

        print(f"{script} finalizado com codigo {rc}")


print("\n" + "=" * 60)
print(f"Gerando conexoes consolidadas...")
print(f"    --> Analisando de: {RESUME_DIR}  |  Enviando para: {CONNECTIONS_DIR}/connections.log")
script_interface2conn = os.path.join(cwd, "interface2connection.py")

orchestrator_log = os.path.join(LOG_DIR, "orchestrator.log")

if os.path.isfile(script_interface2conn):
    try:
        cmd_conn = [sys.executable, script_interface2conn, "--input", RESUME_DIR, "--output", CONNECTIONS_DIR]
        conn_log = os.path.join(LOG_DIR, "interface2connection.log")
        rc_conn = run_and_stream_capture(cmd_conn, env=None, out_path=conn_log)
        print(f"[interface2connection.py] Finalizou com codigo {rc_conn}")
    except Exception as e:
        print(f"Erro GRAVE ao executar interface2connection.py. Causa: {e}")
        with open(orchestrator_log, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now()}] ERRO FATAL: Falha ao rodar interface2connecion: {e}\n")
else:
    print("Aviso: interface2connection.py nao encontrado. Pulando etapa de conexoes.")
    with open(orchestrator_log, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now()}] AVISO: {script_interface2conn} nao encontrado, skippando loop.\n")

end_time = datetime.now()
print("\n" + "=" * 60)
print("Fim:", end_time.strftime("%Y-%m-%d %H:%M:%S"))

duration = end_time - start_time
total_seconds = int(duration.total_seconds())
hours = total_seconds // 3600
minutes = (total_seconds % 3600) // 60
seconds = total_seconds % 60
print(f"Tempo total: {hours:02d}:{minutes:02d}:{seconds:02d}")

sys.exit(0)
