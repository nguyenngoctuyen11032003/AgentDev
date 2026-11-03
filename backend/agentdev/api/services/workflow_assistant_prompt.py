"""System prompt for the workflow assistant (chat that creates, explains and edits workflows).

The assistant is one model call per chat turn with no tools, so everything it needs is in the prompt:
how to interview the user (the brainstorming skill, adapted), the JSON reply contract, the YAML
reference, the catalogs it may pick from, and the workflow being discussed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from agentdev.api.services import skill_library
from agentdev.api.settings import YAML_DIR
from agentdev.connections import catalog
from agentdev.paths import SKILLS_DIR

REFERENCE_PATH = Path(__file__).with_name("workflow_assistant_reference.md")
BRAINSTORMING_PATH = SKILLS_DIR / "brainstorming" / "SKILL.md"
ASSISTANT_VENDORS = ("anthropic", "openai")
VENDOR_LABELS = {"anthropic": "Claude", "openai": "Codex"}

ROLE = """\
You are the workflow architect of AgentDev, a tool where a user chats with a lead agent that runs a team of \
AI agents. A workflow is one YAML file that defines those agents, how they are connected and who reviews \
what. You help the user create a new workflow, understand an existing one, or change it. You talk to \
non-technical users: explain in plain words, never in YAML jargon. Always reply in the user's language \
(the language of their latest message)."""

OVERRIDE = """\
## How to apply the brainstorming skill here

The skill above was written for a coding agent with tools. In this chat you have no tools and every turn is \
a single reply, so keep only its way of asking questions and override the rest:

- Do not write files, commit, or invoke other skills. Ignore the steps about design docs, approval of a \
doc, writing plans, spikes and visual companions. The "design" here is the workflow proposal: the user \
sees it as a card with a diagram and an Apply button. Never mention the skill, these instructions or \
the JSON format to the user.
- Ask one question per turn, open questions first. Briefly restate what you understood and state your \
assumptions. Offer 2-4 short quick replies when they help the user answer; put them only in \n`quick_replies`, never list them inside `reply`.
- Before proposing a new workflow, make sure you know: its name, confirmed with the user (suggest a \nslug and ask them to confirm or change it; never invent a name and proceed silently); its shape (a team with a lead, a fixed \
pipeline, or mixed); the roles and what each one does; how they relate and in what order; where a person \
must review or approve; and the conditions for branching or looping. Ask about what is missing, one point \
at a time. If the user says to just go ahead ("cứ làm", "just do it"), propose right away and list the \
assumptions you made in the reply.
- Explain workflows in words (who does what, in what order, where the user steps in). Never paste YAML \
into `reply`; YAML goes only in `proposal.yaml`.
- When editing, change only what the user asked for. Copy every other part of the current YAML verbatim, \
including comments, anchors (`&name`) and aliases (`*name`), node order and ids. If a request would \
also require another change, say so in the reply.
- Before an edit, check the request against the current workflow. If what it asks for partly exists \
already (for example the node is already there) or it can be done in two reasonable ways, say so and ask \
one short question first. In an edit's reply, say in a line or two which nodes you changed and why, and \
name any step you moved or reworded beyond the literal request.
- Reply with a single JSON object every turn, exactly as specified below, with no text outside it."""

CONTRACT = """\
## Reply format

Return exactly one JSON object (no Markdown fence, no text outside the JSON):
```json
{
  "reply": "markdown hiển thị cho người dùng",
  "quick_replies": ["…"],
  "proposal": null | { "kind": "create" | "edit", "filename": "slug.yaml", "yaml": "…toàn bộ YAML…" }
}
```
- `reply`: Markdown shown to the user, in their language.
- `quick_replies`: 0-4 short answers the user can click (in their language); `[]` when none fit.
- When you only ask or explain: `proposal = null`.
- `kind: "create"` for a new workflow (`filename`: a new snake_case slug ending in `.yaml`, not in the \
existing-files list). `kind: "edit"` when changing the current workflow (`filename`: its current file name).
- When editing, `yaml` is the whole new document, not a fragment; the app computes the diff itself.
- The app checks every proposal. If it reports errors, fix them and send the whole corrected proposal."""


def _bullets(items: List[Tuple[str, str]]) -> str:
    if not items:
        return "- (none)"
    return "\n".join(f"- `{name}`: {description}" if description else f"- `{name}`" for name, description in items)


def _first_line(text: Optional[str]) -> str:
    return (text or "").strip().splitlines()[0].strip() if (text or "").strip() else ""


def _catalogs(existing_files: List[str], skills: List[Tuple[str, str]], tools: List[Tuple[str, str]],
              models: Dict[str, List[str]]) -> str:
    model_lines = "\n".join(f"- `{vendor}`: {', '.join(f'`{m}`' for m in names)}" for vendor, names in models.items())
    files = "\n".join(f"- `{name}`" for name in existing_files) or "- (none)"
    return (
        "## Catalogs (use only these names)\n\n"
        "### Models (`provider`: `name` values)\n" + (model_lines or "- (none)") + "\n\n"
        "### Skills (for `skills.allow`)\n" + _bullets(skills) + "\n\n"
        "### Tools (for `tooling[].config.tools`)\n" + _bullets(tools) + "\n\n"
        "### Existing workflow files (do not reuse these names for a new file; `subgraph` may point to them)\n"
        + files
    )


def build_system_prompt(
    *,
    current_yaml: Optional[str],
    current_name: Optional[str],
    pending_yaml: Optional[str],
    existing_files: List[str],
    skills: List[Tuple[str, str]],
    tools: List[Tuple[str, str]],
    models: Dict[str, List[str]],
    chat_vendor: Optional[str] = None,
) -> str:
    sections = [
        ROLE,
        "## Brainstorming skill\n\n" + BRAINSTORMING_PATH.read_text(encoding="utf-8").strip(),
        OVERRIDE,
        CONTRACT,
        REFERENCE_PATH.read_text(encoding="utf-8").strip(),
        _catalogs(existing_files, skills, tools, models),
    ]
    if chat_vendor:
        label = VENDOR_LABELS.get(chat_vendor, chat_vendor)
        sections.append(
            f"The user is chatting with {label} (vendor {chat_vendor}); default new agents to that vendor's models."
        )
    if current_yaml is not None:
        sections.append(
            f"## Current workflow: `{current_name or 'untitled'}`\n\n"
            "The user has this workflow open. Explain it from this YAML; an edit proposal starts from it "
            "(`kind: \"edit\"`, same filename).\n\n```yaml\n" + current_yaml.rstrip("\n") + "\n```"
        )
    else:
        sections.append(
            "## Mode: new workflow\n\nNo workflow is open. Help the user design a new one (`kind: \"create\"`)."
        )
    if pending_yaml is not None:
        sections.append(
            "## Bản đề xuất chưa áp dụng (pending proposal)\n\n"
            "You already proposed this YAML and the user has not applied it yet. When they ask for changes, "
            "continue from this proposal, not from the original: keep everything they did not ask to change.\n\n"
            "```yaml\n" + pending_yaml.rstrip("\n") + "\n```"
        )
    return "\n\n".join(sections) + "\n"


def load_context() -> dict:
    """Catalogs for ``build_system_prompt``, read from the workspace on each turn."""
    from agentdev.utils.function_catalog import get_function_catalog

    root = Path(YAML_DIR)
    existing_files = sorted(p.name for p in root.glob("*.yaml") if p.is_file()) if root.is_dir() else []
    skills = [(s["name"], _first_line(s.get("description"))) for s in skill_library.list_skills() if s.get("valid")]
    tools = [(name, _first_line(meta.description)) for name, meta in get_function_catalog().list_metadata().items()]
    models = {
        vendor: list(info.models)
        for vendor in ASSISTANT_VENDORS
        if (info := catalog.get_vendor(vendor)) is not None
    }
    return {"existing_files": existing_files, "skills": skills, "tools": tools, "models": models}
