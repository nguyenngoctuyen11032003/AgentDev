"""Workflow Lab: check that a workflow is ready to use before relying on it.

Two levels:
- ``static_check``: instant, free. Structure, accounts, skills, tools, team wiring.
- ``LabJob``: runs the workflow on test scenarios (optionally several times each), lets an AI judge
  grade every answer against the scenario's acceptance criteria, and reports pass rate, stability,
  duration and token use. Questions the workflow asks the user are answered automatically.
"""

from __future__ import annotations

import copy
import functools
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from agentdev.utils.code_execution import UNSAFE_CODE_EXECUTION_ENV
from agentdev.utils.human_prompt import AUTO_ANSWER, AutoAnswerChannel

PASS, WARN, FAIL = "pass", "warn", "fail"
UNSAFE_TOOLS = {"execute_code", "run_shell_command", "uv_run", "install_python_packages", "init_python_env"}
PASS_THRESHOLD = 0.8
MAX_SCENARIOS = 20
MAX_REPEATS = 5


# ---------------------------------------------------------------------------- static check


def _check(checks: List[Dict[str, Any]], check_id: str, status: str, detail: str = "", **extra: Any) -> None:
    checks.append({"id": check_id, "status": status, "detail": detail, **extra})


def _agent_nodes(graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [n for n in graph.get("nodes") or [] if isinstance(n, dict) and n.get("type") == "agent"]


def _tool_names(config: Dict[str, Any]) -> List[str]:
    names: List[str] = []
    for tooling in config.get("tooling") or []:
        if not isinstance(tooling, dict) or tooling.get("type") != "function":
            continue
        for tool in (tooling.get("config") or {}).get("tools") or []:
            name = tool.get("name") if isinstance(tool, dict) else tool
            if isinstance(name, str):
                names.append(name)
    return names


def static_check(yaml_path: Path) -> Dict[str, Any]:
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        checks: List[Dict[str, Any]] = []
        _check(checks, "yaml", FAIL, str(exc))
        return _summarise(checks)
    return static_check_data(data)


def static_check_data(data: Any) -> Dict[str, Any]:
    """Same checks as ``static_check`` on an already-parsed workflow (e.g. YAML not yet saved)."""
    from agentdev.api.services import skill_library
    from agentdev.connections.autobind import bind_default_connections
    from agentdev.validation.check import check_config

    checks: List[Dict[str, Any]] = []
    if not isinstance(data, dict):
        _check(checks, "structure", FAIL, "Workflow must be a mapping")
        return _summarise(checks)

    error = check_config(data)
    _check(checks, "structure", FAIL if error else PASS, error)
    if error:
        return _summarise(checks)

    graph = data.get("graph") or {}
    nodes = {n.get("id"): n for n in graph.get("nodes") or [] if isinstance(n, dict)}
    agents = _agent_nodes(graph)
    edges = graph.get("edges") or []
    wired = {e.get("from") for e in edges} | {e.get("to") for e in edges}
    start = list(graph.get("start") or [])

    # Accounts: bind on a copy exactly as a run would.
    try:
        bound = copy.deepcopy(data)
        bind_default_connections(bound, os.environ)
        _check(checks, "accounts", PASS)
    except Exception as exc:  # noqa: BLE001 - shown to the user
        _check(checks, "accounts", FAIL, str(exc))

    # Roles.
    empty_roles = [a["id"] for a in agents if not str((a.get("config") or {}).get("role") or "").strip()]
    _check(checks, "roles", WARN if empty_roles else PASS, ", ".join(empty_roles), nodes=empty_roles)

    # Skills.
    library = {s["name"]: s for s in skill_library.list_skills()}
    missing_skills: List[str] = []
    for agent in agents:
        skills = (agent.get("config") or {}).get("skills") or {}
        if not skills.get("enabled"):
            continue
        for entry in skills.get("allow") or []:
            name = entry.get("name") if isinstance(entry, dict) else entry
            if name not in library or not library[name]["valid"]:
                missing_skills.append(f"{agent['id']}: {name}")
    _check(checks, "skills", WARN if missing_skills else PASS, "; ".join(missing_skills), items=missing_skills)

    # Tools.
    try:
        from agentdev.utils.function_catalog import get_function_catalog

        known_tools = set(get_function_catalog().list_metadata().keys())
    except Exception:  # noqa: BLE001
        known_tools = set()
    unknown_tools: List[str] = []
    unsafe_used: List[str] = []
    for agent in agents:
        for name in _tool_names(agent.get("config") or {}):
            base = name.split(":")[0]
            if known_tools and name not in known_tools and not name.endswith(":All"):
                unknown_tools.append(f"{agent['id']}: {name}")
            if base in UNSAFE_TOOLS or name in UNSAFE_TOOLS or base == "uv_related":
                unsafe_used.append(agent["id"])
    _check(checks, "tools", FAIL if unknown_tools else PASS, "; ".join(unknown_tools), items=unknown_tools)
    exec_enabled = os.environ.get(UNSAFE_CODE_EXECUTION_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
    unsafe_nodes = sorted(set(unsafe_used))
    _check(
        checks,
        "code_execution",
        WARN if unsafe_nodes and not exec_enabled else PASS,
        ", ".join(unsafe_nodes),
        nodes=unsafe_nodes,
        enabled=exec_enabled,
    )

    # Team leads and who can ever run.
    leads = [a for a in agents if ((a.get("config") or {}).get("team") or {}).get("enabled")]
    reachable = set(start) | {e.get("to") for e in edges}
    team_issues: List[str] = []
    team_members: List[str] = []  # valid members of every lead, in roster order (for Lab sample scenarios)
    for lead in leads:
        members = ((lead.get("config") or {}).get("team") or {}).get("members") or []
        if members:
            for member in members:
                node = nodes.get(member)
                if node is None or node.get("type") != "agent":
                    team_issues.append(f"{lead['id']} → {member}")
                else:
                    reachable.add(member)
                    team_members.append(member)
        else:
            staff = [a["id"] for a in agents if a["id"] != lead["id"] and a["id"] not in wired]
            reachable.update(staff)
            team_members.extend(staff)
            if not staff:
                team_issues.append(f"{lead['id']}: no members")
    if leads:
        lead_ids = {lead["id"] for lead in leads}
        members = list(dict.fromkeys(m for m in team_members if m not in lead_ids))
        _check(checks, "team", FAIL if team_issues else PASS, "; ".join(team_issues), items=team_issues,
               leads=[lead["id"] for lead in leads], members=members)
    never_run = sorted(nid for nid in nodes if nid not in reachable)
    _check(checks, "unreachable", WARN if never_run else PASS, ", ".join(never_run), nodes=never_run)

    return _summarise(checks)


def _summarise(checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    statuses = [c["status"] for c in checks]
    overall = FAIL if FAIL in statuses else WARN if WARN in statuses else PASS
    return {"status": overall, "checks": checks}


# ---------------------------------------------------------------------------- scenario runs


@dataclass
class Scenario:
    prompt: str
    criteria: str = ""
    name: str = ""


@dataclass
class LabJob:
    id: str
    workflow: str
    scenarios: List[Scenario]
    repeats: int
    # Status of step 1 (``static_check``) when the run started: a FAIL means the workflow is not ready.
    config_status: str = ""
    status: str = "queued"  # queued | running | completed | cancelled | error
    results: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    # Guards ``results`` (and the entries in it): the worker thread updates them while requests read them.
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    @property
    def total(self) -> int:
        return len(self.scenarios) * self.repeats

    def add_result(self, entry: Dict[str, Any]) -> None:
        with self.lock:
            self.results.append(entry)

    def update_result(self, entry: Dict[str, Any], **changes: Any) -> None:
        with self.lock:
            entry.update(changes)

    def to_dict(self) -> Dict[str, Any]:
        with self.lock:
            results = copy.deepcopy(self.results)
            status = self.status
        done = [r for r in results if r.get("status") in ("passed", "failed", "error")]
        judged = [r for r in done if r.get("status") in ("passed", "failed")]
        passed = [r for r in done if r.get("status") == "passed"]
        errors = [r for r in done if r.get("status") == "error"]
        pass_rate = (len(passed) / len(done)) if done else 0.0
        per_scenario: List[Dict[str, Any]] = []
        for index, scenario in enumerate(self.scenarios):
            runs = [r for r in done if r["scenario"] == index]
            ok = [r for r in runs if r["status"] == "passed"]
            members: List[str] = []
            for run in runs:
                for name in list(run.get("members") or []) + list((run.get("agents") or {}).keys()):
                    if name not in members:
                        members.append(name)
            per_scenario.append({
                "index": index,
                "name": scenario.name or f"#{index + 1}",
                "runs": len(runs),
                "passed": len(ok),
                # Stable = every repeat gave the same verdict.
                "stable": len({r["status"] for r in runs}) <= 1 if runs else None,
                "seconds": round(sum(r.get("seconds", 0) or 0 for r in runs) / len(runs), 1) if runs else None,
                "tokens": sum(r.get("tokens", 0) or 0 for r in runs),
                "cost_usd": round(sum(r.get("cost_usd", 0.0) or 0.0 for r in runs), 4),
                "members": members,
            })
        config_failed = self.config_status == FAIL
        verdict = None
        if status == "completed":
            ready = bool(done) and pass_rate >= PASS_THRESHOLD and not errors and not config_failed
            verdict = "ready" if ready else "not_ready"
        return {
            "id": self.id,
            "workflow": self.workflow,
            "status": status,
            "error": self.error,
            "total": self.total,
            "done": len(done),
            "passed": len(passed),
            "judged": len(judged),
            "errors": len(errors),
            "pass_rate": round(pass_rate, 3),
            "threshold": PASS_THRESHOLD,
            "verdict": verdict,
            "config_status": self.config_status,
            "config_failed": config_failed,
            "basic_graded": len([r for r in judged if (r.get("judge") or {}).get("judged_by") == "basic"]),
            "scenarios": per_scenario,
            "results": results,
            "duration_seconds": round((self.finished_at or time.time()) - self.started_at, 1),
            "total_tokens": sum(r.get("tokens", 0) for r in results),
            "cost_usd": round(sum(r.get("cost_usd", 0.0) for r in results), 4),
        }


JUDGE_SYSTEM = (
    "You grade the answer of an AI workflow against the acceptance criteria of a test scenario. "
    "Be strict but fair: pass only when every criterion is met by the answer itself. "
    "Also check the answer is in the same language as the request and actually addresses it. "
    'Reply with JSON only: {"pass": true|false, "score": 0-10, "reason": "<one or two sentences, in the request\'s language>"}'
)


class JudgeAccount:
    """The signed-in account that grades one lab job, resolved once and reused for every answer.

    Prefers the default connection when it is a signed-in (CLI / OAuth) account, else the first such
    account. When grading hits a quota error, the account is marked exhausted for this job and the
    judge switches to another account via ``pick_fallback``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._resolved = False
        self._conn: Any = None
        self._model: Optional[str] = None
        self.exhausted: set = set()

    @staticmethod
    def _signed_in(conn: Any) -> bool:
        from agentdev.connections.catalog import AUTH_CLI, AUTH_OAUTH

        return getattr(conn, "auth_type", None) in (AUTH_CLI, AUTH_OAUTH)

    def _pick(self) -> Any:
        from agentdev.connections.store import get_store

        store = get_store()
        default = store.default_connection()
        if default is not None and self._signed_in(default) and default.id not in self.exhausted:
            return default
        return next((c for c in store.list() if self._signed_in(c) and c.id not in self.exhausted), None)

    def current(self) -> tuple:
        """(connection, model name); raises when no signed-in account is available."""
        from agentdev.runtime.node.agent.account_fallback import default_model_for

        with self._lock:
            if not self._resolved:
                self._conn = self._pick()
                self._resolved = True
            if self._conn is None:
                raise RuntimeError("No signed-in account to grade the answers. Sign in on the Connections page.")
            if self._model is None:
                self._model = default_model_for(self._conn) or ""  # slow (CLI detection): once per account
            return self._conn, self._model

    def switch(self, failed_id: str) -> bool:
        """Mark ``failed_id`` exhausted and move to another account. False when none is left."""
        from agentdev.runtime.node.agent.account_fallback import pick_fallback

        with self._lock:
            self.exhausted.add(failed_id)
            if self._conn is not None and self._conn.id != failed_id:
                return True  # already switched
            self._conn = pick_fallback(failed_id, needs_tools=False, exhausted=self.exhausted)
            self._model = None
            self._resolved = True
            return self._conn is not None


def _judge_call(conn: Any, model: str, user: str) -> str:
    from agentdev.connections.resolver import resolve_connection
    from agentdev.entity.messages import Message, MessageRole
    from agentdev.runtime.node.agent import ProviderRegistry

    creds = resolve_connection(conn.id)
    provider_name = creds.provider or creds.vendor
    provider_class = ProviderRegistry.get_provider(provider_name)
    config = SimpleConfig(name=model, provider=provider_name, api_key=creds.token,
                          base_url=creds.base_url or "", params={"timeout": 180})
    provider = provider_class(config)
    response = provider.call_model(
        provider.create_client(),
        [Message(role=MessageRole.SYSTEM, content=JUDGE_SYSTEM), Message(role=MessageRole.USER, content=user)],
        [],
    )
    return response.message.text_content()


DEFAULT_CRITERIA = (
    "Answers the request correctly and completely, in the user's language, concise; "
    "for build tasks the deliverable exists and works"
)


def _basic_verdict(answer: str, reason: str = "") -> Dict[str, Any]:
    """Fallback grade when the AI judge cannot be reached: a non-empty, error-free answer passes."""
    ok = bool(answer.strip()) and not answer.lstrip().lower().startswith("error calling model")
    return {"pass": ok, "score": 10 if ok else 0, "reason": reason, "judged_by": "basic"}


def _judge(prompt: str, criteria: str, answer: str, questions: List[Dict[str, str]],
           account: Optional[JudgeAccount] = None) -> Dict[str, Any]:
    """Grade with a signed-in account (``judged_by: "ai"``); without criteria, ``DEFAULT_CRITERIA`` apply.

    Raises when no account can grade; ``LabRunner`` then falls back to ``_basic_verdict``.
    """
    criteria = criteria.strip() or DEFAULT_CRITERIA
    from agentdev.runtime.node.agent import account_fallback

    def out_of_quota(exc: BaseException) -> bool:
        exhaustion = getattr(account_fallback, "is_exhaustion_error", None)
        return account_fallback.is_quota_error(exc) or bool(exhaustion and exhaustion(exc))

    account = account or JudgeAccount()
    asked = "\n".join(f"- {q['node']}: {q['question']}" for q in questions) or "(none)"
    user = (
        f"## Request\n{prompt}\n\n## Acceptance criteria\n{criteria}\n\n"
        f"## Questions the workflow asked the user (auto-answered: approved)\n{asked}\n\n## Answer\n{answer[:20000]}"
    )
    conn, model = account.current()
    try:
        text = _judge_call(conn, model, user)
    except Exception as exc:  # noqa: BLE001 - retried once on another account when out of quota
        if not out_of_quota(exc) or not account.switch(conn.id):
            raise
        conn, model = account.current()
        text = _judge_call(conn, model, user)
    match = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(match.group(0)) if match else {}
    except ValueError:
        data = {}
    return {
        "pass": bool(data.get("pass")),
        "score": data.get("score"),
        "reason": str(data.get("reason") or text[:300]),
        "judged_by": "ai",
        "judge_model": f"{conn.label} ({model})",
    }


@dataclass
class SimpleConfig:
    """Minimal provider config for the judge call (same attributes providers read from AgentConfig)."""

    name: str
    provider: str
    api_key: Optional[str] = None
    base_url: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    token_tracker: Any = None
    node_id: Optional[str] = "lab_judge"


# Reply the Lab gives when a team lead stops to have its plan approved.
PLAN_APPROVAL = "Đồng ý, làm đi."


def _global_state(executor: Any, context: Any) -> Dict[str, Any]:
    """The run's shared state (best effort: whatever the executor exposes)."""
    try:
        state = executor._get_execution_context().global_state
        if isinstance(state, dict):
            return state
    except Exception:  # noqa: BLE001
        pass
    state = getattr(context, "global_state", None)
    return state if isinstance(state, dict) else {}


def _pending_plan(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The plan a team lead submitted for approval in this run (``plan_pending``), if any."""
    plan = state.get("plan_pending")
    if not plan:
        return None
    return plan if isinstance(plan, dict) else {"plan": str(plan)}


def _run_turn(yaml_path: Path, session: str, prompt: str, cancel_event: threading.Event) -> Dict[str, Any]:
    """Run the workflow once on ``prompt``; the turns of one scenario share the ``session`` folder."""
    from agentdev.entity.graph_config import GraphConfig
    from agentdev.runtime.node.agent.team import team_digest_from_state, user_exchanges
    from agentdev.runtime.sdk import OUTPUT_ROOT, ensure_schema_registry_populated
    from agentdev.utils.human_prompt import HumanPromptService
    from agentdev.validation.check import load_config
    from agentdev.workflow.graph import GraphExecutor
    from agentdev.workflow.graph_context import GraphContext

    ensure_schema_registry_populated()
    design = load_config(yaml_path)
    graph_config = GraphConfig.from_definition(
        design.graph, name=session, output_root=OUTPUT_ROOT, source_path=str(yaml_path), vars=design.vars
    )
    context = GraphContext(config=graph_config)
    executor = GraphExecutor(context, cancel_event=cancel_event)
    channel = AutoAnswerChannel()
    executor._human_prompt_service = HumanPromptService(log_manager=executor.log_manager, channel=channel)
    executor._execute(prompt)
    final = executor.get_final_output_message()
    usage = executor.token_tracker.get_token_usage() if executor.token_tracker else {}
    cost = sum(
        float((call.get("metadata") or {}).get("total_cost_usd") or 0) for call in usage.get("call_history") or []
    )
    state = _global_state(executor, context)
    return {
        "answer": final.text_content() if final is not None else "",
        "tokens": (usage.get("total_usage") or {}).get("total_tokens", 0),
        "cost_usd": cost,
        "agents": dict(usage.get("node_execution_counts") or {}),
        "questions": list(channel.questions),
        "team": team_digest_from_state(state),
        "exchanges": user_exchanges(state),
        "plan": _pending_plan(state),
        "output_dir": str(context.directory),
    }


def _run_once(yaml_path: Path, scenario: Scenario, cancel_event: threading.Event,
              run_turn: Callable[..., Dict[str, Any]] = _run_turn) -> Dict[str, Any]:
    """Run one scenario. When a team lead stops with a plan for approval, approve it and run a second
    turn, so the judge grades the work and not only the plan (two turns at most)."""
    from agentdev.api.services.conversation_turns import compose_follow_up_prompt, make_turn

    session = f"lab_{yaml_path.stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    started = time.time()
    turns = [run_turn(yaml_path, session, scenario.prompt, cancel_event)]
    plan = turns[0].get("plan")
    if plan and not cancel_event.is_set():
        first = turns[0]
        plan_text = first.get("answer") or str(plan.get("plan") or plan.get("summary") or "")
        turn = make_turn(scenario.prompt, plan_text, exchanges=first.get("exchanges") or [])
        turn["kind"] = "plan"
        turns.append(run_turn(yaml_path, session, compose_follow_up_prompt([turn], PLAN_APPROVAL), cancel_event))

    agents: Dict[str, int] = {}
    members: List[str] = []
    for item in turns:
        for name, count in (item.get("agents") or {}).items():
            agents[name] = agents.get(name, 0) + (count or 0)
        for entry in item.get("team") or []:
            member = entry.get("member") if isinstance(entry, dict) else None
            if member and member not in members:
                members.append(member)
    result: Dict[str, Any] = {
        "answer": turns[-1].get("answer", ""),
        "seconds": round(time.time() - started, 1),
        "tokens": sum(item.get("tokens", 0) or 0 for item in turns),
        "cost_usd": round(sum(float(item.get("cost_usd", 0) or 0) for item in turns), 4),
        "agents": agents,
        "members": members,
        "questions": [q for item in turns for q in item.get("questions") or []],
        "turns": len(turns),
        "output_dir": turns[-1].get("output_dir", ""),
    }
    if len(turns) > 1:
        result["plan"] = {
            "node": str(plan.get("node") or ""),
            "summary": str(plan.get("summary") or ""),
            "text": (turns[0].get("answer") or str(plan.get("plan") or ""))[:20000],
        }
    return result


def _lab_dir() -> Path:
    from agentdev.paths import STORAGE_DIR

    return Path(STORAGE_DIR) / "lab_jobs"


class StoredJob:
    """A finished (or interrupted) job read back from disk after a server restart."""

    def __init__(self, data: Dict[str, Any]) -> None:
        self.data = data
        self.cancel_event = threading.Event()

    def to_dict(self) -> Dict[str, Any]:
        return self.data


class LabRunner:
    """Runs Lab jobs in threads; every change is also written to storage/lab_jobs/<id>.json so results
    survive a backend reload (a job that was running when the server stopped is reported as interrupted)."""

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        self._jobs: Dict[str, LabJob] = {}
        self._lock = threading.Lock()
        self._store_dir = store_dir

    def _dir(self) -> Path:
        return self._store_dir or _lab_dir()

    def _save(self, job: LabJob) -> None:
        try:
            folder = self._dir()
            folder.mkdir(parents=True, exist_ok=True)
            tmp = folder / f"{job.id}.json.tmp"
            tmp.write_text(json.dumps(job.to_dict(), ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, folder / f"{job.id}.json")
        except OSError:
            pass  # persistence is best effort; the in-memory job is authoritative

    def _load(self, job_id: str) -> Optional[StoredJob]:
        if not re.fullmatch(r"[0-9a-f]{12}", job_id or ""):
            return None
        path = self._dir() / f"{job_id}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if data.get("status") in ("queued", "running"):
            data["status"] = "error"
            data["error"] = "interrupted: the server restarted while this run was in progress"
            for result in data.get("results") or []:
                if result.get("status") == "running":
                    result["status"] = "error"
                    result["error"] = "interrupted"
        return StoredJob(data)

    def start(self, yaml_path: Path, workflow: str, scenarios: List[Scenario], repeats: int,
              run_once: Callable[..., Dict[str, Any]] = _run_once,
              judge: Callable[..., Dict[str, Any]] = _judge, config_status: str = "") -> LabJob:
        job = LabJob(id=uuid.uuid4().hex[:12], workflow=workflow, scenarios=scenarios, repeats=repeats,
                     config_status=config_status)
        if judge is _judge:
            judge = functools.partial(_judge, account=JudgeAccount())  # one judge account per job
        with self._lock:
            self._jobs[job.id] = job
        self._save(job)
        thread = threading.Thread(target=self._run, args=(job, yaml_path, run_once, judge), daemon=True)
        thread.start()
        return job

    def get(self, job_id: str):
        return self._jobs.get(job_id) or self._load(job_id)

    def cancel(self, job_id: str):
        job = self._jobs.get(job_id)
        if job is not None:
            job.cancel_event.set()
            return job
        return self._load(job_id)

    def _run(self, job: LabJob, yaml_path: Path, run_once, judge) -> None:
        job.status = "running"
        try:
            for repeat in range(job.repeats):
                for index, scenario in enumerate(job.scenarios):
                    if job.cancel_event.is_set():
                        job.status = "cancelled"
                        return
                    entry: Dict[str, Any] = {"scenario": index, "repeat": repeat + 1, "status": "running"}
                    job.add_result(entry)
                    self._save(job)
                    try:
                        outcome = run_once(yaml_path, scenario, job.cancel_event)
                    except Exception as exc:  # noqa: BLE001 - reported per run
                        if job.cancel_event.is_set():
                            job.update_result(entry, status="cancelled")
                            job.status = "cancelled"
                            return
                        job.update_result(entry, status="error", error=str(exc)[:2000])
                        continue
                    job.update_result(entry, **outcome)
                    try:
                        verdict = judge(scenario.prompt, scenario.criteria, outcome.get("answer", ""),
                                        outcome.get("questions", []))
                        job.update_result(entry, status="passed" if verdict.get("pass") else "failed", judge=verdict)
                    except Exception as exc:  # noqa: BLE001 - no account could grade: basic check instead
                        verdict = _basic_verdict(outcome.get("answer", ""), f"AI judge unavailable: {exc}"[:500])
                        job.update_result(entry, status="passed" if verdict["pass"] else "failed", judge=verdict)
                    self._save(job)
            job.status = "completed"
        except Exception as exc:  # noqa: BLE001
            job.status = "error"
            job.error = str(exc)
        finally:
            job.finished_at = time.time()
            self._save(job)


_runner = LabRunner()


def get_lab_runner() -> LabRunner:
    return _runner
