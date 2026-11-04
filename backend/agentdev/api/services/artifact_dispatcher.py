"""Utilities to distribute artifact events to internal consumers."""

import logging
from pathlib import Path
from typing import Optional, Sequence

from agentdev.api.services.artifact_events import ArtifactEvent
from agentdev.api.services.local_projects import is_noise_path, mentioned_in, wants_files_shown
from agentdev.api.services.session_store import WorkflowSessionStore
from agentdev.workflow.hooks.workspace_artifact import WorkspaceArtifact


class ArtifactDispatcher:
    """Persists artifact events and optionally mirrors them to WebSocket clients."""

    def __init__(
        self,
        session_id: str,
        session_store: WorkflowSessionStore,
        websocket_manager=None,
        local_root: Optional[Path] = None,
    ) -> None:
        self.session_id = session_id
        self.session_store = session_store
        self.websocket_manager = websocket_manager
        self.logger = logging.getLogger(__name__)
        # Set when the run works in a folder opened in place: the agents edit the real files,
        # so they are not listed back in the chat unless the user asks to see them.
        self.local_root = Path(local_root) if local_root else None
        self.request_text = ""

    def set_request(self, text: Optional[str]) -> None:
        self.request_text = text or ""

    def _filter_local(self, events: list) -> list:
        if self.local_root is None:
            return events
        if not wants_files_shown(self.request_text):
            return []
        kept = [
            event
            for event in events
            if event.change_type != "deleted" and not is_noise_path(event.relative_path)
        ]
        named = [event for event in kept if mentioned_in(self.request_text, event.relative_path)]
        kept = named or kept
        for event in kept:
            event.extra = {**(event.extra or {}), "open_local": True}
        return kept[:10]

    def emit_workspace_artifacts(self, artifacts: Sequence[WorkspaceArtifact]) -> None:
        if not artifacts:
            return
        events = [self._workspace_to_event(artifact) for artifact in artifacts]
        self.emit(self._filter_local(events))

    def emit(self, events: Sequence[ArtifactEvent]) -> None:
        if not events:
            return
        queue = self.session_store.get_artifact_queue(self.session_id)
        if not queue:
            self.logger.debug("Artifact queue missing for session %s", self.session_id)
            return
        queue.append_many(events)
        if self.websocket_manager:
            payload = {
                "type": "artifact_created",
                "data": {
                    "session_id": self.session_id,
                    "events": [event.to_dict() for event in events],
                },
            }
            try:
                self.websocket_manager.send_message_sync(self.session_id, payload)
            except Exception as exc:
                self.logger.warning("Failed to broadcast artifact events: %s", exc)

    def _workspace_to_event(self, artifact: WorkspaceArtifact) -> ArtifactEvent:
        return ArtifactEvent(
            node_id=artifact.node_id,
            attachment_id=artifact.attachment_id,
            file_name=artifact.file_name,
            relative_path=artifact.relative_path,
            workspace_path=artifact.absolute_path,
            mime_type=artifact.mime_type,
            size=artifact.size,
            sha256=artifact.sha256,
            data_uri=artifact.data_uri,
            created_at=artifact.created_at,
            change_type=artifact.change_type,
            extra=artifact.extra,
        )
