#!/usr/bin/env bash
# Serve the OrphicOS brain: UI-TARS-1.5-7B via vLLM, OpenAI-compatible on http://localhost:8000/v1
# First run downloads the model weights from Hugging Face (~16 GB, one-time).
set -euo pipefail

VENV="$HOME/.orphic-brain/venv"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$VENV" ]; then
    bash "$SCRIPT_DIR/setup_wsl.sh"
fi

export HF_HUB_ENABLE_HF_TRANSFER=1

# gpu-memory-utilization 0.85 leaves VRAM headroom for the local STT model (Phase 5).
exec "$VENV/bin/vllm" serve ByteDance-Seed/UI-TARS-1.5-7B \
    --served-model-name ui-tars-1.5-7b \
    --host 0.0.0.0 \
    --port 8000 \
    --max-model-len 32768 \
    --gpu-memory-utilization 0.85 \
    --limit-mm-per-prompt '{"image": 5}'
