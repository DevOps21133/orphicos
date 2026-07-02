"""OrphicOS thin client — the hands.

Captures a command, reads the live Windows UI Automation tree, sends both to the
OrphicOS brain (SERVER_BASE) with a per-user token, and executes the actions the
brain returns. There is NO AI model, NO provider SDK, and NO LLM key anywhere in
this package (CLAUDE.md Rules 1 & 6) — the only network destination is SERVER_BASE.
"""
