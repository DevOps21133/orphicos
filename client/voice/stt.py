"""Local speech-to-text for OrphicOS voice input.

The single STT boundary: everything else calls `transcribe(audio) -> str` and nothing
more, so the engine is swappable by reimplementing this one module. The current engine
is faster-whisper (MIT; CTranslate2 runtime), running ENTIRELY on this machine — the
microphone audio never leaves the device. No LLM, no provider, no key (Rule 1): this
is a local acoustic model, not a brain.

MODEL_NAME is "base": on this class of hardware it transcribes a 5–10s utterance well
under the 2s key-release→text target (§7.4), even on the CPU fallback path. The model
weights download once, on first use, into a local cache dir under %LOCALAPPDATA%.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import numpy as np

MODEL_NAME = "base"       # Whisper size; chosen for the <2s latency target (§7.4)
SAMPLE_RATE = 16000       # Whisper's native input rate; the recorder captures at this rate

_CACHE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "OrphicOS" / "stt-models"

_lock = threading.Lock()
_model = None


def _load():
    """Load the model once (thread-safe). GPU first; verified CPU fallback.

    CUDA can fail lazily (missing cuDNN, driver mismatch) at inference rather than at
    construction, so the GPU path is validated with a tiny real inference before we
    commit to it; any failure falls back to int8 CPU, which still meets the latency
    target for the "base" model.
    """
    global _model
    with _lock:
        if _model is not None:
            return _model
        from faster_whisper import WhisperModel

        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            model = WhisperModel(MODEL_NAME, device="cuda", compute_type="float16",
                                 download_root=str(_CACHE_DIR))
            # Validate the GPU path end-to-end with 0.1s of silence.
            list(model.transcribe(np.zeros(SAMPLE_RATE // 10, dtype=np.float32))[0])
        except Exception:  # noqa: BLE001 — any GPU-stack failure means: use the CPU
            model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8",
                                 download_root=str(_CACHE_DIR))
        _model = model
        return _model


def preload() -> None:
    """Download (first run) and load the model ahead of the first utterance."""
    _load()


def transcribe(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> str:
    """Transcribe mono float32 PCM to text, locally. Returns "" for silence/noise."""
    if sample_rate != SAMPLE_RATE:
        raise ValueError(f"audio must be {SAMPLE_RATE} Hz, got {sample_rate}")
    pcm = np.ascontiguousarray(np.asarray(audio, dtype=np.float32).reshape(-1))
    if pcm.size == 0:
        return ""
    model = _load()
    segments, _info = model.transcribe(pcm, beam_size=1, vad_filter=False)
    return " ".join(seg.text.strip() for seg in segments).strip()
