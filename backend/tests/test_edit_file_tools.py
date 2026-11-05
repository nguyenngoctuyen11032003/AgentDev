"""edit_file / multi_edit: content-anchored, atomic edits that keep line endings and BOM."""

from pathlib import Path

import pytest

from agentdev.utils.attachments import AttachmentStore
from functions.function_calling import file as ft


def _ctx(root: Path) -> dict:
    store = AttachmentStore(root.parent / (root.name + "_store"))
    return {"python_workspace_root": str(root), "graph_directory": str(root), "attachment_store": store}


def _put(root: Path, name: str, data: bytes) -> Path:
    path = root / name
    path.write_bytes(data)
    return path


def test_edit_file_replaces_unique_match(tmp_path):
    p = _put(tmp_path, "a.py", b"x = 1\ny = 2\n")
    out = ft.edit_file("a.py", "y = 2", "y = 3", _context=_ctx(tmp_path))
    assert p.read_bytes() == b"x = 1\ny = 3\n" and out["replacements"] == 1


def test_edit_file_missing_string_errors_without_write(tmp_path):
    p = _put(tmp_path, "a.py", b"x = 1\n")
    with pytest.raises(ValueError, match="not found"):
        ft.edit_file("a.py", "zzz", "q", _context=_ctx(tmp_path))
    assert p.read_bytes() == b"x = 1\n"


def test_edit_file_duplicate_requires_replace_all(tmp_path):
    p = _put(tmp_path, "a.py", b"a\nfoo\nb\nfoo\n")
    with pytest.raises(ValueError, match="2 times"):
        ft.edit_file("a.py", "foo", "bar", _context=_ctx(tmp_path))
    assert p.read_bytes() == b"a\nfoo\nb\nfoo\n"
    out = ft.edit_file("a.py", "foo", "bar", replace_all=True, _context=_ctx(tmp_path))
    assert p.read_bytes() == b"a\nbar\nb\nbar\n" and out["replacements"] == 2


def test_edit_file_rejects_empty_or_identical(tmp_path):
    _put(tmp_path, "a.py", b"x\n")
    with pytest.raises(ValueError):
        ft.edit_file("a.py", "", "y", _context=_ctx(tmp_path))
    with pytest.raises(ValueError):
        ft.edit_file("a.py", "x", "x", _context=_ctx(tmp_path))


def test_edit_file_keeps_crlf_with_multiline_strings(tmp_path):
    p = _put(tmp_path, "a.txt", b"a\r\nb\r\nc\r\n")
    ft.edit_file("a.txt", "a\nb", "A\nB\nB2", _context=_ctx(tmp_path))
    assert p.read_bytes() == b"A\r\nB\r\nB2\r\nc\r\n"


def test_edit_file_keeps_lf_when_given_crlf_strings(tmp_path):
    p = _put(tmp_path, "a.txt", b"a\nb\n")
    ft.edit_file("a.txt", "a\r\nb", "X", _context=_ctx(tmp_path))
    assert p.read_bytes() == b"X\n"


def test_edit_file_keeps_bom_and_does_not_add_one(tmp_path):
    bom = _put(tmp_path, "b.md", "Việt\nNam\n".encode("utf-8-sig"))
    ft.edit_file("b.md", "Nam", "Nam!", _context=_ctx(tmp_path))
    assert bom.read_bytes() == "Việt\nNam!\n".encode("utf-8-sig")
    plain = _put(tmp_path, "c.md", "Việt\n".encode("utf-8"))
    ft.edit_file("c.md", "Việt", "Việt Nam", _context=_ctx(tmp_path))
    assert plain.read_bytes() == "Việt Nam\n".encode("utf-8")


def test_edit_file_large_file(tmp_path):
    body = "".join(f"line {i}\n" for i in range(300_000)) + "TARGET\n"
    p = _put(tmp_path, "big.txt", body.encode())
    assert p.stat().st_size > 2_000_000
    ft.edit_file("big.txt", "TARGET", "DONE", _context=_ctx(tmp_path))
    assert p.read_bytes().endswith(b"line 299999\nDONE\n")


def test_edit_file_leaves_no_temp_files(tmp_path):
    _put(tmp_path, "a.py", b"x\n")
    ft.edit_file("a.py", "x", "y", _context=_ctx(tmp_path))
    assert sorted(f.name for f in tmp_path.iterdir()) == ["a.py"]


def test_edit_file_outside_workspace_and_attachments(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (tmp_path / "evil.txt").write_text("x")
    with pytest.raises((ValueError, FileNotFoundError)):
        ft.edit_file("../evil.txt", "x", "y", _context=_ctx(ws))
    (ws / "attachments").mkdir()
    (ws / "attachments" / "k.txt").write_text("x")
    with pytest.raises(ValueError, match="attachments"):
        ft.edit_file("attachments/k.txt", "x", "y", _context=_ctx(ws))


def test_edit_file_flag_off(tmp_path, monkeypatch):
    p = _put(tmp_path, "a.py", b"x\n")
    monkeypatch.setenv("AGENTDEV_EDIT_TOOLS", "0")
    with pytest.raises(ValueError, match="disabled"):
        ft.edit_file("a.py", "x", "y", _context=_ctx(tmp_path))
    assert p.read_bytes() == b"x\n"


def test_multi_edit_applies_in_order(tmp_path):
    p = _put(tmp_path, "a.py", b"one\ntwo\nthree\n")
    out = ft.multi_edit(
        "a.py",
        [{"old_string": "one", "new_string": "uno"}, {"old_string": "uno\ntwo", "new_string": "UNO\nDOS"}],
        _context=_ctx(tmp_path),
    )
    assert p.read_bytes() == b"UNO\nDOS\nthree\n" and out["applied_edits"] == 2


def test_multi_edit_is_all_or_nothing(tmp_path):
    p = _put(tmp_path, "a.py", b"one\ntwo\n")
    with pytest.raises(ValueError, match="edit 2"):
        ft.multi_edit(
            "a.py",
            [{"old_string": "one", "new_string": "1"}, {"old_string": "missing", "new_string": "x"}],
            _context=_ctx(tmp_path),
        )
    assert p.read_bytes() == b"one\ntwo\n"


def test_multi_edit_crlf_and_replace_all(tmp_path):
    p = _put(tmp_path, "a.txt", b"a\r\na\r\nb\r\n")
    ft.multi_edit(
        "a.txt",
        [{"old_string": "a", "new_string": "z", "replace_all": True}, {"old_string": "z\nb", "new_string": "end"}],
        _context=_ctx(tmp_path),
    )
    assert p.read_bytes() == b"z\r\nend\r\n"


def test_multi_edit_rejects_empty_list(tmp_path):
    _put(tmp_path, "a.py", b"x\n")
    with pytest.raises(ValueError):
        ft.multi_edit("a.py", [], _context=_ctx(tmp_path))


def test_new_tools_are_registered_and_write_tools():
    from agentdev.runtime.node.executor.workspace_standards import WORKSPACE_WRITE_TOOLS
    from agentdev.utils.function_catalog import get_function_catalog

    names = get_function_catalog().list_function_names()
    assert "edit_file" in names and "multi_edit" in names
    assert {"edit_file", "multi_edit"} <= WORKSPACE_WRITE_TOOLS


# --- apply_text_edits safety -------------------------------------------------------------------


def test_apply_text_edits_end_line_beyond_file_fails_loudly(tmp_path):
    p = _put(tmp_path, "a.txt", b"1\n2\n3\n")
    with pytest.raises(ValueError, match="beyond the end"):
        ft.apply_text_edits("a.txt", start_line=2, end_line=99, replacement="X", _context=_ctx(tmp_path))
    assert p.read_bytes() == b"1\n2\n3\n"


def test_apply_text_edits_expected_old_guards_the_range(tmp_path):
    p = _put(tmp_path, "a.txt", b"1\n2\n3\n")
    with pytest.raises(ValueError, match="expected_old"):
        ft.apply_text_edits("a.txt", start_line=2, replacement="X", expected_old="nope", _context=_ctx(tmp_path))
    assert p.read_bytes() == b"1\n2\n3\n"
    ft.apply_text_edits("a.txt", start_line=2, replacement="X", expected_old="2", _context=_ctx(tmp_path))
    assert p.read_bytes() == b"1\nX\n3\n"


def test_apply_text_edits_append_at_end_still_works(tmp_path):
    p = _put(tmp_path, "a.txt", b"1\n2\n")
    ft.apply_text_edits("a.txt", start_line=3, replacement="3", _context=_ctx(tmp_path))
    assert p.read_bytes() == b"1\n2\n3\n"
