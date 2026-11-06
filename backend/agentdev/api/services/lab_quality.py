"""Lab quality rubric: grade a run on several dimensions, not only "did it pass and how long did it take".

The judge scores six dimensions (requirements, correctness, craft, verification, communication, effort_fit), says
how big the request is (``scope``), lists the requirements it found unmet and suggests fixes. This module holds the
rubric text for the judge, the parsing of its answer, the scope-based time/token budgets and the per-dimension fix
directions that go into the brief for the workflow assistant.

Pure functions (no I/O). Finding texts are Vietnamese like the rest of the Lab diagnosis (see lab_diagnosis.py).
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

DIMENSIONS = ("requirements", "correctness", "craft", "verification", "communication", "effort_fit")
# A run whose answer misses the request or does not work fails, whatever its overall score.
CORE_DIMENSIONS = ("requirements", "correctness")
CORE_MIN = 6.0
WEAK_BELOW = 7.0  # a dimension averaging under this across the job gets its own finding + fix direction
POOR_BELOW = 5.0  # a dimension averaging under this blocks the "ready" verdict

DOMAINS = ("code", "video", "content", "general")
SCOPES = ("small", "medium", "large")
# Time / fresh-token budget of one run by the size of the request (the judge estimates the size).
SCOPE_SECONDS = {"small": 120, "medium": 300, "large": 900}
SCOPE_TOKENS = {"small": 40_000, "medium": 150_000, "large": 400_000}
# A large request finished in under this share of its budget while missing requirements was done too quickly.
SHALLOW_SHARE = 0.25

NOTE_CHARS = 300
MAX_FIXES = 3
MAX_MISSING = 6

DIMENSION_LABELS = {
    "requirements": "Khớp và đủ yêu cầu",
    "correctness": "Đúng / chạy được",
    "craft": "Chất lượng chuyên môn",
    "verification": "Có kiểm chứng",
    "communication": "Trình bày, ngôn ngữ",
    "effort_fit": "Độ sâu so với quy mô",
}

_VIDEO = re.compile(r"\b(video|clip|tiktok|reels?|shorts?|youtube|storyboard|kịch bản|phân cảnh|cảnh quay|"
                    r"voice ?over|lồng tiếng|dựng phim|veo|render|quảng cáo)\b|视频|分镜|脚本", re.IGNORECASE)
_CODE = re.compile(r"\b(code|app|website|web|api|backend|frontend|react|vue|python|javascript|typescript|node|"
                   r"html|css|sql|database|bug|fix|test|deploy|repo|script|cli|lập trình|phần mềm|ứng dụng|"
                   r"sửa lỗi|chức năng|trang web|dev|developer|software)\b|代码|程序|应用|网站|修复", re.IGNORECASE)
_CONTENT = re.compile(r"\b(bài viết|blog|báo cáo|report|tài liệu|document|nghiên cứu|research|tóm tắt|summary|"
                      r"email|marketing|content|nội dung|kế hoạch|plan|phân tích|analysis|seo)\b|文章|报告|文档",
                      re.IGNORECASE)


def task_domain(prompt: str, workflow_hint: str = "") -> str:
    """What kind of deliverable the request is about: the request decides first, the workflow breaks a tie."""
    for text in (prompt or "", workflow_hint or ""):
        hits = {name: len(rx.findall(text)) for name, rx in (("video", _VIDEO), ("code", _CODE), ("content", _CONTENT))}
        best = max(hits, key=lambda k: hits[k])
        if hits[best]:
            return best
    return "general"


_CRAFT = {
    "code": ("code quality: clear structure and names, input validation and error handling, no placeholder/TODO/"
             "stub or fake data where real logic was asked, no secrets or injection holes, dependencies declared, "
             "meaningful tests, a run command or README; uses the stack the request names; an app with a login ships "
             "a working demo account and the reply states the login page, username and password (see Run facts)"),
    "video": ("video craft: the script fits the requested length, tone and audience; a shot/scene list whose timings "
              "add up to the target duration; a hook in the first seconds and a clear ending/CTA; concrete, "
              "consistent visual prompts (same characters, style, brand); voice-over/subtitle text ready to use. A "
              "render skipped at a PAID gate is not a defect"),
    "content": ("writing craft: accurate facts (sources for claims), a clear structure, the requested length and "
                "tone, actionable and specific rather than generic filler"),
    "general": "professional quality of the deliverable for its kind: accurate, specific, no generic filler",
}

_RUBRIC = (
    "Grade these dimensions 0-10 each:\n"
    "- requirements: list every explicit requirement of the request (features, counts, length, format, stack, "
    "language) and check each one; any unmet one goes into \"missing\".\n"
    "- correctness: the deliverable is right and would work as delivered (code runs, numbers add up, facts true).\n"
    "- craft: {craft}.\n"
    "- verification: what was checked is shown (commands run and their result, files produced), not just claimed.\n"
    "- communication: the user's language, clear, honest about limits, no padding.\n"
    "- effort_fit: estimate the request's scope (small = one quick reply or file, medium = a few files or parts, "
    "large = a whole app, a multi-scene video, a long document). Compare with the run facts: a large request finished "
    "fast with a thin or partial result scores low; a small request that ran a long pipeline or took many minutes "
    "scores low too.\n"
    "The overall score follows the weakest important dimension: never 7 or more while requirements or correctness "
    "is under 6."
)

REPLY_FORMAT = (
    '{"pass": true|false, "score": 0-10, "reason": "<one or two sentences>", "scope": "small|medium|large", '
    '"dimensions": {"requirements": {"score": 0-10, "note": "<short>"}, "correctness": {...}, "craft": {...}, '
    '"verification": {...}, "communication": {...}, "effort_fit": {...}}, '
    '"missing": ["<unmet requirement>"], "fixes": ["<what the WORKFLOW (its roles, steps, checks) should change>"]}'
)


def rubric_text(domain: str) -> str:
    """The rubric section of the judge message for a kind of task (stable per scenario: prompt-cache friendly)."""
    return _RUBRIC.format(craft=_CRAFT.get(domain, _CRAFT["general"]))


def _score(value: Any) -> Optional[float]:
    if isinstance(value, dict):
        value = value.get("score")
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        match = re.match(r"\s*(\d+(?:\.\d+)?)", str(value))
        if not match:
            return None
        number = float(match.group(1))
    if 10 < number <= 100:
        number /= 10
    return max(0.0, min(10.0, number))


def parse_dimensions(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """The judge's per-dimension scores, cleaned: only known keys with a usable 0-10 score."""
    raw = data.get("dimensions") if isinstance(data, dict) else None
    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(raw, dict):
        return out
    for key in DIMENSIONS:
        item = raw.get(key)
        value = _score(item)
        if value is None:
            continue
        note = str(item.get("note") or "").strip()[:NOTE_CHARS] if isinstance(item, dict) else ""
        out[key] = {"score": round(value, 1), "note": note}
    return out


def _texts(value: Any, limit: int) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(v).strip()[:NOTE_CHARS] for v in value if str(v or "").strip()][:limit]


def quality_fields(data: Dict[str, Any], domain: str) -> Dict[str, Any]:
    """What the verdict keeps from the judge's rubric answer (empty dims when the judge gave none)."""
    scope = str((data or {}).get("scope") or "").strip().lower()
    return {
        "domain": domain if domain in DOMAINS else "general",
        "scope": scope if scope in SCOPES else "",
        "dimensions": parse_dimensions(data or {}),
        "missing": _texts((data or {}).get("missing"), MAX_MISSING),
        "fixes": _texts((data or {}).get("fixes"), MAX_FIXES),
    }


def core_gate_failed(dimensions: Dict[str, Dict[str, Any]]) -> List[str]:
    """Core dimensions under CORE_MIN: such a run cannot pass even with a good overall score."""
    return [k for k in CORE_DIMENSIONS if k in dimensions and dimensions[k]["score"] < CORE_MIN]


def scope_budget(scope: str) -> Optional[Dict[str, int]]:
    """Seconds/tokens a run of this size may use, or None when the size is unknown."""
    if scope not in SCOPES:
        return None
    return {"seconds": SCOPE_SECONDS[scope], "tokens": SCOPE_TOKENS[scope]}


# Direction for the workflow assistant per weak dimension and kind of task: what to change IN THE WORKFLOW.
_FIX = {
    "requirements": {
        "*": ("Thêm bước tách yêu cầu thành danh sách kiểm (checklist) ở đầu quy trình (người lập kế hoạch), truyền "
              "danh sách đó cho người làm, và cho người duyệt cuối đối chiếu TỪNG mục trước khi kết thúc; mục nào "
              "chưa làm thì quay lại sửa (vòng có giới hạn) hoặc nói rõ trong câu trả lời."),
    },
    "correctness": {
        "code": ("Bắt người viết code chạy thử (build/test/chạy lệnh) trước khi bàn giao và sửa đến khi chạy được; "
                 "thêm node kiểm thử chạy lệnh thật (run_shell_command/execute_code) thay vì chỉ đọc code."),
        "video": ("Cho người duyệt kiểm tra tính nhất quán: tổng thời lượng các cảnh = thời lượng yêu cầu, nhân vật/"
                  "bối cảnh khớp giữa các cảnh, lời thoại khớp hình."),
        "*": "Thêm bước tự kiểm tra kết quả (số liệu, sự thật, logic) trước khi trả lời; người duyệt phải chỉ ra lỗi cụ thể.",
    },
    "craft": {
        "code": ("Viết rõ chuẩn code trong role của dev và reviewer: cấu trúc module, đặt tên, xử lý lỗi và kiểm tra "
                 "đầu vào, không để TODO/stub/dữ liệu giả, không lộ secret, có test và README/lệnh chạy; reviewer "
                 "dùng đúng danh sách này để duyệt và dùng model mạnh hơn cho bước viết code."),
        "video": ("Viết rõ chuẩn kịch bản trong role biên kịch/đạo diễn: hook 3 giây đầu, danh sách cảnh có thời lượng, "
                  "prompt hình ảnh cụ thể và nhất quán (nhân vật, phong cách, thương hiệu), lời thoại/phụ đề dùng được "
                  "ngay, kết có CTA; người duyệt chấm theo đúng danh sách này."),
        "content": ("Viết rõ chuẩn nội dung trong role người viết và người duyệt: đúng độ dài và giọng văn, có nguồn "
                    "cho số liệu, cấu trúc rõ, cụ thể thay vì chung chung."),
        "*": "Nêu tiêu chuẩn chất lượng cụ thể trong role người làm và người duyệt; người duyệt chấm theo tiêu chuẩn đó.",
    },
    "verification": {
        "code": ("Yêu cầu câu trả lời cuối có dòng 'Đã kiểm chứng: <lệnh> → <kết quả>' cho build/test thật; cấp cho "
                 "người kiểm thử công cụ chạy lệnh và cấm báo 'đã chạy' khi chưa chạy."),
        "*": "Yêu cầu câu trả lời cuối nêu đã kiểm tra gì và kết quả (file đã tạo, lệnh đã chạy), không chỉ khẳng định.",
    },
    "communication": {
        "*": ("Người trả lời cuối dùng đúng ngôn ngữ của người dùng, tóm tắt ngắn: đã làm gì, ở đâu (file), cách dùng, "
              "giới hạn còn lại; không để node lưu/hệ thống trả lời thay."),
    },
    "effort_fit": {
        "*": ("Chia nhánh theo quy mô: việc nhỏ đi đường ngắn (1 agent, model nhẹ); việc lớn mới qua kế hoạch → làm → "
              "kiểm thử → duyệt, chia thành các phần làm song song khi độc lập và không bỏ phần nào của yêu cầu."),
    },
}


def fix_direction(dimension: str, domain: str) -> str:
    table = _FIX.get(dimension) or {}
    return table.get(domain) or table.get("*", "")


def _judged_with_dims(runs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for run in runs:
        judge = run.get("judge") or {}
        if run.get("status") in ("passed", "failed") and judge.get("judged_by") == "ai" and judge.get("dimensions"):
            out.append(run)
    return out


def quality_profile(runs: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Average of every dimension over the AI-graded runs, the weakest first; None when no run has dimensions."""
    graded = _judged_with_dims(runs)
    if not graded:
        return None
    averages: Dict[str, float] = {}
    for key in DIMENSIONS:
        values = [r["judge"]["dimensions"][key]["score"] for r in graded if key in r["judge"]["dimensions"]]
        if values:
            averages[key] = round(sum(values) / len(values), 1)
    domains = [r["judge"].get("domain") for r in graded if r["judge"].get("domain")]
    scopes = [r["judge"].get("scope") for r in graded if r["judge"].get("scope")]
    return {
        "runs": len(graded),
        "domain": max(set(domains), key=domains.count) if domains else "general",
        "scope": max(set(scopes), key=scopes.count) if scopes else "",
        "dimensions": averages,
        "weak": [k for k, v in sorted(averages.items(), key=lambda kv: kv[1]) if v < WEAK_BELOW],
        "poor": [k for k, v in averages.items() if v < POOR_BELOW],
    }


def quality_findings(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Job-level findings: one per weak dimension (with the worst run's note, the judge's own fixes and a direction
    for the workflow), plus a "done too fast for its size" finding per run that skipped parts of a large request."""
    profile = quality_profile(runs)
    findings: List[Dict[str, Any]] = []
    if profile:
        graded = _judged_with_dims(runs)
        domain = profile["domain"]
        for key in profile["weak"]:
            scored = [r for r in graded if key in r["judge"]["dimensions"]]
            worst = min(scored, key=lambda r: r["judge"]["dimensions"][key]["score"])
            note = worst["judge"]["dimensions"][key]["note"]
            judge_fixes = list(dict.fromkeys(f for r in scored if r["judge"]["dimensions"][key]["score"] < WEAK_BELOW
                                             for f in r["judge"].get("fixes") or []))[:2]
            fix = fix_direction(key, domain)
            if judge_fixes:
                fix += " Giám khảo gợi ý: " + " | ".join(judge_fixes)
            findings.append({
                "code": f"weak_{key}",
                "kind": "quality",
                "dimension": key,
                "severity": "fail" if profile["dimensions"][key] < POOR_BELOW else "warn",
                "layer": "workflow",
                "scenario": None,
                "repeat": None,
                "detail": (f"Tiêu chí \"{DIMENSION_LABELS[key]}\" trung bình {profile['dimensions'][key]:g}/10 "
                           f"trên {len(scored)} lượt" + (f"; ví dụ: {note}" if note else "") + "."),
                "fix": fix,
            })
    for run in runs:
        judge = run.get("judge") or {}
        budget = scope_budget(judge.get("scope") or "")
        if judge.get("scope") != "large" or not budget or not judge.get("missing"):
            continue
        seconds = float(run.get("seconds") or 0)
        if 0 < seconds < budget["seconds"] * SHALLOW_SHARE:
            findings.append({
                "code": "shallow_for_scope",
                "kind": "quality",
                "severity": "warn",
                "layer": "workflow",
                "scenario": run.get("scenario"),
                "repeat": run.get("repeat"),
                "detail": (f"Yêu cầu lớn nhưng xong sau {seconds:.0f}s và còn thiếu: "
                           + "; ".join(judge["missing"][:3]) + "."),
                "fix": ("Quy trình làm qua loa với việc lớn: người lập kế hoạch phải tách đủ các phần của yêu cầu, "
                        "người làm hoàn thành từng phần và người duyệt chặn bàn giao khi còn phần chưa làm."),
            })
    return findings


def verdict_reasons(profile: Optional[Dict[str, Any]]) -> List[str]:
    """Reasons that block "ready": a dimension averaging under POOR_BELOW."""
    if not profile:
        return []
    return [f"Tiêu chí \"{DIMENSION_LABELS[k]}\" trung bình {profile['dimensions'][k]:g}/10 (dưới {POOR_BELOW:g})."
            for k in DIMENSIONS if k in profile["poor"]]


def brief_section(profile: Optional[Dict[str, Any]]) -> List[str]:
    """Lines for the fix brief: the score of every dimension, weakest first."""
    if not profile or not profile["dimensions"]:
        return []
    lines = ["", f"### Chất lượng theo tiêu chí (TB {profile['runs']} lượt, loại việc: {profile['domain']}"
             + (f", quy mô: {profile['scope']}" if profile["scope"] else "") + ")"]
    for key, value in sorted(profile["dimensions"].items(), key=lambda kv: kv[1]):
        mark = " ← cần sửa" if key in profile["weak"] else ""
        lines.append(f"- {DIMENSION_LABELS[key]}: {value:g}/10{mark}")
    return lines


def run_brief_lines(judge: Dict[str, Any]) -> List[str]:
    """Per-run lines for the fix brief: unmet requirements and the judge's suggested changes."""
    lines = []
    if judge.get("missing"):
        lines.append("- Yêu cầu chưa đáp ứng: " + "; ".join(judge["missing"]))
    dims = judge.get("dimensions") or {}
    weak = [f"{DIMENSION_LABELS[k]} {dims[k]['score']:g}" for k in DIMENSIONS if k in dims and dims[k]["score"] < WEAK_BELOW]
    if weak:
        lines.append("- Tiêu chí yếu: " + ", ".join(weak))
    if judge.get("fixes"):
        lines.append("- Giám khảo đề xuất: " + " | ".join(judge["fixes"]))
    return lines
