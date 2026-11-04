from typing import Any, Dict

from agentdev.entity.enums import LogLevel, EventType
from agentdev.utils.logger import WorkflowLogger, LogEntry

# What the browser gets of a log entry. The execution log and the resume checkpoint keep the full
# entry; the socket copy is also stored in the session's replay buffer, so a full prompt per model
# call (hundreds of KB each) made a reopened session download and replay tens of MB.
_CLIENT_TEXT_LIMIT = 2000
# Model-call fields the run page never reads (it uses stage and model_name).
_MODEL_CALL_DROP = ("input",)


def _clip(value: Any, limit: int = _CLIENT_TEXT_LIMIT, depth: int = 0) -> Any:
    """``value`` with long strings shortened (nested dicts/lists too, a few levels deep)."""
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + f"… [{len(value) - limit} more chars]"
    if depth >= 4:
        return value
    if isinstance(value, dict):
        return {k: _clip(v, limit, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [_clip(v, limit, depth + 1) for v in value]
    return value


def client_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """The socket copy of a log entry: no model prompt, long texts clipped."""
    details = entry.get("details")
    kind = getattr(entry.get("event_type"), "value", entry.get("event_type"))
    # Only call records are trimmed; NODE_END and the rest carry the replies shown in the chat.
    if not isinstance(details, dict) or kind not in (EventType.MODEL_CALL.value, EventType.TOOL_CALL.value):
        return entry
    slim = dict(details)
    if kind == EventType.MODEL_CALL.value:
        for key in _MODEL_CALL_DROP:
            slim.pop(key, None)
    return {**entry, "details": _clip(slim)}


class WebSocketLogger(WorkflowLogger):
    """Workflow logger that also pushes entries via WebSocket."""

    def __init__(self, websocket_manager, session_id: str, workflow_id: str = None, log_level: LogLevel = LogLevel.DEBUG,
                 on_entry=None):
        super().__init__(workflow_id, log_level, log_to_console=False)
        self.websocket_manager = websocket_manager
        self.session_id = session_id
        self.on_entry = on_entry  # called with each entry as a dict (resume checkpoint)

    def add_log(self, level: LogLevel, message: str = None, node_id: str = None,
                event_type: EventType = None, details: Dict[str, Any] = None,
                duration: float = None) -> LogEntry | None:
        log_entry = super().add_log(level, message, node_id, event_type, details, duration)
        if not log_entry:
            return None

        entry_dict = log_entry.to_dict()
        # Send the message using the sync method which handles event loop properly
        self.websocket_manager.send_message_sync(self.session_id, {
            "type": "log",
            "data": client_entry(entry_dict)
        })
        if self.on_entry is not None:
            try:
                self.on_entry(entry_dict)
            except Exception:  # noqa: BLE001 - never break logging
                pass

        return log_entry
