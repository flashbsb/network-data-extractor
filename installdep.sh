#!/bin/bash

# installdep.sh - Automated dependency installer for Network Data Extractor
# Valid for Debian/Ubuntu (including Debian 13 / Trixie with PEP 668)

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo)."
  exit 1
fi

echo "Updating package list..."
apt-get update

echo "Installing Python3, Pip, Core & Topology packages (Pandas, Paramiko, NetworkX, NumPy, SciPy, Psutil, Chardet), Zip, and Tar..."
apt-get install -y \
  python3 \
  python3-pip \
  python3-pandas \
  python3-paramiko \
  python3-networkx \
  python3-numpy \
  python3-scipy \
  python3-psutil \
  python3-chardet \
  zip \
  tar

echo ""
echo "Validating installed dependencies..."
python3 network-data-extractor.py --check-deps

echo "Done! You can now run the orchestrator:"
echo "  python3 network-data-extractor.py --help"
