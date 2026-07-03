"""OrphicOS voice input (Phase 3): local STT front door for the command bar.

Speech is a FRONT DOOR only — transcribed text lands in the same command path as
typed text, and is NEVER auto-submitted (the confirm gate, CLAUDE.md §7.3). STT runs
entirely on this machine; microphone audio never touches the network. The resulting
TEXT then travels to the OrphicOS brain exactly like a typed command (Rule 3).
"""
from client.voice.controller import VoiceController
from client.voice.stt import transcribe

__all__ = ["VoiceController", "transcribe"]
