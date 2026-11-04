"""File tools: compact results (re-read by every later model call) and errors the model can act on.

Evidence: a CTO run on a 600-file project spent one round on paths prefixed with the folder name
(``pdc-vr360/...``), then one ``describe_available_files`` returned ~80 KB of JSON (absolute paths,
node_modules, every .webp) that every later call of the loop re-read.
"""

import json

import pytest

from agentdev.utils.attachments import AttachmentStore
from agentdev.api.services.attachment_service import render_project_tree
from functions.function_calling.file import (
    describe_available_files,
    list_directory,
    read_file_segment,
    save_file,
    search_in_files,
)


def _write(root, rel, text="x"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "my-shop"
    _write(root, "README.md", "# Shop\n")
    _write(root, "package.json", "{}\n")
    _write(root, "src/app/page.tsx", "export default function Page() {}\nconst heroTitle = 1\n")
    _write(root, "src/lib/util.ts", "export const heroTitle = 'x'\n")
    for i in range(60):
        (root / "public/images").mkdir(parents=True, exist_ok=True)
        (root / "public/images" / f"photo-{i}.webp").write_bytes(b"RIFF\0\0WEBP")
    _write(root, "node_modules/react/index.js", "const heroTitle = 'dependency'\n")
    _write(root, "node_modules/react/package.json", "{}\n")
    return root


@pytest.fixture()
def ctx(tmp_path, project):
    return {
        "attachment_store": AttachmentStore(tmp_path / "store"),
        "python_workspace_root": str(project),
        "graph_directory": str(project),
    }


def _size(result):
    return len(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


def test_describe_is_compact_skips_dependencies_and_summarises_big_folders(ctx, project):
    result = describe_available_files(_context=ctx)
    tree = result["tree"]
    assert "src/app/page.tsx" in tree and "README.md" in tree
    assert "node_modules/ (skipped" in tree and "react/index.js" not in tree
    assert "public/images/ (60 files" in tree and "photo-1.webp" not in tree
    assert str(project) not in json.dumps(result)  # no absolute paths
    assert "\\" not in tree  # POSIX paths, as the tools take them
    assert result["total_files"] == 64
    assert _size(result) < 1200


def test_describe_respects_the_line_limit(ctx):
    result = describe_available_files(limit=3, _context=ctx)
    assert len(result["tree"].splitlines()) == 3
    assert result["truncated"] is True and "list_directory" in result["note"]


def test_list_directory_returns_workspace_relative_paths(ctx):
    result = list_directory("src", recursive=True, _context=ctx)
    assert any(entry.startswith("src/app/page.tsx  ") and entry.endswith(" B") for entry in result["entries"])
    assert "src/app/" in result["entries"]
    assert all(entry.startswith("src/") for entry in result["entries"])


def test_recursive_listing_folds_big_folders_and_dependencies(ctx):
    result = list_directory(".", recursive=True, _context=ctx)
    entries = result["entries"]
    assert any(entry.startswith("public/images/* (60 files") for entry in entries)
    assert not any("photo-1.webp" in entry for entry in entries)
    assert "node_modules/ (dependency/build folder, not expanded)" in entries
    # Listing the big folder itself still shows every file.
    assert len(list_directory("public/images", _context=ctx)["entries"]) == 60


def test_folder_name_prefix_is_repaired_with_a_note(ctx):
    listing = list_directory("my-shop", _context=ctx)
    assert listing["directory"] == "." and "README.md" in " ".join(listing["entries"])
    assert "used '.'" in listing["note"]
    segment = read_file_segment("my-shop/src/app/page.tsx", _context=ctx)
    assert segment["path"] == "src/app/page.tsx" and "Page" in segment["snippet"]
    assert "src/app/page.tsx" in segment["note"]


def test_real_subfolder_named_like_the_root_wins(ctx, project):
    _write(project, "my-shop/notes.md", "inner")
    assert read_file_segment("my-shop/notes.md", _context=ctx)["snippet"] == "inner"
    assert "note" not in read_file_segment("my-shop/notes.md", _context=ctx)


def test_uploaded_project_id_prefix_maps_to_projects_folder(tmp_path):
    workspace = tmp_path / "code_workspace"
    _write(workspace, "projects/shop/src/main.js", "v1\n")
    ctx = {
        "attachment_store": AttachmentStore(tmp_path / "store"),
        "python_workspace_root": str(workspace),
        "graph_directory": str(tmp_path),
    }
    segment = read_file_segment("shop/src/main.js", _context=ctx)
    assert segment["path"] == "projects/shop/src/main.js"


def test_history_pointer_to_session_attachment_is_readable(tmp_path, project):
    # Folder opened in place: the workspace is the project, the overview lives in the session folder.
    session = tmp_path / "session_x"
    overview = _write(session, "code_workspace/attachments/abc/PROJECT.md", "# Project: my-shop\n")
    ctx = {
        "attachment_store": AttachmentStore(tmp_path / "store"),
        "python_workspace_root": str(project),
        "graph_directory": str(session),
    }
    assert read_file_segment(str(overview), _context=ctx)["snippet"].startswith("# Project")
    with pytest.raises(ValueError):
        read_file_segment(str(tmp_path / "elsewhere.txt"), _context=ctx)


def test_not_found_error_suggests_the_fix(ctx):
    with pytest.raises(FileNotFoundError) as excinfo:
        read_file_segment("src/page.tsx", _context=ctx)
    message = str(excinfo.value)
    assert "Did you mean: src/app/page.tsx" in message
    assert "Top-level entries:" in message and "src/" in message
    assert "do not prefix them with the folder name 'my-shop/'" in message
    with pytest.raises(FileNotFoundError, match="Did you mean: src/lib"):
        list_directory("lib", _context=ctx)


def test_read_file_segment_metadata_is_lean(ctx):
    result = read_file_segment("src/app/page.tsx", line_count=1, _context=ctx)
    assert set(result) == {"path", "start_line", "end_line", "total_lines", "truncated", "file_size", "snippet"}
    assert result["truncated"] is True and result["total_lines"] == 2


def test_save_file_with_folder_prefix_does_not_nest_a_copy(ctx, project):
    result = save_file("my-shop/src/new.ts", "export {}\n", _context=ctx)
    assert (project / "src/new.ts").exists()
    assert not (project / "my-shop").exists()
    assert result["path"] == "src/new.ts" and "note" in result


def test_search_skips_dependencies_and_binaries(ctx):
    result = search_in_files("heroTitle", _context=ctx)
    files = {match["file"] for match in result["matches"]}
    assert files == {"src/app/page.tsx", "src/lib/util.ts"}
    assert result["searched_files"] == 4  # README, package.json and the two sources
    assert result["skipped_binary_or_large_files"] == 60


def test_search_globs(ctx):
    nested = search_in_files("heroTitle", globs=["*.ts"], _context=ctx)  # any depth, like ripgrep
    assert {m["file"] for m in nested["matches"]} == {"src/lib/util.ts"}
    as_string = search_in_files("heroTitle", globs="src/**/*.{ts,tsx}", _context=ctx)
    assert {m["file"] for m in as_string["matches"]} == {"src/app/page.tsx", "src/lib/util.ts"}
    named = search_in_files("heroTitle", globs=["node_modules/**/*.js"], _context=ctx)
    assert {m["file"] for m in named["matches"]} == {"node_modules/react/index.js"}
    nothing = search_in_files("heroTitle", globs=["app/**/*.py"], _context=ctx)
    assert nothing["matches"] == [] and "relative to the workspace root" in nothing["note"]


def test_search_clips_minified_lines(ctx, project):
    _write(project, "src/bundle.js", "var heroTitle=1;" + "x" * 5000 + "\n")
    result = search_in_files("heroTitle", globs=["src/bundle.js"], _context=ctx)
    line = result["matches"][0]["line_text"]
    assert len(line) < 400 and line.endswith("chars]")


def test_project_tree_fits_budget_and_keeps_structure_visible():
    files = [f"public/images/marker/img-{i}.webp" for i in range(400)]
    files += [f"audio-originals/site-{s}/cum{i}.mp3" for s in range(4) for i in range(30)]
    files += [f"src/app/route-{i}/page.tsx" for i in range(40)]
    files += [f"src/components/C{i}.tsx" for i in range(30)]
    files += ["README.md", "package.json"]
    lines = render_project_tree(files, max_lines=60)
    text = "\n".join(lines)
    assert len(lines) <= 60
    assert lines[0] == "audio-originals/ (120 files: 120 .mp3)"  # media-only folder: one line
    assert "public/ (400 files: 400 .webp)" in lines
    assert "src/" in lines and "  app/" in lines and "README.md" in lines
    assert "img-1.webp" not in text
    assert "    ... +30 more folders (30 files)" in lines  # 40 route folders: 10 shown
    assert "    ... +20 more files (20 .tsx)" in lines  # 30 components: 10 shown


def test_project_tree_small_project_is_listed_in_full():
    files = ["README.md", "src/main.py", "src/util/helpers.py"]
    assert render_project_tree(files) == ["src/", "  util/", "    helpers.py", "  main.py", "README.md"]
