"""Client → brain transport. Talks ONLY to SERVER_BASE with the OrphicOS token."""
from client.net.client import BrainClient, BrainError

__all__ = ["BrainClient", "BrainError"]
