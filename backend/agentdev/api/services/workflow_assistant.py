"""Workflow assistant: one chat turn with Claude or Codex.

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
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from agentdev.api.services.workflow_assistant_prompt import build_system_prompt, load_context
from agentdev.api.services.workflow_diff import diff_workflows, new_dangerous_tool_items, unrequested_changes
from agentdev.api.services.workflow_lab import FAIL, WARN, SimpleConfig, static_check_data
from agentdev.api.services.workflow_storage import validate_workflow_filename
from agentdev.api.settings import YAML_DIR
from agentdev.runtime.node.agent import account_fallback
from agentdev.runtime.node.agent.providers._cli_common import CliProviderError
from agentdev.runtime.node.agent.providers.cli_cancel import CliCancelled, cli_cancel_scope

logger = logging.getLogger(__name__)

VENDOR_LABELS = {"anthropic": "Claude", "openai": "Codex"}
MAX_REPAIRS = 2
HISTORY_LIMIT = 40  # (20 turns) longer histories are trimmed
HISTORY_TAIL = 24  # messages kept, after the first user message, once trimmed
CALL_TIMEOUT = 180
MAX_QUICK_REPLIES = 4
MAX_CONCURRENT_TURNS = 4  # each turn runs a CLI for up to (MAX_REPAIRS + 1) x CALL_TIMEOUT
MAX_REQUEST_CHARS = 400_000  # sum of message contents and pending_yaml

ERROR_CODES = ("quota_exhausted", "not_signed_in", "timeout", "cancelled", "provider_error", "bad_request",
               "busy")

ModelCall = Callable[[str, List[dict]], str]


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
    """One entry per assistant vendor (always both), with the signed-in connection it would use."""
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


def _provider_call(connection_id: str, model: str) -> ModelCall:
    """A ``call(system, messages)`` that asks the given connection once (no tools), like the Lab judge."""

    def call(system: str, messages: List[dict]) -> str:
        from agentdev.connections.resolver import resolve_connection
        from agentdev.entity.messages import Message, MessageRole
        from agentdev.runtime.node.agent import ProviderRegistry

        creds = resolve_connection(connection_id)
        provider_name = creds.provider or creds.vendor
        provider_class = ProviderRegistry.get_provider(provider_name)
        config = SimpleConfig(name=model, provider=provider_name, api_key=creds.token,
                              base_url=creds.base_url or "", params={"timeout": CALL_TIMEOUT},
                              node_id="workflow_assistant")
        provider = provider_class(config)
        roles = {"user": MessageRole.USER, "assistant": MessageRole.ASSISTANT}
        history = [Message(role=MessageRole.SYSTEM, content=system)]
        history += [Message(role=roles[m["role"]], content=m["content"]) for m in messages]
        response = provider.call_model(provider.create_client(), history, [])
        return response.message.text_content()

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
        current = current.__cause__ or current.__context__
    return False


# What the browser sees for each failure. The raw provider text can hold CLI stderr, local paths and the
# account email, so it is only logged here.
_PUBLIC_MESSAGES = {
    "quota_exhausted": "The account has reached its usage limit.",
    "timeout": "The model took too long to answer.",
    "not_signed_in": "The CLI is not signed in or not installed.",
    "provider_error": "The model call failed. Details are in the server log.",
}


def _provider_failure(code: str, exc: BaseException) -> AssistantError:
    logger.warning("Workflow assistant model call failed (%s): %s", code, exc)
    return AssistantError(code, _PUBLIC_MESSAGES[code])


def _guarded_call(call: ModelCall, system: str, messages: List[dict], event: threading.Event) -> str:
    """Run one model call inside the cancel scope and map failures to ``AssistantError`` (with a short
    message safe to show in the browser; the provider's own text goes to the server log)."""
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
        raise _provider_failure("provider_error", exc) from exc
    if event.is_set():
        raise AssistantError("cancelled", "Stopped")
    return text or ""


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


def _parse(text: str) -> Tuple[dict, Optional[str]]:
    """(parsed reply, None), or (empty reply, error) when the text was meant as the JSON reply but is
    broken or truncated: showing it raw would put braces and escaped YAML in the chat bubble."""
    text = text or ""
    data = _json_object(text)
    if data is None or not ({"reply", "proposal"} & data.keys()):
        if _JSON_LIKE_RE.search(text):
            return {"reply": "", "quick_replies": [], "proposal": None}, _json_error(text)
        return {"reply": text.strip(), "quick_replies": [], "proposal": None}, None
    quick = data.get("quick_replies")
    quick_replies = [str(q) for q in quick if isinstance(q, (str, int, float)) and str(q).strip()] \
        if isinstance(quick, list) else []
    proposal = data.get("proposal")
    return {
        "reply": str(data.get("reply") or ""),
        "quick_replies": quick_replies[:MAX_QUICK_REPLIES],
        "proposal": proposal if proposal not in (None, {}, "") else None,
    }, None


def parse_model_output(text: str) -> dict:
    """``{reply, quick_replies, proposal}`` from the model's text. Text that holds no JSON object is
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


def _check_proposal(raw: Any, workflow: Optional[str], saved_text: Optional[str], saved_doc: Optional[dict],
                    user_texts: List[str]) -> Tuple[Optional[dict], List[str]]:
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

    # 3. Static check. An ``accounts`` FAIL only means this machine has not bound a connection for a
    # provider yet; that is not the model's fault, so it does not fail the proposal. The UI shows it,
    # like every WARN check, from ``proposal.checks``.
    report = static_check_data(data)
    errors = [f"{c['id']}: {c.get('detail') or 'failed'}" for c in report["checks"]
              if c["status"] == FAIL and c["id"] != "accounts"]
    old = saved_doc if kind == "edit" else None

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


def _repair_request(errors: List[str], *, bad_json: bool = False) -> str:
    # The user never sees this exchange: the corrected ``reply`` replaces the first one, so it must still
    # be written for them (seen in a real run: "Merged the duplicate connections..." in English).
    if bad_json:
        return errors[0] + " Return the complete JSON object (`reply`, `quick_replies`, `proposal`), with " \
            "newlines inside strings written as \\n. If the workflow is large, keep `reply` short." + \
            _REPAIR_FOOTER
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


def run_turn(*, vendor: str, workflow: Optional[str], messages: List[dict], pending_yaml: Optional[str],
             request_id: str, call: Optional[ModelCall] = None) -> dict:
    """One chat turn: ``{reply, quick_replies, proposal, model_used, validation_errors}``; raises
    ``AssistantError``. ``validation_errors`` lists what was still wrong when the repair loop gave up
    (``proposal`` is then None); it is empty otherwise.

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

    system = build_system_prompt(current_yaml=saved_text, current_name=workflow if workflow else None,
                                 pending_yaml=pending_yaml or None, chat_vendor=vendor, **load_context())

    event = threading.Event()
    with _cancel_lock:
        if request_id in _cancel_events:
            raise AssistantError("bad_request", f"Request {request_id} is already running")
        if len(_cancel_events) >= MAX_CONCURRENT_TURNS:
            raise AssistantError("busy", "Too many concurrent requests; try again when one has finished")
        _cancel_events[request_id] = event
    try:
        errors: List[str] = []
        for attempt in range(MAX_REPAIRS + 1):
            text = _guarded_call(call, system, history, event)
            parsed, json_error = _parse(text)
            if json_error is not None:
                # Broken or truncated JSON reply: never shown raw; the model resends it whole.
                errors, repair = [json_error], _repair_request([json_error], bad_json=True)
            elif parsed["proposal"] is None:
                return {**parsed, "model_used": model_used, "validation_errors": []}
            else:
                proposal, errors = _check_proposal(parsed["proposal"], workflow, saved_text, saved_doc,
                                                   user_texts)
                if proposal is not None:
                    return {**parsed, "proposal": proposal, "model_used": model_used, "validation_errors": []}
                repair = _repair_request(errors)
            if attempt < MAX_REPAIRS:
                history = history + [{"role": "assistant", "content": text},
                                     {"role": "user", "content": repair}]
        # Gave up: the UI shows its own (translated) header above ``validation_errors``.
        return {**parsed, "proposal": None, "model_used": model_used, "validation_errors": errors}
    finally:
        with _cancel_lock:
            if _cancel_events.get(request_id) is event:
                del _cancel_events[request_id]
