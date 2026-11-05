"""Agent Skills discovery and loading helpers."""

import logging
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Sequence

import yaml

from agentdev.entity.tool_spec import ToolSpec
from agentdev.paths import SKILLS_ROOT


DEFAULT_SKILLS_ROOT = SKILLS_ROOT
MAX_SKILL_FILE_BYTES = 128 * 1024
MAX_LISTED_SKILL_FILES = 60
# A skill whose SKILL.md is longer than this many characters gets a size hint in the on-demand catalog:
# once loaded it stays in the context of every later model call (~4 chars per token).
LARGE_SKILL_CHARS = 30_000
# Ticked skills whose instructions fit in this many characters (frontmatter stripped, in tick order)
# go straight into the agent's system prompt: the agent follows them without first spending a model
# call on activate_skill, and the system prompt is the static, prompt-cached part of every call.
# Skills past the budget stay in the catalog and are loaded on demand. ~32k chars is ~8k tokens:
# two typical skills of the library.
MAX_PRELOADED_SKILL_CHARS = 16_000
_LISTED_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".py", ".js", ".ts", ".sh", ".html", ".css"}
_TOOL_ENTRY = re.compile(r"[^\s,()]+(?:\([^)]*\))?")


class SkillValidationError(ValueError):
    """Raised when a skill directory or SKILL.md file is invalid."""


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str
    skill_dir: Path
    skill_file: Path
    frontmatter: Mapping[str, object]
    allowed_tools: tuple[str, ...]
    compatibility: Mapping[str, object]


def parse_skill_file(skill_file: str | Path) -> SkillMetadata:
    path = Path(skill_file).resolve()
    text = path.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(text, path)

    raw_name = frontmatter.get("name")
    raw_description = frontmatter.get("description")
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise SkillValidationError(f"{path}: skill frontmatter must define a non-empty name")
    if not isinstance(raw_description, str) or not raw_description.strip():
        raise SkillValidationError(f"{path}: skill frontmatter must define a non-empty description")

    name = raw_name.strip()
    description = raw_description.strip()
    if path.parent.name != name:
        raise SkillValidationError(
            f"{path}: skill name '{name}' must match directory name '{path.parent.name}'"
        )

    allowed_tools = _parse_optional_str_list(frontmatter.get("allowed-tools"), path, "allowed-tools")
    compatibility = _parse_optional_mapping(frontmatter.get("compatibility"), path, "compatibility")

    return SkillMetadata(
        name=name,
        description=description,
        skill_dir=path.parent,
        skill_file=path,
        frontmatter=dict(frontmatter),
        allowed_tools=tuple(allowed_tools),
        compatibility=dict(compatibility),
    )


def _parse_frontmatter(text: str, path: Path) -> Mapping[str, object]:
    if not text.startswith("---"):
        raise SkillValidationError(f"{path}: SKILL.md must start with YAML frontmatter")

    lines = text.splitlines()
    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        raise SkillValidationError(f"{path}: closing frontmatter delimiter not found")

    payload = "\n".join(lines[1:end_idx])
    try:
        data = yaml.safe_load(payload) or {}
    except yaml.YAMLError as exc:
        raise SkillValidationError(f"{path}: invalid YAML frontmatter: {exc}") from exc
    if not isinstance(data, Mapping):
        raise SkillValidationError(f"{path}: skill frontmatter must be a mapping")
    return data


def _strip_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                return "\n".join(lines[idx + 1:]).strip()
    return text.strip()


def _parse_optional_str_list(value: object, path: Path, field_name: str) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        # "Read, Bash(npx impeccable *)" / "Read Grep": keep "Tool(pattern with spaces)" in one piece.
        return _TOOL_ENTRY.findall(value)
    if not isinstance(value, list):
        raise SkillValidationError(f"{path}: {field_name} must be a list of strings")

    result: List[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise SkillValidationError(f"{path}: {field_name}[{idx}] must be a non-empty string")
        result.append(item.strip())
    return result


def _parse_optional_mapping(value: object, path: Path, field_name: str) -> Mapping[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise SkillValidationError(f"{path}: {field_name} must be a mapping")
    return {str(key): value[key] for key in value}


MAX_PROMPT_DESCRIPTION_CHARS = 200
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def summarise_description(description: str, limit: int = MAX_PROMPT_DESCRIPTION_CHARS) -> str:
    """Short form of a skill description for the prompt: what it does + when to use it.

    Keeps the first sentence and the first "Use when…" sentence, then cuts at a word boundary.
    """
    text = " ".join((description or "").split())
    if len(text) <= limit:
        return text
    sentences = [s for s in _SENTENCE_END.split(text) if s]
    picked = sentences[:1]
    when = next((s for s in sentences[1:] if s.lower().startswith(("use when", "use this", "use for", "use before"))), None)
    if when:
        picked.append(when)
    short = " ".join(picked)
    if len(short) > limit:
        head = short[:limit]
        # Prefer ending at a clause boundary ("..., when ...") inside the "Use when" part.
        cut = max(head.rfind(", "), head.rfind("; "))
        if cut <= len(picked[0]) + 20:
            cut = head.rfind(" ")
        short = head[:cut].rstrip(",;: ") + "."
    return short


class AgentSkillManager:
    """Discover and read Agent Skills from the fixed project-level skills directory."""

    def __init__(
        self,
        allow: Sequence[str] | None = None,
        available_tool_names: Sequence[str] | None = None,
        warning_reporter: Callable[[str], None] | None = None,
    ) -> None:
        self.root = DEFAULT_SKILLS_ROOT
        # Tick order is kept: it decides which skills are preloaded when they do not all fit.
        self.allow_order = list(dict.fromkeys(item.strip() for item in (allow or []) if item and item.strip()))
        self.allow = set(self.allow_order)
        self.available_tool_names = {item.strip() for item in (available_tool_names or []) if item and item.strip()}
        self.warning_reporter = warning_reporter
        self._skills_by_name: Dict[str, SkillMetadata] | None = None
        self._skill_content_cache: Dict[str, str] = {}
        self._activation_state: Dict[str, bool] = {}
        self._current_skill_name: str | None = None
        self._discovery_warnings: List[str] = []
        self._preloaded: List[str] = []

    def discover(self) -> List[SkillMetadata]:
        if self._skills_by_name is None:
            discovered: Dict[str, SkillMetadata] = {}
            root = self.root
            if root.exists() and root.is_dir():
                for metadata in self._iter_root_skills(root):
                    if self.allow and metadata.name not in self.allow:
                        continue
                    if not self._is_skill_compatible(metadata):
                        continue
                    discovered.setdefault(metadata.name, metadata)
            self._skills_by_name = discovered
        return list(self._skills_by_name.values())

    def has_skills(self) -> bool:
        return bool(self.discover())

    def skill_body(self, skill_name: str) -> str:
        """SKILL.md without its frontmatter (name and description are already in the catalog)."""
        skill = self._get_skill(skill_name)
        cached = self._skill_content_cache.get(skill.name)
        if cached is None:
            cached = skill.skill_file.read_text(encoding="utf-8")
            self._skill_content_cache[skill.name] = cached
        return _strip_frontmatter(cached)

    def preload(self, budget: int | None = None) -> List[SkillMetadata]:
        """Pick the ticked skills whose instructions go into the system prompt (see MAX_PRELOADED_SKILL_CHARS).

        Only skills the user ticked explicitly: with an empty allowlist the agent sees the whole library,
        and preloading arbitrary skills would only cost tokens. Greedy in tick order; a skill that does not
        fit is skipped (it stays loadable on demand) and smaller ones after it may still fit.
        """
        if budget is None:
            budget = MAX_PRELOADED_SKILL_CHARS
        if not self.allow_order:
            self._preloaded = []
            return []
        by_name = {skill.name: skill for skill in self.discover()}
        picked: List[SkillMetadata] = []
        used = 0
        for name in self.allow_order:
            skill = by_name.get(name)
            if skill is None:
                continue
            try:
                size = len(self.skill_body(name))
            except OSError:
                continue
            if used + size > budget:
                logging.getLogger(__name__).info(
                    "Skill '%s' (%d chars) not preloaded: budget of %d chars used; it stays loadable on demand",
                    name, size, budget,
                )
                continue
            used += size
            picked.append(skill)
        self._preloaded = [skill.name for skill in picked]
        return picked

    def is_preloaded(self, skill_name: str) -> bool:
        return skill_name in self._preloaded

    def needs_skill_tool_specs(self) -> bool:
        """False when every skill is preloaded and none has extra files: activate_skill and
        read_skill_file would never be useful, so they are not sent with each model call."""
        skills = self.discover()
        if not skills or not self._preloaded:
            return True
        return any(not self.is_preloaded(s.name) or self.skill_files(s.name) for s in skills)

    def build_preloaded_skills_section(self, *, with_paths: bool = False) -> str:
        """Full instructions of the preloaded skills, for the system prompt. ``with_paths``: native agents
        read a skill's other files themselves, so they get its folder instead of the read_skill_file hint."""
        blocks: List[str] = []
        for name in self._preloaded:
            skill = self._get_skill(name)
            head = f"## Skill: {skill.name}\n{summarise_description(skill.description)}"
            files = self.skill_files(skill.name)
            if files and with_paths:
                head += f"\n(Skill folder, for the files it references: {skill.skill_dir.as_posix()})"
            elif files:
                head += (
                    "\n(Files in this skill, read the ones it points to with `read_skill_file`: "
                    + ", ".join(files) + ")"
                )
            blocks.append(f"{head}\n\n{self.skill_body(skill.name)}\n[End skill: {skill.name}]")
        return "\n\n".join(blocks)

    def build_available_skills_xml(self) -> str:
        """Catalog of the skills to load on demand (preloaded skills are already in the prompt)."""
        skills = [skill for skill in self.discover() if not self.is_preloaded(skill.name)]
        if not skills:
            return ""

        # Sent with every model call of the agent, so keep it short: the name (what activate_skill
        # takes) and a trimmed description. No file paths: skills are loaded by name.
        lines = ["<available_skills>"]
        for skill in skills:
            lines.extend(
                [
                    "  <skill>",
                    f"    <name>{escape(skill.name)}</name>",
                    f"    <description>{escape(summarise_description(skill.description))}</description>",
                ]
            )
            size = self._skill_size(skill)
            if size > LARGE_SKILL_CHARS:
                lines.append(
                    f"    <size>very large (~{size // 4000}k tokens): load it only when the task really needs it</size>"
                )
            if skill.allowed_tools:
                lines.append("    <allowed_tools>")
                for tool_name in skill.allowed_tools:
                    lines.append(f"      <tool>{escape(tool_name)}</tool>")
                lines.append("    </allowed_tools>")
            lines.append("  </skill>")
        lines.append("</available_skills>")
        return "\n".join(lines)

    @staticmethod
    def _skill_size(skill: SkillMetadata) -> int:
        try:
            return skill.skill_file.stat().st_size
        except OSError:
            return 0

    def activate_skill(self, skill_name: str) -> Dict[str, str | List[str]]:
        skill = self._get_skill(skill_name)
        body = self.skill_body(skill.name)  # without the frontmatter: name and description are known already
        self._activation_state[skill.name] = True
        self._current_skill_name = skill.name
        # No absolute server path: the model loads skills by name and reads files via read_skill_file.
        return {
            "skill_name": skill.name,
            "instructions": body,
            "allowed_tools": list(self.enforced_tools(skill)),
            "files": self.skill_files(skill.name),
        }

    def skill_files(self, skill_name: str, limit: int = MAX_LISTED_SKILL_FILES) -> List[str]:
        """Relative paths of the skill's other text files (references, examples), for read_skill_file."""
        skill = self._get_skill(skill_name)
        found: List[str] = []
        for path in sorted(skill.skill_dir.rglob("*")):
            if len(found) >= limit:
                found.append("…")
                break
            rel = path.relative_to(skill.skill_dir)
            if (
                not path.is_file()
                or rel.as_posix() == "SKILL.md"
                or any(part.startswith(".") or part == "__pycache__" for part in rel.parts)
                or path.suffix.lower() not in _LISTED_SUFFIXES
            ):
                continue
            found.append(rel.as_posix())
        return found

    def allowed_tools_for_active(self) -> tuple[str, ...]:
        """Tools the activated skills restrict the agent to, or () for no restriction.

        Several skills can be active at once (e.g. a frontend skill and a testing skill). A restriction
        only holds when every active skill declares one, and then their tools are combined: one skill's
        narrow list must not block the tools another active skill needs.
        """
        active = [skill for skill in self.discover() if self.is_activated(skill.name)]
        if not active:
            return ()
        lists = [self.enforced_tools(skill) for skill in active]
        if any(not tools for tools in lists):
            return ()
        combined: List[str] = []
        for tools in lists:
            combined.extend(name for name in tools if name not in combined)
        return tuple(combined)

    def enforced_tools(self, skill: SkillMetadata) -> tuple[str, ...]:
        """The skill's allowed-tools entries that name tools this agent has.

        Entries in Claude Code syntax (``Bash(npx x *)``) or naming tools AgentDev does not have are
        advisory: they never hide the skill and never restrict the agent's tools.
        """
        return tuple(name for name in skill.allowed_tools if name in self.available_tool_names)

    def build_skill_file_listing(self) -> str:
        """Name, short description and SKILL.md path of each skill, for agents that read files themselves."""
        lines = []
        for skill in self.discover():
            if self.is_preloaded(skill.name):
                continue
            path = skill.skill_file.as_posix()
            lines.append(f"- {skill.name}: {summarise_description(skill.description)} (file: {path})")
        return "\n".join(lines)

    def read_skill_file(self, skill_name: str, relative_path: str) -> Dict[str, str]:
        skill = self._get_skill(skill_name)
        if not self.is_activated(skill.name) and not self.is_preloaded(skill.name):
            raise ValueError(f"Skill '{skill.name}' must be activated before reading files")

        normalized = relative_path.strip()
        if not normalized:
            raise ValueError("relative_path is required")

        candidate = (skill.skill_dir / normalized).resolve()
        try:
            candidate.relative_to(skill.skill_dir)
        except ValueError as exc:
            raise ValueError("relative_path must stay within the skill directory") from exc

        if not candidate.exists() or not candidate.is_file():
            raise ValueError(f"Skill file '{normalized}' not found")
        if candidate.stat().st_size > MAX_SKILL_FILE_BYTES:
            raise ValueError(f"Skill file '{normalized}' exceeds the {MAX_SKILL_FILE_BYTES} byte limit")

        return {
            "skill_name": skill.name,
            "path": str(candidate),
            "relative_path": str(candidate.relative_to(skill.skill_dir)),
            "content": candidate.read_text(encoding="utf-8"),
        }

    def is_activated(self, skill_name: str) -> bool:
        return bool(self._activation_state.get(skill_name))

    def active_skill(self) -> SkillMetadata | None:
        if self._current_skill_name is None:
            return None
        skills = self._skills_by_name
        if skills is None:
            return None
        return skills.get(self._current_skill_name)

    def discovery_warnings(self) -> List[str]:
        self.discover()
        return list(self._discovery_warnings)

    def build_tool_specs(self) -> List[ToolSpec]:
        """``activate_skill`` and ``read_skill_file``; only ``read_skill_file`` when every skill is preloaded
        (nothing is left to activate, but a skill's other files can still be read)."""
        if not self.has_skills():
            return []
        specs = self._all_tool_specs()
        everything_preloaded = bool(self._preloaded) and all(self.is_preloaded(s.name) for s in self.discover())
        return [spec for spec in specs if spec.name != "activate_skill"] if everything_preloaded else specs

    def _all_tool_specs(self) -> List[ToolSpec]:
        return [
            ToolSpec(
                name="activate_skill",
                description="Load the full SKILL.md instructions for a discovered agent skill.",
                parameters={
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "Exact skill name from <available_skills>.",
                        }
                    },
                    "required": ["skill_name"],
                },
                metadata={"source": "agent_skill_internal"},
            ),
            ToolSpec(
                name="read_skill_file",
                description="Read a text file inside an activated skill directory, such as references or scripts.",
                parameters={
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "Exact activated skill name from <available_skills>.",
                        },
                        "relative_path": {
                            "type": "string",
                            "description": "Path relative to the skill directory, for example references/example.md.",
                        },
                    },
                    "required": ["skill_name", "relative_path"],
                },
                metadata={"source": "agent_skill_internal"},
            ),
        ]

    def _iter_root_skills(self, root: Path) -> Iterable[SkillMetadata]:
        for candidate in sorted(root.iterdir()):
            if not candidate.is_dir():
                continue
            skill_file = candidate / "SKILL.md"
            if not skill_file.is_file():
                continue
            try:
                yield parse_skill_file(skill_file)
            except SkillValidationError as exc:
                # Only a skill this agent ticked is worth a chat warning; a broken file elsewhere in the library
                # would otherwise warn on every agent node of every run.
                if candidate.name in self.allow:
                    self._warn(str(exc))
                else:
                    self._discovery_warnings.append(str(exc))
                continue

    def _get_skill(self, skill_name: str) -> SkillMetadata:
        for skill in self.discover():
            if skill.name == skill_name:
                return skill
        raise ValueError(f"Skill '{skill_name}' not found")

    def _is_skill_compatible(self, skill: SkillMetadata) -> bool:
        # allowed-tools is advisory (see enforced_tools): skills imported from Claude Code declare tools
        # such as "Bash(npx impeccable *)" or "Read" that AgentDev agents do not have, and the skill's
        # instructions are still useful. Dropping them silently hid skills the user had ticked.
        return True

    def _warn(self, message: str) -> None:
        self._discovery_warnings.append(message)
        if self.warning_reporter is not None:
            self.warning_reporter(message)
