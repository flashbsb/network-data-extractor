#!/bin/bash
# ==============================================================================
# Network Data Extractor - Production Cron Runner Template
# ==============================================================================
# This template demonstrates automated cron invocation with structured health
# telemetry tokens and execution timing.
# ==============================================================================
set -euo pipefail

# Resolve repository directory dynamically relative to this script
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Default collection filter (e.g. weekly / semi-weekly scope)
DEFAULT_FILTER="in:RTAC;RTED;RTOC;RTIC"
FILTER="${1:-${NDX_FILTER:-$DEFAULT_FILTER}}"

START_TIME=$(date +%s)

# Abnormal termination trap
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

# 1. Load credentials safely from environment file
ENV_FILE="${NDX_ENV_FILE:-$REPO_DIR/.env}"
if [ -f "$ENV_FILE" ]; then
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    export NDX_SSH_USER="${NDX_SSH_USER:-}"
    export NDX_SSH_PASS="${NDX_SSH_PASS:-}"
else
    echo "[ERRO] [STATUS: FAILED] Arquivo de ambiente .env nao encontrado em: $ENV_FILE" >&2
    exit 1
fi

# 2. Enter repository directory
cd "$REPO_DIR"

# 3. Execute orchestrator with production parameters
python3 network-data-extractor.py \
  --elements "${NDX_ELEMENTS:-config/elements.cfg}" \
  --commands config/commands.cfg \
  --filter "${FILTER}" \
  --diff \
  --inventory \
  --ping-matrix --ping-commands config/commands.icmp.cfg \
  --ping-format html,csv \
  --topology \
  --outbase "${NDX_OUTBASE:-infos}" \
  --storage-mode hybrid \
  --skip-wizard

END_TIME=$(date +%s)
ELAPSED=$(( END_TIME - START_TIME ))
ELAPSED_MIN=$(( ELAPSED / 60 ))
ELAPSED_SEC=$(( ELAPSED % 60 ))

echo "============================================================"
echo "[INFO] [STATUS: COMPLETED] [$(date '+%Y-%m-%d %H:%M:%S')] Execucao concluida com sucesso em ${ELAPSED_MIN}m ${ELAPSED_SEC}s."
echo "============================================================"
