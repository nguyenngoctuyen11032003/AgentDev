"""Detect locally installed, already-logged-in vendor CLIs (claude / codex).

The app never reads or stores CLI tokens; it only asks the CLI for its own
status and later spawns it as a subprocess.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

DETECT_TIMEOUT = 10

VENDOR_CLI = {"anthropic": "claude", "openai": "codex"}
_STATUS_ARGS = {"anthropic": ["auth", "status"], "openai": ["login", "status"]}
_LOGIN_HINT = {"anthropic": "claude auth login", "openai": "codex login"}
_LOGOUT_ARGS = {"anthropic": ["auth", "logout"], "openai": ["logout"]}
_API_KEY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY")


def _native_exe_behind_shim(binary: str, shim: str) -> Optional[str]:
    """The real executable an npm ``.cmd`` shim launches, when it can be found next to the shim.

    The shim costs ``cmd.exe`` + ``node`` start-up (~0.4s measured for codex) on every call, leaves
    extra processes to kill on cancel, and its cmd.exe hop mangles quotes in argv values. Only the
    known npm layouts are recognised; anything else keeps using the shim."""
    import platform

    root = os.path.dirname(shim)
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    triple = "aarch64-pc-windows-msvc" if arch == "arm64" else "x86_64-pc-windows-msvc"
    candidates: List[str] = []
    if binary == "codex":
        platform_pkg = f"codex-win32-{arch}"
        base = os.path.join(root, "node_modules", "@openai")
        for pkg_root in (os.path.join(base, "codex", "node_modules", "@openai", platform_pkg),
                         os.path.join(base, platform_pkg)):
            candidates.append(os.path.join(pkg_root, "vendor", triple, "bin", "codex.exe"))
    elif binary == "claude":
        candidates.append(os.path.join(root, "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe"))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def find_cli(binary: str) -> Optional[str]:
    """Resolve an executable path (shutil.which honours PATHEXT, so .cmd shims work).

    On Windows an npm ``.cmd`` shim is replaced by the native executable it launches when that is found."""
    path = shutil.which(binary)
    if path and os.name == "nt" and path.lower().endswith((".cmd", ".bat")):
        return _native_exe_behind_shim(binary, path) or path
    return path


def cli_env() -> Dict[str, str]:
    """Environment for spawning a CLI: API-key vars dropped so the account login is used."""
    return {k: v for k, v in os.environ.items() if k not in _API_KEY_VARS}


def new_process_group_kwargs() -> Dict[str, Any]:
    """Popen kwargs that start a CLI in its own process group, so its tree can be killed alone."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill a CLI and everything it spawned (npm .cmd shims run the real CLI as a child)."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
                check=False,
            )
        else:
            import signal

            pgid = os.getpgid(proc.pid)
            # Only a CLI started in its own group (new_process_group_kwargs) may be killed as a
            # group: killing our own group would take the server down with it.
            if pgid != os.getpgid(0):
                os.killpg(pgid, signal.SIGKILL)
    except Exception:  # noqa: BLE001 - fall back to killing just the process
        pass
    try:
        proc.kill()
    except OSError:
        pass


_POLL_INTERVAL = 0.2


class CliIdle(Exception):
    """A streaming CLI produced no output for too long while no tool was running; it was killed."""

    def __init__(self, idle_seconds: float):
        super().__init__(f"no output for {idle_seconds:.0f}s")
        self.idle_seconds = idle_seconds


def _cancelled_error(cmd: List[str]) -> Exception:
    # Imported lazily: the providers package imports this module.
    from agentdev.runtime.node.agent.providers.cli_cancel import CliCancelled

    return CliCancelled(f"`{os.path.basename(str(cmd[0])) if cmd else 'cli'}` CLI stopped by the user")


def run_capture(
    cmd: List[str],
    *,
    input: Optional[str] = None,
    timeout: float = DETECT_TIMEOUT,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    cancel_event: Optional[threading.Event] = None,
    on_stdout_line: Optional[Callable[[str], None]] = None,
    idle_notice: float = 0,
    idle_kill: float = 0,
    is_busy: Optional[Callable[[], bool]] = None,
    on_idle: Optional[Callable[[float, bool], None]] = None,
) -> "subprocess.CompletedProcess[str]":
    """Run a CLI with a hard timeout (and an optional cancel event) that also kills child processes.

    ``subprocess.run`` only kills the direct child on timeout and then waits on the pipes,
    which hangs forever when a grandchild still holds them (Windows .cmd shims). Here stdin is
    fed and stdout/stderr are drained by threads while the main thread polls every 0.2s for
    exit, timeout (-> ``subprocess.TimeoutExpired``) or cancellation (-> ``CliCancelled``).

    ``on_stdout_line`` (optional) is called from the stdout reader thread with each stdout line as it
    arrives (newline included); it must not block. The returned stdout is the same text either way.

    Idle watchdog (only meaningful for a CLI that streams output): ``idle_notice`` seconds without any
    stdout/stderr output calls ``on_idle(idle_seconds, busy)`` (again every ``idle_notice`` seconds);
    ``idle_kill`` seconds without output while ``is_busy()`` is false (no tool running) kills the CLI
    tree and raises ``CliIdle``. A running tool (build, tests) is never treated as a hang.
    """
    if cancel_event is not None and cancel_event.is_set():
        raise _cancelled_error(cmd)
    kwargs = new_process_group_kwargs()
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env=env if env is not None else cli_env(),
        **kwargs,
    )
    chunks: Dict[str, List[str]] = {"out": [], "err": []}
    watching = idle_notice > 0 or idle_kill > 0
    last_output = [time.monotonic()]

    def _drain(stream: Any, key: str) -> None:
        try:
            if (key == "out" and on_stdout_line is not None) or watching:
                for line in iter(stream.readline, ""):
                    chunks[key].append(line)
                    last_output[0] = time.monotonic()
                    if key == "out" and on_stdout_line is not None:
                        try:
                            on_stdout_line(line)
                        except Exception:  # noqa: BLE001 - a listener must never stop the draining
                            pass
            else:
                chunks[key].append(stream.read())
        except (OSError, ValueError):
            pass

    def _feed() -> None:
        try:
            proc.stdin.write(input)  # type: ignore[union-attr]
        except (OSError, ValueError):
            pass  # the CLI exited / closed stdin early
        try:
            proc.stdin.close()  # type: ignore[union-attr]
        except (OSError, ValueError):
            pass

    threads = [
        threading.Thread(target=_drain, args=(proc.stdout, "out"), daemon=True),
        threading.Thread(target=_drain, args=(proc.stderr, "err"), daemon=True),
    ]
    if input is not None:
        threads.append(threading.Thread(target=_feed, daemon=True))
    for thread in threads:
        thread.start()

    def _abort() -> None:
        kill_process_tree(proc)
        # The pipe threads are daemons: give them a moment, but don't hold up a stop for long
        # (a killed grandchild's pipe can stay open for seconds on Windows).
        for thread in threads:
            thread.join(0.3)
        try:
            proc.wait(1)
        except Exception:  # noqa: BLE001
            pass

    deadline = time.monotonic() + timeout
    notices = 0
    # Wait for the process to exit and for the pipes to close (a grandchild may still hold them).
    while proc.poll() is None or any(t.is_alive() for t in threads):
        if cancel_event is not None and cancel_event.is_set():
            _abort()
            raise _cancelled_error(cmd)
        if time.monotonic() >= deadline:
            _abort()
            raise subprocess.TimeoutExpired(cmd, timeout)
        if watching and proc.poll() is None:
            idle = time.monotonic() - last_output[0]
            busy = bool(is_busy()) if is_busy is not None else False
            if idle_kill > 0 and not busy and idle >= idle_kill:
                _abort()
                raise CliIdle(idle)
            if idle_notice > 0 and idle >= idle_notice * (notices + 1):
                notices = int(idle // idle_notice)
                if on_idle is not None:
                    try:
                        on_idle(idle, busy)
                    except Exception:  # noqa: BLE001 - reporting must never stop the run
                        pass
            elif idle < idle_notice:
                notices = 0
        if proc.poll() is None:
            try:
                proc.wait(_POLL_INTERVAL)
            except subprocess.TimeoutExpired:
                pass
        else:
            for thread in threads:
                thread.join(_POLL_INTERVAL)
                if thread.is_alive():
                    break
    return subprocess.CompletedProcess(cmd, proc.returncode, "".join(chunks["out"]), "".join(chunks["err"]))


def _run(path: str, args: List[str], timeout: float = DETECT_TIMEOUT) -> Tuple[int, str, str]:
    proc = run_capture([path, *args], timeout=timeout)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _account_from_status(text: str) -> Optional[str]:
    """Pull the signed-in email out of `claude auth status` JSON (None if not present)."""
    email = _profile_from_status(text).get("email")
    return email if isinstance(email, str) and 3 <= len(email) <= 254 else None


# Non-secret fields of `claude auth status` JSON that describe the signed-in account.
_PROFILE_FIELDS = ("email", "authMethod", "apiProvider", "orgId", "orgName", "subscriptionType")


def _profile_from_status(text: str) -> Dict[str, str]:
    import json

    try:
        data = json.loads(text)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: data[k][:200] for k in _PROFILE_FIELDS if isinstance(data.get(k), str) and data[k]}


def _first_line(text: str, limit: int = 120) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:limit]
    return ""


def logout_cli(vendor: str) -> bool:
    """Sign the vendor CLI out (`claude auth logout` / `codex logout`). Never raises."""
    binary = VENDOR_CLI.get(vendor)
    path = find_cli(binary) if binary else None
    if not path:
        return False
    try:
        code, _out, _err = _run(path, _LOGOUT_ARGS[vendor])
    except Exception:  # noqa: BLE001
        return False
    finally:
        _STATUS_CACHE.pop(vendor, None)
    return code == 0


# Result of the last real detection per vendor: (monotonic time, result).
_STATUS_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
STATUS_MAX_AGE = 15.0


def detect_cli_recent(vendor: str, max_age: float = STATUS_MAX_AGE) -> Dict[str, Any]:
    """:func:`detect_cli`, reusing a result younger than ``max_age`` seconds.

    Detection spawns the CLI twice (``--version`` and the login status); account lookups (model pickers,
    workflow binding, the connections page) call it many times per request. Login, logout and every
    uncached :func:`detect_cli` refresh the cache, so a state change is seen at once."""
    entry = _STATUS_CACHE.get(vendor)
    if entry is not None and time.monotonic() - entry[0] < max_age:
        return dict(entry[1])
    return detect_cli(vendor)


def detect_cli(vendor: str) -> Dict[str, Any]:
    """Return {installed, path, version, logged_in, detail}. Never raises."""
    result = _detect_cli(vendor)
    if vendor in VENDOR_CLI and result.get("installed") and result.get("logged_in") is not None:
        _STATUS_CACHE[vendor] = (time.monotonic(), dict(result))
    else:
        _STATUS_CACHE.pop(vendor, None)
    return result


def _detect_cli(vendor: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "installed": False,
        "path": None,
        "version": None,
        "logged_in": None,
        "account": None,
        "detail": "",
    }
    binary = VENDOR_CLI.get(vendor)
    if binary is None:
        result["detail"] = f"Unsupported vendor: {vendor}"
        return result
    try:
        path = find_cli(binary)
        if not path:
            result["detail"] = f"`{binary}` CLI not found on PATH"
            return result
        result["installed"] = True
        result["path"] = path
        try:
            _code, out, err = _run(path, ["--version"])
            result["version"] = _first_line(out or err) or None
        except Exception:  # noqa: BLE001
            pass
        try:
            code, out, err = _run(path, _STATUS_ARGS[vendor])
            text = (out + "\n" + err).lower()
            if code == 0 and "not logged in" not in text and "not signed in" not in text:
                result["logged_in"] = True
                result["detail"] = "Logged in"
                result["account"] = _account_from_status(out)
                result["profile"] = _profile_from_status(out) if vendor == "anthropic" else {}
                result["status_text"] = _first_line(out or err)
            else:
                result["logged_in"] = False
                result["detail"] = f"Not logged in; run `{_LOGIN_HINT[vendor]}`"
        except Exception as exc:  # noqa: BLE001
            result["detail"] = f"Login status undetermined ({type(exc).__name__})"
    except Exception as exc:  # noqa: BLE001
        result["detail"] = f"Detection failed: {type(exc).__name__}"
    return result
