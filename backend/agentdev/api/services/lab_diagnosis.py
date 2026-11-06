"""Lab diagnosis: why a test run was slow or failed, and a ready-to-send brief for the workflow assistant.

Pure functions (no I/O) so they are easy to test. Findings are plain dicts:
``{"code", "severity" ("warn" | "fail"), "detail", "fix"}``; ``detail`` and ``fix`` are Vietnamese because
the Lab, the workflow assistant chat and its users are Vietnamese-first (the assistant answers in the
language of the message it receives).
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from agentdev.utils.redact import redact_secrets

# Time budget (seconds) of a greeting-like run; real requests get LONG_SECONDS. Override with AGENTDEV_LAB_SLOW_SECONDS.
SLOW_SECONDS = int(os.environ.get("AGENTDEV_LAB_SLOW_SECONDS", "120"))
# One node running this many times in a run is a loop worth reporting. A guarded review loop of 2 rounds
# legitimately runs its writer/reviewer 3 times (first pass + 2 revisions), which the fix text allows.
LOOP_CALLS = 4
BRIEF_PROMPT_CHARS = 1500  # prompt/criteria quoted in the fix brief (a scenario prompt can be 20k chars)
SIMPLE_PROMPT_CHARS = 140  # short requests (greetings, questions) must not trigger a whole production line
SIMPLE_MAX_AGENTS = 2
LONG_SECONDS = 300  # budget of a run on a real (non-greeting) request
SIMPLE_TOKENS = 40_000
LONG_TOKENS = 150_000


# A short request that asks for work to be DONE ("Viết app todo bằng React") is real work, not a greeting:
# length alone must not give it the tight greeting budget.
_WORK_REQUEST = re.compile(
    r"\b(viết|tạo|xây|làm|sửa|fix|thiết kế|lập|dựng|triển khai|phát triển|build|create|write|implement|develop|design|"
    r"generate|refactor|app|website|video|api|plan)\b|写|创建|开发|修复|设计",
    re.IGNORECASE,
)


_VI_CHARS = re.compile(r"[ăâđêôơưàảãáạằẳẵắặầẩẫấậèẻẽéẹềểễếệìỉĩíịòỏõóọồổỗốộờởỡớợùủũúụừửữứựỳỷỹýỵ]", re.IGNORECASE)


def is_simple_prompt(prompt: str) -> bool:
    """Greeting-like or a plain question: short AND not asking for a deliverable."""
    text = (prompt or "").strip()
    return len(text) <= SIMPLE_PROMPT_CHARS and not _WORK_REQUEST.search(text)


def run_budget(prompt: str, max_seconds: Optional[int] = None, max_tokens: Optional[int] = None) -> Dict[str, int]:
    """Seconds/tokens one run may use: tight for greeting-like prompts, wider for real work; per-scenario overrides win."""
    simple = is_simple_prompt(prompt)
    return {
        "seconds": int(max_seconds or (SLOW_SECONDS if simple else LONG_SECONDS)),
        "tokens": int(max_tokens or (SIMPLE_TOKENS if simple else LONG_TOKENS)),
    }


# Cache-read token counts as reported by each provider (Claude CLI, Codex CLI, Gemini). Providers add them to the
# input/total tokens, but they are billed at ~10% (see CACHE_READ_WEIGHT).
_CACHE_READ_KEYS = ("cache_read_input_tokens", "cached_input_tokens", "cached_content_token_count")


def _cache_read(call: Dict[str, Any]) -> int:
    meta = call.get("metadata") or {}
    for key in _CACHE_READ_KEYS:
        try:
            value = int(meta.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value:
            return value
    return 0


CACHE_READ_WEIGHT = 0.1  # a cache read costs ~10% of a fresh input token


def cached_tokens(run: Dict[str, Any]) -> int:
    """Cache-read tokens included in ``run["tokens"]`` (0 when the timeline does not know them)."""
    cached = sum(int(item.get("cache_read") or 0) for item in run.get("timeline") or [])
    return min(cached, int(run.get("tokens") or 0))


def fresh_tokens(run: Dict[str, Any]) -> int:
    """Tokens of a run with cache reads weighted at their price (~10%), so one cached system prompt does not
    look heavy but a loop re-reading a huge cached context still does."""
    tokens = int(run.get("tokens") or 0)
    cached = cached_tokens(run)
    return int(tokens - cached + cached * CACHE_READ_WEIGHT)


def over_budget(run: Dict[str, Any], budget: Dict[str, int]) -> bool:
    return float(run.get("seconds") or 0) > budget["seconds"] or fresh_tokens(run) > budget["tokens"]


def _budget_of(run: Dict[str, Any], prompt: str) -> Dict[str, int]:
    """The budget the Lab attached to the run (``budget_seconds``/``budget_tokens``), else the default for the prompt."""
    default = run_budget(prompt)
    return {"seconds": int(run.get("budget_seconds") or default["seconds"]),
            "tokens": int(run.get("budget_tokens") or default["tokens"])}


def node_timeline(call_history: Iterable[Dict[str, Any]], started: Optional[datetime]) -> List[Dict[str, Any]]:
    """Per-call time estimate: the gap between one model call finishing and the previous one.

    The token tracker stamps every call when it ends, so the gap is the call's duration (plus a little
    orchestration time). Returns one entry per call, in order: ``{node, seconds, tokens, model}``.
    """
    timeline: List[Dict[str, Any]] = []
    previous = started
    for call in call_history or []:
        try:
            stamp = datetime.fromisoformat(str(call.get("timestamp")))
        except ValueError:
            stamp = None
        if stamp is not None and stamp.tzinfo is not None:
            stamp = stamp.astimezone().replace(tzinfo=None)  # tracker stamps are naive local time
        seconds = 0.0
        if stamp is not None:
            if previous is not None:
                seconds = max(0.0, (stamp - previous).total_seconds())
            previous = stamp
        timeline.append({
            "node": str(call.get("node_id") or "?"),
            "seconds": round(seconds, 1),
            "tokens": int(call.get("total_tokens") or 0),
            "cache_read": _cache_read(call),
            "model": str(call.get("model_name") or ""),
        })
    return timeline


def summarise_timeline(timeline: List[Dict[str, Any]], top: int = 5) -> List[Dict[str, Any]]:
    """Per node: calls, seconds, tokens, slowest first."""
    nodes: Dict[str, Dict[str, Any]] = {}
    for item in timeline:
        entry = nodes.setdefault(item["node"], {"node": item["node"], "calls": 0, "seconds": 0.0, "tokens": 0,
                                                "model": item.get("model", "")})
        entry["calls"] += 1
        entry["seconds"] = round(entry["seconds"] + item["seconds"], 1)
        entry["tokens"] += item["tokens"]
    return sorted(nodes.values(), key=lambda n: n["seconds"], reverse=True)[:top]


def node_summary(run: Dict[str, Any], top: int = 5) -> List[Dict[str, Any]]:
    """Slowest nodes of a run. Uses the measured wall time of each node run (``node_runs`` of the token
    tracker) when the run carries it - exact for parallel branches and nodes without model calls - and falls
    back to the gap estimate of the timeline (wrong when branches overlap)."""
    node_runs = run.get("node_runs") or []
    if not node_runs:
        return summarise_timeline(run.get("timeline") or [], top)
    tokens: Dict[str, int] = {}
    for item in run.get("timeline") or []:
        tokens[item["node"]] = tokens.get(item["node"], 0) + int(item.get("tokens") or 0)
    nodes: Dict[str, Dict[str, Any]] = {}
    for item in node_runs:
        name = str(item.get("node") or "?")
        entry = nodes.setdefault(name, {"node": name, "calls": 0, "seconds": 0.0, "tokens": tokens.get(name, 0)})
        entry["calls"] += 1
        entry["seconds"] = round(entry["seconds"] + float(item.get("wall_ms") or 0) / 1000.0, 1)
    return sorted(nodes.values(), key=lambda n: n["seconds"], reverse=True)[:top]


def _run_counts(run: Dict[str, Any]) -> Dict[str, int]:
    """How many times each node ran: from ``node_runs`` when present (``agents`` counts model calls)."""
    node_runs = run.get("node_runs") or []
    if not node_runs:
        return dict(run.get("agents") or {})
    counts: Dict[str, int] = {}
    for item in node_runs:
        name = str(item.get("node") or "?")
        counts[name] = counts.get(name, 0) + 1
    return counts


# --- Layers: which part of the system a finding is about ---------------------------------------------------------
# workflow: the YAML (roles, edges, loops, limits) - the workflow assistant fixes it.
# environment: accounts, quotas, rate limits, network, the machine - the user fixes it; the workflow is fine.
# platform: a suspected AgentDev bug (engine, executor, tools) - a developer fixes it on a branch, never live.
# scenario: the Lab test itself (vague criteria, a judge that disagrees with itself) - the user reviews it.
LAYERS = ("workflow", "platform", "environment", "scenario")

# Structured error kind of a failed run (``run["error_kind"]``, set by the Lab from the exception class) -> layer.
KIND_LAYER = {
    "timeout": "workflow", "loop_limit": "workflow", "budget_limit": "workflow", "workflow_error": "workflow",
    "quota": "environment", "cli": "environment", "provider_timeout": "environment", "model_call": "environment",
    "network": "environment", "os_error": "environment",
    "engine_exception": "platform", "unknown": "platform",
    "interrupted": "environment",
}

# Built-in exception types that only come from a bug in Python code (AgentDev's), never from the model's work.
PYTHON_BUG_TYPES = frozenset({
    "AttributeError", "TypeError", "KeyError", "NameError", "ImportError", "ModuleNotFoundError", "IndexError",
    "AssertionError", "NotImplementedError", "UnboundLocalError", "RecursionError", "ZeroDivisionError",
})
# Tool-call error codes the agent executor records when a tool cannot run at all (see agent_executor).
PLATFORM_TOOL_CODES = frozenset({"TOOL_NOT_FOUND", "TOOL_NOT_ALLOWED"})


def _chain(exc: BaseException, limit: int = 8) -> List[BaseException]:
    out: List[BaseException] = []
    current: Optional[BaseException] = exc
    while current is not None and len(out) < limit and current not in out:
        out.append(current)
        current = current.__cause__ or current.__context__
    return out


def _causes(exc: BaseException, limit: int = 8) -> List[BaseException]:
    """``exc`` and its explicit causes (``raise ... from``), without implicit ``__context__`` links."""
    out: List[BaseException] = []
    current: Optional[BaseException] = exc
    while current is not None and len(out) < limit and current not in out:
        out.append(current)
        current = current.__cause__
    return out


def classify_exception(exc: BaseException) -> str:
    """The ``error_kind`` of a run that raised ``exc``, from exception classes only (no message parsing)."""
    from agentdev.runtime.node.agent.account_fallback import QuotaExceededError
    from agentdev.runtime.node.agent.providers._cli_common import CliProviderError, CliTimeoutError
    from agentdev.connections.autobind import NoSignedInAccountError
    from agentdev.connections.resolver import ConnectionResolutionError
    from agentdev.entity.configs.base import ConfigError
    from agentdev.utils.exceptions import ConfigurationError, MACException, ValidationError, WorkflowExecutionError
    from agentdev.utils.token_tracker import BudgetExceededError
    from agentdev.validation.check import DesignError
    from yaml import YAMLError

    chain = _chain(exc)
    if type(exc).__name__ == "LabRunTimeoutError":
        return "timeout"
    # A Python bug type only counts when it is the error or an explicit cause (``raise X from bug``): an error
    # raised while handling an unrelated KeyError (implicit ``__context__``) is not that KeyError's fault.
    if any(type(e).__module__ == "builtins" and type(e).__name__ in PYTHON_BUG_TYPES for e in _causes(exc)):
        return "engine_exception"
    # Order matters: the specific cause (no account, a bad YAML) wins over the ModelCallError the agent executor
    # wraps every failure of its node in, and that one wins over the generic WorkflowExecutionError.
    config_errors = (ConfigurationError, ValidationError, DesignError, ConfigError, YAMLError)
    checks = (
        ("quota", lambda e: isinstance(e, QuotaExceededError)),
        ("budget_limit", lambda e: isinstance(e, BudgetExceededError)),
        ("loop_limit", lambda e: isinstance(e, MACException) and (e.details or {}).get("kind") == "loop_limit"),
        ("provider_timeout", lambda e: isinstance(e, CliTimeoutError)),
        ("cli", lambda e: isinstance(e, (CliProviderError, NoSignedInAccountError, ConnectionResolutionError))),
        ("workflow_error", lambda e: isinstance(e, config_errors)),
        ("model_call", lambda e: isinstance(e, WorkflowExecutionError) and type(e).__name__ == "ModelCallError"),
        ("workflow_error", lambda e: isinstance(e, WorkflowExecutionError)),
        ("network", lambda e: isinstance(e, ConnectionError)),
        ("os_error", lambda e: isinstance(e, OSError)),
    )
    for kind, test in checks:
        if any(test(e) for e in chain):
            return kind
    return "unknown"


# Fallback for runs stored before the Lab recorded ``error_kind`` (old jobs): the error text is all there is.
# ONE ordered table, first match wins. Keep it tight: "stopped after 3 retries: 429" is a provider error, and only
# the Lab's own "Run stopped after N minutes/s without finishing" is a timeout.
_TEXT_KINDS = (
    (re.compile(r"^\s*interrupted", re.IGNORECASE), "interrupted"),
    (re.compile(r"Vượt giới hạn|Run budget exceeded"), "budget_limit"),
    (re.compile(r"^Run stopped after \d+(?: minutes|s) without finishing|probably looping"), "timeout"),
    (re.compile(r"safety limit"), "loop_limit"),
    (re.compile(r"usage limit|hit your .{0,20}limit|insufficient_quota|exceeded your current quota|out of credits",
                re.IGNORECASE), "quota"),
    (re.compile(r"\b429\b|rate.?limit|too many requests|overloaded|stopped after \d+ retries", re.IGNORECASE),
     "model_call"),
    (re.compile(r"not logged in|log ?in\b|unauthori[sz]ed|\b401\b|authenticat|CLI (?:is )?(?:missing|not found)",
                re.IGNORECASE), "cli"),
    (re.compile(r"connection (?:refused|reset|error|aborted)|getaddrinfo|ECONNRESET|network is unreachable",
                re.IGNORECASE), "network"),
    (re.compile(r"Traceback \(most recent call last\)|\b(?:" + "|".join(sorted(PYTHON_BUG_TYPES)) + r")\b"),
     "engine_exception"),
)


def error_kind_of(run: Dict[str, Any]) -> str:
    """The structured ``error_kind`` of a run, else the text fallback for old jobs; "" when the run has no error."""
    kind = str(run.get("error_kind") or "")
    error = str(run.get("error") or "")
    if kind:
        return kind if kind in KIND_LAYER else "unknown"
    if not error:
        return ""
    for pattern, text_kind in _TEXT_KINDS:
        if pattern.search(error):
            return text_kind
    return "unknown"


_ENV_FIX = {
    "quota": "Tài khoản đã hết hạn mức: chờ hạn mức làm mới hoặc đăng nhập tài khoản khác (Cài đặt > Tài khoản).",
    "cli": "CLI chưa cài hoặc chưa đăng nhập: chạy `claude login` / `codex login` (hoặc đăng nhập lại ở Cài đặt > Tài khoản).",
    "provider_timeout": "Nhà cung cấp model không trả lời kịp: kiểm tra mạng và trạng thái nhà cung cấp, rồi chạy lại.",
    "model_call": ("Model không trả lời sau nhiều lần thử (thường là 429/quá tải): chờ hết giới hạn tốc độ rồi chạy "
                   "lại, hoặc giảm số lượt chạy song song của Phòng thí nghiệm (AGENTDEV_LAB_WORKERS)."),
    "network": "Mất kết nối mạng tới nhà cung cấp: kiểm tra mạng/proxy rồi chạy lại.",
    "os_error": "Lỗi của máy (ổ đĩa đầy, quyền, file bị khoá): kiểm tra máy rồi chạy lại.",
}
_NOT_WORKFLOW = " Không sửa quy trình vì lỗi này."


def _error_finding(error: str, kind: str = "") -> Dict[str, Any]:
    kind = kind or error_kind_of({"error": error})
    detail = error[:400]
    if kind == "interrupted":
        return {"code": "interrupted", "severity": "warn", "detail": detail, "layer": "environment",
                "error_kind": kind,
                "fix": "Máy chủ khởi động lại khi lượt này đang chạy; không phải lỗi của quy trình. Hãy chạy lại kiểm định."}
    if kind == "budget_limit":
        return {"code": "budget_limit", "severity": "fail", "detail": detail, "layer": "workflow", "error_kind": kind,
                "fix": ("Lượt chạy chạm giới hạn run_limits của quy trình: giảm vòng lặp và rút gọn node tốn nhiều nhất "
                        "được nêu; chỉ nâng giới hạn khi việc này thật sự lớn.")}
    if kind in ("timeout", "loop_limit"):
        return {"code": "timeout", "severity": "fail", "detail": detail, "layer": "workflow", "error_kind": kind,
                "fix": ("Lượt chạy quá thời gian tối đa, thường do vòng lặp không thoát được: thêm node loop_counter ở "
                        "mọi vòng sửa/duyệt và bảo đảm các điều kiện duyệt chấp nhận cả câu tự trả lời của Phòng thí "
                        "nghiệm ([Automatic answer ...]), trừ bước tốn tiền hoặc không thể hoàn tác: ở đó câu tự trả "
                        "lời phải đi nhánh bỏ qua; nếu không có vòng lặp thì rút gọn các bước dài.")}
    if kind == "workflow_error":
        return {"code": "workflow_error", "severity": "fail", "detail": detail, "layer": "workflow", "error_kind": kind,
                "fix": "Lỗi cấu hình/luồng của quy trình nêu trên: sửa node, cạnh hoặc điều kiện liên quan rồi chạy lại."}
    layer = KIND_LAYER.get(kind, "platform")
    if layer == "environment":
        return {"code": "error", "severity": "fail", "detail": detail, "layer": layer, "error_kind": kind,
                "fix": _ENV_FIX.get(kind, "Sửa lỗi tài khoản/máy nêu trên rồi chạy lại.") + _NOT_WORKFLOW}
    return {"code": "platform_error", "severity": "fail", "detail": detail, "layer": "platform", "error_kind": kind,
            "fix": ("Nghi lỗi nền tảng AgentDev (engine/executor/công cụ), không phải lỗi quy trình: chép báo cáo nền "
                    "tảng gửi người phát triển để sửa trên nhánh riêng.")}


def _tool_platform_finding(run: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A tool that could not run at all (unknown tool, not granted) or crashed with a Python bug: platform layer.
    A tool that ran and failed (exit code 1, file not found) is normal work and is not reported here."""
    if run.get("status") == "passed":
        return None  # the agent recovered (a mistyped tool name, a retry): nothing to report
    hits: List[str] = []
    for item in run.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("error_code") or "")
        exc_type = str(item.get("exception_type") or "")
        if code in PLATFORM_TOOL_CODES or exc_type in PYTHON_BUG_TYPES:
            label = f"{item.get('node') or '?'}/{item.get('tool') or '?'} ({code or exc_type})"
            if label not in hits:
                hits.append(label)
    if not hits:
        return None
    return {"code": "tool_error", "severity": "warn", "layer": "platform",
            "detail": "Công cụ không chạy được: " + "; ".join(hits[:5]) + ".",
            "fix": ("Nghi lỗi nền tảng: công cụ không tồn tại, không được cấp cho agent hoặc bị lỗi bên trong. Chép "
                    "báo cáo nền tảng gửi người phát triển; chỉ sửa quy trình nếu vai trò yêu cầu một công cụ sai tên.")}


def diagnose_run(run: Dict[str, Any], prompt: str = "") -> List[Dict[str, Any]]:
    """Findings for one finished run (``run`` is a result entry of a Lab job).

    Time and tokens are judged against the run's budget (``budget_seconds``/``budget_tokens`` attached by the
    Lab, else :func:`run_budget` of the prompt), so a real task is not flagged for using what it is allowed;
    cache reads count at CACHE_READ_WEIGHT when the timeline knows them.
    """
    findings: List[Dict[str, Any]] = []
    prompt = prompt or ""
    seconds = float(run.get("seconds") or 0)
    tokens = int(run.get("tokens") or 0)
    fresh = fresh_tokens(run)
    agents: Dict[str, int] = dict(run.get("agents") or {})
    counts = _run_counts(run)
    measured_runs = bool(run.get("node_runs"))
    nodes = node_summary(run)
    status = run.get("status")
    budget = _budget_of(run, prompt)

    error = str(run.get("error") or "")
    error_layer = ""
    if error:
        finding = _error_finding(error, error_kind_of(run))
        error_layer = finding["layer"]
        findings.append(finding)
    tool_finding = _tool_platform_finding(run)
    if tool_finding:
        findings.append(tool_finding)

    if seconds > budget["seconds"]:
        slowest = nodes[0] if nodes else None
        share = f"; chậm nhất là {slowest['node']} ({slowest['seconds']:.0f}s, {slowest['calls']} lần)" if slowest else ""
        findings.append({
            "code": "over_budget",
            "kind": "time",
            "severity": "warn",
            "detail": f"Chạy mất {seconds:.0f}s (ngân sách {budget['seconds']}s){share}.",
            # A run slowed down by retries (429) or a crash is not a slow workflow.
            "layer": error_layer if error_layer in ("environment", "platform") else "workflow",
            "fix": ("Giảm thời gian: dùng model nhẹ hơn và effort thấp cho các node duyệt/lưu/tóm tắt, bỏ bớt node "
                    "không cần cho việc nhỏ, cho các nhánh độc lập chạy song song, giảm số vòng sửa."),
        })

    looping = {n: c for n, c in counts.items() if c >= LOOP_CALLS}
    if looping:
        names = ", ".join(f"{n} ×{c}" for n, c in sorted(looping.items(), key=lambda kv: -kv[1]))
        what = "Có node chạy lặp nhiều lần" if measured_runs else "Có node gọi model nhiều lần (có thể là vòng lặp)"
        findings.append({
            "code": "loop",
            "severity": "warn",
            "detail": f"{what}: {names}.",
            "fix": (("" if measured_runs else "Nếu node này nằm trong vòng sửa/duyệt (không phải một agent tự gọi "
                     "công cụ nhiều bước): ")
                    + "đặt giới hạn vòng (loop_counter, tối đa 2 vòng), cho node duyệt trả APPROVED khi chỉ còn lỗi "
                    "nhỏ, và nêu tiêu chí duyệt cụ thể để không yêu cầu sửa vô hạn."),
        })

    # A short prompt with an explicit larger budget (scenario max_seconds / long-task budget) is real work.
    simple = is_simple_prompt(prompt) and budget["seconds"] <= SLOW_SECONDS
    if simple and len(agents) > SIMPLE_MAX_AGENTS:
        findings.append({
            "code": "overkill",
            "severity": "warn",
            "detail": f"Yêu cầu ngắn/đơn giản nhưng {len(agents)} agent đã chạy ({', '.join(agents)}).",
            "fix": ("Thêm lối rẽ ở đầu quy trình: lời chào, câu hỏi về đội hoặc việc nhỏ được người đầu tiên trả lời "
                    "thẳng và kết thúc, không đi qua cả dây chuyền duyệt/sản xuất."),
        })

    if fresh > budget["tokens"]:
        cache = cached_tokens(run)
        cached = (f" (tổng {tokens:,} token, trong đó {cache:,} token đọc từ cache được tính 10%)"
                  if cache else "")
        findings.append({
            "code": "over_budget",
            "kind": "tokens",
            "severity": "warn",
            "detail": f"Tốn {fresh:,} token quy đổi cho một lượt chạy{cached}, ngân sách {budget['tokens']:,}.",
            "fix": ("Rút gọn vai trò (role), chỉ cho mỗi agent đọc đúng file cần thiết, dùng clear_context trên các "
                    "liên kết dài và chọn model nhỏ cho việc đơn giản."),
        })

    judge = run.get("judge") or {}
    if status == "unjudged":
        findings.append({
            "code": "judge_unavailable", "severity": "warn", "layer": "environment",
            "detail": "Giám khảo AI không chấm được lượt này (không gọi được tài khoản hoặc trả lời sai định dạng).",
            "fix": "Đăng nhập/chờ hạn mức của một tài khoản rồi bấm Tiếp tục để chấm lại." + _NOT_WORKFLOW,
        })
    if status == "failed" and judge.get("judged_by") == "basic":
        # The basic check fails only an empty answer or a model-call error; no AI judge was available.
        findings.append({
            "code": "no_answer",
            "severity": "fail",
            # An empty final answer is the workflow's fault; an answer the basic check rejected (a model error
            # text) while no AI judge could run is the accounts' fault.
            "layer": "workflow" if not str(run.get("answer") or "").strip() else "environment",
            "detail": "Không nhận được câu trả lời dùng được (trống hoặc lỗi gọi model); chưa có giám khảo AI để chấm.",
            "fix": ("Kiểm tra tài khoản/model của các agent và bảo đảm node cuối luôn trả lời người dùng; đăng nhập "
                    "một tài khoản để giám khảo AI chấm được."),
        })
    elif status == "failed" and judge.get("reason"):
        findings.append({
            "code": "quality",
            "severity": "fail",
            "detail": f"Giám khảo: {judge['reason']}",
            "fix": ("Sửa vai trò/luồng để câu trả lời đạt đúng tiêu chí (ngôn ngữ, nội dung, độ ngắn gọn). "
                    "Người trả lời cuối cùng phải là agent hiểu yêu cầu, không phải node lưu trữ/hệ thống."),
        })
    elif status == "failed" and not error:
        findings.append({"code": "quality", "severity": "fail", "detail": "Câu trả lời không đạt tiêu chí.",
                         "fix": "Rà lại vai trò của agent trả lời cuối cùng so với tiêu chí đạt."})

    answer = str(run.get("answer") or "")
    if status in ("failed", "passed") and answer and judge.get("judged_by") == "ai" and not judge.get("pass"):
        head = answer.lstrip()[:60].lower()
        # Only a reply in another language than the request: an English refusal to an English request is a
        # legitimate answer (e.g. "I cannot render without your OK; skipped.").
        prompt_vi = bool(_VI_CHARS.search(prompt or ""))
        if prompt_vi and not _VI_CHARS.search(answer[:400]) and                 head.startswith(("no files were saved", "there is no", "i could not", "i cannot")):
            findings.append({
                "code": "wrong_final_node",
                "severity": "warn",
                "detail": "Câu trả lời cuối là thông báo hệ thống bằng ngôn ngữ khác, không trả lời người dùng.",
                "fix": "Node cuối (lưu trữ/kết thúc) chỉ chạy khi có việc để lưu và luôn trả lời bằng ngôn ngữ của người dùng.",
            })
    for finding in findings:
        finding.setdefault("layer", "workflow")
    return findings


CRITERIA_MIN_CHARS = 20  # shorter criteria ("tốt", "đúng ý") leave the judge guessing
CRITERIA_MIN_WORDS = 4
CRITERIA_MIN_CJK_CHARS = 8  # Chinese/Japanese criteria have no spaces: count characters instead of words


def _vague(text: str) -> bool:
    if not re.search(r"\s", text) and re.search(r"[぀-ヿ㐀-鿿]", text):
        return len(text) < CRITERIA_MIN_CJK_CHARS
    return len(text) < CRITERIA_MIN_CHARS or len(text.split()) < CRITERIA_MIN_WORDS


def diagnose_job(runs: List[Dict[str, Any]], prompts: Dict[int, str],
                 criteria: Optional[Dict[int, str]] = None) -> List[Dict[str, Any]]:
    """Per-run findings, with the scenario index attached, then per-scenario findings of the test itself:
    a judge that gave opposite verdicts to the repeats of one scenario (its failures move to the ``scenario``
    layer: the failure may be the judge's) and, when ``criteria`` is given, missing or vague criteria."""
    out: List[Dict[str, Any]] = []
    finished = [r for r in runs if r.get("status") not in ("running", None)]
    for run in finished:
        for finding in diagnose_run(run, prompts.get(run.get("scenario", -1), "")):
            out.append({**finding, "scenario": run.get("scenario"), "repeat": run.get("repeat")})
    scenarios = sorted({r.get("scenario") for r in finished if isinstance(r.get("scenario"), int)})
    for index in scenarios:
        mine = [r for r in finished if r.get("scenario") == index]
        verdicts = {r.get("status") for r in mine} & {"passed", "failed"}
        # Only AI verdicts can disagree with themselves: the basic check (empty answer) is deterministic. The
        # failures keep their layer: a workflow that passes 1 run in 3 is unreliable and still needs a fix.
        ai_only = all((r.get("judge") or {}).get("judged_by") == "ai" for r in mine
                      if r.get("status") in ("passed", "failed"))
        if verdicts == {"passed", "failed"} and ai_only:
            out.append({"code": "judge_flaky", "severity": "warn", "layer": "scenario", "scenario": index,
                        "repeat": None,
                        "detail": "Các lần chạy của cùng kịch bản được chấm trái nhau (lần đạt, lần trượt).",
                        "fix": ("Làm rõ tiêu chí đạt (cụ thể, đo được) rồi chạy lại vài lần; nếu kết quả vẫn dao động, "
                                "so câu trả lời của lượt đạt và lượt trượt trước khi sửa quy trình.")})
        # Criteria only matter where the scenario did not pass every run (a passing job needs no advice).
        if criteria is None or all(r.get("status") == "passed" for r in mine):
            continue
        text = str(criteria.get(index) or "").strip()
        if not text:
            out.append({"code": "criteria_missing", "severity": "warn", "layer": "scenario", "scenario": index,
                        "repeat": None,
                        "detail": "Kịch bản không có tiêu chí đạt; giám khảo đã chấm theo tiêu chí mặc định.",
                        "fix": "Thêm tiêu chí đạt cụ thể (nội dung, ngôn ngữ, độ dài, file cần có) cho kịch bản."})
        elif _vague(text):
            out.append({"code": "criteria_vague", "severity": "warn", "layer": "scenario", "scenario": index,
                        "repeat": None, "detail": f"Tiêu chí đạt quá ngắn/mơ hồ: \"{text[:80]}\".",
                        "fix": "Viết tiêu chí đo được (cần có gì, ngôn ngữ, độ dài) để giám khảo chấm ổn định."})
    return out


def layer_of(finding: Dict[str, Any]) -> str:
    """A finding's layer; findings built before layers existed are workflow findings."""
    layer = finding.get("layer")
    return layer if layer in LAYERS else "workflow"


def _counted(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # A run cut by a server restart says nothing about anything: it is never counted nor sent anywhere.
    return [f for f in findings if f.get("code") != "interrupted"]


def layer_counts(findings: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {layer: 0 for layer in LAYERS}
    for finding in _counted(findings):
        counts[layer_of(finding)] += 1
    return counts


def build_environment_hints(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """What the user must fix outside the workflow (accounts, quotas, network), one entry per distinct problem."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for f in _counted(findings):
        if layer_of(f) != "environment":
            continue
        key = (f["code"], f.get("error_kind") or f["detail"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"code": f["code"], "error_kind": f.get("error_kind", ""), "detail": f["detail"], "fix": f["fix"],
                    "scenario": f.get("scenario")})
    return out


def _scrub(text: Any, limit: int) -> str:
    """One line, secrets masked: report fields come from a run (untrusted) and must not open a heading of their own
    (a newline + ``## Rules`` in an error must stay inside its bullet)."""
    return " ".join(redact_secrets(text).split())[:limit]


def _scenario_of(scenarios: List[Any], run: Dict[str, Any]) -> Any:
    index = run.get("scenario", 0)
    index = index if isinstance(index, int) else 0
    return scenarios[index] if 0 <= index < len(scenarios) else None


def _scenario_name(scenario: Any, run: Dict[str, Any]) -> str:
    index = run.get("scenario", 0)
    return getattr(scenario, "name", "") or f"#{(index if isinstance(index, int) else 0) + 1}"


def _run_key(item: Dict[str, Any]) -> tuple:
    return (item.get("scenario"), item.get("repeat"))


def build_platform_report(workflow: str, runs: List[Dict[str, Any]], scenarios: List[Any],
                          findings: List[Dict[str, Any]], workflow_hash: str = "") -> str:
    """Markdown evidence of suspected AgentDev bugs for a human or a developer agent (never sent to the workflow
    assistant as something to fix): scenario, error, node/tool trace and how to reproduce. "" when none."""
    platform = [f for f in _counted(findings) if layer_of(f) == "platform"]
    if not platform:
        return ""
    keys = {_run_key(f) for f in platform}
    workflow = _scrub(workflow, 200)
    lines = [
        "# Báo cáo nghi lỗi nền tảng AgentDev",
        "",
        f"- Quy trình: `{workflow}`" + (f" (bản `{workflow_hash[:12]}`)" if workflow_hash else ""),
        f"- Số chẩn đoán thuộc nền tảng: {len(platform)}",
        "- Đây là lỗi của engine/executor/công cụ, không phải của quy trình: sửa trên nhánh riêng, có test hồi quy, "
        "không sửa code đang chạy.",
    ]
    shown = 0
    for run in runs:
        if _run_key(run) not in keys or shown >= 5:
            continue
        shown += 1
        scenario = _scenario_of(scenarios, run)
        lines += ["", f"## Kịch bản: {_scrub(_scenario_name(scenario, run), 200)} (lần {run.get('repeat', 1)}) — "
                      f"{_scrub(run.get('status'), 40)}"]
        lines.append(f"- Yêu cầu gửi vào: {_scrub(getattr(scenario, 'prompt', ''), 500)}")
        if run.get("error"):
            lines.append(f"- Lỗi ({error_kind_of(run)}): {_scrub(run['error'], 1500)}")
        trail = [_scrub(item.get("node") or "?", 120) for item in run.get("node_runs") or [] if isinstance(item, dict)]
        if trail:
            lines.append("- Node đã chạy (cũ → mới): " + " → ".join(trail[-12:]))
        tools = [e for e in run.get("evidence") or [] if isinstance(e, dict)
                 and (e.get("error_code") or e.get("exception_type") or e.get("ok") is False)]
        for item in tools[-8:]:
            extra = ", ".join(f"{k}={_scrub(item[k], 80)}" for k in ("error_code", "exception_type", "exit_code")
                              if item.get(k) not in (None, ""))
            lines.append(f"- Công cụ: {_scrub(item.get('node') or '?', 120)} / {_scrub(item.get('tool') or '?', 120)}"
                         + (f" ({extra})" if extra else "")
                         + (f": {_scrub(item.get('command'), 160)}" if item.get("command") else ""))
        for f in platform:
            if _run_key(f) == _run_key(run):
                lines.append(f"- Chẩn đoán [{_scrub(f['code'], 60)}]: {_scrub(f['detail'], 1500)}")
    first = next((r for r in runs if _run_key(r) in keys), None)
    name = _scrub(_scenario_name(_scenario_of(scenarios, first), first), 200) if first else "?"
    lines += [
        "",
        "## Cách tái hiện",
        f"1. Mở Phòng thí nghiệm, chọn quy trình `{workflow}`.",
        f"2. Chạy kịch bản \"{name}\" (yêu cầu ở trên), 1 lần lặp.",
        "3. Xem log của node/công cụ nêu trên; lỗi mong đợi là lỗi ghi ở trên.",
        "4. Viết test hồi quy tái hiện lỗi (đỏ trước), sửa, rồi chạy lại kịch bản trước/sau.",
    ]
    return "\n".join(lines)


def compare_baseline(current: Dict[str, Any], baseline: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Regression flags of a finished job against the last job that was ready (pass rate -10 points, time/cost +30%).

    ``cost_usd`` is a job total: when both sides carry their number of finished runs (``done``) it is compared
    per run, so a job with more scenarios/repeats is not reported as more expensive.
    """
    if not baseline:
        return {}
    flags: Dict[str, Any] = {}
    cur_rate, old_rate = current.get("pass_rate"), baseline.get("pass_rate")
    if cur_rate is not None and old_rate is not None and round(old_rate - cur_rate, 4) > 0.10:
        flags["pass_rate"] = {"was": old_rate, "now": cur_rate}
    now, was = current.get("avg_seconds"), baseline.get("avg_seconds")
    if now is not None and was and now > was * 1.3:
        flags["avg_seconds"] = {"was": was, "now": now}
    now, was = current.get("cost_usd"), baseline.get("cost_usd")
    cur_runs, old_runs = current.get("done"), baseline.get("done")
    if now is not None and was and cur_runs and old_runs:
        if now / cur_runs > (was / old_runs) * 1.3:
            flags["cost_usd"] = {"was": round(was / old_runs, 4), "now": round(now / cur_runs, 4), "per_run": True}
    elif now is not None and was and now > was * 1.3:
        flags["cost_usd"] = {"was": was, "now": now}
    return flags


def regression_finding(flags: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not flags:
        return None
    parts = []
    if "pass_rate" in flags:
        parts.append(f"tỷ lệ đạt {flags['pass_rate']['was'] * 100:.0f}% → {flags['pass_rate']['now'] * 100:.0f}%")
    if "avg_seconds" in flags:
        parts.append(f"thời gian TB {flags['avg_seconds']['was']:.0f}s → {flags['avg_seconds']['now']:.0f}s")
    if "cost_usd" in flags:
        unit = "/lượt" if flags["cost_usd"].get("per_run") else ""
        was, now = flags["cost_usd"]["was"], flags["cost_usd"]["now"]
        digits = 2 if min(was, now) >= 1 else 4  # small per-run costs must not print as $0.00 → $0.01
        parts.append(f"chi phí ${was:.{digits}f}{unit} → ${now:.{digits}f}{unit}")
    return {
        "code": "regression",
        "severity": "warn",
        "layer": "workflow",
        "detail": "So với lần đạt trước: " + "; ".join(parts) + ".",
        "fix": "Xem lại những thay đổi gần đây của quy trình (vai trò, model, vòng lặp) và hoàn tác phần làm kém đi.",
    }


def build_fix_brief(workflow: str, runs: List[Dict[str, Any]], scenarios: List[Any], findings: List[Dict[str, Any]],
                    pass_rate: float, threshold: float) -> str:
    """The message to send the workflow assistant: facts first, requested changes, constraints.

    Only ``workflow`` findings ask for a fix; findings of the other layers are listed as "do not fix the workflow
    for these" so the assistant does not invent a fix for an account error or an AgentDev bug. Empty when no
    workflow finding exists (the job then carries ``platform_report`` / ``environment_hints`` instead).
    """
    findings = _counted(findings)
    workflow_findings = [f for f in findings if layer_of(f) == "workflow"]
    if not workflow_findings:
        return ""
    others = {layer: [f for f in findings if layer_of(f) == layer] for layer in ("environment", "platform", "scenario")}
    lines = [
        f"Quy trình `{workflow}` vừa được kiểm định trong Phòng thí nghiệm. "
        f"Tỷ lệ đạt {pass_rate * 100:.0f}% (yêu cầu ≥ {threshold * 100:.0f}%). "
        "Hãy tìm nguyên nhân gốc trong quy trình và đề xuất BẢN SỬA hoàn chỉnh (thẻ đề xuất để tôi bấm Áp dụng) "
        "cho các lỗi thuộc quy trình dưới đây; nếu thấy quy trình không cần sửa, hãy nói rõ vì sao.",
    ]
    # Runs a workflow finding is about: failed ones first, then e.g. a passed but slow run, at most 5. A run whose
    # only findings are environment/platform/scenario ones is not shown here.
    flagged = {_run_key(f) for f in workflow_findings if f.get("scenario") is not None}
    in_brief = [r for r in runs if _run_key(r) in flagged]
    selected = ([r for r in in_brief if r.get("status") in ("failed", "error")]
                + [r for r in in_brief if r.get("status") not in ("failed", "error")])
    for run in (selected or runs)[:5]:
        index = run.get("scenario", 0)
        index = index if isinstance(index, int) else 0
        scenario = scenarios[index] if 0 <= index < len(scenarios) else None
        lines += ["", f"### Kịch bản: {getattr(scenario, 'name', '') or f'#{index + 1}'} (lần {run.get('repeat', 1)}) — {run.get('status')}"]
        lines.append(f"- Yêu cầu gửi vào: {str(getattr(scenario, 'prompt', ''))[:BRIEF_PROMPT_CHARS]}")
        criteria = (getattr(scenario, "criteria", "") or "").strip()
        if criteria:
            lines.append(f"- Tiêu chí đạt: {criteria[:BRIEF_PROMPT_CHARS]}")
        reason = (run.get("judge") or {}).get("reason")
        if reason:
            lines.append(f"- Giám khảo nhận xét: {reason}")
        if run.get("error") and KIND_LAYER.get(error_kind_of(run)) == "workflow":
            lines.append(f"- Lỗi: {str(run['error'])[:500]}")
        agents = ", ".join(f"{n} ×{c}" if c > 1 else n for n, c in (run.get("agents") or {}).items())
        if agents:
            lines.append(f"- Agent đã chạy: {agents}")
        slow_nodes = node_summary(run, 3)
        if slow_nodes:
            lines.append("- Node tốn thời gian nhất: " + "; ".join(
                f"{n['node']} {n['seconds']:.0f}s/{n['calls']} lần/{n['tokens']:,} token" for n in slow_nodes))
        cache = cached_tokens(run)
        cache_note = f" (gồm {cache:,} token đọc từ cache, giá ~10%)" if cache else ""
        lines.append(f"- Tổng: {float(run.get('seconds') or 0):.0f}s, {int(run.get('tokens') or 0):,} token{cache_note}")
        answer = " ".join(str(run.get("answer") or "").split())[:400]
        if answer:
            lines.append(f"- Câu trả lời nhận được: {answer}")
    lines += ["", "### Chẩn đoán tự động (lỗi thuộc quy trình)"]
    seen = set()
    for f in workflow_findings:
        key = (f["code"], f["detail"])
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- [{f['code']}] {f['detail']} → Hướng sửa: {f['fix']}")
    headings = {
        "environment": "### Lỗi môi trường (không sửa quy trình)",
        "platform": "### Nghi lỗi nền tảng (không sửa quy trình; đã có báo cáo nền tảng riêng)",
        "scenario": "### Kịch bản/giám khảo cần xem lại (không sửa quy trình)",
    }
    for layer, heading in headings.items():
        items = list({f["detail"]: f for f in others[layer]}.values())[:5]
        if items:
            lines += ["", heading] + [f"- [{f['code']}] {f['detail']}" for f in items]
    lines += [
        "",
        "### Yêu cầu khi sửa",
        "- Chỉ sửa những gì cần để khắc phục các lỗi thuộc quy trình ở trên; giữ nguyên phần đang chạy tốt.",
        "- Quy trình phải chạy NHANH: việc nhỏ trả lời trong vài chục giây, mọi vòng lặp có giới hạn, model nhẹ cho việc đơn giản.",
        "- Các bước duyệt của người phải chấp nhận cả câu tự trả lời `[Automatic answer ...]` của Phòng thí nghiệm "
        "(người thật vẫn chỉ cần gõ OK). Ngoại lệ: bước duyệt trước việc tốn tiền hoặc không thể hoàn tác (tạo video, "
        "gửi email, thanh toán, đăng bài) phải có `paid: true` trong config của node duyệt và đưa câu tự trả lời, "
        "câu bỏ qua `[Skipped automatically ...]` và lúc hết giờ sang nhánh bỏ qua, không được duyệt.",
        "- Sau khi sửa, nói rõ đã đổi gì và vì sao nó khắc phục từng lỗi.",
        "",
        "Thông tin bổ sung của tôi: ",
    ]
    return "\n".join(lines)
