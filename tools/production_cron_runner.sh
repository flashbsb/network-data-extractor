#!/bin/bash
# /home/flashbsb/projetos/d-network-data-extractor/run_cron.sh
# Production Cron Runner with structured status tokens & health telemetry
set -euo pipefail

# Definição do filtro padrão (semanal: segundas e sextas)
DEFAULT_FILTER="in:RTAC;RTED;RTOC;RTIC"

# Captura do filtro via parâmetro $1, variável de ambiente $NDX_FILTER ou valor padrão
FILTER="${1:-${NDX_FILTER:-$DEFAULT_FILTER}}"

START_TIME=$(date +%s)

# Captura de encerramento anormal
handle_exit() {
    EXIT_CODE=$?
    if [ "$EXIT_CODE" -ne 0 ]; then
        END_TIME=$(date +%s)
        ELAPSED=$(( END_TIME - START_TIME ))
        echo "============================================================" >&2
        echo "[ERRO] [STATUS: FAILED] [$(date '+%Y-%m-%d %H:%M:%S')] Execucao abortada com erro (exit code: $EXIT_CODE, duracao: ${ELAPSED}s)." >&2
        echo "============================================================" >&2
    fi
}
trap handle_exit EXIT

echo "============================================================"
echo "[INFO] [STATUS: STARTING] [$(date '+%Y-%m-%d %H:%M:%S')] Iniciando execucao da cron"
echo "[INFO] Filtro em uso: ${FILTER}"
echo "============================================================"

# 1. Carrega as credenciais de produção de forma segura
ENV_FILE="/home/flashbsb/projetos/d-network-data-extractor/.env"
if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
    export NDX_SSH_USER
    export NDX_SSH_PASS
else
    echo "[ERRO] [STATUS: FAILED] Arquivo de ambiente .env nao encontrado em: $ENV_FILE" >&2
    exit 1
fi

# 2. Entra no diretorio corrente para execucao
cd /home/flashbsb/projetos/network-data-extractor

# 3. Executa o script orquestrador com a sintaxe exata solicitada
/usr/bin/python3 network-data-extractor.py \
  --elements ../d-network-data-extractor/config/elements.cfg \
  --commands ../d-network-data-extractor/config/commands.cfg \
  --filter "${FILTER}" \
  --diff \
  --inventory \
  --ping-matrix --ping-commands ../d-network-data-extractor/config/commands.icmp.cfg \
  --ping-format html,csv \
  --topology \
  --topology-generator-path ../network-topology-generator/network-topology-generator.py \
  --topo-config ../network-topology-generator/config/config.json \
  --topo-elements ../d-network-topology-generator/config/elements.csv \
  --topo-locations ../d-network-topology-generator/config/locations.csv \
  --outbase ../d-network-data-extractor/infos/bb \
  --storage-mode hybrid \
  --skip-wizard

END_TIME=$(date +%s)
ELAPSED=$(( END_TIME - START_TIME ))
ELAPSED_MIN=$(( ELAPSED / 60 ))
ELAPSED_SEC=$(( ELAPSED % 60 ))

echo "============================================================"
echo "[INFO] [STATUS: COMPLETED] [$(date '+%Y-%m-%d %H:%M:%S')] Execucao concluida com sucesso em ${ELAPSED_MIN}m ${ELAPSED_SEC}s."
echo "============================================================"
