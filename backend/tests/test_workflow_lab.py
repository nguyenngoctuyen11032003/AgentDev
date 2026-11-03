"""Workflow Lab: static readiness check and scenario evaluation."""

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import lab as lab_route
from agentdev.api.services import skill_library, workflow_lab
from agentdev.api.services.workflow_lab import AUTO_ANSWER, LabRunner, Scenario, static_check, static_check_data
from agentdev.entity.messages import Message, MessageRole, ToolCallPayload
from agentdev.runtime.node.agent import ModelResponse, ProviderRegistry, account_fallback
from agentdev.runtime.node.executor import agent_executor as agent_executor_module

REPO = Path(__file__).resolve().parents[2]


def _agent(node_id, role="r", **extra):
    config = {"connection": "fake", "provider": "fake", "name": "m", "role": role}
    config.update(extra)
    return {"id": node_id, "type": "agent", "config": config}


def _write(tmp_path, nodes, edges=(), start=("Lead",), name="wf.yaml"):
    path = tmp_path / name
    path.write_text(yaml.safe_dump({"version": "0.4.0", "graph": {
        "id": "wf", "start": list(start), "end": list(start), "nodes": nodes, "edges": list(edges)}}), encoding="utf-8")
    return path


@pytest.fixture()
def no_skills(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    root.mkdir()
    monkeypatch.setattr(skill_library, "SKILLS_ROOT", root)
    return root


def _by_id(report):
    return {c["id"]: c for c in report["checks"]}


def test_static_check_reports_problems(tmp_path, no_skills, monkeypatch):
    monkeypatch.setenv("MAC_ALLOW_UNSAFE_CODE_EXECUTION", "0")
    nodes = [
        _agent("Lead", team={"enabled": True, "members": ["Dev", "Ghost"]}),
        _agent("Dev", role="", skills={"enabled": True, "allow": [{"name": "missing-skill"}]},
               tooling=[{"type": "function", "config": {"tools": [{"name": "run_shell_command"}]}}]),
        _agent("Orphan"),
    ]
    report = static_check(_write(tmp_path, nodes))
    checks = _by_id(report)
    assert report["status"] == "fail"
    assert checks["team"]["status"] == "fail" and "Ghost" in checks["team"]["detail"]
    assert checks["roles"]["nodes"] == ["Dev"]
    assert checks["skills"]["status"] == "warn"
    assert checks["code_execution"]["status"] == "warn" and checks["code_execution"]["nodes"] == ["Dev"]
    assert checks["unreachable"]["nodes"] == ["Orphan"]


def test_static_check_template_passes_structure(no_skills):
    report = static_check(REPO / "workspace" / "workflows" / "software_company.yaml")
    checks = _by_id(report)
    assert checks["structure"]["status"] == "pass"
    assert checks["team"]["status"] == "pass"
    # Members (leads excluded) feed the Lab's sample scenarios.
    assert "QA Tester" in checks["team"]["members"] and "CTO" not in checks["team"]["members"]
    assert checks["unreachable"]["status"] == "pass"


@pytest.mark.parametrize("name", ["software_company.yaml", "demo_loop_counter.yaml"])
def test_static_check_data_matches_file_check(tmp_path, no_skills, name):
    path = tmp_path / name
    path.write_text((REPO / "workspace" / "workflows" / name).read_text(encoding="utf-8"), encoding="utf-8")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert static_check_data(data) == static_check(path)


def test_static_check_data_rejects_non_mapping():
    report = static_check_data(["x"])
    assert report["status"] == "fail"
    assert _by_id(report)["structure"]["status"] == "fail"


def test_runner_aggregates_and_verdict():
    answers = iter(["ok", "ok", "bad", "ok"])

    def run_once(path, scenario, cancel):
        return {"answer": next(answers), "tokens": 10, "cost_usd": 0.01, "questions": []}

    def judge(prompt, criteria, answer, questions):
        return {"pass": answer == "ok", "score": 9, "reason": ""}

    runner = LabRunner()
    job = runner.start(Path("x.yaml"), "x.yaml", [Scenario("a", "c"), Scenario("b", "c")], 2,
                       run_once=run_once, judge=judge)
    for _ in range(100):
        if job.status not in ("queued", "running"):
            break
        time.sleep(0.02)
    data = job.to_dict()
    assert data["status"] == "completed" and data["done"] == 4 and data["passed"] == 3
    assert data["pass_rate"] == 0.75 and data["verdict"] == "not_ready"
    scenario_a, scenario_b = data["scenarios"]
    assert scenario_a["runs"] == 2 and scenario_a["stable"] is False and scenario_b["stable"] is True
    assert data["total_tokens"] == 40


def test_basic_verdict_fallback():
    assert workflow_lab._basic_verdict("answer") == {"pass": True, "score": 10, "reason": "", "judged_by": "basic"}
    assert workflow_lab._basic_verdict("Error calling model x")["pass"] is False


class LeadProvider:
    calls = []

    def __init__(self, config):
        self.config = config

    def create_client(self):
        return None

    def call_model(self, client, conversation, timeline, tool_specs=None, **kwargs):
        LeadProvider.calls.append([m.text_content() for m in conversation])
        if len(LeadProvider.calls) == 1:
            call = ToolCallPayload(id="c1", function_name="ask_user", arguments=json.dumps({"question": "Duyệt kế hoạch?"}))
            return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content="", tool_calls=[call]))
        return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content="Xong"))

    def extract_token_usage(self, response):
        return None


def test_run_once_answers_questions_automatically(tmp_path, monkeypatch):
    creds = SimpleNamespace(provider="fake", vendor="fake", token="", base_url="")
    monkeypatch.setattr(agent_executor_module, "resolve_connection", lambda _id: creds)
    monkeypatch.setattr(ProviderRegistry, "get_provider", lambda _name: LeadProvider)
    LeadProvider.calls = []
    path = _write(tmp_path, [_agent("Lead", team={"enabled": True}), _agent("Dev")])
    result = workflow_lab._run_once(path, Scenario("Làm web"), workflow_lab.threading.Event())
    assert result["answer"] == "Xong"
    assert result["questions"] == [{"node": "Lead", "question": "Duyệt kế hoạch?"}]
    assert any(AUTO_ANSWER in text for text in LeadProvider.calls[1])


def test_api_check_and_validation(tmp_path, no_skills, monkeypatch):
    path = _write(tmp_path, [_agent("Lead")], name="mine.yaml")
    monkeypatch.setattr(lab_route, "_resolve_yaml_path", lambda name: tmp_path / name)
    app = FastAPI()
    app.include_router(lab_route.router)
    client = TestClient(app)
    res = client.post("/api/lab/check", json={"yaml_file": "mine"})
    assert res.status_code == 200 and res.json()["workflow"] == "mine.yaml"
    assert client.post("/api/lab/check", json={"yaml_file": "../x"}).status_code == 400
    assert client.post("/api/lab/check", json={"yaml_file": "nope"}).status_code == 404
    assert client.post("/api/lab/evaluate", json={"yaml_file": "mine", "scenarios": []}).status_code == 400
    assert client.get("/api/lab/jobs/unknown").status_code == 404


def test_to_dict_returns_snapshot_while_worker_updates():
    """The worker mutates result entries while requests serialise the job: to_dict must copy under a lock."""
    def run_once(path, scenario, cancel):
        return {"answer": "ok", "tokens": 1, "questions": [], **{f"k{i}": i for i in range(200)}}

    def judge(prompt, criteria, answer, questions):
        return {"pass": True}

    job = LabRunner().start(Path("x.yaml"), "x.yaml", [Scenario(str(i), "c") for i in range(20)], 5,
                            run_once=run_once, judge=judge)
    for _ in range(2000):
        data = job.to_dict()  # must never raise "dictionary changed size during iteration"
        if data["status"] not in ("queued", "running"):
            break
    deadline = time.monotonic() + 30  # each result is also persisted to disk, so allow real time
    while job.status in ("queued", "running") and time.monotonic() < deadline:
        time.sleep(0.02)
    data = job.to_dict()
    assert data["status"] == "completed" and data["done"] == 100
    data["results"][0]["status"] = "tampered"
    assert job.results[0]["status"] == "passed"


def _conn(conn_id, vendor, auth_type="cli"):
    from agentdev.connections.store import Connection

    return Connection(id=conn_id, vendor=vendor, label=conn_id, auth_type=auth_type)


@pytest.fixture()
def judge_env(monkeypatch):
    from agentdev.connections import store as store_module

    conns = [_conn("key", "anthropic", "api_key"), _conn("claude", "anthropic"), _conn("codex", "openai")]
    fake_store = SimpleNamespace(list=lambda: list(conns), default_connection=lambda: conns[0])
    monkeypatch.setattr(store_module, "get_store", lambda: fake_store)
    monkeypatch.setattr(account_fallback, "get_store", lambda: fake_store)
    model_calls = []

    def default_model_for(conn):
        model_calls.append(conn.id)
        return f"{conn.id}-model"

    monkeypatch.setattr(account_fallback, "default_model_for", default_model_for)
    calls = []
    monkeypatch.setattr(workflow_lab, "_judge_call", lambda conn, model, user: (calls.append((conn.id, model)), "")[1])
    return SimpleNamespace(conns=conns, store=fake_store, model_calls=model_calls, calls=calls, monkeypatch=monkeypatch)


def test_judge_account_resolved_once_and_skips_api_key_default(judge_env):
    judge_env.monkeypatch.setattr(workflow_lab, "_judge_call", lambda conn, model, user: (
        judge_env.calls.append((conn.id, model)), '{"pass": true, "score": 9, "reason": "ok"}')[1])
    account = workflow_lab.JudgeAccount()
    for _ in range(3):
        verdict = workflow_lab._judge("p", "criteria", "answer", [], account=account)
        assert verdict["pass"] is True and verdict["judged_by"] == "ai"
        assert verdict["judge_model"] == "claude (claude-model)"
    assert judge_env.calls == [("claude", "claude-model")] * 3
    assert judge_env.model_calls == ["claude"]  # model detection runs once per job


def test_judge_prefers_signed_in_default(judge_env):
    judge_env.store.default_connection = lambda: judge_env.conns[2]
    workflow_lab._judge("p", "criteria", "answer", [], account=workflow_lab.JudgeAccount())
    assert judge_env.calls == [("codex", "codex-model")]


def test_judge_switches_account_on_quota_error(judge_env):
    def judge_call(conn, model, user):
        judge_env.calls.append(conn.id)
        if conn.id == "claude":
            raise account_fallback.QuotaExceededError("You've hit your usage limit")
        return '{"pass": false, "reason": "missing"}'

    judge_env.monkeypatch.setattr(workflow_lab, "_judge_call", judge_call)
    account = workflow_lab.JudgeAccount()
    first = workflow_lab._judge("p", "criteria", "answer", [], account=account)
    second = workflow_lab._judge("p", "criteria", "answer", [], account=account)
    assert first["pass"] is False and first["judge_model"] == "codex (codex-model)"
    assert second["judge_model"] == "codex (codex-model)"
    assert judge_env.calls == ["claude", "codex", "codex"]
    assert account.exhausted == {"claude"}
    assert judge_env.model_calls == ["claude", "codex"]


def test_judge_raises_when_no_fallback_left(judge_env):
    judge_env.conns[:] = [_conn("claude", "anthropic")]

    def judge_call(conn, model, user):
        raise account_fallback.QuotaExceededError("rate limit exceeded")

    judge_env.monkeypatch.setattr(workflow_lab, "_judge_call", judge_call)
    with pytest.raises(account_fallback.QuotaExceededError, match="rate limit"):
        workflow_lab._judge("p", "criteria", "answer", [], account=workflow_lab.JudgeAccount())


def test_judge_without_signed_in_account(judge_env):
    judge_env.conns[:] = [_conn("key", "anthropic", "api_key")]
    with pytest.raises(RuntimeError, match="No signed-in account"):
        workflow_lab._judge("p", "criteria", "answer", [], account=workflow_lab.JudgeAccount())


@pytest.fixture(autouse=True)
def _lab_store(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow_lab, "_lab_dir", lambda: tmp_path / "lab_jobs")
    return tmp_path / "lab_jobs"


def test_jobs_survive_a_server_restart(_lab_store):
    def run_once(path, scenario, cancel):
        return {"answer": "ok", "tokens": 5, "questions": []}

    job = LabRunner().start(Path("x.yaml"), "x.yaml", [Scenario("a", "c")], 1,
                            run_once=run_once, judge=lambda *a: {"pass": True})
    for _ in range(200):
        if job.status == "completed":
            break
        time.sleep(0.02)
    time.sleep(0.05)
    restored = LabRunner().get(job.id).to_dict()  # a fresh runner = the server after a reload
    assert restored["status"] == "completed" and restored["verdict"] == "ready" and restored["passed"] == 1


def test_running_job_is_reported_as_interrupted_after_restart(_lab_store):
    _lab_store.mkdir(parents=True, exist_ok=True)
    (_lab_store / "abcdef123456.json").write_text(json.dumps({
        "id": "abcdef123456", "status": "running", "results": [{"scenario": 0, "status": "running"}]}), encoding="utf-8")
    data = LabRunner().get("abcdef123456").to_dict()
    assert data["status"] == "error" and "interrupted" in data["error"]
    assert data["results"][0]["status"] == "error"
    assert LabRunner().get("../../etc") is None
