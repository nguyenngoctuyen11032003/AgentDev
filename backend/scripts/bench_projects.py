"""Project benchmark: can a workflow change a medium repo correctly, and at what cost?

    cd backend
    uv run python -m scripts.bench_projects --fake                      # free: harness + failure detection check
    uv run python -m scripts.bench_projects --fake --tasks a,b --out docs/audit/
    uv run python -m scripts.bench_projects --real --workflow bugfix_team --tasks a,b,c --max-usd 5 --max-runs 3

A fixture repo (~1,600 files, git-initialised, see ``bench_repo_gen``) is generated in a temp folder for every
run and the workflow is started with that folder as its project workspace. Three standard tasks, each judged by
the harness itself (never by the model):
  a  fix a bug that has a red test          acceptance: hidden clamp test + whole suite green, no test removed
  b  add ``truncate_words`` + a test        acceptance: hidden behaviour test + whole suite green
  c  rename ``normalize_value`` (14+ files) acceptance: old name gone (grep), new name in every user file,
                                            suite green, probe outputs identical to before

Per run: success (acceptance AND suite green), wall time, model calls, tokens, cost_usd (+ cost_known), files
changed outside the task's allowed list, corrupted files (BOM / CRLF introduced, syntax errors), final test status.

``--fake``: a fake provider performs scripted edits that solve each task, and (default) one scripted failure mode
per task, so the failure detection is itself exercised. No model, no network, no cost.
``--real``: logged-in CLI accounts only. Cheapest Claude model unless ``--model``. Hard caps ``--max-usd`` (5) and
``--max-runs`` (3): refused up front when the plan needs more runs, no new run starts once the spent total reaches
the cap, and the engine's own ``run_limits.max_cost_usd`` is set on every run. A workflow with any ``paid: true``
node is refused; a gate that asks a person is auto-answered only when it is not paid (paid gates are skipped).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

import yaml

from scripts.bench_repo_gen import build_repo, git, list_files

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "docs" / "audit"
WORKFLOW_DIR = REPO_ROOT / "workspace" / "workflows"
REAL_MODEL = "claude-haiku-5-5"
FAKE_MODEL = "fake-model"
BOM = b"\xef\xbb\xbf"
OLD_NAME, NEW_NAME = "normalize_value", "normalize_number"
PYTEST_TIMEOUT_S = 120

TASK_PROMPTS = {
    "a": ("The test tests/test_core_mathx.py::test_clamp_above fails. Find the root cause in the project and fix "
          "the bug with the smallest change. Do not edit or delete tests."),
    "b": ("Add a function truncate_words(text, n, suffix='...') to pkg/core/text.py: it returns text unchanged when "
          "it has at most n words, otherwise the first n words joined by single spaces followed by suffix. Add a "
          "test for it in tests/test_core_text.py. Touch no other file."),
    "c": (f"Rename the function {OLD_NAME} to {NEW_NAME} everywhere in the project (definition, imports, calls, "
          "tests). No behaviour change. Do not leave the old name anywhere."),
}

# Hidden acceptance tests: written outside the repo by the harness, never shown to the model.
HIDDEN_A = '''from pkg.core.mathx import clamp


def test_hidden_clamp():
    assert clamp(15, 0, 10) == 10
    assert clamp(10, 0, 10) == 10
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(0.5, 0, 1) == 0.5
'''
HIDDEN_B = '''from pkg.core.text import truncate_words


def test_hidden_truncate_words():
    assert truncate_words("one two three", 5) == "one two three"
    assert truncate_words("one two three", 3) == "one two three"
    assert truncate_words("one  two three four", 2) == "one two..."
    assert truncate_words("a b c d", 1, suffix="~") == "a~"
    assert truncate_words("", 3) == ""
'''
PROBE = f'''
import json, importlib
mod = importlib.import_module("pkg.core.norm")
fn = getattr(mod, "{NEW_NAME}", None) or getattr(mod, "{OLD_NAME}")
out = {{"norm": [fn(v) for v in (1, "2.345", " 7 ", 3.14159, -0.005)]}}
import pathlib
for p in sorted(pathlib.Path("pkg").glob("sub*/m*.py")):
    if "normalize_" in p.read_text(encoding="utf-8"):
        m = importlib.import_module(".".join(p.with_suffix("").parts))
        out[p.as_posix()] = [m.clean(v) for v in (1, "2.5", " 9.999 ")]
print(json.dumps(out, sort_keys=True))
'''


# --------------------------------------------------------------------------- scripted edits (fake model)


def _read(repo: Path, rel: str) -> str:
    return (repo / rel).read_bytes().decode("utf-8")


def _put(repo: Path, rel: str, text: str) -> None:
    (repo / rel).write_bytes(text.encode("utf-8"))


def solve_a(repo: Path, mode: str) -> None:
    src = _read(repo, "pkg/core/mathx.py")
    if mode == "good":
        _put(repo, "pkg/core/mathx.py", src.replace("hi - 1", "hi"))
    else:  # wrong_fix: the red test stays red
        _put(repo, "pkg/core/mathx.py", src.replace("return hi - 1", "return value"))


def solve_b(repo: Path, mode: str) -> None:
    func = ('\n\ndef truncate_words(text, n, suffix="..."):\n    words = text.split()\n    if len(words) <= n:\n'
            '        return text\n    return " ".join(words[:n]) + suffix\n')
    _put(repo, "pkg/core/text.py", _read(repo, "pkg/core/text.py") + func)
    test = ('from pkg.core.text import truncate_words\n\n\ndef test_truncate_words():\n'
            '    assert truncate_words("a b c", 2) == "a b..."\n')
    if mode == "good":
        _put(repo, "tests/test_core_text.py", _read(repo, "tests/test_core_text.py") + "\n\n" + test)
        return
    # damage: BOM + CRLF in an unrelated module (still valid python), a syntax error in another one
    _put(repo, "tests/test_core_text.py", _read(repo, "tests/test_core_text.py") + "\n\n" + test)
    raw = _read(repo, "pkg/sub01/m01.py").replace("\n", "\r\n")
    (repo / "pkg/sub01/m01.py").write_bytes(BOM + raw.encode("utf-8"))
    _put(repo, "pkg/sub01/m00.py", _read(repo, "pkg/sub01/m00.py") + "\ndef broken(:\n    pass\n")


def solve_c(repo: Path, mode: str) -> None:
    files = [p for p in list_files(repo) if p.endswith(".py") and OLD_NAME in _read(repo, p)]
    if mode == "partial_rename":
        files = files[:-1]  # forgets one file: old name stays, import breaks
    for rel in files:
        _put(repo, rel, _read(repo, rel).replace(OLD_NAME, NEW_NAME))


SOLVERS: Dict[str, Callable[[Path, str], None]] = {"a": solve_a, "b": solve_b, "c": solve_c}
FAIL_MODE = {"a": "wrong_fix", "b": "damage", "c": "partial_rename"}
ALLOWED_STATIC = {
    "a": ["pkg/core/mathx.py", "tests/test_core_mathx.py"],
    "b": ["pkg/core/text.py", "pkg/core/__init__.py", "tests/test_core_text.py"],
    "c": [],  # the files that contain the old name (computed per repo)
}


class FakeState:
    task: Optional[str] = None
    mode: str = "good"
    repo: Optional[Path] = None
    applied = False
    calls = 0


def make_fake_provider():
    from agentdev.entity.messages import Message, MessageRole
    from agentdev.runtime.node.agent import ModelResponse
    from agentdev.runtime.node.agent.providers._cli_common import record_token_usage
    from agentdev.utils.token_tracker import TokenUsage

    class FakeProvider:
        def __init__(self, config):
            self.config = config
            self.model_name = str(config.name)

        def create_client(self):
            return None

        def call_model(self, client, conversation, timeline, tool_specs=None, **kwargs):
            FakeState.calls += 1
            if not FakeState.applied and FakeState.task and FakeState.repo is not None:
                FakeState.applied = True  # the scripted "model" edits the project once, on its first call
                SOLVERS[FakeState.task](FakeState.repo, FakeState.mode)
            chars = sum(len(m.text_content()) for m in conversation)
            answer = f"[{self.config.node_id}] scripted edit applied ({FakeState.mode})."
            record_token_usage(self, {"usage": {"input_tokens": (chars + 3) // 4,
                                                "output_tokens": (len(answer) + 3) // 4}}, "fake")
            return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content=answer))

        def extract_token_usage(self, response):
            usage = response.get("usage") or {}
            inp, out = int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
            return TokenUsage(input_tokens=inp, output_tokens=out, total_tokens=inp + out,
                              metadata={"estimated": True, "total_cost_usd": None})

    return FakeProvider


def _auto_answer_request():
    """Replacement for ``HumanPromptService.request``: approves, except a paid gate which is always skipped."""
    from agentdev.utils.human_prompt import AutoAnswerChannel, PromptResult

    channel = AutoAnswerChannel()

    def request(self, node_id, task_description, *, inputs=None, metadata=None):
        result = channel.request(node_id=node_id, task=task_description, inputs=inputs, metadata=metadata)
        return result if isinstance(result, PromptResult) else PromptResult(text=str(result))

    return request


def install_fake() -> Callable[[], None]:
    """Patch the engine for a free fake run and return a callable that undoes every patch."""
    from agentdev.runtime.node.agent import ProviderRegistry
    from agentdev.runtime.node.executor import agent_executor as module
    from agentdev.utils.human_prompt import HumanPromptService

    orig_resolve = module.resolve_connection
    orig_get = ProviderRegistry.__dict__["get_provider"]
    orig_request = HumanPromptService.__dict__["request"]
    provider = make_fake_provider()
    creds = SimpleNamespace(provider="fake", vendor="fake", token="", base_url="")
    module.resolve_connection = lambda _id: creds
    ProviderRegistry.get_provider = staticmethod(lambda _name: provider)
    HumanPromptService.request = _auto_answer_request()

    def restore() -> None:
        module.resolve_connection = orig_resolve
        ProviderRegistry.get_provider = orig_get
        HumanPromptService.request = orig_request

    return restore


class RealCounter:
    calls = 0


def install_real_counting() -> Callable[[], None]:
    """Real providers, unchanged, plus a count of model calls and non-interactive non-paid gate answers."""
    from agentdev.runtime.node.agent import ProviderRegistry
    from agentdev.utils.human_prompt import HumanPromptService

    orig_get = ProviderRegistry.__dict__["get_provider"]
    orig_request = HumanPromptService.__dict__["request"]
    original = ProviderRegistry.get_provider
    cache: Dict[str, Any] = {}

    def counting(real_cls):
        class Counting(real_cls):  # type: ignore[misc, valid-type]
            def call_model(self, *args, **kwargs):
                RealCounter.calls += 1
                return super().call_model(*args, **kwargs)

        return Counting

    def get(name):
        cls = original(name)
        if cls is None:
            return None
        return cache.setdefault(name, counting(cls))

    ProviderRegistry.get_provider = staticmethod(get)
    HumanPromptService.request = _auto_answer_request()

    def restore() -> None:
        ProviderRegistry.get_provider = orig_get
        HumanPromptService.request = orig_request

    return restore


# --------------------------------------------------------------------------- checks (the harness is the judge)


def run_pytest(repo: Path, *extra: str, cwd: Optional[Path] = None) -> Dict[str, Any]:
    env = {**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(repo)}
    env.pop("PYTEST_ADDOPTS", None)
    try:
        proc = subprocess.run([sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", *extra],
                              cwd=cwd or repo, env=env, capture_output=True, text=True, timeout=PYTEST_TIMEOUT_S)
        out, code = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "passed": 0, "failed": 0, "errors": 0, "total": 0, "returncode": None}
    num = lambda word: int((re.search(rf"(\d+) {word}", out.splitlines()[-1] if out.strip() else "") or [0, 0])[1])  # noqa: E731
    passed, failed, errors = num("passed"), num("failed"), num("error")
    status = "green" if code == 0 and passed > 0 else ("red" if failed or errors or code == 1 else "error")
    return {"status": status, "passed": passed, "failed": failed, "errors": errors,
            "total": passed + failed + errors, "returncode": code, "tail": out.strip().splitlines()[-1:] }


def changed_files(repo: Path) -> Dict[str, str]:
    """Path -> 'M' / 'A' / 'D' against the baseline commit (ignored files such as __pycache__ do not show)."""
    out = git(repo, "status", "--porcelain", "-uall", "-z").stdout.decode("utf-8", "replace")
    result: Dict[str, str] = {}
    for entry in filter(None, out.split("\0")):
        code, path = entry[:2], entry[3:]
        result[path] = "D" if "D" in code else ("A" if "?" in code or "A" in code else "M")
    return result


def corrupted_files(repo: Path, changes: Dict[str, str]) -> List[Dict[str, str]]:
    """BOM / CRLF introduced into a file, and python files that no longer compile."""
    bad: List[Dict[str, str]] = []
    for path, kind in sorted(changes.items()):
        if kind == "D" or not (repo / path).is_file():
            continue
        data = (repo / path).read_bytes()
        before = git(repo, "show", f"HEAD:{path}", check=False)
        orig = before.stdout if before.returncode == 0 else None
        if data.startswith(BOM) and not (orig or b"").startswith(BOM):
            bad.append({"path": path, "problem": "bom_added"})
        if b"\r\n" in data and (orig is None or b"\r\n" not in orig):
            bad.append({"path": path, "problem": "crlf_added"})
    for path in list_files(repo):
        if path.endswith(".py"):
            try:
                compile((repo / path).read_bytes(), path, "exec")
            except (SyntaxError, ValueError) as exc:
                bad.append({"path": path, "problem": f"syntax_error: {str(exc)[:80]}"})
    return bad


def outside_scope(changes: Dict[str, str], allowed: List[str]) -> List[str]:
    return sorted(p for p in changes if p not in set(allowed))


def _hidden_check(repo: Path, scratch: Path, name: str, source: str) -> bool:
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / name).write_text(source, encoding="utf-8")
    return run_pytest(repo, "--rootdir", str(scratch), str(scratch / name))["status"] == "green"


def _probe(repo: Path) -> Optional[str]:
    env = {**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(repo)}
    proc = subprocess.run([sys.executable, "-B", "-c", PROBE], cwd=repo, env=env, capture_output=True, text=True,
                          timeout=PYTEST_TIMEOUT_S)
    return proc.stdout.strip() if proc.returncode == 0 else None


def _files_with(repo: Path, needle: str) -> List[str]:
    hits = []
    for rel in list_files(repo):
        try:
            if needle in (repo / rel).read_bytes().decode("utf-8", "ignore"):
                hits.append(rel)
        except OSError:
            continue
    return hits


def acceptance(task: str, repo: Path, scratch: Path, before: Dict[str, Any], tests: Dict[str, Any]) -> Dict[str, Any]:
    """Objective, harness-run acceptance check. Returns ``{"passed": bool, "checks": {...}}``."""
    checks: Dict[str, bool] = {}
    if task == "a":
        checks["hidden_clamp_test"] = _hidden_check(repo, scratch, "test_hidden_a.py", HIDDEN_A)
        checks["no_test_removed"] = tests["total"] >= before["tests"]["total"]
    elif task == "b":
        checks["hidden_feature_test"] = _hidden_check(repo, scratch, "test_hidden_b.py", HIDDEN_B)
        checks["no_test_removed"] = tests["total"] >= before["tests"]["total"]
    elif task == "c":
        old_hits = _files_with(repo, OLD_NAME)
        new_hits = _files_with(repo, NEW_NAME)
        checks["old_name_gone"] = not old_hits
        checks["new_name_in_all_user_files"] = set(before["old_name_files"]) <= set(new_hits)
        probe = _probe(repo)
        checks["behaviour_unchanged"] = probe is not None and probe == before["probe"]
        checks["no_test_removed"] = tests["total"] >= before["tests"]["total"]
        if old_hits:
            checks["old_name_left_in"] = False
    return {"passed": all(v for k, v in checks.items() if k != "old_name_left_in") and bool(checks), "checks": checks}


# --------------------------------------------------------------------------- workflows


def resolve_workflow(value: str) -> Path:
    path = Path(value)
    for cand in (path, WORKFLOW_DIR / value, WORKFLOW_DIR / f"{value}.yaml"):
        if cand.is_file():
            return cand.resolve()
    raise SystemExit(f"workflow not found: {value} (looked in {WORKFLOW_DIR})")


def _paid_paths(node: Any, trail: str = "") -> List[str]:
    found: List[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "paid" and value:
                found.append(trail or "<root>")
            found += _paid_paths(value, f"{trail}/{key}" if trail else str(key))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found += _paid_paths(value, f"{trail}[{i}]")
    return found


def assert_no_paid(definition: Dict[str, Any], name: str) -> None:
    """Real mode never runs a paid step: a workflow with any ``paid: true`` node is refused (no reachability guess)."""
    paid = _paid_paths(definition)
    if paid:
        raise SystemExit(f"refused: workflow '{name}' has paid gate(s) ({', '.join(paid[:4])}); "
                         "the project benchmark never runs paid steps")


def prepare_definition(path: Path, mode: str, model: str, max_usd: Optional[float]) -> Dict[str, Any]:
    definition = yaml.safe_load(path.read_text(encoding="utf-8"))
    graph = definition["graph"]
    for node in graph.get("nodes", []):
        if node.get("type") != "agent":
            continue
        cfg = node.setdefault("config", {})
        if mode == "fake":
            cfg.update({"connection": "fake", "provider": "fake", "name": FAKE_MODEL})
        elif model:
            cfg["name"] = model
    graph["log_level"] = "WARNING"
    if max_usd:
        limits = dict(graph.get("run_limits") or {})
        limits["max_cost_usd"] = min(float(limits.get("max_cost_usd") or max_usd), max_usd)
        graph["run_limits"] = limits
    return definition


class _SummaryCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.rows: List[Dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.rows.append(json.loads(record.getMessage()))
        except (ValueError, TypeError):
            pass


def execute(yaml_path: Path, prompt: str, workspace: Path, session: str, timeout_s: float) -> Dict[str, Any]:
    """The same steps as ``run_workflow`` but with the project folder opened in place as the workspace."""
    import agentdev.runtime.sdk as sdk
    from agentdev.entity.graph_config import GraphConfig
    from agentdev.runtime.bootstrap.schema import ensure_schema_registry_populated
    from agentdev.validation.check import load_config
    from agentdev.workflow.graph import GraphExecutor
    from agentdev.workflow.graph_context import GraphContext

    ensure_schema_registry_populated()
    handler = _SummaryCapture()
    summary_logger = logging.getLogger("agentdev.run_summary")
    old_level = summary_logger.level
    summary_logger.setLevel(logging.INFO)
    summary_logger.addHandler(handler)
    cancel = threading.Event()
    timer = threading.Timer(timeout_s, cancel.set)
    timer.daemon = True
    error = None
    usage: Dict[str, Any] = {}
    started = time.perf_counter()
    try:
        timer.start()
        with contextlib.redirect_stdout(sys.stderr):  # load_config prints 'Workflow OK.'
            design = load_config(yaml_path)
        config = GraphConfig.from_definition(design.graph, name=session, output_root=sdk.OUTPUT_ROOT,
                                             source_path=str(yaml_path), vars=design.vars)
        executor = GraphExecutor(GraphContext(config=config), workspace_root=workspace, cancel_event=cancel)
        try:
            executor._execute(prompt)
        finally:
            if executor.token_tracker:
                usage = executor.token_tracker.get_token_usage() or {}
    except Exception as exc:  # noqa: BLE001 - the benchmark reports how the run ended
        error = f"{type(exc).__name__}: {str(exc)[:160]}"
    finally:
        timer.cancel()
        summary_logger.removeHandler(handler)
        summary_logger.setLevel(old_level)
    if cancel.is_set() and not error:
        error = f"timeout after {timeout_s:.0f}s"
    return {"error": error, "wall_s": round(time.perf_counter() - started, 2), "usage": usage, "turns": handler.rows}


# --------------------------------------------------------------------------- one run


def run_one(task: str, mode: str, failure: Optional[str], yaml_path: Path, tmp: Path, seed: int,
            model: str, remaining_usd: Optional[float], timeout_s: float, label: str,
            small: bool = False) -> Dict[str, Any]:
    repo = tmp / f"repo_{label}"
    scale = {"subpackages": 6, "docs": 20} if small else {}  # small: unit tests only
    info = build_repo(repo, seed=seed, bug=(task == "a"), **scale)
    before: Dict[str, Any] = {"tests": run_pytest(repo)}
    expected = "red" if task == "a" else "green"
    if before["tests"]["status"] != expected:
        raise SystemExit(f"fixture check failed for task {task}: baseline tests are "
                         f"{before['tests']['status']}, expected {expected}")
    allowed = list(ALLOWED_STATIC[task])
    if task == "c":
        before["old_name_files"] = _files_with(repo, OLD_NAME)
        before["probe"] = _probe(repo)
        allowed = list(before["old_name_files"])

    definition = prepare_definition(yaml_path, mode, model, remaining_usd if mode == "real" else None)
    run_yaml = tmp / f"run_{label}.yaml"
    run_yaml.write_text(yaml.safe_dump(definition, allow_unicode=True), encoding="utf-8")

    FakeState.task, FakeState.mode, FakeState.repo, FakeState.applied, FakeState.calls = (
        task, failure or "good", repo, False, 0)
    RealCounter.calls = 0
    result = execute(run_yaml, TASK_PROMPTS[task], repo, f"benchproj_{label}", timeout_s)
    FakeState.task = FakeState.repo = None

    changes = changed_files(repo)
    corrupted = corrupted_files(repo, changes)
    tests = run_pytest(repo)
    accept = acceptance(task, repo, tmp / f"hidden_{label}", before, tests)
    turns = result["turns"]
    summary = (result["usage"] or {}).get("summary") or {}
    cost = round(sum(float(t.get("cost_usd") or 0) for t in turns), 6)
    cost_known = all(bool(t.get("cost_known", True)) for t in turns)
    out_scope = outside_scope(changes, allowed)
    return {
        "task": task,
        "label": label,
        "failure_mode": failure,
        "success": bool(accept["passed"] and tests["status"] == "green"),
        "clean": not out_scope and not corrupted,
        "acceptance": accept,
        "wall_s": result["wall_s"],
        "model_calls": FakeState.calls if mode == "fake" else RealCounter.calls,
        "agent_turns": len(turns),
        "tokens_in": sum(int(t.get("tokens_in") or 0) for t in turns),
        "tokens_out": sum(int(t.get("tokens_out") or 0) for t in turns),
        "cache_read": sum(int(t.get("cache_read") or 0) for t in turns),
        "total_tokens": (result["usage"].get("total_usage") or {}).get("total_tokens"),
        "cost_usd": cost if turns else float(summary.get("cost_usd") or 0.0),
        "cost_known": cost_known,
        "files_changed": sorted(changes),
        "files_outside_scope": out_scope,
        "corrupted_files": corrupted,
        "tests_before": before["tests"]["status"],
        "tests_after": tests["status"],
        "tests_after_counts": {k: tests[k] for k in ("passed", "failed", "errors")},
        "repo_files": info["file_count"],
        "engine_error": result["error"],
    }


# --------------------------------------------------------------------------- plan and report


def plan_runs(tasks: List[str], mode: str, with_failures: bool) -> List[Dict[str, Any]]:
    plan = []
    for task in tasks:
        plan.append({"task": task, "failure": None, "label": f"{task}_ok"})
        if mode == "fake" and with_failures:
            plan.append({"task": task, "failure": FAIL_MODE[task], "label": f"{task}_{FAIL_MODE[task]}"})
    return plan


def run_all(mode: str, workflow: str, tasks: List[str], *, max_usd: float = 5.0, max_runs: int = 3,
            model: Optional[str] = None, seed: int = 1234, failures: bool = True,
            timeout_s: float = 900.0, small: bool = False) -> Dict[str, Any]:
    unknown = [t for t in tasks if t not in TASK_PROMPTS]
    if unknown:
        raise SystemExit(f"unknown task(s): {', '.join(unknown)}; choose from a, b, c")
    yaml_path = resolve_workflow(workflow)
    plan = plan_runs(tasks, mode, failures)
    chosen_model = (model or REAL_MODEL) if mode == "real" else FAKE_MODEL
    if mode == "real":
        assert_no_paid(yaml.safe_load(yaml_path.read_text(encoding="utf-8")), yaml_path.stem)
        if len(plan) > max_runs:
            raise SystemExit(f"refused: the plan needs {len(plan)} runs but --max-runs is {max_runs}. "
                             "Pick fewer tasks with --tasks, or raise --max-runs on purpose.")
    runs: List[Dict[str, Any]] = []
    spent = 0.0
    stopped = None
    with tempfile.TemporaryDirectory(prefix="agentdev-bench-projects-") as tmp_name:
        import agentdev.runtime.sdk as sdk

        tmp = Path(tmp_name)
        orig_root = sdk.OUTPUT_ROOT
        sdk.OUTPUT_ROOT = tmp / "out"  # keep benchmark output out of the real warehouse
        restore = install_fake() if mode == "fake" else install_real_counting()
        try:
            for item in plan:
                if mode == "real" and spent >= max_usd:
                    stopped = f"stopped before {item['label']}: spent ${spent:.4f} reached --max-usd {max_usd}"
                    break
                run = run_one(item["task"], mode, item["failure"], yaml_path, tmp, seed, chosen_model,
                              max_usd - spent if mode == "real" else None, timeout_s, item["label"], small)
                spent += run["cost_usd"]
                runs.append(run)
        finally:
            restore()
            sdk.OUTPUT_ROOT = orig_root
    unknown_cost = [r["label"] for r in runs if not r["cost_known"]]
    return {
        "mode": mode,
        "workflow": yaml_path.stem,
        "model": chosen_model,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "limits": {"max_runs": max_runs, "max_usd": max_usd, "planned_runs": len(plan)},
        "runs": runs,
        "stopped": stopped,
        "total_cost_usd": round(spent, 4),
        "cost_note": (f"cost unknown for: {', '.join(unknown_cost)} (cost_usd is a lower bound)"
                      if unknown_cost and mode == "real" else None),
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [f"# Project benchmark ({report['mode']})", "",
             f"- workflow: `{report['workflow']}`; model: `{report['model']}`; generated: {report['generated_at']}",
             f"- total cost: ${report['total_cost_usd']}" + (f" ({report['cost_note']})" if report["cost_note"] else "")]
    if report["stopped"]:
        lines.append(f"- {report['stopped']}")
    lines += ["", "| run | ok | clean | sec | calls | tokens in/out | cost $ (known) | outside scope | corrupted | tests |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for r in report["runs"]:
        lines.append(
            f"| {r['label']} | {r['success']} | {r['clean']} | {r['wall_s']} | {r['model_calls']} | "
            f"{r['tokens_in']}/{r['tokens_out']} | {r['cost_usd']} ({r['cost_known']}) | "
            f"{', '.join(r['files_outside_scope']) or '-'} | "
            f"{', '.join(c['path'] + ':' + c['problem'].split(':')[0] for c in r['corrupted_files']) or '-'} | "
            f"{r['tests_before']} -> {r['tests_after']} |")
        if r["engine_error"]:
            lines.append(f"| {r['label']} | ERROR | {r['engine_error']} |")
    lines += ["", "Acceptance checks:", ""]
    lines += [f"- {r['label']}: {json.dumps(r['acceptance']['checks'])}" for r in report["runs"]]
    return "\n".join(lines) + "\n"


def write_outputs(report: Dict[str, Any], out_dir: Path) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    paths = [out_dir / f"bench-projects-{stamp}.json", out_dir / f"bench-projects-{stamp}.md"]
    paths[0].write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    paths[1].write_text(render_markdown(report), encoding="utf-8")
    return paths


def resolve_out(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fake", action="store_true", help="fake model, scripted edits, zero cost (default)")
    mode.add_argument("--real", action="store_true", help="logged-in CLI accounts, spends tokens")
    parser.add_argument("--workflow", default="bugfix_team", help="name in workspace/workflows or a path")
    parser.add_argument("--tasks", default="a,b,c", help="comma list of a (bug fix), b (feature), c (rename)")
    parser.add_argument("--model", help="real mode: model for every agent node (default claude-haiku-5-5)")
    parser.add_argument("--max-usd", type=float, default=5.0, help="real mode: most spend allowed (default 5)")
    parser.add_argument("--max-runs", type=int, default=3, help="real mode: most runs allowed (default 3)")
    parser.add_argument("--timeout", type=float, default=900.0, help="seconds per run before it is cancelled")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--no-failure-modes", action="store_true", help="fake: skip the scripted failure runs")
    parser.add_argument("--json", action="store_true", help="print JSON instead of markdown")
    parser.add_argument("--out", help="folder for bench-projects-<timestamp>.{json,md} (relative: from repo root)")
    args = parser.parse_args(argv)

    report = run_all("real" if args.real else "fake", args.workflow, [t.strip() for t in args.tasks.split(",") if t.strip()],
                     max_usd=args.max_usd, max_runs=args.max_runs, model=args.model, seed=args.seed,
                     failures=not args.no_failure_modes, timeout_s=args.timeout)
    if args.out:
        for path in write_outputs(report, resolve_out(args.out)):
            print(f"wrote {path}", file=sys.stderr)
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
