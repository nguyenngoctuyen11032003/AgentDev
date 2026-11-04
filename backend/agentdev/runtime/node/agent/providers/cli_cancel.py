"""Cancellation scope for vendor CLI subprocesses.

The agent executor wraps each model call in ``with cli_cancel_scope(context.cancel_event):``; the CLI
runner (``run_cli`` -> ``cli_auth.run_capture``) polls ``current_cancel_event()`` while the CLI runs and,
once it is set, kills the CLI's whole process tree and raises ``CliCancelled``.
"""

from __future__ import annotations

import contextvars
import os
import threading
from contextlib import contextmanager
from typing import Callable, Iterator, Optional, Tuple

_CANCEL_EVENT: contextvars.ContextVar[Optional[threading.Event]] = contextvars.ContextVar(
    "agentdev_cli_cancel_event", default=None
)


class CliCancelled(Exception):
    """The run was stopped while a vendor CLI was running; the CLI was killed."""


def current_cancel_event() -> Optional[threading.Event]:
    """The cancel event of the enclosing ``cli_cancel_scope`` (None outside any scope)."""
    return _CANCEL_EVENT.get()


IdleListener = Callable[[float, bool, bool], None]  # (idle seconds, a tool is running, CLI was killed)

_IDLE_LISTENER: contextvars.ContextVar[Optional[IdleListener]] = contextvars.ContextVar(
    "agentdev_cli_idle_listener", default=None
)

DEFAULT_IDLE_NOTICE = 180.0  # seconds without CLI output before the UI is told the agent is thinking long
DEFAULT_IDLE_KILL = 600.0  # seconds without output and without a running tool before the CLI is killed


def _env_seconds(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.environ.get(name, default)))
    except ValueError:
        return default


def idle_limits() -> Tuple[float, float]:
    """(notice, kill) seconds. ``AGENTDEV_CLI_IDLE_NOTICE`` / ``AGENTDEV_CLI_IDLE_KILL``; 0 disables."""
    return _env_seconds("AGENTDEV_CLI_IDLE_NOTICE", DEFAULT_IDLE_NOTICE), _env_seconds(
        "AGENTDEV_CLI_IDLE_KILL", DEFAULT_IDLE_KILL
    )


def current_idle_listener() -> Optional[IdleListener]:
    return _IDLE_LISTENER.get()


@contextmanager
def cli_idle_scope(listener: Optional[IdleListener]) -> Iterator[None]:
    """Report a silent CLI (long thinking, then a kill) to ``listener`` for CLI calls in this block."""
    if listener is None:
        yield
        return
    token = _IDLE_LISTENER.set(listener)
    try:
        yield
    finally:
        _IDLE_LISTENER.reset(token)


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
