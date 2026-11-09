"""Human-named project folders under PROJECTS_DIR (see utils/project_folders.py)."""

import pytest

from agentdev import paths
from agentdev.utils import project_folders as pf


@pytest.mark.parametrize("text,expected", [
    ("Quản lý công việc nhóm!", "quan-ly-cong-viec-nhom"),
    ("Đặt bàn nhà hàng", "dat-ban-nha-hang"),
    ("  Web  bán   hàng / v2 ", "web-ban-hang-v2"),
    ("***", "project"),
    ("", "project"),
    (None, "project"),
    ("con", "con-project"),
    ("NUL", "nul-project"),
    ("a" * 100, "a" * 40),
])
def test_slugify(text, expected):
    assert pf.slugify(text) == expected


def test_slugify_cuts_on_a_word_boundary():
    slug = pf.slugify("xay dung he thong quan ly kho hang cho cua hang vat lieu xay dung lon")
    assert len(slug) <= 40 and not slug.endswith("-") and slug.startswith("xay-dung-he-thong")


def test_create_project_dir_never_reuses_a_name(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path / "AgentDev")
    first = pf.create_project_dir("Web bán hàng")
    second = pf.create_project_dir("Web bán hàng")
    assert first.name == "web-ban-hang" and second.name == "web-ban-hang-2"
    assert first.parent == (tmp_path / "AgentDev").resolve()
    assert (first / ".agentdev" / ".gitignore").read_text(encoding="utf-8") == "*\n"
    assert [p.name for p in first.iterdir()] == [".agentdev"]  # nothing else: the project starts empty
    assert pf.is_managed(first) and pf.is_managed(second)


def test_is_managed_only_for_folders_under_the_root(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path / "AgentDev")
    (tmp_path / "other").mkdir()
    assert not pf.is_managed(tmp_path / "other")
    assert not pf.is_managed(tmp_path / "AgentDev")  # the root itself is not a project
    assert not pf.is_managed(None)


def test_lab_root_is_inside_projects_root(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path / "AgentDev")
    assert pf.lab_root() == tmp_path / "AgentDev" / "AgentDev_lab"
