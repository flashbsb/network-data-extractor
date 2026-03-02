#!/bin/bash

# installdep.sh - Because dependencies don't install themselves.
# Valid for Debian/Ubuntu minimal.

if [ "$EUID" -ne 0 ]
  then echo "Please run as root (sudo). I don't have a crystal ball to guess your password."
  exit
fi

echo "Updating package list (this might take a while if you're on dial-up)..."
apt-get update

echo "Installing Python3, Pip, Pandas, and Paramiko..."
apt-get install -y python3 python3-pip python3-pandas python3-paramiko

# If pandas via apt is too old (debian stable moments), we guarantee it via pip
# But usually apt resolves the basics.
# pip3 install pandas --break-system-packages 2>/dev/null || pip3 install pandas

echo "Done. Now you can run the orchestrator:"
echo "  python3 network-data-extractor.py --help"
