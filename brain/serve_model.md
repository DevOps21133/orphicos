# OrphicOS Brain — Local Model Serving (living doc)

## Decision (2026-07-02)

**Path A: vLLM inside WSL2.** Probed on this rig:

- WSL2 present, default distro Ubuntu 24.04.2 LTS, Python 3.12.3, venv + pip working.
- RTX 5090 visible inside WSL via `nvidia-smi` (GPU passthrough confirmed).
- Docker Desktop not installed → Docker path not considered.

Model: `ByteDance-Seed/UI-TARS-1.5-7B`, served under the fixed alias
`ui-tars-1.5-7b` (`--served-model-name`) so the engine config never has to
change if the serving backend does. Endpoint: `http://localhost:8000/v1`
(WSL2 forwards localhost to Windows automatically).

## Bring-up

```powershell
# From Windows — launches the server in its own WSL window:
.\brain\scripts\brain_up.ps1

# Health check:
.\brain\scripts\brain_health.ps1
```

First run: `vllm_serve.sh` auto-runs `setup_wsl.sh` (venv at
`~/.orphic-brain/venv` in WSL, installs vLLM) and vLLM downloads the model
weights from Hugging Face (~16 GB, one-time — the only permitted network
activity besides dependency installs).

Serving parameters (see `brain/scripts/vllm_serve.sh`):
- `--max-model-len 32768` — the engine needs >= 20k tokens of context.
- `--gpu-memory-utilization 0.85` — leaves VRAM headroom for the local STT
  model that will live alongside the brain (Phase 5).
- `--limit-mm-per-prompt {"image": 5}` — multiple screenshots per request.

## Smoke test (Phase 1 task 3)

_Pending: run after first bring-up. Record the exact image+prompt request and
response here, plus `nvidia-smi` VRAM usage._
