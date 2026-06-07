#!/bin/bash

echo ""
echo " ============================================"
echo "  CANARY-FILE - Deception Security System"
echo " ============================================"
echo ""

# Check Python
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo " [ERROR] Python not found. Install Python 3.9+"
    echo " Mac: brew install python3"
    exit 1
fi

echo " [*] Python: $($PYTHON --version)"

# Install pip if missing
if ! $PYTHON -m pip --version &>/dev/null; then
    echo " [*] Installing pip..."
    curl https://bootstrap.pypa.io/get-pip.py | $PYTHON
fi

# Install dependencies
echo " [*] Installing dependencies..."
$PYTHON -m pip install -r requirements.txt -q

echo ""
echo " [*] Starting Canary-File server..."
echo ""
echo "  Dashboard  →  http://127.0.0.1:5000"
echo "  Press Ctrl+C to stop"
echo ""

$PYTHON app.py
