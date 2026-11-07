"""Lab: an app behind a login must come with its demo account, shown to the tester next to the run."""

import time
from pathlib import Path

import pytest

from agentdev.api.services import workflow_lab
from agentdev.api.services.lab_diagnosis import diagnose_run
from agentdev.api.services.lab_login import find_credentials, judge_fact, login_info
from agentdev.api.services.workflow_lab import LabRunner, Scenario


@pytest.fixture(autouse=True)
def _lab_store(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow_lab, "_lab_dir", lambda: tmp_path / "lab_jobs")


@pytest.mark.parametrize("text,user,password", [
    ("Đăng nhập với tài khoản: `admin`, mật khẩu: `Admin@123`", "admin", "Admin@123"),
    ("- **Username**: demo@shop.vn\n- **Password**: secret99", "demo@shop.vn", "secret99"),
    ("Login: admin/admin123 tại http://localhost:3000/login", "admin", "admin123"),
    ("password: p4ss user: alice", "alice", "p4ss"),
    ("Tài khoản demo là manager, mật khẩu là 123456", "manager", "123456"),
])
def test_find_credentials(text, user, password):
    found = find_credentials(text)
    assert found and found[0]["username"] == user and found[0]["password"] == password


def test_placeholders_are_not_credentials():
    assert find_credentials("username: <your user>, password: <your password>") == []
    assert find_credentials("Set PASSWORD=your_password in .env") == []


def test_login_info_reads_source_and_readme(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Login.vue").write_text('<input type="password" v-model="pw">', encoding="utf-8")
    (tmp_path / "README.md").write_text("## Tài khoản thử\n- user: staff\n- password: Staff#2026\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "README.md").write_text("user: npm password: leaked", encoding="utf-8")
    info = login_info("Đã xong app.", tmp_path)
    assert info["needs_login"] is True
    assert info["credentials"] == [{"username": "staff", "password": "Staff#2026", "source": "README.md"}]


def test_login_info_flags_app_with_login_and_no_account(tmp_path):
    (tmp_path / "app.py").write_text("from flask_login import LoginManager\n", encoding="utf-8")
    info = login_info("App chạy ở http://localhost:5000", tmp_path)
    assert info == {"needs_login": True, "credentials": [], "login_url": ""}
    assert "NO demo account" in judge_fact(info)


def test_login_info_is_none_without_login(tmp_path):
    (tmp_path / "index.html").write_text("<h1>Hello</h1>", encoding="utf-8")
    assert login_info("Trang tĩnh xong.", tmp_path) is None


def test_missing_account_is_a_workflow_finding():
    run = {"status": "failed", "answer": "x", "login": {"needs_login": True, "credentials": []}}
    finding = [f for f in diagnose_run(run, "Viết app quản lý kho có đăng nhập") if f["code"] == "login_missing"]
    assert finding and finding[0]["layer"] == "workflow" and "tài khoản demo" in finding[0]["fix"]


def test_runner_stores_login_and_tells_the_judge(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "server.js").write_text("app.post('/login', passport.authenticate('local'))", encoding="utf-8")
    yaml_path = tmp_path / "wf.yaml"
    yaml_path.write_text("graph:\n  id: dev\n  nodes: []\n", encoding="utf-8")
    seen = {}

    def judge(prompt, criteria, answer, questions, facts=""):
        seen["facts"] = facts
        return {"pass": True, "score": 9, "reason": "ok", "judged_by": "ai"}

    def run_once(path, scenario, cancel):
        return {"status": "done", "answer": "Xong. Tài khoản: admin / Admin123", "seconds": 5, "output_dir": str(out)}

    job = LabRunner(store_dir=tmp_path / "store").start(yaml_path, "wf.yaml", [Scenario(prompt="Viết app")], 1,
                                                        run_once=run_once, judge=judge)
    deadline = time.monotonic() + 20
    while job.status in ("queued", "running") and time.monotonic() < deadline:
        time.sleep(0.02)
    login = job.to_dict()["results"][0]["login"]
    assert login["needs_login"] and login["credentials"][0]["username"] == "admin"
    assert "a demo account was reported" in seen["facts"]


def test_env_account_with_value_in_env_example(tmp_path):
    (tmp_path / "server").mkdir()
    (tmp_path / "server" / "seed.js").write_text(
        "const u = process.env.SEED_ADMIN_USERNAME || 'admin';\nconst p = process.env.SEED_ADMIN_PASSWORD;\n"
        "const db = process.env.DB_PASSWORD;\nbcrypt.hash(p)", encoding="utf-8")
    (tmp_path / "server" / ".env.example").write_text("DB_PASSWORD=pg\nSEED_ADMIN_PASSWORD=Admin@2026\n", encoding="utf-8")
    info = login_info("", tmp_path)
    assert info["credentials"] == [{"username": "admin", "password": "Admin@2026", "source": "server/.env.example"}]
    assert "env" not in info


def test_env_account_without_value_names_the_variable(tmp_path):
    (tmp_path / "seed.py").write_text(
        "import os\npw = os.getenv('DEMO_PASSWORD')\nuser = os.environ.get('DEMO_USER', 'demo')\ncheck_password(pw)",
        encoding="utf-8")
    info = login_info("", tmp_path)
    assert info["credentials"] == []
    assert info["env"] == {"user_var": "DEMO_USER", "username": "demo", "password_var": "DEMO_PASSWORD",
                           "password": "", "source": ""}


# ---------------------------------------------------------------------------- review regressions


@pytest.mark.parametrize("text", [
    "Login: POST /api/auth",
    "Đăng nhập: GET /login",
    "DB_USER=postgres DB_PASSWORD=supersecret",
    "SMTP_USER: mailer SMTP_PASS: hunter2xyz",
    "bypass: true, user: x",
])
def test_routes_and_service_secrets_are_not_demo_accounts(text):
    assert find_credentials(text) == []


@pytest.mark.parametrize("text,user,password", [
    ("**Tài khoản:** admin / **Mật khẩu:** 123456", "admin", "123456"),
    ("- **Username:** `admin`\n- **Password:** `admin123`", "admin", "admin123"),
])
def test_markdown_formatted_accounts(text, user, password):
    found = find_credentials(text)
    assert found and (found[0]["username"], found[0]["password"]) == (user, password)


def test_login_url_scan_is_fast_on_long_url_runs():
    from agentdev.api.services.lab_login import _URL

    started = time.monotonic()
    _URL.findall("http://localhost/" * 6000)
    assert time.monotonic() - started < 1.0
    assert _URL.findall("Mở http://localhost:3000/admin/login để vào") == ["http://localhost:3000/admin/login"]


# Regression: README listed accounts as "- Role: `email` / `password`" under a "Đăng nhập demo" heading, and the
# seed read the password as ``process.env.SEED_DEMO_PASSWORD || 'Demo@123'``; the Lab showed "no account".
@pytest.mark.parametrize("text,user,password", [
    ("- Manager: `manager@demo.local` / `Demo@123`", "manager@demo.local", "Demo@123"),
    ("**Tài khoản demo (seed):** manager@demo.local / Demo@123 (quản lý)", "manager@demo.local", "Demo@123"),
    ("## Đăng nhập demo\n\n- Quản lý: `boss` / `Boss#1`", "boss", "Boss#1"),
])
def test_role_list_accounts(text, user, password):
    found = find_credentials(text)
    assert found and (found[0]["username"], found[0]["password"]) == (user, password)


def test_slash_pairs_outside_a_login_section_are_not_accounts():
    assert find_credentials("## Cài đặt\n- Dùng: `npm` / `yarn`\n- Cổng: 3000 / 3001") == []


def test_env_default_password_with_readme_accounts(tmp_path):
    (tmp_path / "server").mkdir()
    (tmp_path / "server" / "seed.js").write_text(
        "const demoPassword = () => process.env.SEED_DEMO_PASSWORD || 'Demo@123';\nbcrypt.hashSync(demoPassword())",
        encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "## Đăng nhập demo\n\nMở http://localhost:3000/login:\n\n- Manager: `manager@demo.local` / `Demo@123`\n"
        "- Staff: `staff@demo.local` / `Demo@123`\n", encoding="utf-8")
    info = login_info("Xong.", tmp_path)
    assert [(c["username"], c["password"]) for c in info["credentials"]] == [
        ("manager@demo.local", "Demo@123"), ("staff@demo.local", "Demo@123")]
    assert "env" not in info
