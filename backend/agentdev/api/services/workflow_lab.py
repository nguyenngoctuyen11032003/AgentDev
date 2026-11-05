"""Workflow Lab: check that a workflow is ready to use before relying on it.

Two levels:
- ``static_check``: instant, free. Structure, accounts, skills, tools, team wiring.
- ``LabJob``: runs the workflow on test scenarios (optionally several times each), lets an AI judge
  grade every answer against the scenario's acceptance criteria, and reports pass rate, stability,
  duration and token use. Questions the workflow asks the user are answered automatically.
"""

from __future__ import annotations

import contextvars
import copy
import functools
import hashlib
import json
import math
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from agentdev.api.services.lab_diagnosis import (
    SLOW_SECONDS,
    build_fix_brief,
    compare_baseline,
    diagnose_job,
    node_timeline,
    over_budget,
    regression_finding,
    run_budget,
)
from agentdev.api.services.workflow_patterns.graph_analysis import (  # noqa: F401 - re-exported
    CRITICAL_PATH_AGENTS,
    CRITICAL_PATH_SECONDS,
    LOOP_PASS_SECONDS,
    TIER_SECONDS,
    Graph,
    edge_condition_matches,
    model_tier,
)
from agentdev.utils.code_execution import UNSAFE_CODE_EXECUTION_ENV
from agentdev.utils.human_prompt import AUTO_ANSWER, AUTO_SKIP_PAID, AutoAnswerChannel

PASS, WARN, FAIL = "pass", "warn", "fail"
UNSAFE_TOOLS = {"execute_code", "run_shell_command", "uv_run", "install_python_packages", "init_python_env"}
PASS_THRESHOLD = 0.8
MAX_SCENARIOS = 20
MAX_REPEATS = 5
RUN_TIMEOUT_SECONDS = int(os.environ.get("AGENTDEV_LAB_RUN_TIMEOUT", "600"))
# After the watchdog (or a job cancel) asks a run to stop, how long it may take to wind down before the worker
# gives up on it: a hung model call or CLI never checks the cancel event.
TIMEOUT_GRACE_SECONDS = 20
SCENARIO_PASS_SHARE = 2 / 3  # every scenario must pass at least this share of its own runs


def _lab_workers() -> int:
    try:
        return max(1, min(int(os.environ.get("AGENTDEV_LAB_WORKERS", "3")), 8))
    except ValueError:
        return 3


def _strict_budget() -> bool:
    return os.environ.get("AGENTDEV_LAB_STRICT", "1").strip().lower() not in {"0", "false", "no", "off"}


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

    _graph_checks(checks, graph, nodes, edges, start)
    return _summarise(checks)


# --- graph analysis (loops, human approvals, dead ends, model sanity, critical path)
# The graph logic itself lives in workflow_patterns.graph_analysis (shared with the proposal lint).

LIGHT_ROLE_WORDS = ("review", "qa", "summar", "archiv", "save", "guard", "check")
# Graph checks whose FAIL a proposed edit may keep when the saved file already had the same problem.
BASELINE_EXEMPT_CHECKS = ("loops", "human_auto")


def _paid_gates(g: Graph) -> set:
    """Human gates marked ``paid: true``: the Lab refuses them (``AUTO_SKIP_PAID``) instead of approving."""
    return {nid for nid, node in g.nodes.items() if node.get("type") == "human"
            and isinstance(node.get("config"), dict) and node["config"].get("paid") is True}


def _humans_blocking_lab_answer(g: Graph) -> List[Any]:
    """Gates the Lab's automatic answer cannot move on: approval for ordinary gates, refusal for paid ones."""
    paid = _paid_gates(g)
    bad = [n for n in g.humans_blocking_auto_answer(AUTO_ANSWER) if n not in paid]
    if paid:
        bad += [n for n in g.humans_blocking_auto_answer(AUTO_SKIP_PAID) if n in paid]
        # The skip answer must also stay out of the paid step: an edge that fires whatever the answer is
        # (missing/"true" condition, empty keyword list) would carry the refusal straight into it.
        bad += [n for n in sorted(paid, key=str) if n not in bad and any(
            e.get("from") == n and _fires_on_any_answer(e.get("condition")) for e in g.edges)]
    return bad


def _fires_on_any_answer(condition: Any) -> bool:
    """Whether an edge condition passes whatever text reaches it (cannot tell approval from refusal)."""
    from agentdev.validation.check_workflow import is_always_true_condition

    if is_always_true_condition(condition):
        return True
    if isinstance(condition, dict) and condition.get("type") == "keyword":
        cfg = condition.get("config") if isinstance(condition.get("config"), dict) else {}
        return not (cfg.get("any") or cfg.get("none") or cfg.get("regex"))
    return False


def _graph_checks(checks, graph, nodes, edges, start) -> None:
    g = Graph(graph)
    ids = list(g.nodes)

    # (1) loops without a guard
    unguarded = [sorted(str(n) for n in c) for c in g.unguarded_cycles()]
    _check(checks, "loops", FAIL if unguarded else PASS,
           "; ".join(" -> ".join(c) for c in unguarded), loops=unguarded)

    # (2) human approvals must accept the Lab's automatic answer (a guarded feedback loop is fine)
    bad_humans = [str(n) for n in _humans_blocking_lab_answer(g)]
    _check(checks, "human_auto", FAIL if bad_humans else PASS, ", ".join(bad_humans), nodes=bad_humans)

    # (3) nodes that can never reach an end node
    ends = {n for n in (graph.get("end") or []) if n in g.adj}
    if ends:
        seen = set(ends)
        todo = list(ends)
        while todo:
            for prev in g.radj.get(todo.pop(), []):
                if prev not in seen:
                    seen.add(prev)
                    todo.append(prev)
        wired = {e.get("from") for e in g.edges} | {e.get("to") for e in g.edges}
        dead = sorted(str(n) for n in ids if n in wired and n not in seen)
        _check(checks, "dead_end", WARN if dead else PASS, ", ".join(dead), nodes=dead)

    # (4) heavy model/effort on light roles
    heavy: List[str] = []
    for nid, node in g.nodes.items():
        if node.get("type") != "agent":
            continue
        cfg = node.get("config") or {}
        label = f"{nid} {str(cfg.get('role') or '')[:80]}".lower()
        if not any(w in label for w in LIGHT_ROLE_WORDS):
            continue
        effort = str((cfg.get("params") or {}).get("effort") or "").lower()
        if model_tier(cfg.get("name")) == "top" or effort == "high":
            heavy.append(str(nid))
    _check(checks, "model_fit", WARN if heavy else PASS, ", ".join(heavy), nodes=heavy)

    # (5) critical path (the one speed estimate shown for a workflow)
    path = g.critical_path()
    seconds, agent_count = path["estimated_seconds"], path["agents"]
    _check(checks, "critical_path", WARN if path["slow"] else PASS,
           f"~{seconds}s, {agent_count} agent" if agent_count else "", estimated_seconds=seconds,
           agents=agent_count, heavy_agents=path["heavy_agents"])


def new_failures(report: Dict[str, Any], baseline: Any) -> List[Dict[str, Any]]:
    """FAIL checks of ``report`` that a proposed edit introduces, given the saved workflow ``baseline``
    (parsed YAML, or None for a new file). ``accounts`` never counts (it is this machine's setup, not the
    proposal). A ``loops`` / ``human_auto`` FAIL is dropped when every loop / gate it names was already
    broken in the saved file, so editing an unrelated part of an old workflow is not rejected."""
    fails = [c for c in report.get("checks") or [] if c.get("status") == FAIL and c.get("id") != "accounts"]
    if not isinstance(baseline, dict) or not any(c["id"] in BASELINE_EXEMPT_CHECKS for c in fails):
        return fails
    g = Graph.from_workflow(baseline)
    old_loops = [{str(n) for n in c} for c in g.unguarded_cycles()]
    old_humans = {str(n) for n in _humans_blocking_lab_answer(g)}
    out: List[Dict[str, Any]] = []
    for c in fails:
        if c["id"] == "loops":
            new = [loop for loop in c.get("loops") or [] if not any(set(loop) & old for old in old_loops)]
            if not new:
                continue
            c = {**c, "loops": new, "detail": "; ".join(" -> ".join(loop) for loop in new)}
        elif c["id"] == "human_auto":
            new = [n for n in c.get("nodes") or [] if n not in old_humans]
            if not new:
                continue
            c = {**c, "nodes": new, "detail": ", ".join(new)}
        out.append(c)
    return out


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
    max_seconds: Optional[int] = None  # per-run budgets; default depends on the prompt (see lab_diagnosis.run_budget)
    max_tokens: Optional[int] = None


@dataclass
class LabJob:
    id: str
    workflow: str
    scenarios: List[Scenario]
    repeats: int
    # Status of step 1 (``static_check``) when the run started: a FAIL means the workflow is not ready.
    config_status: str = ""
    workflow_hash: str = ""  # sha256 of the workflow YAML text when the job started
    store_dir: Optional[Path] = None  # where finished jobs live (to find the baseline run)
    status: str = "queued"  # queued | running | completed | cancelled | error
    results: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    # Guards ``results`` (and the entries in it): the worker thread updates them while requests read them.
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    # Serialises writes of this job's JSON file (LabRunner._save is called from several worker threads).
    save_lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    _baseline: Optional[Dict[str, Any]] = field(default=None, repr=False, compare=False)
    _baseline_loaded: bool = field(default=False, repr=False, compare=False)
    _baseline_lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    # Bumped on every change of ``results``: ``to_dict`` recomputes the summary only when it moved.
    _version: int = field(default=0, repr=False, compare=False)
    _cache: Optional[Tuple[Any, Dict[str, Any]]] = field(default=None, repr=False, compare=False)

    @property
    def total(self) -> int:
        return len(self.scenarios) * self.repeats

    def add_result(self, entry: Dict[str, Any]) -> None:
        with self.lock:
            entry.setdefault("run_id", _new_run_id(self.id))
            self.results.append(entry)
            self._version += 1

    def _find_baseline(self) -> Optional[Dict[str, Any]]:
        """The latest earlier completed job of this workflow that was ready (cached: found once)."""
        with self._baseline_lock:
            if self._baseline_loaded:
                return self._baseline
            for item in list_stored_jobs(self.store_dir or _lab_dir(), self.workflow, limit=50):
                if (item["id"] != self.id and item["status"] == "completed" and item["verdict"] == "ready"
                        and (item.get("finished_at") or 0) and (item.get("started_at") or 0) < self.started_at):
                    self._baseline = item
                    break
            self._baseline_loaded = True
        return self._baseline

    def update_result(self, entry: Dict[str, Any], **changes: Any) -> None:
        with self.lock:
            entry.update(changes)
            self._version += 1

    def to_dict(self) -> Dict[str, Any]:
        """The job summary. The expensive part (diagnosis, fix brief, budgets) is cached per version of the
        results and job state; only the running duration is refreshed on each poll."""
        with self.lock:
            key = (self._version, self.status, self.finished_at, self.error, self.config_status, len(self.results))
            cached = self._cache
        if cached is None or cached[0] != key:
            cached = (key, self._build_dict())
            with self.lock:
                self._cache = cached
        data = copy.deepcopy(cached[1])  # callers may change their copy
        # Outside the cache: it reads the disk (an output folder deleted later does not bump the version).
        data["resumable"] = (data["status"] in ("cancelled", "error") and data["judged"] < self.total) or (
            data["status"] == "completed" and bool(_rejudgeable(data["results"])))
        data["duration_seconds"] = round((self.finished_at or time.time()) - self.started_at, 1)
        return data

    def _build_dict(self) -> Dict[str, Any]:
        with self.lock:
            results = sorted(copy.deepcopy(self.results), key=lambda r: (r.get("repeat", 0), r.get("scenario", 0)))
            status = self.status
        for run in results:
            run.setdefault("run_id", _legacy_run_id(self.id, run))
        # "unjudged": the run finished but no judge could grade it; it counts as done (progress) but is in
        # neither the numerator nor the denominator of the pass rate.
        done = [r for r in results if r.get("status") in ("passed", "failed", "error", "unjudged")]
        for run in done:
            scenario = self.scenarios[run["scenario"]] if 0 <= run.get("scenario", -1) < len(self.scenarios) else None
            budget = run_budget(scenario.prompt if scenario else "", getattr(scenario, "max_seconds", None),
                                getattr(scenario, "max_tokens", None))
            run["budget_seconds"], run["budget_tokens"] = budget["seconds"], budget["tokens"]
            run["over_budget"] = over_budget(run, budget)
        judged = [r for r in done if r.get("status") in ("passed", "failed")]
        judge_tokens = sum(int((r.get("judge") or {}).get("tokens") or 0) for r in results)
        judge_cost = sum(float((r.get("judge") or {}).get("cost_usd") or 0.0) for r in results)
        run_cost = sum(float(r.get("cost_usd", 0.0) or 0.0) for r in results)
        passed = [r for r in done if r.get("status") == "passed"]
        errors = [r for r in done if r.get("status") == "error"]
        unjudged = [r for r in done if r.get("status") == "unjudged"]
        graded = [r for r in done if r.get("status") != "unjudged"]
        pass_rate = (len(passed) / len(graded)) if graded else 0.0
        per_scenario: List[Dict[str, Any]] = []
        for index, scenario in enumerate(self.scenarios):
            finished = [r for r in done if r["scenario"] == index]
            runs = [r for r in finished if r["status"] != "unjudged"]
            ok = [r for r in runs if r["status"] == "passed"]
            members: List[str] = []
            for run in finished:
                for name in list(run.get("members") or []) + list((run.get("agents") or {}).keys()):
                    if name not in members:
                        members.append(name)
            per_scenario.append({
                "index": index,
                "name": scenario.name or f"#{index + 1}",
                # The scenario itself is stored too, so a run interrupted by a server restart can be resumed.
                "prompt": scenario.prompt,
                "criteria": scenario.criteria,
                "max_seconds": scenario.max_seconds,
                "max_tokens": scenario.max_tokens,
                "runs": len(runs),
                "passed": len(ok),
                # Stable = every repeat gave the same verdict.
                "stable": len({r["status"] for r in runs}) <= 1 if runs else None,
                "seconds": round(sum(r.get("seconds", 0) or 0 for r in runs) / len(runs), 1) if runs else None,
                "tokens": sum(r.get("tokens", 0) or 0 for r in runs),
                "cost_usd": round(sum(r.get("cost_usd", 0.0) or 0.0 for r in runs), 4),
                "members": members,
                "needed": math.ceil(len(runs) * SCENARIO_PASS_SHARE - 1e-9) if runs else 0,
                "over_budget": len([r for r in runs if r.get("over_budget")]),
                "unjudged": len(finished) - len(runs),
            })
        config_failed = self.config_status == FAIL
        findings = diagnose_job(done, {i: sc.prompt for i, sc in enumerate(self.scenarios)})
        slow_runs = len([r for r in done if (r.get("seconds") or 0) > (r.get("budget_seconds") or SLOW_SECONDS)])
        verdict = None
        reasons: List[str] = []
        unverified = len([r for r in passed if (r.get("judge") or {}).get("judged_by") == "basic"])
        over = len([r for r in done if r.get("over_budget")])
        baseline: Optional[Dict[str, Any]] = None
        regression: Dict[str, Any] = {}
        if status == "completed":
            if not done:
                reasons.append("Chưa có lượt chạy nào hoàn tất.")
            if config_failed:
                reasons.append("Bước 1 (kiểm tra cấu hình) còn lỗi FAIL.")
            if graded and pass_rate < PASS_THRESHOLD:
                reasons.append(f"Tỷ lệ đạt {pass_rate * 100:.0f}% thấp hơn ngưỡng {PASS_THRESHOLD * 100:.0f}%.")
            if errors:
                reasons.append(f"{len(errors)} lượt chạy lỗi hoặc hết thời gian chờ.")
            for item in per_scenario:
                if item["runs"] and item["passed"] < item["needed"]:
                    reasons.append(f"Kịch bản \"{item['name']}\" chỉ đạt {item['passed']}/{item['runs']} lượt "
                                   f"(cần ít nhất {item['needed']}).")
            if unjudged:
                reasons.append(f"{len(unjudged)} lượt chưa chấm được (không gọi được giám khảo AI hoặc giám khảo trả lời "
                               "không đúng định dạng): không tính vào tỷ lệ đạt.")
            if passed and unverified == len(passed):
                reasons.append("Mọi lượt đạt chỉ được chấm bằng kiểm tra cơ bản (không có giám khảo AI) nên chưa được xác minh.")
            if over and _strict_budget():
                reasons.append(f"{over} lượt chạy vượt ngân sách thời gian/token.")
            verdict = "not_ready" if reasons else "ready"
            baseline = self._find_baseline()
            if baseline:
                current = {
                    # Nothing graded (all unjudged): no pass rate to compare, not a drop to 0%.
                    "pass_rate": round(pass_rate, 3) if graded else None,
                    "avg_seconds": round(sum(r.get("seconds", 0) or 0 for r in done) / len(done), 1) if done else None,
                    "cost_usd": round(run_cost, 4),  # runs only, like the baseline below
                    "done": len(done),
                }
                regression = compare_baseline(current, dict(baseline, cost_usd=_run_cost_of(baseline)))
                extra = regression_finding(regression)
                if extra:
                    findings.append(extra)
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
            "verdict_reasons": reasons,
            "unverified": unverified,
            "unjudged": len(unjudged),
            "skipped_gates": sorted({str(g) for r in done for g in r.get("skipped_gates") or []}),
            "over_budget_runs": over,
            "workflow_hash": self.workflow_hash,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "baseline": baseline,
            "regression": regression,
            "basic_graded": len([r for r in done if (r.get("judge") or {}).get("judged_by") == "basic"]),
            "scenarios": per_scenario,
            "findings": findings,
            "slow_runs": slow_runs,
            "slow_seconds": SLOW_SECONDS,
            "avg_seconds": round(sum(r.get("seconds", 0) or 0 for r in done) / len(done), 1) if done else None,
            "fix_brief": build_fix_brief(self.workflow, graded, self.scenarios, findings, pass_rate, PASS_THRESHOLD) if status == "completed" else "",
            "results": results,
            # "resumable" is set by to_dict (not cached): stopped before every run was graded, the rest can still
            # run under this job (LabRunner.resume); unjudged runs with an answer are only graded again on resume.
            "duration_seconds": round((self.finished_at or time.time()) - self.started_at, 1),
            # Totals include grading: the judge (and its second look) runs on the user's account too.
            "total_tokens": sum(r.get("tokens", 0) or 0 for r in results) + judge_tokens,
            "cost_usd": round(run_cost + judge_cost, 4),
            "run_cost_usd": round(run_cost, 4),
            "judge_tokens": judge_tokens,
            "judge_cost_usd": round(judge_cost, 4),
        }


def _run_cost_of(job: Dict[str, Any]) -> Optional[float]:
    """Cost of a stored job's runs without grading (older jobs have no ``judge_cost_usd``: all run cost)."""
    if job.get("run_cost_usd") is not None:
        return float(job["run_cost_usd"])
    if job.get("cost_usd") is None:
        return None
    return float(job["cost_usd"]) - float(job.get("judge_cost_usd") or 0.0)


def _unjudged_with_answer(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Unjudged runs that have an answer: never run through the workflow again on resume."""
    return [r for r in results if r.get("status") == "unjudged" and str(r.get("answer") or "").strip()]


def _rejudgeable(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Unjudged runs resume can grade again from what they stored. A run whose recorded output folder is gone
    (retention) stays unjudged: the judge would see "no files" and fail a build that did produce them."""
    return [r for r in _unjudged_with_answer(results)
            if not r.get("output_dir") or Path(str(r["output_dir"])).is_dir()]


def _new_run_id(job_id: str) -> str:
    """Id of one run of a job (``run_id``): made once when the run starts, kept in the stored job and across
    resume, so its outputs and previews can be keyed by it."""
    return f"{job_id}-{uuid.uuid4().hex[:8]}"


def _legacy_run_id(job_id: str, run: Dict[str, Any]) -> str:
    """Deterministic id for a run stored before ``run_id`` existed (same value on every read)."""
    return f"{job_id}-s{run.get('scenario', 0)}r{run.get('repeat', 0)}"


JUDGE_SYSTEM = (
    "You grade the answer of an AI workflow against the acceptance criteria of a test scenario. "
    "Be strict but fair: pass only when every criterion is met by the answer itself. "
    "Also check the answer is in the same language as the request and actually addresses it. "
    "When the criteria expect a deliverable, verify it in the list of files produced by the run (name, size, preview). "
    "A claim that tests passed or code works counts only when the answer names the command that was run and its "
    "result (e.g. a 'Đã kiểm chứng: <command> → <result>' line) or the produced files show it; an unsupported claim is "
    "unverified: do not give 7 or more for it. A sentence saying a step could not be run is honest, not a pass. "
    "Each run starts in an EMPTY project folder: when the request refers to an existing app whose code it does not "
    "include, a self-contained fix that says plainly the code was not found and labels its root cause as an "
    "assumption meets a root-cause/reproduction criterion; do not fail it for that alone. "
    "Score 0-10 against the criteria; 7 or more only when every criterion is met. "
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
                self._model = _judge_model(self._conn) or default_model_for(self._conn) or ""  # once per account
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


def _judge_model(conn: Any) -> Optional[str]:
    """Mid-tier model of the account's vendor (e.g. Sonnet, not Opus): grading one answer against a
    rubric does not need the top model, and the judge runs once per scenario run."""
    from agentdev.api.services.workflow_patterns.proposal_lint import default_model
    from agentdev.api.services.workflow_patterns.graph_analysis import model_tier

    try:
        name = default_model(getattr(conn, "vendor", "") or "", "mid")
    except Exception:  # noqa: BLE001 - fall back to the account's default model
        return None
    return name if name and model_tier(name) == "mid" else None


def _judge_call(conn: Any, model: str, user: str, system: str = "") -> str:
    from agentdev.connections.resolver import resolve_connection
    from agentdev.entity.messages import Message, MessageRole
    from agentdev.runtime.node.agent import ProviderRegistry

    from agentdev.utils.token_tracker import TokenTracker

    creds = resolve_connection(conn.id)
    provider_name = creds.provider or creds.vendor
    provider_class = ProviderRegistry.get_provider(provider_name)
    tracker = TokenTracker("lab_judge")  # what the account's call path reports (tokens; cost when it knows it)
    config = SimpleConfig(name=model, provider=provider_name, auth_token=creds.token,
                          base_url=creds.base_url or "", params={"timeout": 180, "effort": "low"},
                          token_tracker=tracker)
    provider = provider_class(config)
    try:
        response = provider.call_model(
            provider.create_client(),
            [Message(role=MessageRole.SYSTEM, content=system or JUDGE_SYSTEM),
             Message(role=MessageRole.USER, content=user)],
            [],
        )
    finally:
        try:
            usage = tracker.get_token_usage()
            costs = [(c.get("metadata") or {}).get("total_cost_usd") for c in usage.get("call_history") or []]
            _record_judge_usage(tokens=int((usage.get("total_usage") or {}).get("total_tokens") or 0),
                                cost_usd=sum(float(c) for c in costs if c is not None) if any(
                                    c is not None for c in costs) else None)
        except Exception:  # noqa: BLE001 - accounting never breaks grading
            pass
    return response.message.text_content()


# Usage of the judge calls made for the verdict being computed in this thread (see ``_judge``).
_JUDGE_USAGE: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar("lab_judge_usage", default=None)


def _record_judge_usage(tokens: int = 0, cost_usd: Optional[float] = None) -> None:
    """Add one judge call's reported usage to the current verdict. A call that reports no cost adds 0:
    prices are never guessed."""
    box = _JUDGE_USAGE.get()
    if box is None:
        return
    box["tokens"] += int(tokens or 0)
    box["cost_usd"] += float(cost_usd or 0.0)


DEFAULT_CRITERIA = (
    "Answers the request correctly and completely, in the user's language, concise; "
    "for build tasks the deliverable exists and works"
)


def _basic_verdict(answer: str, reason: str = "") -> Dict[str, Any]:
    """Fallback when no AI judge could grade the run. An empty answer or a model-call error is a real fail;
    anything else is ``unjudged`` (not a pass: a placeholder, a bare plan or a refusal would pass a
    "non-empty" check) and stays out of the pass rate."""
    unusable = not answer.strip() or answer.lstrip().lower().startswith("error calling model")
    if unusable:
        return {"pass": False, "score": 0, "verdict": "fail", "reason": reason, "judged_by": "basic"}
    return {"pass": False, "score": None, "verdict": "unjudged", "reason": reason, "judged_by": "basic"}


MANIFEST_MAX_FILES = 40
MANIFEST_TEXT_FILES = 5
MANIFEST_PREVIEW_CHARS = 600


def build_output_manifest(output_dir: Any) -> str:
    """Names + sizes of the files a run produced, plus the first ~600 chars of up to 5 text files (binaries skipped),
    so the judge can verify that a deliverable really exists. Empty string when there is nothing."""
    if not output_dir:
        return ""
    root = Path(str(output_dir))
    if not root.is_dir():
        return ""
    files = sorted(p for p in root.rglob("*") if p.is_file())
    if not files:
        return ""
    lines = []
    for path in files[:MANIFEST_MAX_FILES]:
        try:
            lines.append(f"- {path.relative_to(root).as_posix()} ({path.stat().st_size} bytes)")
        except OSError:
            continue
    if len(files) > MANIFEST_MAX_FILES:
        lines.append(f"- ... and {len(files) - MANIFEST_MAX_FILES} more files")
    previews = 0
    for path in files:
        if previews >= MANIFEST_TEXT_FILES:
            break
        try:
            raw = path.read_bytes()[:4000]
        except OSError:
            continue
        if b"\0" in raw:
            continue  # binary
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        previews += 1
        lines += ["", f"### {path.relative_to(root).as_posix()}", text[:MANIFEST_PREVIEW_CHARS]]
    return "\n".join(lines)


def _score_value(score: Any) -> Optional[float]:
    """A judge score as a number, or None when it is missing or not a number ("N/A", "seven")."""
    if score is None or isinstance(score, bool):
        return None
    try:
        return float(score)
    except (TypeError, ValueError):
        match = re.match(r"\s*(\d+(?:\.\d+)?)", str(score))  # "5/10", "8 out of 10"
        return float(match.group(1)) if match else None


def _score10(score: Any) -> Optional[float]:
    """A judge score on the 0-10 scale: "7/10" -> 7, "70/100" -> 7, a bare 75 (a 0-100 answer) -> 7.5."""
    if isinstance(score, str):
        match = re.match(r"\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", score)
        if match and float(match.group(2)) > 0:
            return float(match.group(1)) * 10 / float(match.group(2))
    value = _score_value(score)
    if value is not None and 10 < value <= 100:
        value /= 10
    return value


def _rubric_pass(data: Dict[str, Any]) -> bool:
    """pass must be true AND the score (0-10 scale) at least 7: a verdict without a usable score cannot pass,
    otherwise a lenient judge could wave through an empty or fabricated result."""
    if data.get("pass") is not True:
        return False
    value = _score10(data.get("score"))
    return value is not None and value >= 7


def _first_json(text: str, opener: str, accept: Callable[[Any], bool] = lambda value: True) -> Any:
    """The first complete JSON value starting with ``opener`` ("{" or "[") in ``text`` that ``accept`` takes,
    else None. Decodes exactly one balanced value (``raw_decode``), unlike a greedy regex that also swallows
    any later braces."""
    decoder = json.JSONDecoder()
    text = text or ""
    start = text.find(opener)
    while start != -1:
        try:
            value, _ = decoder.raw_decode(text, start)
        except ValueError:
            value = None
        if value is not None and accept(value):
            return value
        start = text.find(opener, start + 1)
    return None


def _parse_verdict(text: str) -> Dict[str, Any]:
    """The judge's verdict object, or {} when the reply holds no usable one (no JSON object with ``pass``)."""
    return _first_json(text, "{", lambda value: isinstance(value, dict) and "pass" in value) or {}


class JudgeUnparsable(RuntimeError):
    """The judge answered twice without a usable JSON verdict: the run stays unjudged."""


JSON_REMINDER = ("\n\nNHẮC LẠI: chỉ trả về đúng MỘT đối tượng JSON, không thêm chữ nào khác: "
                 '{"pass": true|false, "score": 0-10, "reason": "..."}')


def _borderline(data: Dict[str, Any]) -> bool:
    """Score 6-7 (the pass line is 7): too close to call for a cheap judge. An 8 is a clear pass; looking at
    it again doubled the judge cost of most good runs."""
    value = _score10(data.get("score"))
    return value is not None and 6 <= value < 8


# Answer text sent to the judge: head + tail + passages about the criteria, at most this many characters.
JUDGE_ANSWER_CHARS = 8000
_CLIP_HEAD = 3000
_CLIP_TAIL = 2000
_CLIP_STOPWORDS = {"the", "and", "with", "that", "this", "for", "from", "must", "should", "have", "của", "các",
                   "những", "được", "trong", "phải", "không", "cho", "với", "một", "và", "là"}


def _clip_marker(count: int) -> str:
    return f"\n[… đã lược bớt {count} ký tự …]\n"


def _clip_answer(answer: str, criteria: str, limit: int = JUDGE_ANSWER_CHARS) -> str:
    """The answer for the judge: whole when short, else its head and tail plus the middle passages that mention
    the most criteria keywords (in their original order), each gap marked with how much was left out."""
    if len(answer) <= limit:
        return answer
    head, tail = answer[:_CLIP_HEAD], answer[-_CLIP_TAIL:]
    middle_start, middle_end = _CLIP_HEAD, len(answer) - _CLIP_TAIL
    words = {w for w in re.findall(r"[\w.]{3,}", criteria.lower()) if w not in _CLIP_STOPWORDS}
    marker = len(_clip_marker(len(answer)))  # the longest a gap marker can be
    # Every picked passage costs its text plus the marker in front of it; the closing marker is reserved here.
    budget = limit - _CLIP_HEAD - _CLIP_TAIL - marker
    picks: List[Tuple[int, int]] = []
    if words and budget > marker:
        scored = []
        for start, end in _clip_windows(answer, middle_start, middle_end):
            text = answer[start:end].lower()
            hits = sum(1 for w in words if w in text)
            if hits:
                scored.append((-hits, start, end))
        for _, start, end in sorted(scored):
            cost = (end - start) + marker
            if cost > budget:
                continue
            picks.append((start, end))
            budget -= cost
    parts = [head]
    cursor = middle_start
    for start, end in sorted(picks):
        parts.append(_clip_marker(start - cursor) if start > cursor else "\n")
        parts.append(answer[start:end])
        cursor = end
    parts.append(_clip_marker(middle_end - cursor))
    parts.append(tail)
    out = "".join(parts)
    if len(out) > limit:  # safety net: never send more than the limit
        out = out[:limit - len(tail) - marker] + _clip_marker(len(out) - limit) + tail
        out = out[-limit:] if len(out) > limit else out
    return out


_CLIP_WINDOW = 400


def _clip_windows(answer: str, start: int, end: int) -> List[Tuple[int, int]]:
    """The middle of an answer as passages of at most ``_CLIP_WINDOW`` chars: its lines, long lines (or a text
    without newlines) cut into fixed windows, so a keyword deep inside one long line can still be picked."""
    out: List[Tuple[int, int]] = []
    for match in re.finditer(r"[^\n]+", answer[start:end]):
        a, b = match.start() + start, match.end() + start
        while a < b:
            out.append((a, min(b, a + _CLIP_WINDOW)))
            a += _CLIP_WINDOW
    return out


def _judge_prefix(prompt: str, criteria: str) -> str:
    """The part of the judge message that is the same for every run of a scenario (request + criteria). It comes
    first, after the fixed system prompt, so the account's prompt cache can reuse it across repeats; what
    varies per run (questions, answer, files) follows."""
    return f"## Request\n{prompt}\n\n## Acceptance criteria\n{criteria}\n\n"


def _judge(prompt: str, criteria: str, answer: str, questions: List[Dict[str, str]],
           account: Optional[JudgeAccount] = None, output_dir: Any = None) -> Dict[str, Any]:
    """Grade with a signed-in account (``judged_by: "ai"``); without criteria, ``DEFAULT_CRITERIA`` apply.

    Raises when no account can grade; ``LabRunner`` then falls back to ``_basic_verdict``.
    """
    criteria = criteria.strip() or DEFAULT_CRITERIA
    account = account or JudgeAccount()
    usage = {"tokens": 0, "cost_usd": 0.0, "calls": 0}
    token = _JUDGE_USAGE.set(usage)
    try:
        verdict = _judge_inner(prompt, criteria, answer, questions, account, output_dir, usage)
    except Exception as exc:
        exc.judge_usage = dict(usage)  # type: ignore[attr-defined] - the calls made were still paid for
        raise
    finally:
        _JUDGE_USAGE.reset(token)
    if usage["calls"]:
        verdict.update(tokens=usage["tokens"], cost_usd=round(usage["cost_usd"], 6), calls=usage["calls"])
    return verdict


def _judge_inner(prompt: str, criteria: str, answer: str, questions: List[Dict[str, str]],
                 account: Any, output_dir: Any, usage: Dict[str, Any]) -> Dict[str, Any]:
    skipped = list(dict.fromkeys(str(q.get("node")) for q in questions if q.get("answer") == "skipped"))
    asked = "\n".join(
        f"- {q['node']}: {q['question']} -> " + ("SKIPPED (refused automatically: paid or irreversible step)"
                                               if q.get("answer") == "skipped" else "approved automatically")
        for q in questions) or "(none)"
    user = _judge_prefix(prompt, criteria) + (
        f"## Questions the workflow asked the user (answered automatically)\n{asked}\n\n"
    )
    if skipped:
        user += ("## Skipped approval gates\n"
                 + "\n".join(f"- cổng {n} bị bỏ qua, không phải đã duyệt (bước tốn tiền hoặc không hoàn tác được; "
                             "không ai duyệt nên bước sau nó không chạy)" for n in skipped)
                 + "\nDo not fail the run only because the deliverable of a skipped paid step is missing.\n\n")
    user += f"## Answer\n{_clip_answer(answer, criteria)}"
    manifest = build_output_manifest(output_dir)
    if not answer.strip() and not manifest:
        # Nothing to grade: no judge call is made, so this is a rule-based (basic) fail, not an AI verdict.
        return {"pass": False, "score": 0, "verdict": "fail", "reason": "The run produced no answer and no files.",
                "judged_by": "basic", "judge_model": ""}
    user += f"\n\n## Files produced by the run\n{manifest or '(no files were produced)'}"
    conn, model = account.current()

    def call(text_in: str) -> str:
        nonlocal conn, model
        usage["calls"] += 1
        try:
            return _judge_call(conn, model, text_in)
        except Exception as exc:  # noqa: BLE001 - retried once on another account when out of quota
            if not _out_of_quota(exc) or not account.switch(conn.id):
                raise
            conn, model = account.current()
            usage["calls"] += 1
            return _judge_call(conn, model, text_in)

    text = call(user)
    data = _parse_verdict(text)
    if not data:
        # A reply without a usable JSON verdict is a judge problem, not a failed run: ask once more.
        text = call(user + JSON_REMINDER)
        data = _parse_verdict(text)
        if not data:
            raise JudgeUnparsable(f"The judge did not return a JSON verdict: {text[:200]}")
    # A score next to the pass line is where a cheaper judge is least reliable: grade it again with the
    # account's own default (stronger) model and keep that verdict. Clear passes and fails stay cheap.
    # A pass is never counted without proper grading: when that second look fails (error, no JSON, no score),
    # the run is left unjudged rather than kept on the cheap model's borderline verdict.
    if _borderline(data):
        from agentdev.runtime.node.agent.account_fallback import default_model_for

        strong = default_model_for(conn) or ""
        if strong and strong != model:
            usage["calls"] += 1
            try:
                second = _parse_verdict(_judge_call(conn, strong, user))
            except Exception as exc:  # noqa: BLE001
                raise JudgeUnparsable(f"The second look at a borderline score failed: {exc}"[:300]) from exc
            if "pass" not in second or _score10(second.get("score")) is None:
                raise JudgeUnparsable("The second look at a borderline score gave no usable verdict.")
            data, model = second, strong
    return {
        "pass": _rubric_pass(data),
        "score": data.get("score"),
        "reason": str(data.get("reason") or text[:300]),
        "judged_by": "ai",
        "judge_model": f"{conn.label} ({model})",
    }


def _out_of_quota(exc: BaseException) -> bool:
    """A genuine quota / rate-limit / usage-limit error (another account may still work)."""
    from agentdev.runtime.node.agent import account_fallback

    exhaustion = getattr(account_fallback, "is_exhaustion_error", None)
    return account_fallback.is_quota_error(exc) or bool(exhaustion and exhaustion(exc))


@dataclass
class SimpleConfig:
    """Minimal provider config for the judge call (same attributes providers read from AgentConfig)."""

    name: str
    provider: str
    auth_token: Optional[str] = None  # the account's OAuth token (Google); CLI accounts: empty
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
    from agentdev.utils.exceptions import WorkflowExecutionError
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
    turn_started = datetime.now()
    stopped_at_gate = ""
    try:
        executor._execute(prompt)
    except WorkflowExecutionError:
        # A paid gate refused automatically may leave no branch to take (its only way on is the paid step):
        # that is the intended stop, not a broken workflow.
        if not channel.skipped_gates:
            raise
        stopped_at_gate = ", ".join(channel.skipped_gates)
    final = executor.get_final_output_message()
    usage = executor.token_tracker.get_token_usage() if executor.token_tracker else {}
    cost = sum(
        float((call.get("metadata") or {}).get("total_cost_usd") or 0) for call in usage.get("call_history") or []
    )
    state = _global_state(executor, context)
    return {
        "answer": (f"[Stopped at skipped paid gate: {stopped_at_gate}] The run did not continue into the paid step."
                   if stopped_at_gate else (final.text_content() if final is not None else "")),
        "tokens": (usage.get("total_usage") or {}).get("total_tokens", 0),
        "cost_usd": cost,
        "agents": dict(usage.get("node_execution_counts") or {}),
        "timeline": node_timeline(usage.get("call_history"), turn_started),
        "node_runs": list(usage.get("node_runs") or []),
        "questions": list(channel.questions),
        "skipped_gates": list(channel.skipped_gates),
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
    # A run that loops (e.g. a review cycle that never ends) is stopped after RUN_TIMEOUT_SECONDS.
    job_cancel = cancel_event
    cancel_event = threading.Event()
    timed_out = threading.Event()

    def _watchdog() -> None:
        deadline = time.time() + RUN_TIMEOUT_SECONDS
        while not cancel_event.is_set():
            if job_cancel.is_set():
                cancel_event.set()
            elif time.time() > deadline:
                timed_out.set()
                cancel_event.set()
            else:
                time.sleep(1)

    threading.Thread(target=_watchdog, daemon=True).start()
    try:
        return _run_once_inner(yaml_path, scenario, cancel_event, run_turn, session, started, timed_out)
    except Exception as exc:
        # A failed or timed-out run still took this long: keep it so averages and time regressions are not
        # computed as if the run took 0 seconds.
        exc.lab_seconds = round(time.time() - started, 1)  # type: ignore[attr-defined]
        # What a failed or timed-out run produced is still worth looking at (often most of the work):
        # keep its folder so the Lab can show it instead of leaving it orphaned in the warehouse.
        exc.lab_output_dir = _session_output_dir(session)  # type: ignore[attr-defined]
        raise
    finally:
        cancel_event.set()  # stops the watchdog


def _session_output_dir(session: str) -> str:
    """The newest folder a run of ``session`` wrote (``<warehouse>/<session>_<timestamp>``), or ""."""
    try:
        from agentdev.runtime.sdk import OUTPUT_ROOT

        folders = [p for p in Path(OUTPUT_ROOT).glob(f"{session}_*") if p.is_dir()]
        return str(max(folders, key=lambda p: p.name)) if folders else ""
    except Exception:  # noqa: BLE001 - best effort; the error itself is what gets reported
        return ""


def _run_once_inner(yaml_path: Path, scenario: Scenario, cancel_event: threading.Event, run_turn: Callable[..., Dict[str, Any]],
                    session: str, started: float, timed_out: threading.Event) -> Dict[str, Any]:
    from agentdev.api.services.conversation_turns import compose_follow_up_prompt, make_turn

    minutes = RUN_TIMEOUT_SECONDS // 60
    message = (f"Run stopped after {f'{minutes} minutes' if minutes else f'{RUN_TIMEOUT_SECONDS}s'} without finishing: "
               "the workflow is probably looping (check approval conditions and loop guards).")
    box: Dict[str, Any] = {}
    finished = threading.Event()

    def _work() -> None:
        try:
            box["result"] = _collect_turns(yaml_path, scenario, cancel_event, run_turn, session, started,
                                           compose_follow_up_prompt, make_turn)
        except BaseException as exc:  # noqa: BLE001 - re-raised in the caller's thread
            box["error"] = exc
        finally:
            finished.set()

    threading.Thread(target=_work, daemon=True, name="lab-run").start()
    stop_at: Optional[float] = None
    while not finished.wait(0.5):
        if cancel_event.is_set():
            stop_at = stop_at or time.time() + TIMEOUT_GRACE_SECONDS
            if time.time() > stop_at:  # the run ignores the cancel event (hung call): abandon its thread
                if not timed_out.is_set():
                    raise RuntimeError("Run cancelled")
                raise RuntimeError(message)
    if "error" in box:
        if timed_out.is_set():
            raise RuntimeError(message)
        raise box["error"]
    result = box["result"]
    if timed_out.is_set():
        raise RuntimeError(message)
    return result


def _collect_turns(yaml_path, scenario, cancel_event, run_turn, session, started, compose_follow_up_prompt, make_turn):
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
        "timeline": [t for item in turns for t in item.get("timeline") or []],
        "node_runs": [r for item in turns for r in item.get("node_runs") or []],
        "questions": [q for item in turns for q in item.get("questions") or []],
        "skipped_gates": list(dict.fromkeys(g for item in turns for g in item.get("skipped_gates") or [])),
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


def _replace_with_retry(src: Path, dst: Path, attempts: int = 10, delay: float = 0.02) -> None:
    """``os.replace`` that retries briefly on PermissionError: on Windows the target cannot be replaced
    while another thread or a request is reading it."""
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay * (attempt + 1))


INTERRUPTED_ERROR = "interrupted: the server restarted while this run was in progress"


def _resumable_tasks(data: Dict[str, Any]) -> List[Tuple[int, int]]:
    """(scenario index, repeat index) of every run of a stored job that has no grade yet."""
    specs = data.get("scenarios") or []
    if not specs:
        return []
    repeats = max(1, int(data.get("total") or 0) // len(specs))
    results = data.get("results") or []
    graded = {(int(r.get("scenario", -1)), int(r.get("repeat", 0)) - 1)
              for r in [r for r in results if r.get("status") in ("passed", "failed")] + _unjudged_with_answer(results)}
    return [(index, repeat) for repeat in range(repeats) for index in range(len(specs))
            if (index, repeat) not in graded]


class LabRunner:
    """Runs Lab jobs in threads; every change is also written to storage/lab_jobs/<id>.json so results
    survive a backend reload (a job that was running when the server stopped is reported as interrupted)."""

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        self._jobs: Dict[str, LabJob] = {}
        self._lock = threading.Lock()
        self._resume_lock = threading.Lock()
        self._store_dir = store_dir

    def _dir(self) -> Path:
        return self._store_dir or _lab_dir()

    def _save(self, job: LabJob) -> None:
        # Runs of one job finish on several worker threads: saves are serialised per job (the snapshot is
        # taken inside the lock, so the last write is also the newest state) and every write uses its own
        # temp file, so two writers never share or interleave one.
        with job.save_lock:
            tmp: Optional[Path] = None
            try:
                folder = self._dir()
                folder.mkdir(parents=True, exist_ok=True)
                tmp = folder / f"{job.id}.{uuid.uuid4().hex[:8]}.json.tmp"
                tmp.write_text(json.dumps(job.to_dict(), ensure_ascii=False), encoding="utf-8")
                _replace_with_retry(tmp, folder / f"{job.id}.json")
                tmp = None
            except OSError:
                pass  # persistence is best effort; the in-memory job is authoritative
            finally:
                if tmp is not None:
                    try:
                        tmp.unlink()
                    except OSError:
                        pass

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
            data["error"] = INTERRUPTED_ERROR
            data["interrupted"] = True
            for result in data.get("results") or []:
                if result.get("status") == "running":
                    result["status"] = "error"
                    result["error"] = "interrupted"
        if data.get("status") in ("error", "cancelled", "completed"):
            can_run = data.get("status") != "completed" and bool(_resumable_tasks(data))
            data["resumable"] = (can_run or bool(_rejudgeable(data.get("results") or []))) and all(
                (s.get("prompt") or "").strip() for s in data.get("scenarios") or [{}])
        return StoredJob(data)

    def resume(self, job_id: str, yaml_path: Path,
               run_once: Callable[..., Dict[str, Any]] = _run_once,
               judge: Callable[..., Dict[str, Any]] = _judge) -> LabJob:
        """Continue a job that a server restart (or a cancel) stopped: graded runs are kept and only the
        unfinished ones run again, under the same job id. Raises ValueError when it cannot be resumed.

        The "already running" check and the registration of the resumed job happen under one lock, so two
        quick resumes of the same job cannot start two workers."""
        with self._resume_lock:
            return self._resume(job_id, yaml_path, run_once, judge)

    def _resume(self, job_id: str, yaml_path: Path, run_once, judge) -> LabJob:
        with self._lock:
            if job_id in self._jobs and self._jobs[job_id].status in ("queued", "running"):
                raise ValueError("Lượt kiểm định này vẫn đang chạy.")
        stored = self._load(job_id)
        if stored is None:
            raise LookupError("Lab run not found")
        data = stored.data
        rejudge_ids = {str(r.get("run_id") or _legacy_run_id(data["id"], r)) for r in _rejudgeable(data.get("results") or [])}
        if data.get("status") not in ("error", "cancelled") and not (data.get("status") == "completed" and rejudge_ids):
            raise ValueError("Chỉ chạy tiếp được lượt kiểm định bị gián đoạn hoặc đã dừng.")
        specs = data.get("scenarios") or []
        if not specs or not all((s.get("prompt") or "").strip() for s in specs):
            raise ValueError("Lượt kiểm định này được tạo bởi phiên bản cũ, không lưu nội dung kịch bản: hãy chạy lại từ đầu.")
        try:
            current_hash = hashlib.sha256(Path(yaml_path).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        except OSError:
            current_hash = ""
        tasks = _resumable_tasks(data) if data.get("status") != "completed" else []
        # Re-judging a stored answer does not run the workflow, so only new runs need the same workflow file.
        if tasks and data.get("workflow_hash") and current_hash and data["workflow_hash"] != current_hash:
            raise ValueError("Quy trình đã được sửa sau lượt này: kết quả cũ không còn so được, hãy chạy lại từ đầu.")
        if not tasks and not rejudge_ids:
            raise ValueError("Không còn lượt nào cần chạy tiếp.")
        scenarios = [Scenario(prompt=s.get("prompt", ""), criteria=s.get("criteria", ""), name=s.get("name", ""),
                              max_seconds=s.get("max_seconds"), max_tokens=s.get("max_tokens")) for s in specs]
        keep = [dict(r, scenario=int(r["scenario"]), repeat=int(r["repeat"]),
                     run_id=r.get("run_id") or _legacy_run_id(data["id"], r))
                for r in data.get("results") or [] if r.get("status") in ("passed", "failed")
                or r in _unjudged_with_answer(data.get("results") or [])]
        # Count only the time the job actually ran, not the gap while the server was down.
        elapsed = float(data.get("duration_seconds") or 0)
        job = LabJob(id=data["id"], workflow=data.get("workflow", ""), scenarios=scenarios,
                     repeats=int(data.get("total") or 0) // max(1, len(scenarios)) or 1,
                     config_status=data.get("config_status", ""), workflow_hash=data.get("workflow_hash", ""),
                     store_dir=self._dir(), results=keep, started_at=time.time() - elapsed)
        if judge is _judge:
            judge = functools.partial(_judge, account=JudgeAccount())
        with self._lock:
            self._jobs[job.id] = job
        self._save(job)
        rejudge = [r for r in job.results if r["run_id"] in rejudge_ids]
        thread = threading.Thread(target=self._run, args=(job, yaml_path, run_once, judge, tasks, rejudge), daemon=True)
        thread.start()
        return job

    def start(self, yaml_path: Path, workflow: str, scenarios: List[Scenario], repeats: int,
              run_once: Callable[..., Dict[str, Any]] = _run_once,
              judge: Callable[..., Dict[str, Any]] = _judge, config_status: str = "") -> LabJob:
        try:
            workflow_hash = hashlib.sha256(Path(yaml_path).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        except OSError:
            workflow_hash = ""
        job = LabJob(id=uuid.uuid4().hex[:12], workflow=workflow, scenarios=scenarios, repeats=repeats,
                     config_status=config_status, workflow_hash=workflow_hash, store_dir=self._dir())
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

    def list_jobs(self, workflow: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            live = frozenset(self._jobs)
        return list_stored_jobs(self._dir(), workflow, limit, live_ids=live)

    def _run_task(self, job: LabJob, yaml_path: Path, run_once, judge, index: int, repeat: int) -> None:
        scenario = job.scenarios[index]
        if job.cancel_event.is_set():
            return
        entry: Dict[str, Any] = {"scenario": index, "repeat": repeat + 1, "status": "running",
                                 "run_id": _new_run_id(job.id)}
        job.add_result(entry)
        self._save(job)
        try:
            outcome = run_once(yaml_path, scenario, job.cancel_event)
        except Exception as exc:  # noqa: BLE001 - reported per run
            if job.cancel_event.is_set():
                job.update_result(entry, status="cancelled")
                return
            extra = {"seconds": exc.lab_seconds} if getattr(exc, "lab_seconds", None) is not None else {}
            if getattr(exc, "lab_output_dir", ""):
                extra["output_dir"] = exc.lab_output_dir
            job.update_result(entry, status="error", error=str(exc)[:2000], **extra)
            self._save(job)
            return
        job.update_result(entry, **outcome)
        self._judge_entry(job, judge, entry)

    def _judge_entry(self, job: LabJob, judge, entry: Dict[str, Any]) -> None:
        """Grade one finished run from what it stored (answer, questions, files); also used to re-judge."""
        index = int(entry.get("scenario", 0))
        scenario = job.scenarios[index] if 0 <= index < len(job.scenarios) else Scenario(prompt="")
        if job.cancel_event.is_set() and entry.get("status") == "unjudged":
            return
        kwargs: Dict[str, Any] = {}
        if entry.get("output_dir") and _accepts(judge, "output_dir"):
            kwargs["output_dir"] = entry["output_dir"]
        answer = str(entry.get("answer") or "")
        try:
            verdict = judge(scenario.prompt, scenario.criteria, answer, entry.get("questions") or [], **kwargs)
            job.update_result(entry, status="passed" if verdict.get("pass") else "failed", judge=verdict)
        except Exception as exc:  # noqa: BLE001 - no account could grade: the run stays unjudged
            verdict = _basic_verdict(answer, f"AI judge unavailable: {exc}"[:500])
            spent = getattr(exc, "judge_usage", None) or {}
            if spent.get("calls"):
                verdict.update(tokens=spent["tokens"], cost_usd=round(spent["cost_usd"], 6), calls=spent["calls"])
            job.update_result(entry, status="unjudged" if verdict["verdict"] == "unjudged" else "failed",
                              judge=verdict)
        self._save(job)

    def _run(self, job: LabJob, yaml_path: Path, run_once, judge,
             tasks: Optional[List[Tuple[int, int]]] = None,
             rejudge: Optional[List[Dict[str, Any]]] = None) -> None:
        from concurrent.futures import ThreadPoolExecutor

        job.status = "running"
        try:
            if tasks is None:
                tasks = [(index, repeat) for repeat in range(job.repeats) for index in range(len(job.scenarios))]
            with ThreadPoolExecutor(max_workers=_lab_workers(), thread_name_prefix="lab") as pool:
                futures = [pool.submit(self._judge_entry, job, judge, entry) for entry in rejudge or []]
                futures += [pool.submit(self._run_task, job, yaml_path, run_once, judge, i, r) for i, r in tasks]
                for future in futures:
                    future.result()
            job.finished_at = time.time()  # before the status flips, so a "completed" job always has its end time
            job.status = "cancelled" if job.cancel_event.is_set() else "completed"
        except Exception as exc:  # noqa: BLE001
            job.error = str(exc)
            job.finished_at = time.time()
            job.status = "error"
        finally:
            job.finished_at = job.finished_at or time.time()
            self._save(job)
            try:  # housekeeping after the result is safely on disk: old product folders / job records
                if self._store_dir is not None:
                    return  # custom store (tests): the global warehouse is not ours to prune
                from agentdev.api.services import lab_outputs

                lab_outputs.auto_prune()
            except Exception:  # noqa: BLE001 - never let cleanup affect a finished job
                pass


def _accepts(func: Callable[..., Any], name: str) -> bool:
    import inspect

    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False
    return name in params or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())


def list_stored_jobs(folder: Path, workflow: str, limit: int = 20,
                     live_ids: frozenset = frozenset()) -> List[Dict[str, Any]]:
    """Summaries of stored jobs of ``workflow`` (newest first). A job still held in memory by this server
    (``live_ids``) is running, not interrupted, even though its last snapshot on disk says "running"."""
    rows: List[Dict[str, Any]] = []
    try:
        paths = list(Path(folder).glob("*.json"))
    except OSError:
        return rows
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or data.get("workflow") != workflow:
            continue
        status = data.get("status")
        if status in ("queued", "running") and data.get("id") not in live_ids:
            status = "error"  # interrupted: the server that was running it is gone
        rows.append({
            "id": data.get("id"), "status": status, "verdict": data.get("verdict"),
            "pass_rate": data.get("pass_rate"), "avg_seconds": data.get("avg_seconds"),
            "tokens": data.get("total_tokens"), "cost_usd": data.get("cost_usd"), "done": data.get("done"),
            "judge_cost_usd": data.get("judge_cost_usd"), "run_cost_usd": data.get("run_cost_usd"),
            "workflow_hash": data.get("workflow_hash", ""), "started_at": data.get("started_at") or 0,
            "finished_at": data.get("finished_at"),
        })
    rows.sort(key=lambda r: r["started_at"] or 0, reverse=True)
    return rows[:limit]


_runner = LabRunner()


def get_lab_runner() -> LabRunner:
    return _runner


GENERATE_SYSTEM = (
    "You design acceptance-test scenarios for an AI workflow (a team of agents). Reply with ONLY a JSON array, "
    "no prose and no code fence. Each item: {\"name\": short title, \"prompt\": the request a real user would send "
    "to this workflow (concrete, with the details the workflow needs), \"criteria\": 2-4 checkable pass criteria "
    "separated by semicolons (what the answer and deliverables must contain, which members should have worked, "
    "the language)}. Cover different paths of THIS workflow: the main happy path, a small/quick task, a task that "
    "needs several members, and one edge case (unclear, impossible or unverifiable request). Each run starts in an "
    "EMPTY project folder: a scenario about changing or fixing an existing app must paste the relevant code (a short "
    "file of 10-40 lines) into the prompt, otherwise there is nothing to fix. Fit the workflow's "
    "real purpose and members; never invent members it does not have."
)


def _workflow_brief(data: Dict[str, Any]) -> str:
    graph = (data or {}).get("graph") or {}
    lines = [f"Workflow: {graph.get('id', '')}", f"Description: {graph.get('description', '')}"]
    for node in graph.get("nodes") or []:
        cfg = node.get("config") or {}
        role = " ".join(str(cfg.get("role") or "").split())[:350]
        team = (cfg.get("team") or {}).get("members") or []
        lines.append(
            f"- {node.get('id')} ({node.get('type')}): {node.get('description', '')}"
            + (f" | leads: {', '.join(team)}" if team else "")
            + (f" | role: {role}" if role else "")
        )
    return "\n".join(lines)[:9000]


def generate_scenarios(yaml_path: Path, count: int = 4, language: str = "Vietnamese") -> List[Dict[str, str]]:
    """Ask a signed-in account for ``count`` test scenarios fitted to the workflow. Raises when none can answer."""
    count = max(1, min(int(count or 4), 8))
    data = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8")) or {}
    user = f"Write {count} scenarios in {language}.\n\n{_workflow_brief(data)}"
    account = JudgeAccount()
    conn, model = account.current()
    try:
        text = _judge_call(conn, model, user, GENERATE_SYSTEM)
    except Exception as exc:  # noqa: BLE001 - one retry on another account when this one is out of quota
        if not _out_of_quota(exc) or not account.switch(conn.id):
            raise
        conn, model = account.current()
        text = _judge_call(conn, model, user, GENERATE_SYSTEM)
    match = re.search(r"\[.*\]", text, re.S)
    try:
        items = json.loads(match.group(0)) if match else []
    except ValueError:
        items = []
    out: List[Dict[str, str]] = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and str(item.get("prompt") or "").strip():
            out.append({
                "name": str(item.get("name") or "").strip()[:120],
                "prompt": str(item["prompt"]).strip()[:20_000],
                "criteria": str(item.get("criteria") or "").strip()[:5_000],
            })
    if not out:
        raise RuntimeError("The AI did not return usable scenarios. Try again.")
    return out[:count]
