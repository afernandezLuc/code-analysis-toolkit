#!/usr/bin/env bash
set -e

echo "Updating repositories..."
sudo apt update

echo "Installing system tools..."
sudo apt install -y \
    build-essential cmake make gcc g++ \
    jq wget curl graphviz

echo "Installing static analysis tools..."
sudo apt install -y \
    cppcheck clang clang-tidy clang-tools

echo "Installing coverage tools..."
sudo apt install -y lcov

echo "Installing python..."
sudo apt install -y python3 python3-pip python3-venv

echo "Installing PDF generation tools..."
sudo apt install -y pandoc texlive-xetex

echo "Creating Python virtual environment..."
python3 -m venv .venv

echo "Installing Python packages into virtual environment..."
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install reportlab matplotlib graphviz

echo "Installation completed."
echo "Python venv available at: ./.venv"
echo "Acticate venv first with: source .venv/bin/activate"