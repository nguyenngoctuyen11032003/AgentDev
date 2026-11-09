"""Keep an agent's ``git`` inside its own run folder.

A run folder lives under the warehouse, which is inside the AgentDev repository, so an agent's ``git``
command (``checkout -b``, ``commit``, ``stash`` ...) would walk up and change AgentDev's own repo. Setting
``GIT_CEILING_DIRECTORIES`` to the warehouse stops that search there. A git repo the run itself holds (an
uploaded project, ``git init``) is still found because it sits below the warehouse.
"""

import os
from pathlib import Path
from typing import Dict, Optional


def with_git_ceiling(env: Dict[str, str], cwd: Optional[str]) -> Dict[str, str]:
    """``env`` (modified in place and returned) with the git ceiling set when ``cwd`` is under the warehouse or
    under the projects folder (``~/AgentDev``: a project there must not reach a repo of the user's home)."""
    try:
        from agentdev.utils.project_folders import projects_root
        from agentdev.paths import WAREHOUSE_DIR

        target = Path(cwd).resolve() if cwd else None
        for base in (WAREHOUSE_DIR, projects_root()):
            ceiling = Path(base).resolve()
            if target is not None and ceiling in target.parents:
                existing = env.get("GIT_CEILING_DIRECTORIES")
                env["GIT_CEILING_DIRECTORIES"] = os.pathsep.join(filter(None, [str(ceiling), existing]))
                break
    except (OSError, ValueError):
        pass
    return env
