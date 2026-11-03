"""Cancellation scope for vendor CLI subprocesses.

The agent executor wraps each model call in ``with cli_cancel_scope(context.cancel_event):``; the CLI
runner (``run_cli`` -> ``cli_auth.run_capture``) polls ``current_cancel_event()`` while the CLI runs and,
once it is set, kills the CLI's whole process tree and raises ``CliCancelled``.
"""

from __future__ import annotations

import contextvars
import threading
from contextlib import contextmanager
from typing import Iterator, Optional

_CANCEL_EVENT: contextvars.ContextVar[Optional[threading.Event]] = contextvars.ContextVar(
    "agentdev_cli_cancel_event", default=None
)


class CliCancelled(Exception):
    """The run was stopped while a vendor CLI was running; the CLI was killed."""


def current_cancel_event() -> Optional[threading.Event]:
    """The cancel event of the enclosing ``cli_cancel_scope`` (None outside any scope)."""
    return _CANCEL_EVENT.get()


@contextmanager
def cli_cancel_scope(event: Optional[threading.Event]) -> Iterator[None]:
    """Make ``event`` the current cancel event for CLI calls in this block. No-op when ``event`` is None."""
    if event is None:
        yield
        return
    token = _CANCEL_EVENT.set(event)
    try:
        yield
    finally:
        _CANCEL_EVENT.reset(token)
