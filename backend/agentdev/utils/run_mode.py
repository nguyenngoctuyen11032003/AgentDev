"""How much a chat turn asks the user before acting: picked per turn in the chat's mode menu.

- ``manual``: the workflow as designed (plan approval as configured, every question waits for the user).
- ``plan``: a team lead always presents its plan and waits for approval before assigning work.
- ``auto``: no plan approval; a lead's questions get an automatic "go with your recommendation", but
  approval steps (Human nodes) still wait for the user.
- ``bypass``: every question and approval step is answered automatically.

Money safety does not depend on the mode: the automatic answer starts with ``[Automatic answer``, which
approval gates in front of paid or irreversible steps route to their skip branch (the workflow lint
requires it), and paid tools such as the Veo render still need an explicit ``confirmed=true``.
"""

from typing import Any, Mapping, Optional

RUN_MODES = ("manual", "plan", "auto", "bypass")
DEFAULT_RUN_MODE = "manual"
# Key in the runtime ``global_state`` holding this turn's mode
RUN_MODE_KEY = "run_mode"

# Same opening as the Lab's automatic answer, so approval gates treat both alike
RUN_MODE_AUTO_ANSWER = (
    "[Automatic answer: the user chose to let the team decide in this turn] Approved. Proceed with your "
    "recommended option, state the assumption you made, and finish the task. This does not approve anything "
    "that costs money or cannot be undone (paid renders, purchases, deleting or publishing): do not start "
    "those; list them for the user to confirm in their next message."
)


def normalize_run_mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in RUN_MODES else DEFAULT_RUN_MODE


def plan_approval_for(mode: Any, configured: bool) -> bool:
    """Whether a team lead submits its plan for approval in this turn."""
    mode = normalize_run_mode(mode)
    if mode == "plan":
        return True
    if mode in ("auto", "bypass"):
        return False
    return bool(configured)


def answers_automatically(mode: Any, metadata: Optional[Mapping[str, Any]] = None) -> bool:
    """Whether a question to the user is answered without waiting, in this mode."""
    mode = normalize_run_mode(mode)
    if mode == "bypass":
        return True
    if mode == "auto":
        # A Human node is a deliberate approval step in the workflow: it keeps waiting in auto mode
        return (metadata or {}).get("node_type") != "human"
    return False
