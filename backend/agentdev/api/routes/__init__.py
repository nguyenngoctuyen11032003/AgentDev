"""Aggregates API routers."""

from . import artifacts, execute, execute_sync, health, sessions, uploads, vuegraphs, workflows, websocket, batch, tools, connections, connections_check, connection_oauth, local_folders, skills, lab

ALL_ROUTERS = [
    health.router,
    local_folders.router,
    skills.router,
    lab.router,
    vuegraphs.router,
    workflows.router,
    uploads.router,
    artifacts.router,
    sessions.router,
    batch.router,
    execute.router,
    execute_sync.router,
    tools.router,
    connections.router,
    connections_check.router,
    connection_oauth.router,
    websocket.router,
]

__all__ = ["ALL_ROUTERS"]