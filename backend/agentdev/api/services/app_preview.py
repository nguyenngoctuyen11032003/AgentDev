"""App preview ("Chạy thử") for Lab run outputs.

Starts what a Lab run produced (a Node/Vite/Next app, a Python web app, or a static site) so the
user can try it from the Lab page. Every preview:

- runs with ``cwd`` = the run's product dir (inside ``storage/warehouse``), never anywhere else;
- listens on a port from ``PORT_RANGE`` (47100-47199), checked free by binding, never on the
  ports AgentDev itself uses (5173/5174 frontend, 6400 backend);
- runs in its own process group so the whole tree (npm -> node -> vite ...) can be killed;
- gets an environment without API keys / tokens / AgentDev settings;
- is stopped after ``IDLE_SECONDS`` without anyone asking for its status, when its outputs are
  deleted, and when the server shuts down. At most ``MAX_CONCURRENT`` run at once.

Static sites need no process: their URL is the Lab ``site/`` route that serves the files.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

from agentdev.utils.reserved_ports import RESERVED_PORTS as AGENTDEV_PORTS
from agentdev.utils.reserved_ports import with_reserved_ports

logger = logging.getLogger(__name__)

PORT_RANGE = range(47100, 47200)
RESERVED_PORTS = frozenset(AGENTDEV_PORTS)  # AgentDev's own frontend/backend ports
MAX_CONCURRENT = 3
IDLE_SECONDS = 30 * 60
READY_TIMEOUT = 90.0
INSTALL_TIMEOUT = 300.0
LOG_LINES = 500
LOG_TAIL_LINES = 60

ACTIVE_STATUSES = ("installing", "starting", "running")
_SKIP_DIRS = {"node_modules", ".venv", "venv", ".git", "__pycache__", ".pytest_cache", ".mypy_cache",
              "dist", "build", ".next", "attachments"}
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
# Every credential variable (vendor keys included) matches _DROP_ENV_PATTERN; PORT/HOST are set per preview.
_DROP_ENV_EXACT = {"PORT", "HOST"}
_DROP_ENV_PATTERN = re.compile(r"(API_KEY|_TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.IGNORECASE)
_MONOREPO_PAIRS = (("client", "server"), ("frontend", "backend"), ("web", "api"), ("web", "server"),
                   ("frontend", "server"), ("client", "api"), ("client", "backend"), ("frontend", "api"))
_PROXY_TARGET = re.compile(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0)\s*:\s*(\d{2,5})")


class PreviewError(Exception):
    """A preview cannot be started (nothing runnable, limit reached, bad directory)."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------

def port_is_free(port: int) -> bool:
    """True when nothing listens on ``port`` (IPv4 or IPv6 loopback) and we can bind it."""
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.2)
                if probe.connect_ex((host, port)) == 0:
                    return False
        except OSError:
            pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(("127.0.0.1", port))
    except OSError:
        return False
    return True


def allocate_port(exclude: Optional[set] = None) -> int:
    """First free port of ``PORT_RANGE`` that is not reserved nor in ``exclude``."""
    exclude = set(exclude or ())
    for port in PORT_RANGE:
        if port in RESERVED_PORTS or port in exclude:
            continue
        if port_is_free(port):
            return port
    raise PreviewError("Không còn cổng trống trong khoảng 47100-47199 để chạy thử.", 503)


def port_accepts(port: int) -> bool:
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.5)
                if probe.connect_ex((host, port)) == 0:
                    return True
        except OSError:
            continue
    return False


# ---------------------------------------------------------------------------
# Launch-plan detection
# ---------------------------------------------------------------------------

@dataclass
class ProcTemplate:
    """A process to start. ``{port}`` in ``cmd``/``env`` is replaced by the assigned port;
    ``{server_port}`` by the server port of a client+server pair."""

    name: str
    cwd: Path
    cmd: List[str]
    env: Dict[str, str] = field(default_factory=dict)
    role: str = "main"  # "main" (its port is the URL) or "server"
    preferred_port: Optional[int] = None  # hardcoded port another part expects (vite proxy target)


@dataclass
class LaunchPlan:
    kind: str  # static | node | python | none
    summary: str = ""
    entry: str = ""  # static: relative path of the html page to open
    installs: List[Path] = field(default_factory=list)  # dirs needing `npm install`
    processes: List[ProcTemplate] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _read_text(path: Path, limit: int = 200_000) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _tool(name: str) -> str:
    return shutil.which(name) or name


def _npm() -> str:
    return _tool("npm")


def _vite_configs(directory: Path) -> List[Path]:
    return [p for p in directory.glob("vite.config.*") if p.is_file()]


def _node_process(directory: Path, name: str = "app") -> Optional[Tuple[ProcTemplate, str]]:
    """How to run the Node package in ``directory``; returns (process, framework label)."""
    pkg = _read_json(directory / "package.json")
    scripts = pkg.get("scripts") if isinstance(pkg.get("scripts"), dict) else {}
    deps: Dict[str, Any] = {}
    for key in ("dependencies", "devDependencies"):
        if isinstance(pkg.get(key), dict):
            deps.update(pkg[key])
    script = next((s for s in ("dev", "start", "serve") if isinstance(scripts.get(s), str)), None)
    script_cmd = (scripts.get(script) or "").strip() if script else ""
    first_token = script_cmd.split()[0] if script_cmd else ""
    npm = _npm()
    env = {"PORT": "{port}"}

    if "next" in deps:
        args = ["-p", "{port}", "-H", "127.0.0.1"]
        if first_token == "next":
            cmd = [npm, "run", script, "--", *args]
        else:
            cmd = [npm, "exec", "--no", "--", "next", "dev", *args]
        return ProcTemplate(name, directory, cmd, env), "Next.js"
    if "vite" in deps or _vite_configs(directory):
        # CLI flags override a hardcoded `server.port` in vite.config.
        args = ["--port", "{port}", "--strictPort", "--host", "127.0.0.1"]
        if first_token == "vite" and script:
            cmd = [npm, "run", script, "--", *args]
        else:
            cmd = [npm, "exec", "--no", "--", "vite", *args]
        return ProcTemplate(name, directory, cmd, env), "Vite"
    if "react-scripts" in deps and script:
        return ProcTemplate(name, directory, [npm, "run", script], env), "React"
    if script:
        return ProcTemplate(name, directory, [npm, "run", script], env), "Node"
    main = pkg.get("main") if isinstance(pkg.get("main"), str) else ""
    for candidate in [main, "server.js", "index.js", "app.js", "main.js", "server.mjs", "index.mjs"]:
        if candidate and (directory / candidate).is_file():
            return ProcTemplate(name, directory, [_tool("node"), candidate], env), "Node"
    return None


def _python_exe(directory: Path) -> str:
    for venv in (".venv", "venv"):
        for rel in (("Scripts", "python.exe"), ("bin", "python")):
            candidate = directory.joinpath(venv, *rel)
            if candidate.is_file():
                return str(candidate)
    return sys.executable


def _python_process(directory: Path, name: str = "app") -> Optional[Tuple[ProcTemplate, str]]:
    """How to run a Python web app in ``directory`` (FastAPI, Flask, Django or a script using PORT)."""
    py = _python_exe(directory)
    env = {"PORT": "{port}", "PYTHONUNBUFFERED": "1"}
    manage = directory / "manage.py"
    if manage.is_file() and "django" in _read_text(manage).lower():
        return ProcTemplate(name, directory, [py, "manage.py", "runserver", "127.0.0.1:{port}", "--noreload"], env), "Django"
    candidates: List[Path] = []
    for base in (directory, directory / "app", directory / "src", directory / "backend"):
        for fname in ("main.py", "app.py", "server.py", "run.py", "api.py", "asgi.py", "wsgi.py"):
            path = base / fname
            if path.is_file() and path not in candidates:
                candidates.append(path)
    scripted: Optional[Path] = None
    for path in candidates:
        text = _read_text(path)
        module = ".".join(path.relative_to(directory).with_suffix("").parts)
        match = re.search(r"^(\w+)\s*(?::[^=]*)?=\s*(FastAPI|Starlette)\(", text, re.MULTILINE)
        if match:
            return ProcTemplate(name, directory, [py, "-m", "uvicorn", f"{module}:{match.group(1)}",
                                                  "--host", "127.0.0.1", "--port", "{port}"], env), match.group(2)
        match = re.search(r"^(\w+)\s*=\s*Flask\(", text, re.MULTILINE)
        if match:
            return ProcTemplate(name, directory, [py, "-m", "flask", "--app", f"{module}:{match.group(1)}", "run",
                                                  "--host", "127.0.0.1", "--port", "{port}", "--no-reload"], env), "Flask"
        if scripted is None and "__main__" in text and any(
            token in text for token in ("http.server", "socketserver", "app.run", "uvicorn.run", "web.run_app",
                                        "PORT", "serve_forever")
        ):
            scripted = path
    if scripted is not None:
        return ProcTemplate(name, directory, [py, str(scripted.relative_to(directory))], env), "Python"
    return None


def _static_entry(directory: Path) -> str:
    for base in ("", "public", "dist", "build", "site", "docs", "www"):
        candidate = directory / base / "index.html" if base else directory / "index.html"
        if candidate.is_file():
            return candidate.relative_to(directory).as_posix()
    pages = sorted(p.name for p in directory.glob("*.html") if p.is_file())
    return pages[0] if pages else ""


def _needs_install(directory: Path) -> bool:
    return (directory / "package.json").is_file() and not (directory / "node_modules").is_dir()


def _proxy_port(client: Path) -> Optional[int]:
    texts = [_read_text(p) for p in _vite_configs(client)]
    proxy = _read_json(client / "package.json").get("proxy")
    if isinstance(proxy, str):
        texts.append(proxy)
    for text in texts:
        match = _PROXY_TARGET.search(text)
        if match:
            return int(match.group(1))
    return None


def _monorepo_plan(root: Path) -> Optional[LaunchPlan]:
    for client_name, server_name in _MONOREPO_PAIRS:
        client, server = root / client_name, root / server_name
        if not (client / "package.json").is_file() or not server.is_dir():
            continue
        client_proc = _node_process(client, "client")
        if client_proc is None:
            continue
        if (server / "package.json").is_file():
            server_proc = _node_process(server, "server")
        else:
            server_proc = _python_process(server, "server")
        if server_proc is None:
            continue
        cproc, cfw = client_proc
        sproc, sfw = server_proc
        sproc.role = "server"
        sproc.preferred_port = _proxy_port(client)
        cproc.env.update({"SERVER_PORT": "{server_port}", "API_PORT": "{server_port}",
                          "BACKEND_PORT": "{server_port}", "VITE_API_PORT": "{server_port}"})
        installs: List[Path] = []
        root_pkg = _read_json(root / "package.json")
        if root_pkg.get("workspaces") and _needs_install(root):
            installs.append(root)
        elif not root_pkg.get("workspaces"):
            installs.extend(d for d in (client, server) if _needs_install(d))
        return LaunchPlan(
            kind="node",
            summary=f"Ứng dụng Node ({cfw} + {sfw})",
            entry=f"{client_name}/package.json",
            installs=installs,
            processes=[sproc, cproc],
        )
    return None


def _plan_for_dir(root: Path) -> LaunchPlan:
    plan = _monorepo_plan(root)
    if plan:
        return plan
    if (root / "package.json").is_file():
        node = _node_process(root)
        if node:
            proc, fw = node
            return LaunchPlan(kind="node", summary=f"Ứng dụng Node ({fw})", entry="package.json",
                              installs=[root] if _needs_install(root) else [], processes=[proc])
    python = _python_process(root)
    if python:
        proc, fw = python
        entry = proc.cmd[1] if len(proc.cmd) == 2 else ""
        plan = LaunchPlan(kind="python", summary=f"Ứng dụng Python ({fw})", entry=entry, processes=[proc])
        if (root / "requirements.txt").is_file() or (root / "pyproject.toml").is_file():
            plan.notes.append("Dự án có requirements.txt/pyproject.toml: thư viện không được cài tự động; "
                              "nếu thiếu thư viện, hãy cài vào .venv của dự án.")
        return plan
    entry = _static_entry(root)
    if entry:
        return LaunchPlan(kind="static", summary="Trang web tĩnh", entry=entry)
    return LaunchPlan(kind="none", summary="Không tìm thấy ứng dụng để chạy thử")


def detect_launch_plan(root: Path) -> LaunchPlan:
    """How to run the product in ``root``. Falls back to a single runnable sub-folder
    (e.g. the agents put everything in ``code_workspace/my-app/``)."""
    root = Path(root)
    plan = _plan_for_dir(root)
    if plan.kind in ("node", "python"):
        return plan
    sub_plans: List[Tuple[Path, LaunchPlan]] = []
    try:
        subdirs = [d for d in sorted(root.iterdir()) if d.is_dir() and not d.is_symlink()
                   and d.name not in _SKIP_DIRS and not d.name.startswith(".")]
    except OSError:
        subdirs = []
    for sub in subdirs:
        sub_plan = _plan_for_dir(sub)
        if sub_plan.kind in ("node", "python"):
            sub_plans.append((sub, sub_plan))
    if len(sub_plans) == 1:
        sub, sub_plan = sub_plans[0]
        sub_plan.entry = f"{sub.name}/{sub_plan.entry}" if sub_plan.entry else sub.name
        return sub_plan
    if plan.kind == "static":
        return plan
    for sub in subdirs:
        entry = _static_entry(sub)
        if entry:
            return LaunchPlan(kind="static", summary="Trang web tĩnh", entry=f"{sub.name}/{entry}")
    return plan


# ---------------------------------------------------------------------------
# Processes
# ---------------------------------------------------------------------------

def preview_env(extra: Dict[str, str]) -> Dict[str, str]:
    """Server environment minus secrets / AgentDev settings, plus the preview's own vars."""
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in _DROP_ENV_EXACT and not _DROP_ENV_PATTERN.search(k)
           and not k.upper().startswith("AGENTDEV_")}
    env.update({"HOST": "127.0.0.1", "BROWSER": "none", "NO_UPDATE_NOTIFIER": "1", "FORCE_COLOR": "0",
                "npm_config_update_notifier": "false", "npm_config_fund": "false", "npm_config_audit": "false"})
    env.update(extra)
    return with_reserved_ports(env)


def _popen(cmd: List[str], cwd: Path, env: Dict[str, str]) -> subprocess.Popen:
    from agentdev.connections.cli_auth import new_process_group_kwargs

    kwargs = new_process_group_kwargs()
    if os.name == "nt":
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        cmd, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1, **kwargs,
    )


def _kill_tree(proc: subprocess.Popen) -> None:
    from agentdev.connections.cli_auth import kill_process_tree

    if proc.poll() is None:
        kill_process_tree(proc)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        logger.warning("Preview process %s did not exit after kill", proc.pid)


def _fill(value: str, ports: Dict[str, int]) -> str:
    return value.replace("{port}", str(ports["port"])).replace("{server_port}", str(ports.get("server_port", "")))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Preview:
    key: Tuple[str, int]
    root: Path
    kind: str
    status: str = "idle"
    url: Optional[str] = None
    port: Optional[int] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    frameable: Optional[bool] = None  # False: the app forbids being shown inside another page
    last_access: float = field(default_factory=time.monotonic)
    procs: List[Tuple[str, subprocess.Popen]] = field(default_factory=list)
    log: Deque[str] = field(default_factory=lambda: deque(maxlen=LOG_LINES))
    stop_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add_log(self, line: str) -> None:
        with self.lock:
            self.log.append(_ANSI.sub("", line.rstrip("\r\n")))

    def to_dict(self) -> Dict[str, Any]:
        with self.lock:
            tail = "\n".join(list(self.log)[-LOG_TAIL_LINES:])
        return {"status": self.status, "url": self.url, "port": self.port, "kind": self.kind,
                "log_tail": tail, "error": self.error, "started_at": self.started_at,
                "frameable": self.frameable}


def _pump(preview: Preview, label: str, proc: subprocess.Popen) -> None:
    stream = proc.stdout
    if stream is None:
        return
    try:
        for line in stream:
            preview.add_log(f"[{label}] {line}")
    except (OSError, ValueError):
        pass


class PreviewManager:
    def __init__(self) -> None:
        self._previews: Dict[Tuple[str, int], Preview] = {}
        self._lock = threading.Lock()
        self._reaper: Optional[threading.Thread] = None
        self._closed = False

    # -- public API by (job_id, run_index) ---------------------------------

    def start(self, job_id: str, run_index: int) -> Dict[str, Any]:
        root = _product_dir_for(job_id, run_index)
        return self.start_dir((job_id, run_index), root, _site_base(job_id, run_index))

    def status(self, job_id: str, run_index: int) -> Dict[str, Any]:
        key = (job_id, run_index)
        with self._lock:
            preview = self._previews.get(key)
        if preview is not None:
            preview.last_access = time.monotonic()
            return preview.to_dict()
        kind: Optional[str] = None
        try:
            plan = detect_launch_plan(_product_dir_for(job_id, run_index))
            kind = plan.kind if plan.kind != "none" else None
        except Exception as exc:  # noqa: BLE001 - status of a run without outputs is just idle
            logger.debug("No preview plan for %s/%s: %s", job_id, run_index, exc)
        return {"status": "idle", "url": None, "port": None, "kind": kind, "log_tail": "", "error": None,
                "started_at": None}

    def stop(self, job_id: str, run_index: int) -> Dict[str, Any]:
        with self._lock:
            preview = self._previews.get((job_id, run_index))
        if preview is None:
            return {"status": "stopped", "url": None, "port": None, "kind": None, "log_tail": "", "error": None,
                    "started_at": None}
        self._stop_preview(preview, "Đã dừng chạy thử.")
        return preview.to_dict()

    # -- by directory ------------------------------------------------------

    def start_dir(self, key: Tuple[str, int], root: Path, site_base: str = "") -> Dict[str, Any]:
        root = Path(root).resolve()
        _check_root(root)
        with self._lock:
            if self._closed:
                raise PreviewError("Máy chủ đang tắt.", 503)
            existing = self._previews.get(key)
            if existing is not None and existing.status in ACTIVE_STATUSES:
                existing.last_access = time.monotonic()
                return existing.to_dict()
            plan = detect_launch_plan(root)
            if plan.kind == "none":
                raise PreviewError("Không tìm thấy ứng dụng hoặc trang web để chạy thử trong kết quả này.", 422)
            preview = Preview(key=key, root=root, kind=plan.kind, started_at=_now_iso())
            if plan.kind == "static":
                entry = "" if plan.entry == "index.html" else plan.entry
                preview.status = "running"
                preview.frameable = True  # served by the Lab's own sandboxed site route
                preview.url = f"{site_base}{entry}"
                self._previews[key] = preview
                return preview.to_dict()
            active = [p for p in self._previews.values() if p.kind != "static" and p.status in ACTIVE_STATUSES]
            if len(active) >= MAX_CONCURRENT:
                raise PreviewError(f"Đã có {MAX_CONCURRENT} bản chạy thử đang chạy. Hãy dừng bớt một bản rồi thử lại.",
                                   409)
            preview.status = "installing" if plan.installs else "starting"
            self._previews[key] = preview
            self._ensure_reaper()
        for note in plan.notes:
            preview.add_log(f"[agentdev] {note}")
        threading.Thread(target=self._run, args=(preview, plan), name=f"preview-{key[0]}-{key[1]}",
                         daemon=True).start()
        return preview.to_dict()

    def stop_for_dir(self, path: Any) -> int:
        """Stop every preview whose product dir is ``path`` or inside it. Returns how many."""
        target = Path(str(path)).resolve()
        with self._lock:
            matches = [p for p in self._previews.values() if p.root == target or p.root.is_relative_to(target)]
        for preview in matches:
            self._stop_preview(preview, "Đã dừng vì kết quả bị xoá.")
            with self._lock:
                if self._previews.get(preview.key) is preview:
                    del self._previews[preview.key]
        return len(matches)

    def has_live_preview(self, path: Any) -> bool:
        """True when a preview process runs from ``path`` or a folder inside it."""
        target = Path(str(path)).resolve()
        with self._lock:
            return any(p.kind != "static" and p.status in ACTIVE_STATUSES
                       and (p.root == target or p.root.is_relative_to(target)) for p in self._previews.values())

    def stop_all(self) -> None:
        with self._lock:
            self._closed = True
            previews = list(self._previews.values())
        for preview in previews:
            self._stop_preview(preview, "Máy chủ tắt.")

    # -- internals -------------------------------------------------------

    def _stop_preview(self, preview: Preview, reason: str) -> None:
        preview.stop_event.set()
        with preview.lock:
            procs = list(preview.procs)
        for _label, proc in procs:
            _kill_tree(proc)
        if preview.status in ACTIVE_STATUSES or preview.status == "idle":
            preview.status = "stopped"
            preview.add_log(f"[agentdev] {reason}")

    def _fail(self, preview: Preview, error: str) -> None:
        if preview.stop_event.is_set():
            return
        preview.error = error
        preview.add_log(f"[agentdev] Lỗi: {error}")
        preview.stop_event.set()
        with preview.lock:
            procs = list(preview.procs)
        for _label, proc in procs:
            _kill_tree(proc)
        preview.status = "failed"

    def _spawn(self, preview: Preview, label: str, cmd: List[str], cwd: Path, env: Dict[str, str]) -> subprocess.Popen:
        preview.add_log(f"[agentdev] {label}: {' '.join([os.path.basename(cmd[0]), *cmd[1:]])}")
        proc = _popen(cmd, cwd, env)
        with preview.lock:
            preview.procs.append((label, proc))
        if preview.stop_event.is_set():  # stopped while spawning
            _kill_tree(proc)
        threading.Thread(target=_pump, args=(preview, label, proc), daemon=True).start()
        return proc

    def _run(self, preview: Preview, plan: LaunchPlan) -> None:
        try:
            self._run_inner(preview, plan)
        except PreviewError as exc:
            self._fail(preview, str(exc))
        except Exception as exc:
            logger.exception("App preview failed")
            self._fail(preview, f"{type(exc).__name__}: {exc}")

    def _run_inner(self, preview: Preview, plan: LaunchPlan) -> None:
        for directory in plan.installs:
            if preview.stop_event.is_set():
                return
            preview.status = "installing"
            lock = directory / "package-lock.json"
            cmd = [_npm(), "ci" if lock.is_file() else "install", "--no-audit", "--no-fund"]
            proc = self._spawn(preview, "install", cmd, directory, preview_env({}))
            deadline = time.monotonic() + INSTALL_TIMEOUT
            while proc.poll() is None:
                if preview.stop_event.wait(0.5):
                    return
                if time.monotonic() > deadline:
                    raise PreviewError("Cài thư viện (npm install) quá 5 phút.")
            if proc.returncode != 0:
                raise PreviewError(f"Cài thư viện (npm) thất bại, mã lỗi {proc.returncode}.")
            with preview.lock:
                preview.procs = [(lbl, p) for lbl, p in preview.procs if p is not proc]
        if preview.stop_event.is_set():
            return
        preview.status = "starting"
        for template in plan.processes:
            _seed_env_file(preview, template.cwd)
        ports: Dict[str, int] = {}
        server = next((p for p in plan.processes if p.role == "server"), None)
        ports["port"] = allocate_port()
        if server is not None:
            wanted = server.preferred_port
            if wanted and wanted not in RESERVED_PORTS and wanted != ports["port"] and port_is_free(wanted):
                ports["server_port"] = wanted
                preview.add_log(f"[agentdev] Proxy của client trỏ tới cổng {wanted}: chạy server trên cổng đó.")
            else:
                ports["server_port"] = allocate_port({ports["port"]})
                if wanted:
                    preview.add_log(
                        f"[agentdev] Proxy của client trỏ tới cổng {wanted} nhưng cổng đó bận hoặc bị cấm; server chạy "
                        f"trên cổng {ports['server_port']}, nên lời gọi API qua proxy có thể không tới được server.")
        preview.port = ports["port"]
        for template in plan.processes:
            port_for = ports["server_port"] if template.role == "server" else ports["port"]
            local = dict(ports, port=port_for)
            cmd = [_fill(c, local) for c in template.cmd]
            env = preview_env({k: _fill(v, local) for k, v in template.env.items()})
            self._spawn(preview, template.name, cmd, template.cwd, env)
            if preview.stop_event.is_set():
                return
        deadline = time.monotonic() + READY_TIMEOUT
        while not port_accepts(ports["port"]):
            if preview.stop_event.wait(0.5):
                return
            dead = self._dead_process(preview)
            if dead:
                raise PreviewError(dead)
            if time.monotonic() > deadline:
                raise PreviewError(f"Ứng dụng không mở cổng {ports['port']} sau {int(READY_TIMEOUT)} giây.")
        if server is not None and not port_accepts(ports["server_port"]):
            preview.add_log(f"[agentdev] Server chưa nghe ở cổng {ports['server_port']} (có thể nó dùng cổng cố định).")
        preview.url = f"http://localhost:{ports['port']}/"
        preview.frameable = frame_allowed(preview.url)
        if preview.frameable is False:
            preview.add_log("[agentdev] App chặn hiển thị trong khung của trang khác (X-Frame-Options / frame-ancestors, "
                            "đúng chuẩn bảo mật): mở nó trong tab mới.")
        preview.status = "running"
        preview.add_log(f"[agentdev] Sẵn sàng: {preview.url}")
        while not preview.stop_event.wait(1.0):
            dead = self._dead_process(preview)
            if dead:
                raise PreviewError(dead)

    @staticmethod
    def _dead_process(preview: Preview) -> Optional[str]:
        with preview.lock:
            procs = list(preview.procs)
        for label, proc in procs:
            code = proc.poll()
            if code is not None:
                return f"Tiến trình {label} đã thoát (mã {code})."
        return None

    def _ensure_reaper(self) -> None:
        if self._reaper is None or not self._reaper.is_alive():
            self._reaper = threading.Thread(target=self._reap_loop, name="preview-reaper", daemon=True)
            self._reaper.start()

    def _reap_loop(self) -> None:
        while not self._closed:
            time.sleep(30)
            self.reap_idle()

    def reap_idle(self, now: Optional[float] = None) -> int:
        now = time.monotonic() if now is None else now
        with self._lock:
            idle = [p for p in self._previews.values()
                    if p.kind != "static" and p.status in ACTIVE_STATUSES and now - p.last_access > IDLE_SECONDS]
        for preview in idle:
            self._stop_preview(preview, "Đã dừng vì không dùng trong 30 phút.")
        return len(idle)


# ---------------------------------------------------------------------------
# Lab glue
# ---------------------------------------------------------------------------

def frame_allowed(url: str, timeout: float = 3.0) -> Optional[bool]:
    """Whether the browser will show ``url`` inside the Lab's frame (a page on another origin).

    Many well-built apps send ``X-Frame-Options`` or a CSP ``frame-ancestors`` (helmet does by default); those
    are kept, not stripped, and the UI offers a new tab instead. None when the headers could not be read."""
    import urllib.request

    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=timeout) as resp:  # noqa: S310 - our own localhost preview
            headers = resp.headers
    except Exception:  # noqa: BLE001 - unknown: let the frame try
        return None
    if (headers.get("X-Frame-Options") or "").strip():
        return False  # DENY or SAMEORIGIN: the Lab page is never the app's origin
    for policy in headers.get_all("Content-Security-Policy") or []:
        for directive in policy.split(";"):
            parts = directive.strip().split()
            if parts and parts[0].lower() == "frame-ancestors" and "*" not in parts[1:]:
                return False
    return True


def _seed_env_file(preview: "Preview", directory: Path) -> None:
    """Apps commonly read ``.env`` (``node --env-file=.env``, dotenv) and ship only ``.env.example``: without
    the copy they exit at once. The example holds placeholders, never secrets, so copying it is safe."""
    example, target = directory / ".env.example", directory / ".env"
    try:
        if example.is_file() and not target.exists():
            shutil.copyfile(example, target)
            preview.add_log(f"[agentdev] Chưa có .env: đã tạo từ .env.example trong {directory.name}/ để app khởi động "
                            "(giá trị mẫu; tính năng cần khoá thật như gửi mail có thể không chạy).")
    except OSError as exc:
        preview.add_log(f"[agentdev] Không tạo được .env từ .env.example: {exc}")


def _allowed_root() -> Path:
    from agentdev.paths import WAREHOUSE_DIR

    return Path(WAREHOUSE_DIR).resolve()


def _check_root(root: Path) -> None:
    if not root.is_dir():
        raise PreviewError("Không tìm thấy thư mục kết quả của lượt chạy này.", 404)
    if not root.is_relative_to(_allowed_root()):
        raise PreviewError("Thư mục kết quả nằm ngoài kho lưu trữ, không chạy thử.", 403)


def _site_base(job_id: str, run_index: int) -> str:
    return f"/api/lab/jobs/{job_id}/runs/{run_index}/site/"


def _product_dir_for(job_id: str, run_index: int) -> Path:
    from agentdev.api.services import lab_outputs  # written alongside; imported lazily

    try:
        run_dir = lab_outputs.resolve_run_dir(job_id, run_index)
    except lab_outputs.LabOutputsError as exc:
        raise PreviewError(exc.detail, exc.status_code) from exc
    if not run_dir:
        raise PreviewError("Không tìm thấy kết quả của lượt chạy này.", 404)
    product = lab_outputs.product_dir(Path(run_dir))
    if not product:
        raise PreviewError("Lượt chạy này không có sản phẩm.", 404)
    return Path(product).resolve()


_manager: Optional[PreviewManager] = None
_manager_lock = threading.Lock()


def get_preview_manager() -> PreviewManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = PreviewManager()
            atexit.register(_manager.stop_all)
        return _manager


def shutdown_previews() -> None:
    """Kill every preview process tree (called from the app lifespan on shutdown)."""
    if _manager is not None:
        _manager.stop_all()
