"""File and process tools must keep the user's files and Vietnamese text intact on Windows."""

import sys
from pathlib import Path

import pytest

from agentdev.utils.attachments import AttachmentStore
from functions.function_calling import code_executor, file as file_tools


def _ctx(root: Path) -> dict:
    store = AttachmentStore(root.parent / (root.name + "_store"))
    return {"python_workspace_root": str(root), "graph_directory": str(root), "attachment_store": store}


@pytest.mark.parametrize("original,expected", [
    (b"a\r\nb\r\nc\r\n", b"a\r\nX\r\nc\r\n"),       # CRLF stays CRLF (it became CR CR LF)
    (b"a\nb\nc\n", b"a\nX\nc\n"),                     # LF stays LF
    ("a\nb\nc\n".encode("utf-8-sig"), "a\nX\nc\n".encode("utf-8-sig")),  # a real BOM is kept
])
def test_apply_text_edits_keeps_line_endings_and_bom(tmp_path, original, expected):
    (tmp_path / "f.md").write_bytes(original)
    file_tools.apply_text_edits("f.md", start_line=2, end_line=2, replacement="X", _context=_ctx(tmp_path))
    assert (tmp_path / "f.md").read_bytes() == expected


def test_apply_text_edits_does_not_add_a_bom_to_plain_utf8(tmp_path):
    (tmp_path / "f.md").write_bytes("Tập đoàn\nviệt\n".encode("utf-8"))
    file_tools.apply_text_edits("f.md", start_line=2, end_line=2, replacement="Việt Nam", _context=_ctx(tmp_path))
    data = (tmp_path / "f.md").read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf") and data.decode("utf-8") == "Tập đoàn\nViệt Nam\n"


def test_code_executor_prints_vietnamese(monkeypatch):
    monkeypatch.setenv("MAC_ALLOW_UNSAFE_CODE_EXECUTION", "1")
    result = code_executor.execute_code('print("Tập đoàn việt")')
    text = result if isinstance(result, str) else str(result)
    assert "Tập đoàn việt" in text and "UnicodeEncodeError" not in text
