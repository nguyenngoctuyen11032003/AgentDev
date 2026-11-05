"""Drive a vendor CLI's own sign-in (``claude auth login`` / ``codex login``) from the UI.

The flow mirrors typing the command in a terminal:
  1. ``start`` spawns the CLI and captures the sign-in URL it prints.
  2. The user opens the link, signs in, and (for Claude) copies the code shown.
  3. ``submit_code`` writes that code to the CLI's stdin, exactly as pasting it would.
The app never sees or stores any token; the CLI keeps its own credentials. Only
the URL, an optional device code, and a short status message are exposed.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

from agentdev.connections.cli_auth import (
    VENDOR_CLI,
    cli_env,
    detect_cli,
    find_cli,
    kill_process_tree,
    new_process_group_kwargs,
)

SESSION_TTL = 10 * 60  # seconds a login attempt may stay open
START_WAIT = 15.0  # seconds to wait for the CLI to print its URL
CODE_WAIT = 30.0  # seconds to wait for the CLI to accept a pasted code
MAX_LINES = 60
MAX_LINE_LEN = 300
MAX_URL_LEN = 4096

# mode "paste": browser sign-in; the CLI finishes by itself once the browser is signed in, and a
#   code shown in the browser can be pasted back as a fallback (Claude).
# mode "browser": browser sign-in with a local callback; the CLI exits when done (Codex / ChatGPT).
# mode "device": user types a code shown here into the browser; the CLI polls (Codex device code).
LOGIN_SPECS: Dict[str, Dict[str, Any]] = {
    "anthropic": {"args": ["auth", "login"], "mode": "paste"},
    "openai": {"args": ["login"], "mode": "browser"},
}
# Alternative sign-in methods per vendor, selected by name from the UI.
LOGIN_VARIANTS: Dict[tuple, Dict[str, Any]] = {
    ("openai", "device"): {"args": ["login", "--device-auth"], "mode": "device"},
}

_URL_RE = re.compile(r"https://[^\s\"'<>]+")
_DEVICE_CODE_RE = re.compile(r"\b[A-Z0-9]{4}-[A-Z0-9]{4,6}\b")
_PROMPT_RE = re.compile(r"^Paste code here if prompted\s*>\s*", re.IGNORECASE)
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
# Authorization codes are URL-safe tokens, sometimes "code#state". Reject anything else
# so nothing like control characters or newlines is ever injected into the CLI.
_CODE_RE = re.compile(r"^[A-Za-z0-9._~#:+/=\-]{8,512}$")


class CliLoginError(Exception):
    """Raised for invalid login requests; message is safe to show the user."""


@dataclass
class _Session:
    id: str
    vendor: str
    mode: str
    proc: subprocess.Popen
    started: float = field(default_factory=time.monotonic)
    lines: Deque[str] = field(default_factory=lambda: deque(maxlen=MAX_LINES))
    url: Optional[str] = None
    device_code: Optional[str] = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    reader: Optional[threading.Thread] = None

    def expired(self) -> bool:
        return time.monotonic() - self.started > SESSION_TTL

    def add_line(self, raw: str) -> None:
        full = _ANSI_RE.sub("", raw).strip()
        if not full:
            return
        line = full[:MAX_LINE_LEN]
        with self.lock:
            self.lines.append(line)
            if self.url is None:
                # Search the untruncated line: OAuth URLs are ~500 chars and cutting them drops
                # the trailing `state` parameter ("Missing state parameter").
                match = _URL_RE.search(full[:MAX_URL_LEN])
                if match:
                    self.url = match.group(0)
            if self.device_code is None and self.mode == "device":
                code = _DEVICE_CODE_RE.search(line)
                if code and not _URL_RE.search(line):
                    self.device_code = code.group(0)

    def last_message(self) -> str:
        with self.lock:
            for line in reversed(self.lines):
                if not _URL_RE.search(line):
                    return _PROMPT_RE.sub("", line)
        return ""


class CliLoginManager:
    def __init__(self) -> None:
        self._sessions: Dict[str, _Session] = {}
        self._lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------
    def _reap(self) -> None:
        for sid, session in list(self._sessions.items()):
            if session.expired() or (session.proc.poll() is not None and time.monotonic() - session.started > 60):
                self._kill(session)
                self._sessions.pop(sid, None)

    def shutdown(self) -> None:
        """Kill every pending sign-in process (server shutdown)."""
        with self._lock:
            for session in list(self._sessions.values()):
                self._kill(session)
            self._sessions.clear()

    @staticmethod
    def _kill(session: _Session) -> None:
        if session.proc.poll() is None:
            kill_process_tree(session.proc)

    def start(self, vendor: str, method: Optional[str] = None) -> Dict[str, Any]:
        spec = LOGIN_VARIANTS.get((vendor, method or "")) or LOGIN_SPECS.get(vendor)
        binary = VENDOR_CLI.get(vendor)
        if spec is None or binary is None:
            raise CliLoginError("CLI sign-in is not available for this provider")
        path = find_cli(binary)
        if not path:
            raise CliLoginError(f"`{binary}` CLI is not installed or not on PATH")

        with self._lock:
            self._reap()
            for old in [s for s in self._sessions.values() if s.vendor == vendor]:
                self._kill(old)  # only one attempt per vendor at a time
                self._sessions.pop(old.id, None)
            try:
                proc = subprocess.Popen(
                    [path, *spec["args"]],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=cli_env(),
                    cwd=tempfile.gettempdir(),
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    **new_process_group_kwargs(),
                )
            except OSError as exc:
                raise CliLoginError(f"Could not start `{binary}`: {type(exc).__name__}") from exc
            session = _Session(id=uuid.uuid4().hex, vendor=vendor, mode=spec["mode"], proc=proc)
            self._sessions[session.id] = session

        session.reader = threading.Thread(target=self._read_output, args=(session,), daemon=True)
        session.reader.start()

        deadline = time.monotonic() + START_WAIT
        while time.monotonic() < deadline:
            if session.url and (session.mode == "paste" or session.device_code):
                break
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        if not session.url:
            message = session.last_message() or "The CLI did not print a sign-in link"
            self.cancel(session.id)
            raise CliLoginError(message)
        return self._snapshot(session)

    @staticmethod
    def _read_output(session: _Session) -> None:
        stream = session.proc.stdout
        if stream is None:
            return
        try:
            for raw in stream:
                session.add_line(raw)
        except (OSError, ValueError):
            pass

    # -- operations --------------------------------------------------------
    def _get(self, session_id: str) -> _Session:
        with self._lock:
            self._reap()
            session = self._sessions.get(session_id)
        if session is None:
            raise CliLoginError("Sign-in attempt not found or expired. Start again.")
        return session

    def _snapshot(self, session: _Session) -> Dict[str, Any]:
        code = session.proc.poll()
        if code is None:
            status = "waiting"
        else:
            if session.reader is not None:
                session.reader.join(timeout=2)  # flush the CLI's final message
            # Exit code is trusted only together with the CLI's own status report.
            status = "succeeded" if code == 0 and detect_cli(session.vendor).get("logged_in") else "failed"
        return {
            "sessionId": session.id,
            "mode": session.mode,
            "status": status,
            "url": session.url,
            "deviceCode": session.device_code,
            "message": session.last_message() if status != "waiting" else "",
        }

    def status(self, session_id: str) -> Dict[str, Any]:
        return self._snapshot(self._get(session_id))

    def submit_code(self, session_id: str, code: str) -> Dict[str, Any]:
        session = self._get(session_id)
        if session.mode != "paste":
            raise CliLoginError("This sign-in does not take a pasted code; finish it in the browser")
        code = (code or "").strip()
        if not _CODE_RE.match(code):
            raise CliLoginError("That does not look like a sign-in code")
        if session.proc.poll() is not None:
            raise CliLoginError("The sign-in attempt already ended. Start again.")
        try:
            assert session.proc.stdin is not None
            session.proc.stdin.write(code + "\n")
            session.proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise CliLoginError("Could not send the code to the CLI. Start again.") from exc

        deadline = time.monotonic() + CODE_WAIT
        while time.monotonic() < deadline and session.proc.poll() is None:
            time.sleep(0.2)
        if session.proc.poll() is None:
            self.cancel(session_id)
            raise CliLoginError("The CLI did not respond in time. Start again.")
        snapshot = self._snapshot(session)
        with self._lock:
            self._sessions.pop(session_id, None)
        return snapshot

    def cancel(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        self._kill(session)
        return True


_manager: CliLoginManager | None = None


def get_login_manager() -> CliLoginManager:
    global _manager
    if _manager is None:
        _manager = CliLoginManager()
    return _manager
