"""Workflow assistant: one chat turn with Claude, Codex or Gemini.

A turn builds the system prompt, calls the model once through a signed-in CLI connection, parses the
JSON reply and validates any proposed workflow. A proposal that fails validation is sent back to the
model for repair, at most ``MAX_REPAIRS`` times. The model has no tools and nothing here writes files:
the frontend saves a proposal only when the user applies it.

``run_turn`` is blocking; callers run it in a worker thread. The cancel scope is entered inside
``run_turn`` itself, i.e. in the thread that makes the provider call (the contextvar behind
``cli_cancel_scope`` does not cross threads).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import yaml

from agentdev.api.services.workflow_assistant_prompt import load_context, stable_prefix, turn_context, with_context
from agentdev.api.services.workflow_diff import diff_workflows, new_dangerous_tool_items, unrequested_changes
from agentdev.api.services.workflow_lab import FAIL, WARN, SimpleConfig, new_failures, static_check_data
from agentdev.api.services.workflow_patterns import proposal_lint
from agentdev.api.services.workflow_storage import validate_workflow_filename
from agentdev.api.settings import YAML_DIR
from agentdev.connections.resolver import ConnectionResolutionError
from agentdev.runtime.node.agent import account_fallback
from agentdev.runtime.node.agent.providers._cli_common import CliProviderError
from agentdev.runtime.node.agent.providers.cli_cancel import CliCancelled, cli_cancel_scope

logger = logging.getLogger(__name__)

VENDOR_LABELS = {"anthropic": "Claude", "openai": "Codex", "gemini": "Gemini"}
MAX_REPAIRS = 2
HISTORY_LIMIT = 40  # (20 turns) longer histories are trimmed
HISTORY_TAIL = 24  # messages kept, after the first user message, once trimmed
CALL_TIMEOUT = 180
MAX_QUICK_REPLIES = 4
MAX_CONCURRENT_TURNS = 4  # each turn runs a CLI for up to (MAX_REPAIRS + 1) x CALL_TIMEOUT
MAX_REQUEST_CHARS = 400_000  # sum of message contents and pending_yaml

ERROR_CODES = ("quota_exhausted", "not_signed_in", "timeout", "model_unavailable", "cancelled",
               "provider_error", "bad_request", "busy")

# A model call returns the reply text, or (text, usage) where usage is a dict with any of
# ``input_tokens``, ``output_tokens``, ``cache_read_tokens`` (None values when unknown).
ModelCall = Callable[[str, List[dict]], Union[str, Tuple[str, Optional[dict]]]]
INTENTS = ("ask", "explain", "propose")
USAGE_TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_read_tokens")


class AssistantError(Exception):
    """A turn that cannot produce a reply; ``code`` is one of ``ERROR_CODES``."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def content_hash(text: str) -> str:
    """sha256 hex of ``text`` with CRLF normalised to LF (so the hash ignores line-ending style)."""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------- providers


def _signed_in(conn: Any) -> bool:
    from agentdev.connections.catalog import AUTH_CLI, AUTH_OAUTH

    return getattr(conn, "auth_type", None) in (AUTH_CLI, AUTH_OAUTH)


def list_providers() -> List[dict]:
    """One entry per assistant vendor (always all of them), with the signed-in connection it would use."""
    from agentdev.connections.store import get_store

    store = get_store()
    default = store.default_connection()
    connections = [c for c in store.list() if _signed_in(c)]
    providers = []
    for vendor, label in VENDOR_LABELS.items():
        if default is not None and default.vendor == vendor and _signed_in(default):
            conn = default
        else:
            conn = next((c for c in connections if c.vendor == vendor), None)
        providers.append({
            "vendor": vendor,
            "label": label,
            "connection_id": conn.id if conn else None,
            "model": (account_fallback.default_model_for(conn) or None) if conn else None,
            "available": conn is not None,
        })
    return providers


def _int_or_none(value: Any) -> Optional[int]:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def usage_from_raw(raw: Any) -> Optional[dict]:
    """Token counts from a CLI provider's raw response, or None when it reports none.

    Claude CLI (``--output-format json``): ``usage.input_tokens`` counts only uncached input, so the
    total input is that plus cache writes and cache reads. Codex CLI: ``usage.input_tokens`` already
    includes ``cached_input_tokens``."""
    meta = getattr(raw, "usage_metadata", None)
    if meta is not None and not isinstance(raw, dict):  # Gemini SDK response
        return {"input_tokens": _int_or_none(getattr(meta, "prompt_token_count", None)),
                "output_tokens": _int_or_none(getattr(meta, "candidates_token_count", None)),
                "cache_read_tokens": _int_or_none(getattr(meta, "cached_content_token_count", None))}
    usage = raw.get("usage") if isinstance(raw, dict) else None
    if not isinstance(usage, dict) or not usage:
        return None
    if "cache_read_input_tokens" in usage or "cache_creation_input_tokens" in usage:
        parts = [_int_or_none(usage.get(k)) for k in
                 ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")]
        known = [p for p in parts if p is not None]
        input_tokens = sum(known) if known else None
        cache_read = _int_or_none(usage.get("cache_read_input_tokens"))
    else:
        input_tokens = _int_or_none(usage.get("input_tokens"))
        cache_read = _int_or_none(usage.get("cached_input_tokens"))
    return {"input_tokens": input_tokens, "output_tokens": _int_or_none(usage.get("output_tokens")),
            "cache_read_tokens": cache_read}


def _provider_call(connection_id: str, model: str) -> ModelCall:
    """A ``call(system, messages)`` that asks the given connection once (no tools), like the Lab judge.
    Returns ``(text, usage)``."""

    def call(system: str, messages: List[dict]) -> Tuple[str, Optional[dict]]:
        from agentdev.connections.resolver import resolve_connection
        from agentdev.entity.messages import Message, MessageRole
        from agentdev.runtime.node.agent import ProviderRegistry

        creds = resolve_connection(connection_id)
        provider_name = creds.provider or creds.vendor
        provider_class = ProviderRegistry.get_provider(provider_name)
        config = SimpleConfig(name=model, provider=provider_name, auth_token=creds.token,
                              base_url=creds.base_url or "", params={"timeout": CALL_TIMEOUT},
                              node_id="workflow_assistant")
        provider = provider_class(config)
        roles = {"user": MessageRole.USER, "assistant": MessageRole.ASSISTANT}
        history = [Message(role=MessageRole.SYSTEM, content=system)]
        history += [Message(role=roles[m["role"]], content=m["content"]) for m in messages]
        # The Gemini provider builds its request from the timeline; the CLI providers read the conversation.
        timeline = list(history) if provider_name == "gemini" else []
        response = provider.call_model(provider.create_client(), history, timeline)
        return response.message.text_content(), usage_from_raw(response.raw_response)

    return call


# ---------------------------------------------------------------------------- cancellation

_cancel_lock = threading.Lock()
_cancel_events: Dict[str, threading.Event] = {}


def cancel(request_id: str) -> bool:
    """Stop the running turn ``request_id`` (kills its CLI). False when no such turn is running."""
    with _cancel_lock:
        event = _cancel_events.get(request_id)
    if event is None:
        return False
    event.set()
    return True


def _is_timeout(exc: BaseException) -> bool:
    return isinstance(exc, (TimeoutError, subprocess.TimeoutExpired))


_MODEL_GONE_MARKERS = ("no longer available", "is not found for api version", "model not found")


def _is_model_unavailable(exc: BaseException) -> bool:
    """Gemini answers a retired or unknown model with HTTP 404 (``ClientError``/``APIError`` with code 404)."""
    seen = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current).lower()
        if getattr(current, "code", None) == 404 and type(current).__name__ in ("ClientError", "APIError"):
            return True
        if any(m in text for m in _MODEL_GONE_MARKERS):
            return True
        current = current.__cause__ or current.__context__
    return False


_SIGNED_OUT_MARKERS = ("not logged in", "not installed")


def _is_signed_out(exc: BaseException) -> bool:
    """The CLI providers report a logged-out or missing CLI as ``CliProviderError("... is not logged in:
    ...")`` / ``("... is not installed or not on PATH")``; look along the cause chain too."""
    seen = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, CliProviderError) and any(m in str(current).lower() for m in _SIGNED_OUT_MARKERS):
            return True
        if isinstance(current, ConnectionResolutionError):  # Gemini: sign-in expired or connection gone
            return True
        if type(current).__name__ in ("ClientError", "APIError") and getattr(current, "code", None) in (401, 403):
            return True  # Gemini: the OAuth token was rejected
        current = current.__cause__ or current.__context__
    return False


# What the browser sees for each failure. The raw provider text can hold CLI stderr, local paths and the
# account email, so it is only logged here.
_PUBLIC_MESSAGES = {
    "quota_exhausted": "The account has reached its usage limit.",
    "timeout": "The model took too long to answer.",
    "not_signed_in": "The CLI is not signed in or not installed.",
    "model_unavailable": "The selected model is no longer available. Pick another model or reconnect the account.",
    "provider_error": "The model call failed. Details are in the server log.",
}


def _provider_failure(code: str, exc: BaseException) -> AssistantError:
    logger.warning("Workflow assistant model call failed (%s): %s", code, exc)
    return AssistantError(code, _PUBLIC_MESSAGES[code])


def _guarded_call(call: ModelCall, system: str, messages: List[dict],
                  event: threading.Event) -> Tuple[str, Optional[dict]]:
    """Run one model call inside the cancel scope and map failures to ``AssistantError`` (with a short
    message safe to show in the browser; the provider's own text goes to the server log).
    Returns ``(text, usage or None)``."""
    if event.is_set():
        raise AssistantError("cancelled", "Stopped")
    try:
        with cli_cancel_scope(event):
            text = call(system, messages)
    except AssistantError:
        raise
    except CliCancelled as exc:
        raise AssistantError("cancelled", "Stopped") from exc
    except Exception as exc:  # noqa: BLE001 - every provider failure becomes a coded error
        if event.is_set():
            raise AssistantError("cancelled", "Stopped") from exc
        if account_fallback.is_quota_error(exc) or account_fallback.is_exhaustion_error(exc):
            raise _provider_failure("quota_exhausted", exc) from exc
        if _is_timeout(exc):
            raise _provider_failure("timeout", exc) from exc
        if _is_signed_out(exc):
            raise _provider_failure("not_signed_in", exc) from exc
        if _is_model_unavailable(exc):
            raise _provider_failure("model_unavailable", exc) from exc
        raise _provider_failure("provider_error", exc) from exc
    if event.is_set():
        raise AssistantError("cancelled", "Stopped")
    usage: Optional[dict] = None
    if isinstance(text, tuple):
        text, usage = text
    return text or "", usage if isinstance(usage, dict) else None


# ---------------------------------------------------------------------------- parsing

_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", re.DOTALL)
# Text that is meant to be the JSON reply: an object, a fenced object, or one naming the contract keys.
_JSON_LIKE_RE = re.compile(r'\A\s*(?:\{|```(?:json)?\s*\{)|"(?:reply|proposal)"\s*:')
# strict=False accepts raw control characters (real newlines) inside strings: models often write the
# YAML of ``proposal.yaml`` that way instead of with \n escapes.
_DECODER = json.JSONDecoder(strict=False)


def _json_object(text: str) -> Optional[dict]:
    """The reply object: the whole text, else a ```json fence, else the first object decoded from any
    "{" in the text that has a ``reply`` key (or the first object decoded at all)."""
    for candidate in [text.strip()] + [m.group(1) for m in _FENCE_RE.finditer(text)]:
        try:
            data = _DECODER.decode(candidate)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    first: Optional[dict] = None
    for match in re.finditer(r"\{", text):
        try:
            data, _ = _DECODER.raw_decode(text, match.start())
        except ValueError:
            continue
        if isinstance(data, dict):
            if "reply" in data:
                return data
            first = first if first is not None else data
    return first


def _json_error(text: str) -> str:
    """Why ``text``, which looks like the JSON reply, could not be used (a repair request line)."""
    stripped = text.strip()
    fence = _FENCE_RE.search(stripped)
    candidate = fence.group(1) if fence else re.sub(r"\A```(?:json)?\s*", "", stripped)
    try:
        _DECODER.decode(candidate)
        reason = "it has no `reply` or `proposal` key"
    except ValueError as exc:
        reason = str(exc)
    return f"Your reply was not valid JSON or was cut off ({reason})."


_TRAILING_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```\s*\Z", re.DOTALL)
_META_KEYS = {"intent", "quick_replies"}


def _trailing_meta(text: str) -> Optional[Tuple[str, dict]]:
    """(prose, meta) when ``text`` is a prose reply followed by a JSON object holding only ``intent`` /
    ``quick_replies`` (fenced or bare). Seen in a real run: the model answered in prose and then sent
    ```json {"intent": "explain"}``` on its own."""
    stripped = text.rstrip()
    fence = _TRAILING_FENCE_RE.search(stripped)
    if fence:
        start, payload = fence.start(), fence.group(1)
    else:
        start = stripped.rfind("{")
        payload = stripped[start:] if start >= 0 else ""
    try:
        data = _DECODER.decode(payload)
    except ValueError:
        return None
    prose = stripped[:start].strip()
    if not prose or not isinstance(data, dict) or not data or not set(data) <= _META_KEYS:
        return None
    return prose, data


def _parse(text: str) -> Tuple[dict, Optional[str]]:
    """(parsed reply, None), or (empty reply, error) when the text was meant as the JSON reply but is
    broken or truncated: showing it raw would put braces and escaped YAML in the chat bubble."""
    text = text or ""
    data = _json_object(text)
    if data is None or not ({"reply", "proposal"} & data.keys()):
        meta = _trailing_meta(text)
        if meta is not None:
            prose, data = meta
            data = {**data, "reply": prose, "proposal": None}
            return _parse(json.dumps(data, ensure_ascii=False))
        if _JSON_LIKE_RE.search(text):
            return {"reply": "", "quick_replies": [], "proposal": None, "intent": None}, _json_error(text)
        return {"reply": text.strip(), "quick_replies": [], "proposal": None, "intent": None}, None
    quick = data.get("quick_replies")
    quick_replies = [str(q) for q in quick if isinstance(q, (str, int, float)) and str(q).strip()] \
        if isinstance(quick, list) else []
    proposal = data.get("proposal")
    intent = data.get("intent")
    intent = intent.strip().lower() if isinstance(intent, str) else None
    return {
        "reply": str(data.get("reply") or ""),
        "quick_replies": quick_replies[:MAX_QUICK_REPLIES],
        "proposal": proposal if proposal not in (None, {}, "") else None,
        "intent": intent if intent in INTENTS else None,
    }, None


def parse_model_output(text: str) -> dict:
    """``{reply, quick_replies, proposal, intent}`` from the model's text (``intent``: "ask", "explain",
    "propose" or None when absent or unknown). Text that holds no JSON object is
    the reply itself (``proposal`` None), unless it was meant as the JSON reply and is broken: the reply
    is then empty. ``proposal`` is returned as sent (validated later)."""
    return _parse(text)[0]


# ---------------------------------------------------------------------------- validation


def _duplicate_edges(data: Any) -> List[Tuple[str, str]]:
    """(from, to) pairs that appear on more than one edge of ``graph.edges``, in first-seen order."""
    graph = data.get("graph") if isinstance(data, dict) else None
    edges = graph.get("edges") if isinstance(graph, dict) else None
    seen: Dict[Tuple[str, str], int] = {}
    for edge in edges if isinstance(edges, list) else []:
        if isinstance(edge, dict):
            pair = (str(edge.get("from")), str(edge.get("to")))
            seen[pair] = seen.get(pair, 0) + 1
    return [pair for pair, count in seen.items() if count > 1]


def _load_saved(saved_text: Optional[str]) -> Optional[dict]:
    """The saved workflow as a mapping, or None when there is none or it is broken (unparseable, or not
    a mapping): the diff then treats every proposed node as new. Never raises."""
    if saved_text is None:
        return None
    try:
        data = yaml.safe_load(saved_text)
    except Exception:  # noqa: BLE001 - YAMLError, or a pathological document (e.g. deep nesting)
        return None
    return data if isinstance(data, dict) else None


def _dangerous_tools_check(old: Optional[dict], data: Any) -> Optional[dict]:
    """A WARN check listing the commands, MCP servers and code execution a proposal adds (for an edit,
    only those new or changed versus the saved file). None when there is nothing to report."""
    items = new_dangerous_tool_items(old, data)
    if not items:
        return None
    detail = "; ".join(f"{i['node']}: {i['detail']}" for i in items)
    return {"id": "dangerous_tools", "status": WARN, "detail": detail, "items": items}


def _normalise_extension(filename: str) -> str:
    """``name.yml`` / ``name`` -> ``name.yaml``; anything else unchanged (it is validated next)."""
    if filename.lower().endswith(".yml"):
        return filename[:-4] + ".yaml"
    if filename and "." not in filename:
        return filename + ".yaml"
    return filename


def _check_proposal(raw: Any, workflow: Optional[str], saved_text: Optional[str], saved_doc: Optional[dict],
                    user_texts: List[str], vendor: Optional[str] = None) -> Tuple[Optional[dict], List[str]]:
    """(proposal for the client, []) when valid, else (None, errors to send back to the model).
    ``saved_doc`` is ``_load_saved(saved_text)``; ``user_texts`` every user message of the chat."""
    if not isinstance(raw, dict):
        return None, ["`proposal` must be an object with kind, filename and yaml, or null."]
    kind = raw.get("kind")
    filename = str(raw.get("filename") or "").strip()
    text = raw.get("yaml")
    if kind not in ("create", "edit"):
        return None, ['`proposal.kind` must be "create" or "edit".']
    if not isinstance(text, str) or not text.strip():
        return None, ["`proposal.yaml` must be the whole workflow YAML as a string."]

    # A missing or ``.yml`` extension is fixed here rather than costing a repair round trip (a whole
    # second model call that resends the full YAML).
    filename = _normalise_extension(filename)
    # A "create" that reuses the open workflow's own file name is an edit of it.
    if workflow and kind == "create" and filename == workflow:
        kind = "edit"

    # 1. File name.
    try:
        filename = validate_workflow_filename(filename, require_yaml_extension=True)
    except Exception as exc:  # noqa: BLE001 - ValidationError / SecurityError
        return None, [f"Invalid filename {filename!r}: {getattr(exc, 'message', exc)}. "
                      "Use letters, digits, dots, underscores and hyphens, ending in .yaml."]
    if not filename.endswith(".yaml"):
        return None, [f"Invalid filename {filename!r}: it must end in .yaml."]
    if kind == "create" and (Path(YAML_DIR) / filename).exists():
        return None, [f"A workflow named {filename!r} already exists. Choose a new file name."]
    if kind == "edit" and (not workflow or filename != workflow):
        target = f"the current workflow {workflow!r}" if workflow else "nothing (no workflow is open)"
        return None, [f'"edit" can only change {target}; use "create" for a new file.']

    # 2. YAML.
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return None, [f"Invalid YAML: {exc}"]

    # 2b. Deterministic fixes instead of a repair call. A create is re-dumped from the parsed data (comments
    # and anchors in a brand-new file are not worth a model round trip); an edit is verbatim, so only unknown
    # model names are replaced there, by text.
    fix_notes: List[str] = []
    if isinstance(data, dict):
        if kind == "create":
            for node_id, provider, name in proposal_lint.unknown_models(data):
                chat_vendor = provider if proposal_lint.default_model(provider) else (vendor or provider)
                new = proposal_lint.default_model(chat_vendor)
                if new:
                    node = next(n for n in proposal_lint._agents(data) if n.get("id") == node_id)
                    node["config"]["provider"], node["config"]["name"] = chat_vendor, new
                    fix_notes.append(f"{node_id}: unknown model `{name}` replaced by `{new}`.")
            fix_notes += proposal_lint.downgrade_cheap_nodes(data)
            changed = bool(fix_notes) | bool(proposal_lint.add_case_sensitive(data))
            if changed:
                text = proposal_lint.dump_workflow(data)
        else:
            text, fix_notes = proposal_lint.substitute_models_in_text(text, data, vendor)
            if fix_notes:
                data = yaml.safe_load(text)

    # 3. Static check. An ``accounts`` FAIL only means this machine has not bound a connection for a
    # provider yet; that is not the model's fault, so it does not fail the proposal. The UI shows it,
    # like every WARN check, from ``proposal.checks``.
    report = static_check_data(data)
    # Loops / gates already broken in the saved file are not the edit's doing (``new_failures``).
    old = saved_doc if kind == "edit" else None
    errors = [f"{c['id']}: {c.get('detail') or 'failed'}" for c in new_failures(report, old)]

    # 4. Duplicate edges. The runtime keeps one link per (from, to) pair, so a second edge between the
    # same nodes silently replaces the first. Pairs already duplicated in the saved file are left alone:
    # merging them would be an unrequested change.
    already = set(_duplicate_edges(old))
    errors += [f"edges: {src} → {dst} appears more than once; the runtime keeps only the last one. "
               "Merge them into one edge." for src, dst in _duplicate_edges(data) if (src, dst) not in already]
    if errors:
        return None, errors
    diff = diff_workflows(old, data)
    # Removed/changed nodes the user never named in any turn (edit only).
    warnings = list(unrequested_changes(diff, user_texts)) if kind == "edit" else []
    warnings += fix_notes
    lint_notes, extra_checks = proposal_lint.lint(data)
    if kind == "edit":  # problems already in the saved file are not the edit's doing
        before = set(proposal_lint.lint(old)[0]) if old else set()
        lint_notes = [n for n in lint_notes if n not in before]
    warnings += lint_notes
    report = {**report, "checks": report["checks"] + extra_checks}
    if report["status"] not in (FAIL, WARN) and any(c["status"] == WARN for c in extra_checks):
        report = {**report, "status": WARN}
    # Commands, MCP servers and code execution (independent of the unsafe-code switch on this machine).
    danger = _dangerous_tools_check(old, data)
    if danger is not None:
        report = {**report, "status": FAIL if report["status"] == FAIL else WARN,
                  "checks": report["checks"] + [danger]}
    return {
        "kind": kind,
        "filename": filename,
        "yaml": text,
        "base_hash": content_hash(saved_text) if kind == "edit" and saved_text is not None else None,
        "diff_summary": diff,
        "warnings": warnings,
        "checks": report,
    }, []


_REPAIR_FOOTER = "\nThe user does not see this check: your new `reply` replaces the previous one, so write " \
    "it for the user, in their language, as if it were your first answer, without mentioning the fix." \
    "\nReturn the corrected full JSON."


# Seen in a real run: on both "build it now" turns the reply said "see the card below, click Apply" but
# ``proposal`` was null. The contract's ``intent`` makes that detectable without matching phrases.
MISSING_PROPOSAL_ERROR = 'The reply said a proposal is attached (`intent: "propose"`) but `proposal` is null.'

# Without ``intent`` (legacy path, or the model forgot it) a reply can still tell the user to apply a card
# that is not there, and the older card then looks current. Only this narrow shape is repaired: an
# "apply" word together with a card word. ``intent: "ask"`` / ``"explain"`` turns are never touched.
_APPLY_RE = re.compile(r"\bap dung\b|\bapply\b")
_CARD_RE = re.compile(r"\bcard\b|\bproposal\b|\bban de xuat\b")


def _fold(text: str) -> str:
    """Lower case without Vietnamese accents (``Áp dụng`` -> ``ap dung``)."""
    decomposed = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def announces_card(reply: str) -> bool:
    """The reply tells the user to apply a proposal card (``bấm Áp dụng trên thẻ``, ``apply the card``)."""
    folded = _fold(reply)
    if not _APPLY_RE.search(folded):
        return False
    if _CARD_RE.search(folded) or "thẻ" in unicodedata.normalize("NFC", reply.lower()):
        return True
    # Unaccented "the" is "thẻ" only in a reply typed without any accents (otherwise it is "thế"/"the").
    return folded == reply.lower() and "ap dung" in folded and re.search(r"\bthe\b", folded) is not None


def _needs_proposal(parsed: dict) -> bool:
    if parsed["proposal"] is not None:
        return False
    if parsed["intent"] == "propose":
        return True
    return parsed["intent"] is None and announces_card(parsed["reply"])


_PROPOSAL_EXIT = ' If you were not proposing anything, return intent "ask" or "explain" and a reply that ' \
    "does not mention applying, with `proposal: null`."


def _repair_request(errors: List[str], *, bad_json: bool = False, missing_proposal: bool = False) -> str:
    # The user never sees this exchange: the corrected ``reply`` replaces the first one, so it must still
    # be written for them (seen in a real run: "Merged the duplicate connections..." in English).
    if bad_json:
        return errors[0] + " Return the complete JSON object (`reply`, `quick_replies`, `proposal`), with " \
            "newlines inside strings written as \\n. If the workflow is large, keep `reply` short." + \
            _REPAIR_FOOTER
    if missing_proposal:
        return 'You said you would propose (`intent: "propose"`) or told the user to apply a card, but ' \
            "`proposal` is null. Return the complete JSON including the proposal (`kind`, `filename`, the " \
            "whole `yaml`). If the workflow is large, keep `reply` short." + _PROPOSAL_EXIT + _REPAIR_FOOTER
    return "Your proposal failed validation:\n" + "\n".join(f"- {e}" for e in errors) + _REPAIR_FOOTER


# ---------------------------------------------------------------------------- turn


def _clean_messages(messages: Any) -> List[dict]:
    if not isinstance(messages, list) or not messages:
        raise AssistantError("bad_request", "messages must be a non-empty list")
    cleaned = []
    for m in messages:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant") \
                or not isinstance(m.get("content"), str):
            raise AssistantError("bad_request", "each message needs role user|assistant and string content")
        cleaned.append({"role": m["role"], "content": m["content"]})
    if cleaned[-1]["role"] != "user":
        raise AssistantError("bad_request", "the last message must come from the user")
    if not cleaned[-1]["content"].strip():
        raise AssistantError("bad_request", "the last message is empty")
    return cleaned


def _trim_history(messages: List[dict]) -> List[dict]:
    """Past ``HISTORY_LIMIT`` messages, keep the first user message (the original request) and the
    last ``HISTORY_TAIL`` ones."""
    if len(messages) <= HISTORY_LIMIT:
        return list(messages)
    tail = messages[-HISTORY_TAIL:]
    first_index = next(i for i, m in enumerate(messages) if m["role"] == "user")
    if first_index >= len(messages) - HISTORY_TAIL:
        return tail
    return [messages[first_index]] + tail


def _read_workflow(workflow: str) -> str:
    try:
        name = validate_workflow_filename(workflow, require_yaml_extension=True)
    except Exception as exc:  # noqa: BLE001
        raise AssistantError("bad_request", f"Invalid workflow name: {workflow}") from exc
    path = Path(YAML_DIR) / name
    if not path.is_file():
        raise AssistantError("bad_request", f"Workflow not found: {workflow}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise AssistantError("bad_request", f"The workflow file {name} is not UTF-8 text") from exc


def _add_usage(total: Optional[dict], usage: Optional[dict]) -> Optional[dict]:
    """Sum token counts over the calls of one turn; a count stays None while no call reported it."""
    if usage is None:
        return total
    total = dict(total or {k: None for k in USAGE_TOKEN_KEYS})
    for key in USAGE_TOKEN_KEYS:
        value = usage.get(key)
        if isinstance(value, int):
            total[key] = (total[key] or 0) + value
    return total


def _log_failed_turn(vendor: str, model: Optional[str], code: str, started: float, calls: int,
                     usage: Optional[dict]) -> None:
    """One line per failed or cancelled turn too (no user content): the calls made so far were paid for.
    Token counts are those of the calls that returned before the failure (None when none did)."""
    usage = usage or {}
    level = logging.INFO if code == "cancelled" else logging.WARNING
    logger.log(level, "Workflow assistant turn failed: vendor=%s model=%s code=%s calls=%d duration_ms=%d "
               "input_tokens=%s output_tokens=%s", vendor, model, code, calls,
               int((time.monotonic() - started) * 1000), usage.get("input_tokens"), usage.get("output_tokens"))


def run_turn(*, vendor: str, workflow: Optional[str], messages: List[dict], pending_yaml: Optional[str],
             request_id: str, call: Optional[ModelCall] = None) -> dict:
    """One chat turn: ``{reply, quick_replies, proposal, intent, model_used, validation_errors, usage}``;
    raises ``AssistantError``. ``validation_errors`` lists what was still wrong when the repair loop gave
    up (``proposal`` is then None); it is empty otherwise. ``intent`` is what the model said the turn
    does ("ask", "explain", "propose", or None when it did not say); a "propose" turn without a proposal
    is sent back for repair like an invalid proposal. ``usage``: ``{input_tokens, output_tokens,
    cache_read_tokens, duration_ms, calls}`` summed over the turn's model calls (repairs included);
    token counts are None when the provider does not report them.

    ``call`` replaces the provider (tests); ``model_used`` is then None. Blocking: run it in a worker
    thread. ``cancel(request_id)`` from another thread stops it with code ``cancelled``."""
    if vendor not in VENDOR_LABELS:
        raise AssistantError("bad_request", f"Unknown vendor: {vendor}")
    cleaned = _clean_messages(messages)
    if sum(len(m["content"]) for m in cleaned) + len(pending_yaml or "") > MAX_REQUEST_CHARS:
        raise AssistantError("bad_request", f"The request is too large (over {MAX_REQUEST_CHARS} characters)")
    history = _trim_history(cleaned)
    # Every user turn counts as a request: the diff is against the saved file, so a change asked for in an
    # earlier turn (still pending, not applied) is in it too. Taken before repair messages are appended.
    user_texts = [m["content"] for m in cleaned if m["role"] == "user"]
    # Read and parse the saved file before the (paid) model call, so a bad file fails or degrades here.
    saved_text = _read_workflow(workflow) if workflow else None
    saved_doc = _load_saved(saved_text)

    model_used: Optional[str] = None
    if call is None:
        provider = next(p for p in list_providers() if p["vendor"] == vendor)
        if not provider["available"]:
            raise AssistantError("not_signed_in", f"{provider['label']} is not signed in")
        # An empty model name is fine: the Claude/Codex CLI providers then omit ``--model`` and the CLI
        # uses its own default.
        model_used = provider["model"] or ""
        call = _provider_call(provider["connection_id"], model_used)

    # The system prompt is the same bytes on every turn (a prompt-cache hit); what varies per chat or turn
    # goes in front of the latest user message only (earlier turns are sent as the user wrote them).
    context = load_context()
    system = stable_prefix(skills=context["skills"], tools=context["tools"], models=context["models"])
    turn = turn_context(current_yaml=saved_text, current_name=workflow if workflow else None,
                        pending_yaml=pending_yaml or None, existing_files=context["existing_files"],
                        chat_vendor=vendor, user_text="\n".join(user_texts))
    history = history[:-1] + [{"role": "user", "content": with_context(history[-1]["content"], turn)}]

    event = threading.Event()
    with _cancel_lock:
        if request_id in _cancel_events:
            raise AssistantError("bad_request", f"Request {request_id} is already running")
        if len(_cancel_events) >= MAX_CONCURRENT_TURNS:
            raise AssistantError("busy", "Too many concurrent requests; try again when one has finished")
        _cancel_events[request_id] = event
    started = time.monotonic()
    usage: Optional[dict] = None
    calls = 0

    def finish(result: dict, outcome: str) -> dict:
        duration_ms = int((time.monotonic() - started) * 1000)
        turn_usage = {**(usage or {k: None for k in USAGE_TOKEN_KEYS}), "duration_ms": duration_ms,
                      "calls": calls}
        logger.info("Workflow assistant turn: vendor=%s model=%s prompt_chars=%d calls=%d duration_ms=%d "
                    "input_tokens=%s output_tokens=%s cache_read_tokens=%s intent=%s outcome=%s",
                    vendor, model_used, len(system) + len(turn), calls, duration_ms, turn_usage["input_tokens"],
                    turn_usage["output_tokens"], turn_usage["cache_read_tokens"], result.get("intent"), outcome)
        return {**result, "model_used": model_used, "usage": turn_usage}

    try:
        errors: List[str] = []
        for attempt in range(MAX_REPAIRS + 1):
            calls += 1  # counted before the call, so a failed or cancelled call is in the log line
            text, call_usage = _guarded_call(call, system, history, event)
            usage = _add_usage(usage, call_usage)
            parsed, json_error = _parse(text)
            missing = False
            if json_error is not None:
                # Broken or truncated JSON reply: never shown raw; the model resends it whole.
                errors, repair = [json_error], _repair_request([json_error], bad_json=True)
            elif parsed["proposal"] is None:
                if not _needs_proposal(parsed):
                    return finish({**parsed, "validation_errors": []}, "reply")
                # The reply announces a proposal card that is not there: ask for the proposal itself.
                missing = True
                errors, repair = [MISSING_PROPOSAL_ERROR], _repair_request([], missing_proposal=True)
            else:
                proposal, errors = _check_proposal(parsed["proposal"], workflow, saved_text, saved_doc,
                                                   user_texts, vendor)
                if proposal is not None:
                    return finish({**parsed, "proposal": proposal, "validation_errors": []}, "proposal")
                repair = _repair_request(errors)
            if attempt < MAX_REPAIRS:
                history = history + [{"role": "assistant", "content": text},
                                     {"role": "user", "content": repair}]
        if missing:
            # Gave up on a reply that points at a card that is not there: drop that reply (it would send
            # the user to an older card) and the internal English error; the UI then shows its localised
            # "could not answer" line for an empty reply.
            return finish({**parsed, "reply": "", "quick_replies": [], "proposal": None,
                           "validation_errors": []}, "gave_up")
        # Gave up: the UI shows its own (translated) header above ``validation_errors``.
        return finish({**parsed, "proposal": None, "validation_errors": errors}, "gave_up")
    except AssistantError as exc:
        _log_failed_turn(vendor, model_used, exc.code, started, calls, usage)
        raise
    except Exception:
        _log_failed_turn(vendor, model_used, "internal_error", started, calls, usage)
        raise
    finally:
        with _cancel_lock:
            if _cancel_events.get(request_id) is event:
                del _cancel_events[request_id]
