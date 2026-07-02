#!/usr/bin/env bash
# One-time setup of the OrphicOS brain environment inside WSL2 (Ubuntu 24.04).
# Creates a venv and installs vLLM. Model weights download on first serve.
set -euo pipefail

VENV="$HOME/.orphic-brain/venv"

if [ ! -d "$VENV" ]; then
    echo "Creating venv at $VENV"
    python3 -m venv "$VENV"
fi

"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -U vllm "huggingface_hub[hf_transfer]"

echo "Brain environment ready. Start serving with vllm_serve.sh"
