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
    """``env`` (modified in place and returned) with the git ceiling set when ``cwd`` is under the warehouse."""
    try:
        from agentdev.paths import WAREHOUSE_DIR

        ceiling = Path(WAREHOUSE_DIR).resolve()
        if cwd and ceiling in Path(cwd).resolve().parents:
            existing = env.get("GIT_CEILING_DIRECTORIES")
            env["GIT_CEILING_DIRECTORIES"] = os.pathsep.join(filter(None, [str(ceiling), existing]))
    except (OSError, ValueError):
        pass
    return env
