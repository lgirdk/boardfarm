"""Boardfarm REST API runtime agent."""

# Sent by the control plane on every agent call; an agent refuses a request
# addressed to another session (a stale agent_url whose port Docker reused).
SESSION_HEADER = "X-Boardfarm-Session"
