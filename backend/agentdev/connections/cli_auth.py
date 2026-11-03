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
from typing import Any, Dict, List, Optional, Tuple

DETECT_TIMEOUT = 10

VENDOR_CLI = {"anthropic": "claude", "openai": "codex"}
_STATUS_ARGS = {"anthropic": ["auth", "status"], "openai": ["login", "status"]}
_LOGIN_HINT = {"anthropic": "claude auth login", "openai": "codex login"}
_LOGOUT_ARGS = {"anthropic": ["auth", "logout"], "openai": ["logout"]}
_API_KEY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY")


def find_cli(binary: str) -> Optional[str]:
    """Resolve an executable path (shutil.which honours PATHEXT, so .cmd shims work)."""
    return shutil.which(binary)


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
) -> "subprocess.CompletedProcess[str]":
    """Run a CLI with a hard timeout (and an optional cancel event) that also kills child processes.

    ``subprocess.run`` only kills the direct child on timeout and then waits on the pipes,
    which hangs forever when a grandchild still holds them (Windows .cmd shims). Here stdin is
    fed and stdout/stderr are drained by threads while the main thread polls every 0.2s for
    exit, timeout (-> ``subprocess.TimeoutExpired``) or cancellation (-> ``CliCancelled``).
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

    def _drain(stream: Any, key: str) -> None:
        try:
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
    # Wait for the process to exit and for the pipes to close (a grandchild may still hold them).
    while proc.poll() is None or any(t.is_alive() for t in threads):
        if cancel_event is not None and cancel_event.is_set():
            _abort()
            raise _cancelled_error(cmd)
        if time.monotonic() >= deadline:
            _abort()
            raise subprocess.TimeoutExpired(cmd, timeout)
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
    return code == 0


def detect_cli(vendor: str) -> Dict[str, Any]:
    """Return {installed, path, version, logged_in, detail}. Never raises."""
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
