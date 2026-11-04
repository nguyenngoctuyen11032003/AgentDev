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

# A single run slower than this is reported as slow (seconds). Override with AGENTDEV_LAB_SLOW_SECONDS.
SLOW_SECONDS = int(os.environ.get("AGENTDEV_LAB_SLOW_SECONDS", "120"))
HEAVY_TOKENS = 40_000
LOOP_CALLS = 3  # one node running this many times in a run is a loop worth reporting
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


def over_budget(run: Dict[str, Any], budget: Dict[str, int]) -> bool:
    return float(run.get("seconds") or 0) > budget["seconds"] or int(run.get("tokens") or 0) > budget["tokens"]


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
        seconds = 0.0
        if stamp is not None:
            if previous is not None:
                seconds = max(0.0, (stamp - previous).total_seconds())
            previous = stamp
        timeline.append({
            "node": str(call.get("node_id") or "?"),
            "seconds": round(seconds, 1),
            "tokens": int(call.get("total_tokens") or 0),
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


def diagnose_run(run: Dict[str, Any], prompt: str = "") -> List[Dict[str, Any]]:
    """Findings for one finished run (``run`` is a result entry of a Lab job)."""
    findings: List[Dict[str, Any]] = []
    seconds = float(run.get("seconds") or 0)
    tokens = int(run.get("tokens") or 0)
    agents: Dict[str, int] = dict(run.get("agents") or {})
    nodes = summarise_timeline(run.get("timeline") or [])
    status = run.get("status")

    error = str(run.get("error") or "")
    if error:
        stopped = "looping" in error or "stopped after" in error
        findings.append({
            "code": "timeout" if stopped else "error",
            "severity": "fail",
            "detail": error[:400],
            "fix": ("Có vòng lặp không thoát được: thêm node loop_counter ở mọi vòng sửa/duyệt, và bảo đảm các "
                    "điều kiện duyệt chấp nhận cả câu tự trả lời của Phòng thí nghiệm ([Automatic answer ...])."
                    if stopped else "Sửa nguyên nhân lỗi nêu trên (tài khoản, công cụ, cấu hình) rồi chạy lại."),
        })

    if seconds > SLOW_SECONDS:
        slowest = nodes[0] if nodes else None
        share = f"; chậm nhất là {slowest['node']} ({slowest['seconds']:.0f}s, {slowest['calls']} lần gọi)" if slowest else ""
        findings.append({
            "code": "slow",
            "severity": "warn",
            "detail": f"Chạy mất {seconds:.0f}s (ngưỡng {SLOW_SECONDS}s){share}.",
            "fix": ("Giảm thời gian: dùng model nhẹ hơn và effort thấp cho các node duyệt/lưu/tóm tắt, bỏ bớt node "
                    "không cần cho việc nhỏ, cho các nhánh độc lập chạy song song, giảm số vòng sửa."),
        })

    looping = {n: c for n, c in agents.items() if c >= LOOP_CALLS}
    if looping:
        names = ", ".join(f"{n} ×{c}" for n, c in sorted(looping.items(), key=lambda kv: -kv[1]))
        findings.append({
            "code": "loop",
            "severity": "warn",
            "detail": f"Có node chạy lặp nhiều lần: {names}.",
            "fix": ("Đặt giới hạn vòng (loop_counter, tối đa 2 vòng), cho node duyệt trả APPROVED khi chỉ còn lỗi nhỏ, "
                    "và nêu tiêu chí duyệt cụ thể để không yêu cầu sửa vô hạn."),
        })

    simple = len(prompt.strip()) <= SIMPLE_PROMPT_CHARS
    if simple and len(agents) > SIMPLE_MAX_AGENTS:
        findings.append({
            "code": "overkill",
            "severity": "warn",
            "detail": f"Yêu cầu ngắn/đơn giản nhưng {len(agents)} agent đã chạy ({', '.join(agents)}).",
            "fix": ("Thêm lối rẽ ở đầu quy trình: lời chào, câu hỏi về đội hoặc việc nhỏ được người đầu tiên trả lời "
                    "thẳng và kết thúc, không đi qua cả dây chuyền duyệt/sản xuất."),
        })

    if tokens > HEAVY_TOKENS:
        findings.append({
            "code": "heavy",
            "severity": "warn",
            "detail": f"Tốn {tokens:,} token cho một lượt chạy.",
            "fix": ("Rút gọn vai trò (role), chỉ cho mỗi agent đọc đúng file cần thiết, dùng clear_context trên các "
                    "liên kết dài và chọn model nhỏ cho việc đơn giản."),
        })

    judge = run.get("judge") or {}
    if run.get("over_budget"):
        findings.append({
            "code": "over_budget",
            "severity": "warn",
            "detail": f"Vượt ngân sách: {seconds:.0f}s / {tokens:,} token (cho phép {run.get('budget_seconds')}s / {int(run.get('budget_tokens') or 0):,} token).",
            "fix": "Rút gọn dây chuyền cho loại yêu cầu này: bỏ node không cần, model nhẹ, ít vòng sửa.",
        })
    if status == "failed" and judge.get("reason"):
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
    """Regression flags of a finished job against the last job that was ready (pass rate -10 points, time/cost +30%)."""
    if not baseline:
        return {}
    flags: Dict[str, Any] = {}
    cur_rate, old_rate = current.get("pass_rate"), baseline.get("pass_rate")
    if cur_rate is not None and old_rate is not None and old_rate - cur_rate > 0.10:
        flags["pass_rate"] = {"was": old_rate, "now": cur_rate}
    for key in ("avg_seconds", "cost_usd"):
        now, was = current.get(key), baseline.get(key)
        if now is not None and was and now > was * 1.3:
            flags[key] = {"was": was, "now": now}
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
        parts.append(f"chi phí ${flags['cost_usd']['was']:.2f} → ${flags['cost_usd']['now']:.2f}")
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
    problem_runs = [r for r in runs if r.get("status") in ("failed", "error")]
    if not problem_runs and not findings:
        return ""
    lines = [
        f"Quy trình `{workflow}` vừa được kiểm định trong Phòng thí nghiệm. "
        f"Tỷ lệ đạt {pass_rate * 100:.0f}% (yêu cầu ≥ {threshold * 100:.0f}%). "
        "Hãy tìm nguyên nhân gốc trong quy trình và đề xuất BẢN SỬA hoàn chỉnh (thẻ đề xuất để tôi bấm Áp dụng).",
    ]
    shown = set()
    for run in (problem_runs or runs)[:5]:
        index = run.get("scenario", 0)
        scenario = scenarios[index] if 0 <= index < len(scenarios) else None
        shown.add(index)
        lines += ["", f"### Kịch bản: {getattr(scenario, 'name', '') or f'#{index + 1}'} (lần {run.get('repeat', 1)}) — {run.get('status')}"]
        lines.append(f"- Yêu cầu gửi vào: {getattr(scenario, 'prompt', '')}")
        criteria = (getattr(scenario, "criteria", "") or "").strip()
        if criteria:
            lines.append(f"- Tiêu chí đạt: {criteria}")
        reason = (run.get("judge") or {}).get("reason")
        if reason:
            lines.append(f"- Giám khảo nhận xét: {reason}")
        if run.get("error"):
            lines.append(f"- Lỗi: {str(run['error'])[:500]}")
        agents = ", ".join(f"{n} ×{c}" if c > 1 else n for n, c in (run.get("agents") or {}).items())
        if agents:
            lines.append(f"- Agent đã chạy: {agents}")
        slow_nodes = summarise_timeline(run.get("timeline") or [], 3)
        if slow_nodes:
            lines.append("- Node tốn thời gian nhất: " + "; ".join(
                f"{n['node']} {n['seconds']:.0f}s/{n['calls']} lần/{n['tokens']:,} token" for n in slow_nodes))
        lines.append(f"- Tổng: {run.get('seconds', 0):.0f}s, {int(run.get('tokens') or 0):,} token")
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
