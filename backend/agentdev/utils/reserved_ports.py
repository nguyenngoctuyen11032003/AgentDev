"""Ports AgentDev itself listens on; agent-built projects must never bind them.

AgentDev's frontend dev server uses 5173 (5174 when that is taken) and its backend 6400. A generated app
that hardcodes one of them hijacks the user's AgentDev page, so agents are told (system prompt) and their
subprocesses are hinted (``AGENTDEV_RESERVED_PORTS``) to stay away from them.
"""

RESERVED_PORTS = (5173, 5174, 6400)
RESERVED_PORTS_ENV = "AGENTDEV_RESERVED_PORTS"
# Ports Lab/Run previews of agent-built apps listen on (127.0.0.1 only). Pages served there are model-written
# code, so their origins are refused by the whole API (``connections.security.is_preview_origin``).
PREVIEW_PORT_RANGE = range(47100, 47200)


def with_reserved_ports(env: dict[str, str]) -> dict[str, str]:
    """``env`` (modified in place and returned) with ``AGENTDEV_RESERVED_PORTS`` set."""
    env[RESERVED_PORTS_ENV] = ",".join(str(port) for port in RESERVED_PORTS)
    return env
