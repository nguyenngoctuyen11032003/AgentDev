"""Aggregates API routers."""

from . import artifacts, execute, execute_sync, health, sessions, uploads, vuegraphs, workflows, websocket, batch, tools, connections, connections_check, connection_oauth, local_folders, skills, lab, lab_preview, session_outputs, workflow_assistant

ALL_ROUTERS = [
    health.router,
    local_folders.router,
    skills.router,
    lab.router,
    lab_preview.router,
    session_outputs.router,
    workflow_assistant.router,
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