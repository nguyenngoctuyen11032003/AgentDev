"""Lab diagnosis: why a test run was slow or failed, and a ready-to-send brief for the workflow assistant.

Pure functions (no I/O) so they are easy to test. Findings are plain dicts:
``{"code", "severity" ("warn" | "fail"), "detail", "fix"}``; ``detail`` and ``fix`` are Vietnamese because
the Lab, the workflow assistant chat and its users are Vietnamese-first (the assistant answers in the
language of the message it receives).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

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


def run_budget(prompt: str, max_seconds: Optional[int] = None, max_tokens: Optional[int] = None) -> Dict[str, int]:
    """Seconds/tokens one run may use: tight for greeting-like prompts, wider for real work; per-scenario overrides win."""
    simple = len((prompt or "").strip()) <= SIMPLE_PROMPT_CHARS
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


def _error_finding(error: str) -> Dict[str, Any]:
    if error.strip().lower().startswith("interrupted"):
        return {"code": "interrupted", "severity": "warn", "detail": error[:400],
                "fix": "Máy chủ khởi động lại khi lượt này đang chạy; không phải lỗi của quy trình. Hãy chạy lại kiểm định."}
    if "Vượt giới hạn" in error or "Run budget exceeded" in error:
        return {"code": "budget_limit", "severity": "fail", "detail": error[:400],
                "fix": ("Lượt chạy chạm giới hạn run_limits của quy trình: giảm vòng lặp và rút gọn node tốn nhiều nhất "
                        "được nêu; chỉ nâng giới hạn khi việc này thật sự lớn.")}
    if "looping" in error or "stopped after" in error:
        return {"code": "timeout", "severity": "fail", "detail": error[:400],
                "fix": ("Lượt chạy quá thời gian tối đa, thường do vòng lặp không thoát được: thêm node loop_counter ở "
                        "mọi vòng sửa/duyệt và bảo đảm các điều kiện duyệt chấp nhận cả câu tự trả lời của Phòng thí "
                        "nghiệm ([Automatic answer ...]); nếu không có vòng lặp thì rút gọn các bước dài.")}
    return {"code": "error", "severity": "fail", "detail": error[:400],
            "fix": "Sửa nguyên nhân lỗi nêu trên (tài khoản, công cụ, cấu hình) rồi chạy lại."}


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
    if error:
        findings.append(_error_finding(error))

    if seconds > budget["seconds"]:
        slowest = nodes[0] if nodes else None
        share = f"; chậm nhất là {slowest['node']} ({slowest['seconds']:.0f}s, {slowest['calls']} lần)" if slowest else ""
        findings.append({
            "code": "over_budget",
            "kind": "time",
            "severity": "warn",
            "detail": f"Chạy mất {seconds:.0f}s (ngân sách {budget['seconds']}s){share}.",
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
    simple = len(prompt.strip()) <= SIMPLE_PROMPT_CHARS and budget["seconds"] <= SLOW_SECONDS
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
    if status == "failed" and judge.get("judged_by") == "basic":
        # The basic check fails only an empty answer or a model-call error; no AI judge was available.
        findings.append({
            "code": "no_answer",
            "severity": "fail",
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
        if head.startswith(("no files were saved", "there is no", "i could not", "i cannot")):
            findings.append({
                "code": "wrong_final_node",
                "severity": "warn",
                "detail": "Câu trả lời cuối là thông báo hệ thống bằng ngôn ngữ khác, không trả lời người dùng.",
                "fix": "Node cuối (lưu trữ/kết thúc) chỉ chạy khi có việc để lưu và luôn trả lời bằng ngôn ngữ của người dùng.",
            })
    return findings


def diagnose_job(runs: List[Dict[str, Any]], prompts: Dict[int, str]) -> List[Dict[str, Any]]:
    """Per-run findings, with the scenario index attached."""
    out: List[Dict[str, Any]] = []
    for run in runs:
        if run.get("status") in ("running", None):
            continue
        for finding in diagnose_run(run, prompts.get(run.get("scenario", -1), "")):
            out.append({**finding, "scenario": run.get("scenario"), "repeat": run.get("repeat")})
    return out


def compare_baseline(current: Dict[str, Any], baseline: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Regression flags of a finished job against the last job that was ready (pass rate -10 points, time/cost +30%).

    ``cost_usd`` is a job total: when both sides carry their number of finished runs (``done``) it is compared
    per run, so a job with more scenarios/repeats is not reported as more expensive.
    """
    if not baseline:
        return {}
    flags: Dict[str, Any] = {}
    cur_rate, old_rate = current.get("pass_rate"), baseline.get("pass_rate")
    if cur_rate is not None and old_rate is not None and old_rate - cur_rate > 0.10:
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
        "detail": "So với lần đạt trước: " + "; ".join(parts) + ".",
        "fix": "Xem lại những thay đổi gần đây của quy trình (vai trò, model, vòng lặp) và hoàn tác phần làm kém đi.",
    }


def build_fix_brief(workflow: str, runs: List[Dict[str, Any]], scenarios: List[Any], findings: List[Dict[str, Any]],
                    pass_rate: float, threshold: float) -> str:
    """The message to send the workflow assistant: facts first, requested changes, constraints.

    Empty when nothing needs fixing (all runs passed, none slow and no finding).
    """
    # A run cut by a server restart says nothing about the workflow: it is not a reason to ask for a fix.
    findings = [f for f in findings if f.get("code") != "interrupted"]
    problem_runs = [r for r in runs if r.get("status") in ("failed", "error")
                    and not str(r.get("error") or "").strip().lower().startswith("interrupted")]
    if not problem_runs and not findings:
        return ""
    lines = [
        f"Quy trình `{workflow}` vừa được kiểm định trong Phòng thí nghiệm. "
        f"Tỷ lệ đạt {pass_rate * 100:.0f}% (yêu cầu ≥ {threshold * 100:.0f}%). "
        "Hãy tìm nguyên nhân gốc trong quy trình và đề xuất BẢN SỬA hoàn chỉnh (thẻ đề xuất để tôi bấm Áp dụng).",
    ]
    # Failed runs first, then the runs a finding is about (e.g. a passed but slow run), at most 5.
    flagged = {(f.get("scenario"), f.get("repeat")) for f in findings if f.get("scenario") is not None}
    selected = problem_runs + [r for r in runs if r not in problem_runs
                               and (r.get("scenario"), r.get("repeat")) in flagged]
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
        if run.get("error"):
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
    if findings:
        lines += ["", "### Chẩn đoán tự động"]
        seen = set()
        for f in findings:
            key = (f["code"], f["detail"])
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- [{f['code']}] {f['detail']} → Hướng sửa: {f['fix']}")
    lines += [
        "",
        "### Yêu cầu khi sửa",
        "- Chỉ sửa những gì cần để khắc phục các lỗi trên; giữ nguyên phần đang chạy tốt.",
        "- Quy trình phải chạy NHANH: việc nhỏ trả lời trong vài chục giây, mọi vòng lặp có giới hạn, model nhẹ cho việc đơn giản.",
        "- Các bước duyệt của người phải chấp nhận cả câu tự trả lời `[Automatic answer ...]` của Phòng thí nghiệm "
        "(người thật vẫn chỉ cần gõ OK).",
        "- Sau khi sửa, nói rõ đã đổi gì và vì sao nó khắc phục từng lỗi.",
        "",
        "Thông tin bổ sung của tôi: ",
    ]
    return "\n".join(lines)
