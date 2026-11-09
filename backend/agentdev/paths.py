"""Canonical repository locations shared by the backend.

Single source of truth for every on-disk location the backend uses. All paths
are absolute and independent of the current working directory, so the server,
CLI, scripts and tests behave the same no matter where they are launched from.

Repository layout::

    <PROJECT_ROOT>/
        .env                 ENV_FILE
        backend/             BACKEND_ROOT (agentdev package, scripts, tests)
        workspace/           WORKSPACE_DIR (user-editable content)
            workflows/       WORKFLOWS_DIR
            functions/       FUNCTIONS_DIR (importable as ``functions.*``)
            skills/          SKILLS_DIR
            templates/       TEMPLATES_DIR
            examples/        EXAMPLES_DIR
        storage/             STORAGE_DIR (everything generated at runtime, gitignored)
            warehouse/       WAREHOUSE_DIR (per-session workflow output of runs that predate PROJECTS_DIR)
            db/              DATA_DIR (vuegraphs.db)
            memory/          MEMORY_DIR (relative memory_path / index_path in workflows)
            logs/            LOGS_DIR
            temp/            TEMP_DIR

Set ``AGENTDEV_HOME`` to point ``PROJECT_ROOT`` at another checkout, or
``AGENTDEV_STORAGE_DIR`` to keep runtime data somewhere else (e.g. a volume).
``AGENTDEV_STORAGE_DIR`` may also be set in ``.env``; ``AGENTDEV_HOME`` must be a
real environment variable because it decides where ``.env`` lives.

Import these instead of counting ``Path(__file__).parents[N]`` so that moving a
module never silently changes which directory it resolves to.
"""

import os
import sys
from pathlib import Path

# backend/agentdev/paths.py -> parents[0]=agentdev, [1]=backend, [2]=repo root
BACKEND_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_PROJECT_ROOT = BACKEND_ROOT.parent

_home_override = os.environ.get("AGENTDEV_HOME")
PROJECT_ROOT = (
    Path(_home_override).expanduser().resolve() if _home_override else _DEFAULT_PROJECT_ROOT
)

# Backend source locations (always relative to this file, not AGENTDEV_HOME).
PACKAGE_DIR = BACKEND_ROOT / "agentdev"
SCRIPTS_DIR = BACKEND_ROOT / "scripts"

# User workspace.
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
# ``AGENTDEV_WORKFLOWS_DIR`` points the workflow folder elsewhere (the test suite uses a private copy).
_workflows_override = os.environ.get("AGENTDEV_WORKFLOWS_DIR")
WORKFLOWS_DIR = (
    Path(_workflows_override).expanduser().resolve() if _workflows_override else WORKSPACE_DIR / "workflows"
)
FUNCTIONS_DIR = WORKSPACE_DIR / "functions"
SKILLS_DIR = WORKSPACE_DIR / "skills"
TEMPLATES_DIR = WORKSPACE_DIR / "templates"
EXAMPLES_DIR = WORKSPACE_DIR / "examples"

ENV_FILE = PROJECT_ROOT / ".env"


def _read_dotenv_value(key: str) -> str | None:
    """Read one key from ``ENV_FILE`` without mutating ``os.environ``.

    ``paths`` is imported before ``env_loader.load_dotenv_file()`` runs, so a
    value placed only in ``.env`` would otherwise be ignored here. Real
    environment variables still take precedence (same rule as the loader).
    """
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'") or None
    return None


# Runtime / generated data, grouped under one gitignored ``storage/`` dir.
# AGENTDEV_STORAGE_DIR may come from the real environment or from ``.env``;
# a relative value is resolved against PROJECT_ROOT, never the CWD.
_storage_override = os.environ.get("AGENTDEV_STORAGE_DIR") or _read_dotenv_value("AGENTDEV_STORAGE_DIR")
if _storage_override:
    _storage_path = Path(_storage_override).expanduser()
    STORAGE_DIR = (_storage_path if _storage_path.is_absolute() else PROJECT_ROOT / _storage_path).resolve()
else:
    STORAGE_DIR = PROJECT_ROOT / "storage"
WAREHOUSE_DIR = STORAGE_DIR / "warehouse"
# Where the work of a session that opened no project folder is saved, like IntelliJ's ~/IdeaProjects:
# ``<PROJECTS_DIR>/<project-name>/`` (Lab runs: ``<PROJECTS_DIR>/AgentDev_lab/<run-name>/``). Read it at call
# time through ``agentdev.utils.project_folders`` so tests can redirect it.
_projects_override = os.environ.get("AGENTDEV_PROJECTS_DIR") or _read_dotenv_value("AGENTDEV_PROJECTS_DIR")
PROJECTS_DIR = (
    Path(_projects_override).expanduser().resolve() if _projects_override else Path.home() / "AgentDev"
)
DATA_DIR = STORAGE_DIR / "db"
MEMORY_DIR = STORAGE_DIR / "memory"
LOGS_DIR = STORAGE_DIR / "logs"
TEMP_DIR = STORAGE_DIR / "temp"
VUEGRAPHS_DB_PATH = DATA_DIR / "vuegraphs.db"

# Backward-compatible aliases.
REPO_ROOT = PROJECT_ROOT
SKILLS_ROOT = SKILLS_DIR
# Directory *names* kept for callers that only need a label; prefer the
# absolute ``WORKFLOWS_DIR`` / ``FUNCTIONS_DIR`` constants for filesystem access.
WORKFLOWS_DIR_NAME = WORKFLOWS_DIR.name
FUNCTIONS_DIR_NAME = FUNCTIONS_DIR.name


def ensure_workspace_on_sys_path() -> None:
    """Make ``workspace/`` importable so ``import functions.*`` works (idempotent)."""
    workspace = str(WORKSPACE_DIR)
    if workspace not in sys.path:
        sys.path.append(workspace)


ensure_workspace_on_sys_path()
