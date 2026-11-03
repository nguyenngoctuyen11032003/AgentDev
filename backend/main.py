import argparse
import sys
import signal
import os
import logging

from agentdev.paths import (
    EXAMPLES_DIR,
    FUNCTIONS_DIR,
    LOGS_DIR,
    PACKAGE_DIR,
    SCRIPTS_DIR,
)
from agentdev.runtime.bootstrap.schema import ensure_schema_registry_populated
from agentdev.api.app import app


ensure_schema_registry_populated()


# Directories containing the server's Python sources. When --reload is
# enabled, only these are watched so that agent-generated files under
# storage/ (warehouse, logs, ...) never trigger a StatReload restart mid-workflow
# (issue #569).
# Absolute paths so reload works regardless of the launch directory.
RELOAD_SOURCE_DIRS = [
    str(PACKAGE_DIR),
    str(SCRIPTS_DIR),
    str(FUNCTIONS_DIR),
    str(EXAMPLES_DIR),
]

# Directory names whose contents must never trigger a reload. These are
# expanded into multi-depth glob patterns below so nested files (e.g.
# ``storage/warehouse/demo/foo.py``) are also excluded: uvicorn applies these via
# ``Path.match``, which on Python < 3.13 does not understand ``**`` and
# matches a pattern of N components only against the last N path parts.
# "WareHouse"/"data" are the legacy (pre-storage/) output dir names.
_RELOAD_EXCLUDE_DIRS = ("storage", "warehouse", "WareHouse", "logs", "data", "temp", "node_modules")
_RELOAD_EXCLUDE_MAX_DEPTH = 10

# Glob patterns excluded from reload watching. Only honoured when
# ``watchfiles`` is installed; StatReload (the pure-Python fallback that
# ships with uvicorn core) ignores exclude patterns entirely, so the
# primary defence is the reload_dirs restriction to RELOAD_SOURCE_DIRS.
RELOAD_EXCLUDES = [
    f"{d}{'/*' * (depth + 1)}"
    for d in _RELOAD_EXCLUDE_DIRS
    for depth in range(_RELOAD_EXCLUDE_MAX_DEPTH)
]


def _watchfiles_available() -> bool:
    """Return ``True`` when the ``watchfiles`` package is importable.

    Split out so tests can patch it without touching ``sys.modules``.
    """
    import importlib.util

    return importlib.util.find_spec("watchfiles") is not None


def patch_windows_reload(join_timeout: float = 10.0) -> None:
    """Make ``--reload`` restarts finish on Windows.

    uvicorn restarts a worker on Windows by sending CTRL_C_EVENT and then joining it with no timeout.
    When the server runs without its own console (started from an IDE task, a background shell or a
    service) the event never arrives, the join waits forever and the old worker keeps serving stale
    code. After ``join_timeout`` seconds the old worker is terminated instead.
    """
    if sys.platform != "win32":
        return
    from uvicorn.supervisors import basereload

    if getattr(basereload.BaseReload.restart, "_agentdev_patched", False):
        return

    def restart(self) -> None:
        self.is_restarting = True
        try:
            os.kill(self.process.pid, signal.CTRL_C_EVENT)
            sys.stdout.write(" ")
            sys.stdout.flush()
        except OSError:
            pass
        self.process.join(join_timeout)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(join_timeout)
        self.process = basereload.get_subprocess(config=self.config, target=self.target, sockets=self.sockets)
        self.process.start()

    restart._agentdev_patched = True
    basereload.BaseReload.restart = restart


def build_reload_kwargs(args: argparse.Namespace) -> dict:
    """Build the reload-related kwargs passed to ``uvicorn.run``.

    Extracted so the configuration is unit-testable without spinning up
    a real server. When ``--reload`` is off the return value is empty.
    """
    if not args.reload:
        return {}
    return {
        "reload_dirs": list(args.reload_dir) if args.reload_dir else list(RELOAD_SOURCE_DIRS),
        "reload_excludes": list(args.reload_exclude) if args.reload_exclude else list(RELOAD_EXCLUDES),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentDev Workflow Server")
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Server host (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port (default: 8000)"
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="Log level (default: info)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )
    parser.add_argument(
        "--reload-dir",
        action="append",
        default=None,
        metavar="DIR",
        help=(
            "Directory to watch when --reload is active (repeatable). "
            "Defaults to the server's Python source folders, which excludes "
            "storage/ and other output dirs."
        ),
    )
    parser.add_argument(
        "--reload-exclude",
        action="append",
        default=None,
        metavar="GLOB",
        help=(
            "Glob pattern excluded from reload watching (repeatable). "
            "Requires watchfiles to take effect."
        ),
    )
    return parser


def main():
    import uvicorn

    args = build_parser().parse_args()

    # Configure structured logging
    import os
    os.environ['LOG_LEVEL'] = args.log_level.upper()

    # Ensure log directory exists
    log_dir = LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "server.log"),
            logging.StreamHandler()
        ]
    )

    logger = logging.getLogger(__name__)
    logger.info(f"Starting AgentDev Workflow Server on {args.host}:{args.port}")

    if args.reload and not _watchfiles_available():
        logger.warning(
            "--reload is active but 'watchfiles' is not installed; uvicorn will "
            "fall back to StatReload, which ignores --reload-exclude patterns "
            "(including the storage/ defaults). Install watchfiles (or "
            "`pip install uvicorn[standard]`) to enable exclude filtering."
        )

    if args.reload:
        patch_windows_reload()

    # Launch the server
    uvicorn.run(
        "agentdev.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
        ws="wsproto",
        # Open WebSockets (the Run page) never close on their own; without a limit a reload or
        # Ctrl+C waits for them forever, so the old worker keeps serving stale code. Clients
        # reconnect automatically after the restart.
        timeout_graceful_shutdown=5,
        **build_reload_kwargs(args),
    )


if __name__ == "__main__":
    main()
