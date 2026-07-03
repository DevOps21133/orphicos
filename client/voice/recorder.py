"""Microphone capture for OrphicOS voice input.

Records mono float32 PCM at the STT engine's native 16 kHz between start() and stop(),
entirely in memory via sounddevice (MIT; PortAudio). Nothing is ever written to disk
and the audio never touches the network — only the transcribed TEXT goes anywhere.
"""
from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd

from client.voice.stt import SAMPLE_RATE

MAX_SECONDS = 60.0  # hard cap: a stuck key must not record (or buffer) forever


class Recorder:
    """One microphone capture at a time: start() → stop() -> np.ndarray (float32 mono)."""

    def __init__(self, sample_rate: int = SAMPLE_RATE, max_seconds: float = MAX_SECONDS) -> None:
        self.sample_rate = sample_rate
        self._max_samples = int(sample_rate * max_seconds)
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._samples = 0

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        """Open the default input device and start capturing. Raises if no mic works."""
        with self._lock:
            if self._stream is not None:
                return
            self._chunks = []
            self._samples = 0
            stream = sd.InputStream(samplerate=self.sample_rate, channels=1,
                                    dtype="float32", callback=self._on_audio)
            stream.start()
            self._stream = stream

    def _on_audio(self, indata, frames, time_info, status) -> None:  # sounddevice callback
        # Runs on PortAudio's thread; keep it allocation-light and never raise.
        if self._samples < self._max_samples:
            self._chunks.append(indata[:, 0].copy())
            self._samples += frames

    def stop(self) -> np.ndarray:
        """Stop capturing and return everything recorded since start()."""
        with self._lock:
            stream, self._stream = self._stream, None
            if stream is not None:
                stream.stop()
                stream.close()
            chunks, self._chunks = self._chunks, []
            self._samples = 0
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)
