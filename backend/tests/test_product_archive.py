"""Product folder: its project name heads the file tree, and it downloads as a .zip without dependency folders."""

import io
import json
import time
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev import paths
from agentdev.api.routes import lab as lab_route
from agentdev.api.services import lab_outputs, workflow_lab
from agentdev.api.services.product_archive import build_archive, project_name, slug
from agentdev.api.services.workflow_lab import LabRunner

JOB = "0123456789ab"


def _product(root):
    (root / "client" / "src").mkdir(parents=True)
    (root / "client" / "index.html").write_text("<title>Quản lý cửa hàng</title>", encoding="utf-8")
    (root / "client" / "src" / "main.jsx").write_text("x", encoding="utf-8")
    (root / "server").mkdir()
    (root / "server" / ".env").write_text("SECRET=1", encoding="utf-8")
    (root / "server" / ".env.example").write_text("SECRET=", encoding="utf-8")
    for skipped in ("client/node_modules/react", ".git/objects", "server/.venv/lib", "attachments"):
        (root / skipped).mkdir(parents=True, exist_ok=True)
        (root / skipped / "f.js").write_text("x", encoding="utf-8")
    return root


@pytest.mark.parametrize("folder,files,expected", [
    ("shop-app", {}, "shop-app"),  # a real project folder keeps its own name
    ("code_workspace", {"README.md": "# Cửa hàng **mini**\n"}, "Cửa hàng mini"),
    ("code_workspace", {"package.json": '{"name": "shop-pos"}'}, "shop-pos"),
    ("code_workspace", {"package.json": '{"name": "vite-project"}'}, ""),
    ("code_workspace", {}, ""),
])
def test_project_name(tmp_path, folder, files, expected):
    root = tmp_path / folder
    root.mkdir()
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    assert project_name(root) == expected


def test_project_name_from_web_title(tmp_path):
    root = _product(tmp_path / "code_workspace")
    assert project_name(root) == "Quản lý cửa hàng"
    assert slug(project_name(root)) == "quan-ly-cua-hang"
    assert slug("") == "san-pham"


def test_archive_skips_dependencies_secrets_and_inputs(tmp_path):
    root = _product(tmp_path / "code_workspace")
    archive = build_archive(root, "shop", hide_top=frozenset({"attachments"}))
    try:
        with zipfile.ZipFile(archive) as zf:
            names = sorted(zf.namelist())
    finally:
        archive.unlink()
    assert names == ["shop/client/index.html", "shop/client/src/main.jsx", "shop/server/.env.example"]


def test_archive_of_empty_folder_is_404(tmp_path):
    with pytest.raises(lab_outputs.LabOutputsError) as err:
        build_archive(tmp_path, "x")
    assert err.value.status_code == 404


@pytest.fixture()
def client(tmp_path, monkeypatch):
    warehouse = tmp_path / "warehouse"
    warehouse.mkdir()
    store = tmp_path / "lab_jobs"
    store.mkdir()
    monkeypatch.setattr(paths, "WAREHOUSE_DIR", warehouse)
    monkeypatch.setattr(workflow_lab, "_lab_dir", lambda: store)
    runner = LabRunner(store_dir=store)
    monkeypatch.setattr(workflow_lab, "get_lab_runner", lambda: runner)
    run = warehouse / "lab_wf_20261105100000_abc123_20261105100000"
    _product(run / "code_workspace")
    (run / "code_workspace" / "server" / "seed.js").write_text(
        "const u = process.env.SEED_ADMIN_USERNAME || 'admin'; const p = process.env.SEED_ADMIN_PASSWORD;\n"
        "bcrypt.hash(p); app.post('/login')", encoding="utf-8")
    data = {"id": JOB, "workflow": "wf.yaml", "status": "completed", "started_at": time.time(),
            "results": [{"scenario": 0, "repeat": 1, "status": "passed", "output_dir": str(run), "answer": "xong"}]}
    (store / f"{JOB}.json").write_text(json.dumps(data), encoding="utf-8")
    app = FastAPI()
    app.include_router(lab_route.router)
    return TestClient(app)


def test_listing_carries_name_and_login(client):
    data = client.get(f"/api/lab/jobs/{JOB}/runs/0/files").json()
    assert data["name"] == "Quản lý cửa hàng"
    assert data["login"]["needs_login"] is True
    assert data["login"]["env"]["password_var"] == "SEED_ADMIN_PASSWORD"
    assert data["login"]["env"]["username"] == "admin"


def test_archive_route(client):
    res = client.get(f"/api/lab/jobs/{JOB}/runs/0/archive")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    assert "quan-ly-cua-hang.zip" in res.headers["content-disposition"]
    names = zipfile.ZipFile(io.BytesIO(res.content)).namelist()
    assert names and all(n.startswith("quan-ly-cua-hang/") for n in names)
    assert not any("node_modules" in n or "/.git/" in n or n.endswith("/.env") for n in names)


def test_accounts_saved_per_run_outside_the_product(client, tmp_path):
    url = f"/api/lab/jobs/{JOB}/runs/0/accounts"
    assert client.get(url).json() == {"accounts": []}
    rows = [{"username": " admin ", "password": " Pass 1 ", "note": "quản trị"}, {"username": "", "password": ""}]
    saved = client.put(url, json={"accounts": rows}).json()["accounts"]
    assert saved == [{"username": "admin", "password": " Pass 1 ", "note": "quản trị", "url": ""}]
    assert client.get(url).json()["accounts"] == saved
    stored = list((tmp_path / "product_accounts").glob("*.json"))
    assert len(stored) == 1 and stored[0].name.startswith(f"lab_{JOB}_")
    # never part of the product: not listed, not zipped
    files = client.get(f"/api/lab/jobs/{JOB}/runs/0/files").json()["files"]
    assert not any("account" in f["path"] for f in files)
    assert client.put(url, json={"accounts": []}).json() == {"accounts": []}
    assert not stored[0].exists()


@pytest.mark.parametrize("bad", [
    [{"username": "a", "url": "javascript:alert(1)"}],
    [{"username": 5}],
    [{"username": "x" * 201}],
    ["admin"],
])
def test_accounts_reject_invalid(client, bad):
    res = client.put(f"/api/lab/jobs/{JOB}/runs/0/accounts", json={"accounts": bad})
    assert res.status_code == 400


def test_accounts_unknown_run_is_404(client):
    assert client.get(f"/api/lab/jobs/{JOB}/runs/9/accounts").status_code == 404
