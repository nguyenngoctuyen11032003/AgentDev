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
import re
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from agentdev.api.services.workflow_assistant_prompt import build_system_prompt, load_context
from agentdev.api.services.workflow_diff import diff_workflows, unrequested_changes
from agentdev.api.services.workflow_lab import FAIL, SimpleConfig, static_check_data
from agentdev.api.services.workflow_storage import validate_workflow_filename
from agentdev.api.settings import YAML_DIR
from agentdev.runtime.node.agent import account_fallback
from agentdev.runtime.node.agent.providers.cli_cancel import CliCancelled, cli_cancel_scope

VENDOR_LABELS = {"anthropic": "Claude", "openai": "Codex"}
MAX_REPAIRS = 2
HISTORY_LIMIT = 40  # (20 turns) longer histories are trimmed
HISTORY_TAIL = 24  # messages kept, after the first user message, once trimmed
CALL_TIMEOUT = 180
MAX_QUICK_REPLIES = 4

ERROR_CODES = ("quota_exhausted", "not_signed_in", "timeout", "cancelled", "provider_error", "bad_request")

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


def _guarded_call(call: ModelCall, system: str, messages: List[dict], event: threading.Event) -> str:
    """Run one model call inside the cancel scope and map failures to ``AssistantError``."""
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
            raise AssistantError("quota_exhausted", str(exc)) from exc
        if _is_timeout(exc):
            raise AssistantError("timeout", str(exc)) from exc
        raise AssistantError("provider_error", str(exc)) from exc
    if event.is_set():
        raise AssistantError("cancelled", "Stopped")
    return text or ""


# ---------------------------------------------------------------------------- parsing

_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n\s*```", re.DOTALL)


def _json_object(text: str) -> Optional[dict]:
    """The reply object: the whole text, else a ```json fence, else the first object decoded from any
    "{" in the text that has a ``reply`` key (or the first object decoded at all)."""
    for candidate in [text.strip()] + [m.group(1) for m in _FENCE_RE.finditer(text)]:
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    decoder = json.JSONDecoder()
    first: Optional[dict] = None
    for match in re.finditer(r"\{", text):
        try:
            data, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        if isinstance(data, dict):
            if "reply" in data:
                return data
            first = first if first is not None else data
    return first


def parse_model_output(text: str) -> dict:
    """``{reply, quick_replies, proposal}`` from the model's text. Text that holds no JSON object is
    the reply itself (``proposal`` None). ``proposal`` is returned as sent (validated later)."""
    data = _json_object(text or "")
    if data is None or not ({"reply", "proposal"} & data.keys()):
        return {"reply": (text or "").strip(), "quick_replies": [], "proposal": None}
    quick = data.get("quick_replies")
    quick_replies = [str(q) for q in quick if isinstance(q, (str, int, float)) and str(q).strip()] \
        if isinstance(quick, list) else []
    proposal = data.get("proposal")
    return {
        "reply": str(data.get("reply") or ""),
        "quick_replies": quick_replies[:MAX_QUICK_REPLIES],
        "proposal": proposal if proposal not in (None, {}, "") else None,
    }


# ---------------------------------------------------------------------------- validation


def _check_proposal(raw: Any, workflow: Optional[str], saved_text: Optional[str],
                    last_user_text: str) -> Tuple[Optional[dict], List[str]]:
    """(proposal for the client, []) when valid, else (None, errors to send back to the model)."""
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
    if errors:
        return None, errors

    old = None
    if kind == "edit" and saved_text is not None:
        try:
            old = yaml.safe_load(saved_text)
        except yaml.YAMLError:
            old = None  # a broken saved file: diff as if every node were new
    diff = diff_workflows(old if isinstance(old, dict) else None, data)
    # Removed/changed nodes the user never named (edit only).
    warnings = list(unrequested_changes(diff, last_user_text)) if kind == "edit" else []
    return {
        "kind": kind,
        "filename": filename,
        "yaml": text,
        "base_hash": content_hash(saved_text) if kind == "edit" and saved_text is not None else None,
        "diff_summary": diff,
        "warnings": warnings,
        "checks": report,
    }, []


def _repair_request(errors: List[str]) -> str:
    return "Your proposal failed validation:\n" + "\n".join(f"- {e}" for e in errors) + \
        "\nReturn the corrected full JSON."


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
    return path.read_text(encoding="utf-8")


def run_turn(*, vendor: str, workflow: Optional[str], messages: List[dict], pending_yaml: Optional[str],
             request_id: str, call: Optional[ModelCall] = None) -> dict:
    """One chat turn: ``{reply, quick_replies, proposal, model_used, validation_errors}``; raises
    ``AssistantError``. ``validation_errors`` lists what was still wrong when the repair loop gave up
    (``proposal`` is then None); it is empty otherwise.

    ``call`` replaces the provider (tests); ``model_used`` is then None. Blocking: run it in a worker
    thread. ``cancel(request_id)`` from another thread stops it with code ``cancelled``."""
    if vendor not in VENDOR_LABELS:
        raise AssistantError("bad_request", f"Unknown vendor: {vendor}")
    history = _trim_history(_clean_messages(messages))
    saved_text = _read_workflow(workflow) if workflow else None

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
    last_user_text = history[-1]["content"]

    event = threading.Event()
    with _cancel_lock:
        if request_id in _cancel_events:
            raise AssistantError("bad_request", f"Request {request_id} is already running")
        _cancel_events[request_id] = event
    try:
        errors: List[str] = []
        for attempt in range(MAX_REPAIRS + 1):
            text = _guarded_call(call, system, history, event)
            parsed = parse_model_output(text)
            if parsed["proposal"] is None:
                return {**parsed, "model_used": model_used, "validation_errors": []}
            proposal, errors = _check_proposal(parsed["proposal"], workflow, saved_text, last_user_text)
            if proposal is not None:
                return {**parsed, "proposal": proposal, "model_used": model_used, "validation_errors": []}
            if attempt < MAX_REPAIRS:
                history = history + [{"role": "assistant", "content": text},
                                     {"role": "user", "content": _repair_request(errors)}]
        # Gave up: the UI shows its own (translated) header above ``validation_errors``.
        return {**parsed, "proposal": None, "model_used": model_used, "validation_errors": errors}
    finally:
        with _cancel_lock:
            if _cancel_events.get(request_id) is event:
                del _cancel_events[request_id]
