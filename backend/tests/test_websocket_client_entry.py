"""The socket copy of a log entry is light: no model prompt, long call texts clipped."""

from agentdev.api.services.websocket_logger import client_entry


def _entry(kind, details):
    return {"timestamp": "t", "level": "INFO", "node_id": "CTO", "event_type": kind, "message": "m", "details": details}


def test_model_call_drops_prompt_and_keeps_what_the_page_reads():
    out = client_entry(_entry("MODEL_CALL", {"input": "x" * 400_000, "output": "y" * 9000, "stage": "after",
                                            "model_name": "claude-opus-5-5"}))
    details = out["details"]
    assert "input" not in details
    assert details["stage"] == "after" and details["model_name"] == "claude-opus-5-5"
    assert len(details["output"]) < 2100


def test_tool_call_clips_file_contents_but_keeps_short_arguments():
    out = client_entry(_entry("TOOL_CALL", {"tool_name": "save_file", "stage": "before",
                                           "arguments": {"path": "docs/design.md", "content": "z" * 50_000}}))
    args = out["details"]["arguments"]
    assert args["path"] == "docs/design.md" and len(args["content"]) < 2100


def test_node_end_reply_is_untouched():
    reply = "a" * 50_000
    entry = _entry("NODE_END", {"output": reply})
    assert client_entry(entry)["details"]["output"] == reply


def test_original_entry_is_not_mutated():
    details = {"input": "p" * 10, "stage": "before"}
    client_entry(_entry("MODEL_CALL", details))
    assert "input" in details
