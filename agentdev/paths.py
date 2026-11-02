"""Canonical repository locations shared by the backend.

Import these instead of counting ``Path(__file__).parents[N]`` so that moving a
module never silently changes which directory it resolves to.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Workflow definitions (YAML) served by the API and runnable via run.py / SDK.
WORKFLOWS_DIR_NAME = "workflows"
# User-extensible Python functions (tools, edge conditions, edge processors).
FUNCTIONS_DIR_NAME = "functions"
# Default Agent Skills discovered for agent nodes.
SKILLS_ROOT = (REPO_ROOT / ".agents" / "skills").resolve()
