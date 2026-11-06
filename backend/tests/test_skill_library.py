"""Shared skill library: paste / upload / edit / delete / import from ~/.claude/skills."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import skills as skills_route
from agentdev.api.services import skill_library
from agentdev.runtime.node.agent.skills import manager as skill_manager


SKILL_MD = """---
name: cto-management
description: Use when planning and delegating engineering work as a CTO.
---

# CTO management

Break the request into tasks and assign them.
"""


@pytest.fixture()
def library(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    root.mkdir()
    monkeypatch.setattr(skill_library, "SKILLS_ROOT", root)
    monkeypatch.setattr(skill_manager, "DEFAULT_SKILLS_ROOT", root)
    return root


@pytest.fixture()
def client(library):
    app = FastAPI()
    app.include_router(skills_route.router)
    return TestClient(app)


def _source(tmp_path: Path) -> Path:
    src = tmp_path / "claude-skills"
    good = src / "systematic-debugging"
    (good / "references").mkdir(parents=True)
    (good / "SKILL.md").write_text(
        "---\nname: systematic-debugging\ndescription: Use for any bug.\n---\n\nFind the root cause.\n",
        encoding="utf-8",
    )
    (good / "references" / "notes.md").write_text("extra", encoding="utf-8")
    (good / "node_modules").mkdir()
    (good / "node_modules" / "junk.js").write_text("x", encoding="utf-8")
    bad = src / "broken"
    bad.mkdir()
    (bad / "SKILL.md").write_text("no frontmatter", encoding="utf-8")
    return src


def test_create_from_markdown_with_frontmatter(client, library):
    res = client.post("/api/skills", json={"content": SKILL_MD})
    assert res.status_code == 201
    assert res.json()["name"] == "cto-management"
    assert (library / "cto-management" / "SKILL.md").is_file()
    listed = client.get("/api/skills").json()["skills"]
    assert [s["name"] for s in listed] == ["cto-management"]
    assert listed[0]["valid"] is True


def test_plain_pasted_text_gets_frontmatter(client, library):
    res = client.post(
        "/api/skills",
        json={"content": "Always write a test first.", "name": "tdd-lite", "description": "Use when coding."},
    )
    assert res.status_code == 201
    meta = skill_manager.parse_skill_file(library / "tdd-lite" / "SKILL.md")
    assert meta.description == "Use when coding."


def test_plain_text_without_name_is_rejected(client):
    res = client.post("/api/skills", json={"content": "just text"})
    assert res.status_code == 400


def test_invalid_name_rejected(client):
    res = client.post("/api/skills", json={"content": "x", "name": "../evil", "description": "d"})
    assert res.status_code == 400


def test_duplicate_requires_overwrite(client):
    assert client.post("/api/skills", json={"content": SKILL_MD}).status_code == 201
    assert client.post("/api/skills", json={"content": SKILL_MD}).status_code == 409
    assert client.post("/api/skills", json={"content": SKILL_MD, "overwrite": True}).status_code == 201


def test_update_and_rename(client, library):
    client.post("/api/skills", json={"content": SKILL_MD})
    res = client.put("/api/skills/cto-management", json={"content": SKILL_MD.replace("Break", "Split")})
    assert res.status_code == 200
    assert "Split" in res.json()["content"]
    res = client.put("/api/skills/cto-management", json={"content": SKILL_MD, "name": "cto-core"})
    assert res.status_code == 200
    assert not (library / "cto-management").exists()
    assert (library / "cto-core" / "SKILL.md").is_file()


def test_delete(client, library):
    client.post("/api/skills", json={"content": SKILL_MD})
    assert client.delete("/api/skills/cto-management").status_code == 200
    assert client.get("/api/skills/cto-management").status_code == 404


def test_import_from_claude_folder(client, library, tmp_path):
    src = _source(tmp_path)
    listing = client.get("/api/skills/import-source", params={"source": str(src)}).json()
    names = {s["name"]: s for s in listing["skills"]}
    assert names["systematic-debugging"]["valid"] and not names["systematic-debugging"]["imported"]
    assert names["broken"]["valid"] is False

    res = client.post(
        "/api/skills/import", json={"names": ["systematic-debugging", "broken"], "source": str(src)}
    ).json()
    assert res["imported"] == ["systematic-debugging"]
    assert res["failed"][0]["name"] == "broken"
    assert (library / "systematic-debugging" / "references" / "notes.md").is_file()
    assert not (library / "systematic-debugging" / "node_modules").exists()

    again = client.post("/api/skills/import", json={"names": ["systematic-debugging"], "source": str(src)}).json()
    assert again["skipped"] == ["systematic-debugging"]


def test_imported_skill_is_offered_to_agents(client, library):
    client.post("/api/skills", json={"content": SKILL_MD})
    mgr = skill_manager.AgentSkillManager(allow=["cto-management"])
    xml = mgr.build_available_skills_xml()
    assert "<name>cto-management</name>" in xml
    assert "<location>" not in xml  # skills are activated by name; no file paths in every prompt


def test_prompt_description_is_trimmed():
    long = (
        "Runs reviews. Use when reviewing a diff, when merging, when auditing security, when checking style, "
        "when the user asks for feedback on a pull request before it lands, or when quality matters. "
        "Also triggers on 'review this', 'check my code' and 'is this ready to merge'."
    )
    short = skill_manager.summarise_description(long)
    assert short.startswith("Runs reviews. Use when reviewing a diff") and len(short) <= 200
    assert "triggers" not in short and short.endswith(".")
    assert skill_manager.summarise_description("Short one.") == "Short one."


def test_cross_origin_blocked(client):
    res = client.post("/api/skills", json={"content": SKILL_MD}, headers={"origin": "https://evil.example"})
    assert res.status_code == 403


def _make_link(link: Path, target: Path) -> None:
    """Directory symlink, or a junction on Windows when symlinks need privileges."""
    import os
    import subprocess

    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("cannot create directory links here")
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)


def test_import_does_not_follow_links(client, library, tmp_path):
    src = _source(tmp_path)
    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / "id_rsa").write_text("PRIVATE", encoding="utf-8")
    _make_link(src / "systematic-debugging" / "linked", secret)
    assert skill_library._dir_size(src / "systematic-debugging") < 100

    res = client.post("/api/skills/import", json={"names": ["systematic-debugging"], "source": str(src)}).json()
    assert res["imported"] == ["systematic-debugging"]
    copied = library / "systematic-debugging"
    assert not (copied / "linked").exists()
    assert not any(p.name == "id_rsa" for p in copied.rglob("*"))


def test_import_copies_real_folder_behind_linked_skill(client, library, tmp_path):
    src = _source(tmp_path)
    store = tmp_path / "store"
    store.mkdir()
    real = store / "linked-skill"
    real.mkdir()
    (real / "SKILL.md").write_text("---\nname: linked-skill\ndescription: d\n---\n\nBody\n", encoding="utf-8")
    _make_link(src / "linked-skill", real)
    res = client.post("/api/skills/import", json={"names": ["linked-skill"], "source": str(src)}).json()
    assert res["imported"] == ["linked-skill"] and not res["failed"]
    copied = library / "linked-skill"
    assert (copied / "SKILL.md").is_file()
    assert not skill_library.is_link(copied)


def test_import_continues_after_one_copy_fails(client, library, tmp_path, monkeypatch):
    src = _source(tmp_path)
    other = src / "second-skill"
    other.mkdir()
    (other / "SKILL.md").write_text("---\nname: second-skill\ndescription: d\n---\n\nBody\n", encoding="utf-8")
    real_copytree = skill_library.shutil.copytree

    def copytree(source, dest, **kwargs):
        if Path(source).name == "systematic-debugging":
            raise PermissionError("file in use")
        return real_copytree(source, dest, **kwargs)

    monkeypatch.setattr(skill_library.shutil, "copytree", copytree)
    res = client.post(
        "/api/skills/import", json={"names": ["systematic-debugging", "second-skill"], "source": str(src)}
    ).json()
    assert res["imported"] == ["second-skill"]
    assert res["failed"][0]["name"] == "systematic-debugging" and "Permission denied" in res["failed"][0]["error"]


def test_linked_skill_folder_is_not_deleted_or_overwritten(client, library, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    _make_link(library / "cto-management", outside)
    res = client.delete("/api/skills/cto-management")
    assert res.status_code == 400 and "link" in res.json()["detail"]
    res = client.post("/api/skills", json={"content": SKILL_MD, "overwrite": True})
    assert res.status_code == 400
    res = client.put("/api/skills/cto-management", json={"content": SKILL_MD.replace("Break", "Split")})
    assert res.status_code == 400
    assert (outside / "SKILL.md").read_text(encoding="utf-8") == SKILL_MD


def test_delete_permission_error_is_reported(client, library, monkeypatch):
    client.post("/api/skills", json={"content": SKILL_MD})

    def rmtree(path, *args, **kwargs):
        raise PermissionError("in use")

    monkeypatch.setattr(skill_library.shutil, "rmtree", rmtree)
    res = client.delete("/api/skills/cto-management")
    assert res.status_code == 409 and "Permission denied" in res.json()["detail"]


def test_update_of_missing_skill_is_404(client, library):
    res = client.put("/api/skills/cto-management", json={"content": SKILL_MD})
    assert res.status_code == 404
    assert not (library / "cto-management").exists()


def test_frontmatter_name_used_when_form_name_omitted(client, library):
    """The editor omits unchanged form fields so a name edited in the frontmatter renames the skill."""
    client.post("/api/skills", json={"content": SKILL_MD})
    renamed = SKILL_MD.replace("name: cto-management", "name: cto-lead")
    res = client.put("/api/skills/cto-management", json={"content": renamed, "name": None, "description": None})
    assert res.status_code == 200 and res.json()["name"] == "cto-lead"
    assert not (library / "cto-management").exists()


def test_import_overwrite_keeps_old_on_copy_failure(client, library, tmp_path, monkeypatch):
    """A5-01: a failed overwrite copy must leave the previous skill intact."""
    src = _source(tmp_path)
    client.post("/api/skills/import", json={"names": ["systematic-debugging"], "source": str(src)})
    old = (library / "systematic-debugging" / "SKILL.md").read_text(encoding="utf-8")
    (src / "systematic-debugging" / "SKILL.md").write_text(
        "---\nname: systematic-debugging\ndescription: New.\n---\n\nNew body\n", encoding="utf-8"
    )

    def boom(*args, **kwargs):
        raise PermissionError("file in use")

    monkeypatch.setattr(skill_library.shutil, "copytree", boom)
    res = client.post(
        "/api/skills/import",
        json={"names": ["systematic-debugging"], "source": str(src), "overwrite": True},
    ).json()
    assert res["failed"]
    assert (library / "systematic-debugging" / "SKILL.md").read_text(encoding="utf-8") == old
    assert [p.name for p in library.iterdir()] == ["systematic-debugging"]  # no tmp/backup leftovers


def test_rename_with_failed_write_keeps_old_name(client, library, monkeypatch):
    """A5-10: the folder is only renamed after the new SKILL.md is written."""
    client.post("/api/skills", json={"content": SKILL_MD})
    real_replace = skill_library.os.replace

    def failing_replace(src, dst):
        if str(dst).endswith("SKILL.md"):
            raise OSError("disk full")
        return real_replace(src, dst)

    monkeypatch.setattr(skill_library.os, "replace", failing_replace)
    res = client.put("/api/skills/cto-management", json={"content": SKILL_MD, "name": "renamed-skill"})
    assert res.status_code >= 400
    assert (library / "cto-management" / "SKILL.md").is_file()
    assert not (library / "renamed-skill").exists()
    assert [p.name for p in library.iterdir()] == ["cto-management"]


def test_save_is_atomic_write(client, library, monkeypatch):
    """A5-10: SKILL.md is replaced via a temp file, never truncated in place."""
    client.post("/api/skills", json={"content": SKILL_MD})
    before = (library / "cto-management" / "SKILL.md").read_text(encoding="utf-8")
    real_replace = skill_library.os.replace

    def failing_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(skill_library.os, "replace", failing_replace)
    res = client.put("/api/skills/cto-management", json={"content": SKILL_MD.replace("Break", "Split")})
    assert res.status_code >= 400
    assert (library / "cto-management" / "SKILL.md").read_text(encoding="utf-8") == before
    assert [p.name for p in (library / "cto-management").iterdir()] == ["SKILL.md"]


# ---------------------------------------------------------------- categories + Agent Skills spec


def test_string_compatibility_is_valid(client, library):
    # Agent Skills spec: `compatibility` is a free-text string. 84 skills from public packs use it that way and
    # were shown as broken ("compatibility must be a mapping").
    text = SKILL_MD.replace("description:", "compatibility: Requires ffmpeg and network access\ndescription:")
    (library / "cto-management").mkdir()
    (library / "cto-management" / "SKILL.md").write_text(text, encoding="utf-8")
    entry = client.get("/api/skills").json()["skills"][0]
    assert entry["valid"], entry["error"]
    meta = skill_manager.parse_skill_file(library / "cto-management" / "SKILL.md")
    assert meta.compatibility == {"text": "Requires ffmpeg and network access"}


def test_list_has_auto_category():
    from agentdev.api.services.skill_categories import guess_category

    assert guess_category("remotion-render", "Render a Remotion composition to MP4") == "video"
    assert guess_category("elevenlabs", "Text to speech voices") == "audio"
    assert guess_category("gsap-timeline", "Sequence animations") == "motion"
    assert guess_category("systematic-debugging", "Use when a test fails") == "dev"
    assert guess_category("brainstorming", "Explore ideas before creative work") == "workflow"
    assert guess_category("zzz", "nothing known") == "other"


def test_category_is_listed_and_can_be_set_and_reset(client, library):
    client.post("/api/skills", json={"content": SKILL_MD})
    entry = client.get("/api/skills").json()["skills"][0]
    assert entry["category"] == "workflow" and entry["category_source"] == "auto"

    saved = client.put("/api/skills/cto-management", json={"content": SKILL_MD, "category": "video"}).json()
    assert saved["category"] == "video" and saved["category_source"] == "manual"
    text = (library / "cto-management" / "SKILL.md").read_text(encoding="utf-8")
    assert "metadata:" in text and "category: video" in text

    # Other metadata keys survive; "auto" removes only the category.
    content = saved["content"].replace("metadata:\n", "metadata:\n  owner: team\n")
    reset = client.put("/api/skills/cto-management", json={"content": content, "category": "auto"}).json()
    assert reset["category_source"] == "auto"
    text = (library / "cto-management" / "SKILL.md").read_text(encoding="utf-8")
    assert "category:" not in text and "owner: team" in text


def test_unknown_category_rejected(client):
    res = client.post("/api/skills", json={"content": SKILL_MD, "category": "cooking"})
    assert res.status_code == 400


def test_import_allows_skills_with_large_examples(client, library, tmp_path, monkeypatch):
    # Public video skills ship 30-40 MB of example media; the 5 MB cap refused them.
    monkeypatch.setattr(skill_library, "MAX_IMPORT_DIR_BYTES", 10)
    src = tmp_path / "src" / "big-skill"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(SKILL_MD.replace("cto-management", "big-skill"), encoding="utf-8")
    (src / "clip.mp4").write_bytes(b"x" * 100)
    res = client.post("/api/skills/import", json={"names": ["big-skill"], "source": str(tmp_path / "src")}).json()
    assert res["failed"] and "MB" in res["failed"][0]["error"]  # the cap still exists and is configurable
    assert skill_library.MAX_IMPORT_DIR_BYTES_DEFAULT >= 64 * 1024 * 1024


def test_guide_is_saved_listed_and_cleared(client, library):
    client.post("/api/skills", json={"content": SKILL_MD})
    guide = {
        "purpose": "Chia việc kỹ thuật cho đội.",
        "when": "Có yêu cầu lớn cần chia nhỏ.",
        "benefit": "Kế hoạch rõ ràng, giao đúng người.",
        "requires": "",
        "paid": False,
    }
    saved = client.put("/api/skills/cto-management", json={"content": SKILL_MD, "guide": guide, "category": "workflow"}).json()
    assert saved["guide"]["purpose"] == guide["purpose"] and saved["guide"]["paid"] is False
    assert saved["category"] == "workflow"
    listed = client.get("/api/skills").json()["skills"][0]
    assert listed["guide"]["when"] == guide["when"]
    text = (library / "cto-management" / "SKILL.md").read_text(encoding="utf-8")
    assert "Chia việc kỹ thuật" in text  # unicode kept readable

    # Saving the content again without `guide` keeps it; an empty guide removes it.
    kept = client.put("/api/skills/cto-management", json={"content": saved["content"]}).json()
    assert kept["guide"]["benefit"] == guide["benefit"]
    cleared = client.put("/api/skills/cto-management", json={"content": saved["content"], "guide": {}}).json()
    assert cleared["guide"] is None
    assert cleared["category"] == "workflow"  # other metadata untouched


def test_paid_guide_shown_without_text(client, library):
    client.post("/api/skills", json={"content": SKILL_MD, "guide": {"paid": True, "requires": "API key HeyGen"}})
    entry = client.get("/api/skills").json()["skills"][0]
    assert entry["guide"] == {"purpose": "", "when": "", "benefit": "", "requires": "API key HeyGen", "paid": True}
