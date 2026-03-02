#!/bin/bash

# installdep.sh - Porque dependências não se instalam sozinhas.
# Valido para Debian/Ubuntu minimal.

if [ "$EUID" -ne 0 ]
  then echo "Por favor, execute como root (sudo). Não tenho bola de cristal para adivinhar sua senha."
  exit
fi

echo "Atualizando lista de pacotes (isso pode demorar se sua internet for discada)..."
apt-get update

echo "Instalando Python3, Pip, Pandas e Paramiko..."
apt-get install -y python3 python3-pip python3-pandas python3-paramiko

# Se o pandas via apt for muito antigo (debian stable moments), garantimos via pip
# Mas geralmente o apt resolve para o básico.
# pip3 install pandas --break-system-packages 2>/dev/null || pip3 install pandas

echo "Pronto. Agora você pode rodar o orquestrador:"
echo "  python3 network-data-extractor.py --help"
