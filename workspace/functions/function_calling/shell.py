"""Run a shell command in the project workspace (build, test, lint, package managers)."""

import locale
import os
import re
import shlex
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentdev.connections.cli_auth import kill_process_tree
from agentdev.utils.code_execution import require_unsafe_code_execution

_MAX_TIMEOUT = 1800
_OUTPUT_LIMIT = 12_000
# After the main process exits, how long to keep reading output that background children still hold.
_EXIT_GRACE = 2.0
# After a timeout kill, how long to wait for the pipes to drain.
_KILL_GRACE = 5.0

# ---------------------------------------------------------------------------
# Advisory guard. This is a best-effort tripwire against an agent accidentally wrecking the machine or
# publishing work; it is NOT a sandbox and is trivially bypassable (scripts, aliases, variables, other
# interpreters). The real protection is the server opt-in (MAC_ALLOW_UNSAFE_CODE_EXECUTION) and running
# only trusted workflows.
# ---------------------------------------------------------------------------

_FORK_BOMB = re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:")
_DRIVE = re.compile(r"^[a-z]:[\\/]?$", re.I)
_CMD_FLAG = re.compile(r"^/[a-z](:\S*)?$", re.I)
_HOME_VARS = re.compile(
    r"\$\{?HOME\}?|%USERPROFILE%|%HOMEDRIVE%%HOMEPATH%|%HOMEPATH%|\$env:(USERPROFILE|HOME|HOMEPATH)\b",
    re.I,
)
_PS_ENV = re.compile(r"\$env:(\w+)", re.I)

_SHUTDOWN = {"shutdown", "reboot", "halt", "poweroff", "stop-computer", "restart-computer"}
_FORMAT = {"format", "format-volume", "diskpart"}
_DELETE = {"rm", "rmdir", "rd", "del", "erase", "remove-item", "ri", "rimraf"}
_WRAPPERS = {"powershell", "pwsh", "cmd", "bash", "sh", "zsh", "dash"}
_PREFIXES = {"sudo", "env", "nohup", "time", "command", "exec", "nice", "call", "start", "npx", "xargs"}
_GIT_VALUE_OPTS = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"}
_PKG_VALUE_OPTS = {"--prefix", "-w", "--workspace", "--registry", "--filter", "-C", "--dir", "--cwd"}
_PUBLISH_SUBCOMMAND = {
    "npm": "publish", "pnpm": "publish", "yarn": "publish", "cargo": "publish", "gem": "push",
    "twine": "upload", "poetry": "publish", "uv": "publish", "hatch": "publish", "flit": "publish",
}


def _split_segments(command: str) -> List[str]:
    """Split on unquoted separators so each piece starts with a command word."""
    segments, buf, quote = [], [], None
    for ch in command:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            buf.append(ch)
        elif ch in ";&|\n`(){}":
            segments.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    segments.append("".join(buf))
    return [s.strip() for s in segments if s.strip()]


def _unquote(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "'\"":
        return token[1:-1]
    return token


def _tokens(segment: str) -> List[str]:
    try:
        raw = shlex.split(segment, posix=False)
    except ValueError:
        raw = segment.split()
    return [_unquote(t) for t in raw if t]


def _word(token: str) -> str:
    name = re.split(r"[\\/]", token.lstrip("@"))[-1].lower()
    for ext in (".exe", ".cmd", ".bat", ".ps1"):
        if name.endswith(ext):
            return name[: -len(ext)]
    return name


def _dangerous_target(target: str, root: Path, workdir: Path) -> bool:
    """True for filesystem roots, drive roots, home, or anything resolving outside the workspace."""
    t = target.strip().rstrip(",")
    if not t:
        return False
    if _DRIVE.match(t) or t in ("/", "\\", "~"):
        return True
    t = _HOME_VARS.sub(lambda _: str(Path.home()), t)
    t = _PS_ENV.sub(lambda m: os.environ.get(m.group(1), m.group(0)), t)
    t = os.path.expandvars(os.path.expanduser(t))
    if "$" in t or "%" in t:
        return False  # unexpanded variable: can't tell, stay advisory
    # Judge a glob by the folder it expands in ("C:\*" -> "C:\", "./*" -> ".").
    parts = re.split(r"[\\/]", t)
    for i, part in enumerate(parts):
        if any(c in part for c in "*?["):
            t = "/".join(parts[:i]) or ("/" if t[:1] in "/\\" else ".")
            if re.match(r"^[a-z]:$", t, re.I):
                return True
            break
    try:
        path = Path(t)
        resolved = (path if path.is_absolute() or t[:1] in "/\\" else workdir / path).resolve()
    except (OSError, ValueError):
        return False
    return resolved != root and root not in resolved.parents


def _first_positional(args: List[str], value_opts: set) -> tuple:
    """Return (index, token) of the first non-option argument, skipping option values."""
    i = 0
    while i < len(args):
        a = args[i]
        if a in value_opts:
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        return i, a.lower()
    return -1, ""


def _check_segment(segment: str, root: Path, workdir: Path, depth: int) -> Optional[str]:
    toks = _tokens(segment)
    while toks and (re.match(r"^\w+=", toks[0]) or _word(toks[0]) in _PREFIXES):
        toks = toks[1:]
        while toks and toks[0].startswith("-") and len(toks) > 1:
            toks = toks[1:]  # flags of the prefix (npx -y, start /b handled below)
        while toks and _CMD_FLAG.match(toks[0]):
            toks = toks[1:]
    if not toks:
        return None
    cmd, args = _word(toks[0]), toks[1:]

    if cmd in _WRAPPERS and depth < 3:
        rest: List[str] = []
        for i, a in enumerate(args):
            if a.lower() in ("-c", "-command", "/c", "/k", "-encodedcommand"):
                rest = args[i + 1:]
                break
            if not a.startswith(("-", "/")) and cmd in ("powershell", "pwsh"):
                rest = args[i:]
                break
        if rest:
            return _check(" ".join(rest), root, workdir, depth + 1)
        return None

    if cmd in _SHUTDOWN:
        return "shutting the machine down"
    if cmd.startswith("mkfs") or (cmd in _FORMAT and (cmd != "format" or any(_DRIVE.match(a) for a in args))):
        return "formatting a drive"

    if cmd in _DELETE:
        targets, skip = [], False
        for i, a in enumerate(args):
            if skip:
                skip = False
                continue
            low = a.lower()
            if low in ("-path", "-literalpath"):
                if i + 1 < len(args):
                    targets.extend(args[i + 1].split(","))
                skip = True
                continue
            if low in ("-include", "-exclude", "-filter"):
                skip = True
                continue
            if a == "--" or (a.startswith("-") and len(a) > 1):
                continue
            if cmd in ("rd", "rmdir", "del", "erase") and _CMD_FLAG.match(a):
                continue
            targets.extend(a.split(",") if cmd in ("remove-item", "ri") else [a])
        if any(_dangerous_target(t, root, workdir) for t in targets):
            return "deleting a root, drive, home or out-of-workspace folder"

    if cmd == "git":
        _, sub = _first_positional(args, _GIT_VALUE_OPTS)
        if sub == "push":
            return "pushing to a remote (ask the user to push)"

    if cmd in _PUBLISH_SUBCOMMAND:
        idx, sub = _first_positional(args, _PKG_VALUE_OPTS)
        if cmd == "yarn" and sub == "npm":
            _, sub = _first_positional(args[idx + 1:], _PKG_VALUE_OPTS)
        if sub == _PUBLISH_SUBCOMMAND[cmd]:
            return "publishing a package"
    if cmd == "dotnet":
        _, sub = _first_positional(args, set())
        low = [a.lower() for a in args]
        if sub == "nuget" and "push" in low:
            return "publishing a package"
    if cmd in ("python", "python3", "py") and "-m" in args:
        i = args.index("-m")
        if args[i + 1:i + 2] == ["twine"] and "upload" in [a.lower() for a in args[i + 2:]]:
            return "publishing a package"
    return None


def _check(command: str, root: Path, workdir: Path, depth: int = 0) -> Optional[str]:
    if _FORK_BOMB.search(command):
        return "fork bomb"
    for segment in _split_segments(command):
        reason = _check_segment(segment, root, workdir, depth)
        if reason:
            return reason
    return None


# ---------------------------------------------------------------------------
# Process handling
# ---------------------------------------------------------------------------


def _fallback_encodings() -> List[str]:
    found: List[str] = []
    if os.name == "nt":
        try:
            import ctypes

            found += [f"cp{ctypes.windll.kernel32.GetOEMCP()}", f"cp{ctypes.windll.kernel32.GetACP()}"]
        except Exception:  # noqa: BLE001
            pass
    found.append(locale.getpreferredencoding(False))
    return list(dict.fromkeys(e for e in found if e))


def _decode(data: bytes) -> str:
    """UTF-8 first; cmd.exe built-ins print in the OEM code page, so fall back to it, then ANSI."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    for enc in _fallback_encodings():
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _reader(stream, sink: List[bytes]) -> None:
    try:
        for chunk in iter(lambda: stream.read1(65536) if hasattr(stream, "read1") else stream.read(65536), b""):
            sink.append(chunk)
    except (OSError, ValueError):
        pass


def _run(command: str, workdir: Path, env: Dict[str, str], limit: int) -> tuple:
    """Run with a hard timeout that also kills grandchildren and never blocks on inherited pipes.

    Returns (returncode or None if timed out, stdout bytes, stderr bytes, note).
    """
    kwargs: Dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=str(workdir),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        **kwargs,
    )
    out: List[bytes] = []
    err: List[bytes] = []
    threads = [
        threading.Thread(target=_reader, args=(proc.stdout, out), daemon=True),
        threading.Thread(target=_reader, args=(proc.stderr, err), daemon=True),
    ]
    for t in threads:
        t.start()
    deadline = time.monotonic() + limit
    note = ""
    try:
        proc.wait(timeout=limit)
        returncode: Optional[int] = proc.returncode
        grace = min(_EXIT_GRACE, max(0.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        kill_process_tree(proc)
        returncode = None
        grace = _KILL_GRACE
    end = time.monotonic() + grace
    for t in threads:
        t.join(max(0.0, end - time.monotonic()))
    if returncode is not None and any(t.is_alive() for t in threads):
        note = "[background processes still hold the output; they were left running]"
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    return returncode, b"".join(out), b"".join(err), note


def _workspace_root(ctx: Dict[str, Any] | None) -> Path:
    if not ctx or not ctx.get("python_workspace_root"):
        raise ValueError("workspace root is not available for this run")
    root = Path(ctx["python_workspace_root"]).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _tail(text: str) -> str:
    if len(text) <= _OUTPUT_LIMIT:
        return text
    return f"[… {len(text) - _OUTPUT_LIMIT} earlier characters omitted …]\n" + text[-_OUTPUT_LIMIT:]


def run_shell_command(
    command: str,
    cwd: str = ".",
    timeout: int = 300,
    _context: Dict[str, Any] | None = None,
) -> str:
    """
    Run a shell command inside the project workspace and return its exit code and output.
    Use it to install dependencies, build, run tests, lint or start scripts, e.g. "npm test",
    "npm run build", "pytest -q", "dotnet test". Commands must not wait for keyboard input.
    A few obviously destructive commands (deleting root/home/out-of-workspace folders, git push,
    publishing packages, shutdown, formatting drives) are refused; that check is advisory only.

    Args:
        command (str): The command line to run (Windows: cmd.exe syntax; macOS/Linux: sh syntax).
        cwd (str): Folder to run in, relative to the project workspace root. Defaults to the root.
        timeout (int): Seconds before the command and its child processes are killed (max 1800). Defaults to 300.

    Returns:
        str: "exit code N" (or "timed out after Ns") followed by the combined stdout and stderr
        (the last 12,000 characters).
    """
    require_unsafe_code_execution("run_shell_command")
    command = (command or "").strip()
    if not command:
        raise ValueError("command is required")

    root = _workspace_root(_context)
    workdir = (root / (cwd or ".")).resolve()
    if workdir != root and root not in workdir.parents:
        raise ValueError("cwd must stay inside the project workspace")

    reason = _check(command, root, workdir)
    if reason:
        raise ValueError(f"Blocked: {reason}. Ask the user to do this themselves if it is really needed.")
    if not workdir.is_dir():
        raise ValueError(f"cwd does not exist: {cwd}")

    limit = max(1, min(int(timeout or 300), _MAX_TIMEOUT))
    env = dict(os.environ)
    env.update({"CI": "1", "NO_COLOR": "1", "FORCE_COLOR": "0", "PYTHONIOENCODING": "utf-8"})
    returncode, out, err, note = _run(command, workdir, env, limit)
    output = (_decode(out) + _decode(err)).strip()
    if note:
        output = f"{output}\n{note}".strip()
    if returncode is None:
        return _tail(f"timed out after {limit}s\n{output}")
    return _tail(f"exit code {returncode}\n{output}")
