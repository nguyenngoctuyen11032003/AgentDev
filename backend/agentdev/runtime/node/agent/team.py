"""Team lead orchestration: a lead agent (CTO / PM / CEO) delegates work to member agents.

The user only talks to the lead. The lead decides at run time who to call, how often and in
what order through the ``delegate_task`` tool (one member) or ``delegate_parallel`` (several
independent tasks at once), asks the user through ``ask_user`` when a decision is theirs, and
finally answers the user itself. Members are ordinary agent nodes of
the same workflow; they run through the graph's delegate runner so every view (office, tasks,
overview) still sees their NODE_START / NODE_END events, tagged with ``delegated_by``.
"""

from __future__ import annotations

import contextvars
import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Set, Tuple

from agentdev.entity.messages import Message, MessageRole
from agentdev.entity.tool_spec import ToolSpec
from agentdev.utils.exceptions import WorkflowCancelledError

TEAM_TOOL_SOURCE = "agent_team_internal"
DELEGATE_TOOL = "delegate_task"
DELEGATE_PARALLEL_TOOL = "delegate_parallel"
ASK_USER_TOOL = "ask_user"
MAX_MEMBER_RESULT_CHARS = 16_000
MAX_HISTORY_CHARS = 3_000
MAX_DELEGATION_DEPTH = 3

# Workers start their answer with this when only the user can decide something.
DECISION_MARKER = "DECISION NEEDED:"

DelegateRunner = Callable[[str, List[Message], str], List[Message]]

# Nesting depth of the current delegation chain (lead -> member that is itself a lead -> ...).
# A context variable rather than a shared counter: parallel members each run in a worker thread
# with a copy of the caller's context, so siblings never add to each other's depth.
_DELEGATION_DEPTH: contextvars.ContextVar[int] = contextvars.ContextVar("agentdev_delegation_depth", default=0)


@dataclass
class TeamMember:
    node_id: str
    title: str
    summary: str
    # Members this member leads in turn (a sub-lead such as a PM), so the top lead can route named work.
    manages: tuple = ()


@dataclass
class TeamState:
    """Per-run bookkeeping shared by all leads (kept in ``context.global_state``).

    Thread-safe: parallel delegations read and write it from worker threads.
    """

    history: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    running: Set[str] = field(default_factory=set)
    # Questions leads asked the user during this run and the answers ({"question", "answer"}),
    # kept so the next turn of the conversation still knows what the user decided.
    exchanges: List[Dict[str, str]] = field(default_factory=list)
    lock: Any = field(default_factory=threading.RLock, repr=False, compare=False)

    @property
    def depth(self) -> int:
        """Delegation depth of the calling chain (per call chain, not per run)."""
        return _DELEGATION_DEPTH.get()

    def add_exchange(self, question: str, answer: str) -> None:
        with self.lock:
            self.exchanges.append({"question": question, "answer": answer})

    def add_report(self, member: str, task: str, report: str) -> None:
        with self.lock:
            self.history.setdefault(member, []).append({"task": task, "report": report})

    def recent(self, member: str, count: int = 2) -> List[Dict[str, str]]:
        with self.lock:
            return list(self.history.get(member) or [])[-count:]

    def claim(self, member: str) -> bool:
        """Mark a member busy; False when it is already running (a node's state is not reentrant)."""
        with self.lock:
            if member in self.running:
                return False
            self.running.add(member)
            return True

    def release(self, member: str) -> None:
        with self.lock:
            self.running.discard(member)


@contextmanager
def _nested_delegation() -> Iterator[None]:
    token = _DELEGATION_DEPTH.set(_DELEGATION_DEPTH.get() + 1)
    try:
        yield
    finally:
        _DELEGATION_DEPTH.reset(token)


def _first_line(text: Optional[str], limit: int = 220) -> str:
    for line in (text or "").splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line if len(line) <= limit else line[: limit - 1] + "…"
    return ""


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2 :]
    return f"{head}\n\n[… {len(text) - limit} characters omitted …]\n\n{tail}"


def resolve_members(lead_id: str, team_members: List[str], nodes: Mapping[str, Any]) -> List[TeamMember]:
    """Members listed in config, or every agent node without edges (staff nodes)."""
    if team_members:
        ids = [m for m in team_members if m != lead_id]
    else:
        ids = [
            node_id
            for node_id, node in nodes.items()
            if node_id != lead_id
            and getattr(node, "node_type", None) == "agent"
            and not getattr(node, "predecessors", None)
            and not getattr(node, "successors", None)
        ]
    members: List[TeamMember] = []
    for node_id in ids:
        node = nodes.get(node_id)
        if node is None or getattr(node, "node_type", None) != "agent":
            continue
        description = getattr(node, "description", None) or ""
        role = getattr(node, "role", None) or ""
        members.append(
            TeamMember(
                node_id=node_id,
                title=node_id,
                summary=_first_line(description) or _first_line(role) or "General team member",
                manages=tuple(_sub_team(node_id, node, nodes)),
            )
        )
    return members


def _sub_team(node_id: str, node: Any, nodes: Mapping[str, Any]) -> List[str]:
    """Explicit members of a member that is itself a team lead (empty for ordinary members)."""
    config = getattr(node, "config", None)
    team = getattr(config, "team", None)
    if not team or not getattr(team, "enabled", False):
        return []
    return [m for m in (getattr(team, "members", None) or []) if m != node_id and m in nodes]


LEAD_PROTOCOL = """\
# You lead a team
The user is your client. They talk ONLY to you; your team members never talk to the user.

## First, sort the message
- Greeting, small talk, a question about you, or a knowledge/advice question ("X vs Y?", "how does Z work?"): answer it yourself, right away — no tools, no delegation, no plan. Keep it short (a greeting: 1–3 sentences).
- "Can you build X?": say yes (or what is not possible) and propose a concrete default in a few lines (what you would build, key features, stack) so the user can just say "ok".
- Work on an existing project (attached files or a project folder): look at the relevant files with your read tools BEFORE planning or delegating, and base the plan and briefs on what is really there.
- Small, clear task (a bug fix, one function, a small change): delegate it directly to the right member, no approval round.
- New project or significant feature: see the approval rule below.
- Follow-up message: decisions, plans and answers in the earlier conversation still stand. If your last answer proposed a plan or asked a question and the user now approves ("ok", "duyệt", "go ahead"…) or answers it, act on it immediately — do not re-plan or ask for approval again.

## How you work
1. Fill gaps with sensible, industry-standard defaults and state them as assumptions the user can change, instead of asking about each one. Ask (`ask_user`) only for what you truly cannot assume and that changes the work: one short question, bundled with your proposal and your recommended answer.
2. Decide yourself who does what, in which order, and how many times. Do not call members the task does not need (a one-line fix does not need the whole team). If the request or your brief names a specific person ("ask the QA Tester…"), that person does the work: delegate to them if they are on your team, otherwise to the member who leads them and say in the brief who must do it. Never do a named person's work yourself.
3. Delegate with `delegate_task`. Give each member a self-contained brief: goal, relevant context and earlier results, constraints (stack, files, conventions), and what to hand back. Members do not see this conversation. Scope the brief to what the user asked (plus normal quality); do not add requirements of your own, and judge results against the user's request, not extras.
{parallel_rule}4. Chain work through yourself: pass one member's result to the next (e.g. analysis → fix → test → acceptance review). If a review or test fails, send it back for a fix, at most {max_rounds} rounds, then report the situation to the user.
5. When a member's reply starts with "{marker}", only the user can decide: ask them with `ask_user` (the options and your recommendation), then continue.
6. Finish with ONE short report to the user: the outcome in the first line, then only what applies — what was done, result/checks (tests, QA), files, open issues or next step. Do not paste members' output.

## Rules
- The user's technology choices are binding. If one is clearly wrong for the goal, say so with reasons and a better option, and let the user decide — never silently switch.
- {plan_rule}
- Report only what members actually produced; if something failed or was not checked, say so.
- No process narration ("I will now call…"), no internal tool, node or model names.
- You have at most {max_delegations} delegations for this request; plan accordingly.

## Your team
{roster}
"""

PLAN_RULE_ON = (
    "New project or significant new feature: first send one short, concrete plan (what will be built, stack, task "
    "split and order, your assumptions, any essential question) with `ask_user`, and wait for approval before any "
    "member builds anything. Skip approval when the user already approved (now or earlier in the conversation) or "
    "said to go ahead, and for small tasks and questions."
)
PLAN_RULE_OFF = "Proceed without asking for plan approval; ask the user only for real decisions."

PARALLEL_RULE = (
    "   When several tasks are INDEPENDENT (no task needs another's result and they do not edit the same files), "
    "hand them out at once with `delegate_parallel` — up to {max_parallel} members work at the same time, each "
    "member at most once per call (e.g. backend API + frontend page + data pipeline against an agreed contract). "
    "Agree on shared interfaces first and put them in every brief. Dependent steps (build → test → review) stay "
    "sequential with `delegate_task`. Every task counts as one delegation.\n"
)

MEMBER_PROTOCOL = """\
# You are a member of a team
Your lead ({lead}) assigns you tasks. Do exactly the task in the brief, using your skills, and report back to the lead.
- Report: what you did, the result (files changed, findings, test results), and anything unresolved. Concise and factual; no greeting, no recap of the brief.
- Report only what you actually did and observed. Never claim a test passed or a file exists unless you ran or checked it; say "not run" / "not verified" otherwise.
- If you cannot continue without a decision only the user can make (scope, budget, a technology choice, conflicting requirements), start your reply with "{marker}" followed by the question, the options and your recommendation.
- If the brief conflicts with good practice, say so in your report instead of silently doing something else.
"""

SUB_LEAD_PROTOCOL = """# You are a sub-lead
Your lead ({lead}) assigns you a task; you run your own team ({team}) to get it done and report back to {lead}.
- Delegate the work to the right people on your team instead of doing it yourself, unless it is truly a one-line answer within your own role.
- If the brief names a specific person (e.g. "QA Tester"), that person must do it: delegate to them. Never do a named person's work yourself.
- Report: who did what, the result, and anything unresolved. Concise and factual; no greeting, no recap of the brief. Report only what was actually done.
- If only the user can decide something, start your reply with "{marker}" followed by the question, the options and your recommendation.
"""

# Prepended to the system prompt of every agent that answers a person (not members briefed by a lead).
USER_RESPONSE_RULES = """\
# How you answer
- Language: reply in the language of the user's NEWEST message (Vietnamese → Vietnamese, English → English), even though these instructions are in English. Keep code, file names and technical terms as they are.
- Answer first: the first sentence answers the question or states the result; then only the detail that helps. A greeting or simple question gets a few sentences; "N points" gets exactly N points; "short" / "ngắn gọn" means under ~100 words.
- No filler: no preamble, no restating the question, no extra sections nobody asked for, no generic closing offers. Use bullets or short headings only when they help scanning.
- Be accurate: never invent facts, files, numbers or results. If you are unsure, say so briefly and how to check.
- Ask a clarifying question only when you cannot give a useful answer without it: one question, with your recommended default."""


class TeamDelegation:
    """Tools and prompt section for one lead's execution."""

    def __init__(
        self,
        *,
        lead_id: str,
        members: List[TeamMember],
        runner: DelegateRunner,
        prompt_service: Any,
        state: TeamState,
        max_delegations: int,
        max_review_rounds: int,
        plan_approval: bool,
        max_parallel: int = 1,
    ) -> None:
        self.lead_id = lead_id
        self.members = members
        self.runner = runner
        self.prompt_service = prompt_service
        self.state = state
        self.max_delegations = max_delegations
        self.max_review_rounds = max_review_rounds
        self.plan_approval = plan_approval
        self.max_parallel = max(1, int(max_parallel or 1))
        self.delegations = 0
        self._member_ids = {m.node_id for m in members}
        self._lock = threading.Lock()

    @property
    def parallel_enabled(self) -> bool:
        return self.max_parallel > 1 and len(self.members) > 1

    # ---- prompt ----
    def system_prompt_section(self) -> str:
        roster = "\n".join(
            f"- `{m.node_id}`: {m.summary}" + (f" — leads: {', '.join(m.manages)}" if m.manages else "")
            for m in self.members
        ) or "- (no members configured)"
        return LEAD_PROTOCOL.format(
            max_rounds=self.max_review_rounds,
            marker=DECISION_MARKER,
            plan_rule=PLAN_RULE_ON if self.plan_approval else PLAN_RULE_OFF,
            parallel_rule=PARALLEL_RULE.format(max_parallel=self.max_parallel) if self.parallel_enabled else "",
            max_delegations=self.max_delegations,
            roster=roster,
        )

    # ---- tools ----
    def _member_property(self) -> Dict[str, Any]:
        return {
            "type": "string",
            "enum": [m.node_id for m in self.members],
            "description": "Node ID of the team member.",
        }

    def tool_specs(self) -> List[ToolSpec]:
        task_property = {"type": "string", "description": "Self-contained brief: goal, context, constraints, expected output."}
        specs = [
            ToolSpec(
                name=ASK_USER_TOOL,
                description=(
                    "Ask the user (your client) a question and wait for the answer: plan approval, a decision only "
                    "they can make, or missing essential information. Write it in the user's language."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "The question, with options and your recommendation when relevant."}
                    },
                    "required": ["question"],
                },
                metadata={"source": TEAM_TOOL_SOURCE},
            )
        ]
        if self.members:
            delegate_specs = [
                ToolSpec(
                    name=DELEGATE_TOOL,
                    description=(
                        "Assign a task to one team member and wait for their report. Members only see the brief you "
                        "write, so include all context they need."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {"member": self._member_property(), "task": task_property},
                        "required": ["member", "task"],
                    },
                    metadata={"source": TEAM_TOOL_SOURCE},
                )
            ]
            if self.parallel_enabled:
                delegate_specs.append(
                    ToolSpec(
                        name=DELEGATE_PARALLEL_TOOL,
                        description=(
                            "Assign INDEPENDENT tasks to several different team members at once and wait for all "
                            f"their reports (up to {self.max_parallel} run at the same time). Use only when no task "
                            "needs another task's result; each member may appear at most once per call. Each task "
                            "counts as one delegation. Members only see their own brief."
                        ),
                        parameters={
                            "type": "object",
                            "properties": {
                                "tasks": {
                                    "type": "array",
                                    "minItems": 2,
                                    "maxItems": len(self.members),
                                    "description": "One entry per member; they run concurrently.",
                                    "items": {
                                        "type": "object",
                                        "properties": {"member": self._member_property(), "task": task_property},
                                        "required": ["member", "task"],
                                    },
                                }
                            },
                            "required": ["tasks"],
                        },
                        metadata={"source": TEAM_TOOL_SOURCE},
                    )
                )
            specs = delegate_specs + specs
        return specs

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == DELEGATE_TOOL:
            return self._delegate(str(arguments.get("member", "")).strip(), str(arguments.get("task", "")).strip())
        if tool_name == DELEGATE_PARALLEL_TOOL:
            return self._delegate_parallel(arguments.get("tasks"))
        if tool_name == ASK_USER_TOOL:
            return self._ask_user(str(arguments.get("question", "")).strip())
        raise ValueError(f"Unsupported team tool '{tool_name}'")

    # ---- delegation ----
    def _check_member(self, member: str, task: str) -> None:
        if member not in self._member_ids:
            raise ValueError(f"'{member}' is not on your team. Members: {sorted(self._member_ids)}")
        if not task:
            raise ValueError(f"task is required (member '{member}')")

    def _reserve(self, count: int) -> None:
        """Count ``count`` delegations against the limit, all or nothing."""
        if self.state.depth >= MAX_DELEGATION_DEPTH:
            raise ValueError("Delegation is nested too deeply; do this task yourself or report back.")
        with self._lock:
            left = self.max_delegations - self.delegations
            if left <= 0:
                raise ValueError(
                    f"Delegation limit ({self.max_delegations}) reached for this request. Report the current status to the user."
                )
            if count > left:
                raise ValueError(
                    f"Delegation limit: only {left} of {self.max_delegations} delegations left, but {count} tasks were "
                    "given. Send fewer tasks or report the current status to the user."
                )
            self.delegations += count

    def _delegations_left(self) -> int:
        with self._lock:
            return self.max_delegations - self.delegations

    def _delegate(self, member: str, task: str) -> Dict[str, Any]:
        self._check_member(member, task)
        self._reserve(1)
        result = self._run_member(member, task)
        result["delegations_left"] = self._delegations_left()
        return result

    def _run_member(self, member: str, task: str) -> Dict[str, Any]:
        """Run one member and record its report. Safe to call concurrently for different members."""
        if not self.state.claim(member):
            raise ValueError(f"'{member}' is already working on another task right now; wait for its report first.")
        try:
            brief = self._compose_brief(member, task)
            with _nested_delegation():
                outputs = self.runner(
                    member, [Message(role=MessageRole.USER, content=brief, metadata={"source": self.lead_id})], self.lead_id
                )
        finally:
            self.state.release(member)

        report = "\n\n".join(msg.text_content() for msg in outputs if msg is not None).strip() or "(no output)"
        self.state.add_report(member, task, report)
        return {
            "member": member,
            "report": _truncate(report, MAX_MEMBER_RESULT_CHARS),
            "needs_user_decision": report.lstrip().upper().startswith(DECISION_MARKER),
        }

    def _parse_parallel_tasks(self, raw_tasks: Any) -> List[Tuple[str, str]]:
        if not isinstance(raw_tasks, list) or len(raw_tasks) < 2:
            raise ValueError("tasks must be a list of at least 2 {member, task} items; use delegate_task for a single task.")
        tasks: List[Tuple[str, str]] = []
        seen: Set[str] = set()
        for idx, item in enumerate(raw_tasks):
            if not isinstance(item, Mapping):
                raise ValueError(f"tasks[{idx}] must be an object with 'member' and 'task'")
            member = str(item.get("member", "")).strip()
            task = str(item.get("task", "")).strip()
            self._check_member(member, task)
            if member in seen:
                raise ValueError(
                    f"'{member}' appears more than once. A member can work on only one task at a time: merge its "
                    "tasks into one brief, or give it the next task after this call returns."
                )
            seen.add(member)
            tasks.append((member, task))
        return tasks

    def _delegate_parallel(self, raw_tasks: Any) -> Dict[str, Any]:
        if not self.parallel_enabled:
            raise ValueError("Parallel delegation is disabled for this team; use delegate_task.")
        tasks = self._parse_parallel_tasks(raw_tasks)
        self._reserve(len(tasks))

        def run_one(member: str, task: str) -> Dict[str, Any]:
            try:
                return self._run_member(member, task)
            except WorkflowCancelledError:
                raise
            except Exception as exc:  # one failure must not lose the other members' reports
                return {"member": member, "error": str(exc) or exc.__class__.__name__, "needs_user_decision": False}

        results: List[Dict[str, Any]] = []
        cancelled: Optional[WorkflowCancelledError] = None
        workers = min(self.max_parallel, len(tasks))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"team-{self.lead_id}") as pool:
            # Each worker runs in a copy of this context: it inherits the current delegation depth and
            # only bumps its own copy, so sibling members do not count against each other's depth.
            futures = [pool.submit(contextvars.copy_context().run, run_one, member, task) for member, task in tasks]
            for (member, _task), future in zip(tasks, futures):
                try:
                    results.append(future.result())
                except WorkflowCancelledError as exc:
                    cancelled = cancelled or exc
                    for pending in futures:
                        pending.cancel()  # tasks not started yet never start
                except CancelledError:
                    results.append({"member": member, "error": "cancelled", "needs_user_decision": False})
        if cancelled is not None:
            raise cancelled

        return {
            "results": results,
            "failed": [r["member"] for r in results if "error" in r],
            "needs_user_decision": any(r.get("needs_user_decision") for r in results),
            "delegations_left": self._delegations_left(),
        }

    def _compose_brief(self, member: str, task: str) -> str:
        info = next((m for m in self.members if m.node_id == member), None)
        if info is not None and info.manages:
            parts = [SUB_LEAD_PROTOCOL.format(lead=self.lead_id, team=", ".join(info.manages), marker=DECISION_MARKER)]
        else:
            parts = [MEMBER_PROTOCOL.format(lead=self.lead_id, marker=DECISION_MARKER)]
        previous = self.state.recent(member, 2)
        if previous:
            lines = ["# Your earlier work in this session"]
            for item in previous:
                lines.append(f"## Task\n{_truncate(item['task'], 800)}\n## Your report\n{_truncate(item['report'], MAX_HISTORY_CHARS)}")
            parts.append("\n\n".join(lines))
        parts.append(f"# Task from {self.lead_id}\n{task}")
        return "\n\n".join(parts)

    def _ask_user(self, question: str) -> Dict[str, Any]:
        if not question:
            raise ValueError("question is required")
        if self.prompt_service is None:
            raise RuntimeError("No user is attached to this run; continue with your best judgement and state the assumption.")
        result = self.prompt_service.request(
            self.lead_id,
            question,
            inputs=None,
            metadata={"node_type": "agent", "kind": "lead_question"},
        )
        answer = getattr(result, "text", None)
        if answer is None:
            answer = str(result.as_message_content()) if hasattr(result, "as_message_content") else str(result)
        self.state.add_exchange(question, str(answer))
        return {"answer": answer}


def get_team_state(global_state: Dict[str, Any]) -> TeamState:
    state = global_state.get("_team_state")
    if not isinstance(state, TeamState):
        state = TeamState()
        global_state["_team_state"] = state
    return state


def is_delegated_call() -> bool:
    """True while an agent runs as a member briefed by a lead (it reports to the lead, not a person)."""
    return _DELEGATION_DEPTH.get() > 0


def user_exchanges(global_state: Optional[Mapping[str, Any]]) -> List[Dict[str, str]]:
    """Questions leads asked the user during a run, with the answers (empty when none)."""
    state = (global_state or {}).get("_team_state")
    if not isinstance(state, TeamState):
        return []
    with state.lock:
        return [dict(item) for item in state.exchanges]
