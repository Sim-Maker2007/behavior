#!/usr/bin/env bash
# =============================================================================
# Agent Swarm — Setup Script
# =============================================================================
# Installs OpenViking + MiroFish + Python dependencies.
#
# Usage:
#   chmod +x swarm/setup.sh
#   ./swarm/setup.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=========================================="
echo "  Agent Swarm Setup"
echo "=========================================="

# --- 1. Check prerequisites ---
echo ""
echo "[1/5] Checking prerequisites..."

command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 required"; exit 1; }
command -v pip >/dev/null 2>&1 || command -v pip3 >/dev/null 2>&1 || { echo "ERROR: pip required"; exit 1; }
command -v docker >/dev/null 2>&1 || echo "WARNING: docker not found — needed for docker-compose deployment"
command -v git >/dev/null 2>&1 || { echo "ERROR: git required"; exit 1; }

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Python: $PYTHON_VERSION"

# --- 2. Clone vendor repos if missing ---
echo ""
echo "[2/5] Checking vendor repositories..."

if [ ! -d "$ROOT_DIR/vendor/OpenViking" ]; then
    echo "  Cloning OpenViking..."
    git clone https://github.com/volcengine/OpenViking.git "$ROOT_DIR/vendor/OpenViking"
else
    echo "  OpenViking: already cloned"
fi

if [ ! -d "$ROOT_DIR/vendor/MiroFish" ]; then
    echo "  Cloning MiroFish..."
    git clone https://github.com/666ghj/MiroFish.git "$ROOT_DIR/vendor/MiroFish"
else
    echo "  MiroFish: already cloned"
fi

# --- 3. Install Python dependencies ---
echo ""
echo "[3/5] Installing Python dependencies..."

# OpenViking SDK
pip install openviking --upgrade --quiet
echo "  openviking: installed"

# MiroFish backend dependencies
if [ -f "$ROOT_DIR/vendor/MiroFish/backend/pyproject.toml" ]; then
    pip install -e "$ROOT_DIR/vendor/MiroFish/backend" --quiet 2>/dev/null || \
    pip install -r "$ROOT_DIR/vendor/MiroFish/backend/requirements.txt" --quiet 2>/dev/null || \
    echo "  WARNING: MiroFish backend deps — install manually or use Docker"
fi

# Swarm dependencies
pip install pyyaml requests --quiet
echo "  pyyaml, requests: installed"

# --- 4. Set up environment file ---
echo ""
echo "[4/5] Environment configuration..."

if [ ! -f "$SCRIPT_DIR/.env" ]; then
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    echo "  Created swarm/.env from template — EDIT THIS FILE with your API keys"
else
    echo "  swarm/.env: already exists"
fi

# --- 5. Verify ---
echo ""
echo "[5/5] Verifying installation..."

python3 -c "import openviking; print(f'  openviking: {openviking.__version__}')" 2>/dev/null || \
    echo "  WARNING: openviking import failed — check installation"
python3 -c "import yaml; print('  pyyaml: OK')"
python3 -c "import requests; print('  requests: OK')"

echo ""
echo "=========================================="
echo "  Setup Complete"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Edit swarm/.env with your API keys"
echo "  2. Start services:"
echo "     docker compose -f swarm/docker-compose.yaml up -d"
echo "  3. Run a prediction:"
echo "     python swarm/example_predict.py"
echo ""
echo "  Or start services manually:"
echo "     openviking-server &           # Port 1933"
echo "     cd vendor/MiroFish && python backend/run.py &  # Port 5001"
echo ""
