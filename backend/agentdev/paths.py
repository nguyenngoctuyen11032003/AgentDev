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
            warehouse/       WAREHOUSE_DIR (per-session workflow output)
            db/              DATA_DIR (vuegraphs.db)
            logs/            LOGS_DIR
            temp/            TEMP_DIR

Set ``AGENTDEV_HOME`` to point ``PROJECT_ROOT`` at another checkout, or
``AGENTDEV_STORAGE_DIR`` to keep runtime data somewhere else (e.g. a volume).

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
WORKFLOWS_DIR = WORKSPACE_DIR / "workflows"
FUNCTIONS_DIR = WORKSPACE_DIR / "functions"
SKILLS_DIR = WORKSPACE_DIR / "skills"
TEMPLATES_DIR = WORKSPACE_DIR / "templates"
EXAMPLES_DIR = WORKSPACE_DIR / "examples"

# Runtime / generated data, grouped under one gitignored ``storage/`` dir.
_storage_override = os.environ.get("AGENTDEV_STORAGE_DIR")
STORAGE_DIR = (
    Path(_storage_override).expanduser().resolve()
    if _storage_override
    else PROJECT_ROOT / "storage"
)
WAREHOUSE_DIR = STORAGE_DIR / "warehouse"
DATA_DIR = STORAGE_DIR / "db"
LOGS_DIR = STORAGE_DIR / "logs"
TEMP_DIR = STORAGE_DIR / "temp"
VUEGRAPHS_DB_PATH = DATA_DIR / "vuegraphs.db"
ENV_FILE = PROJECT_ROOT / ".env"

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
