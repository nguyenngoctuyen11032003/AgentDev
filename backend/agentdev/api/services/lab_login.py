"""Login details of an app a Lab run built: does it need a login, and which demo account did the team report?

A tester cannot look at a web app behind a login page without its account, so the Lab finds the demo
username/password in the final answer (or in the README / seed files the run wrote) and shows them next to the
run's preview. An app with a login and no reported account is a workflow finding (see lab_diagnosis).

Reads at most a few small text files of the run's output folder; everything else is pure.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCAN_MAX_FILES = 200  # source files looked at for a login form
SCAN_MAX_BYTES = 60_000  # bytes read per file
DOC_NAMES = re.compile(r"^(readme|seed|demo|accounts?|credentials?|login|users?)([._-].*)?\.(md|txt|json|ya?ml|js|ts|py|sql|env\.example)$|^\.env\.example$",
                       re.IGNORECASE)
SOURCE_EXTS = {".html", ".htm", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".py", ".php", ".rb", ".go", ".java",
               ".cs", ".kt"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".cache", ".nuxt",
             ".turbo", "coverage", ".pytest_cache", ".mypy_cache", ".idea", ".vscode",
             # agent tool folders: .claude/worktrees holds whole copies of the project
             ".claude", ".codex", ".cursor", "worktrees"}
WALK_MAX_FILES = 20_000  # files listed per run (bounds the walk of a huge folder)
# Where login code lives: these files are read first, so a big project's SignInPage.tsx is not past the cap.
_AUTH_PATH = re.compile(r"auth|login|log-in|signin|sign-in|sign_in|session|account|user|password|middleware|guard",
                        re.IGNORECASE)
_TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|e2e|spec|fixtures?|mocks?)(/|$)|\.(test|spec)\.", re.IGNORECASE)
MAX_CREDENTIALS = 5

# A login mentioned in the final answer (with an account next to it, see login_info).
_AUTH = re.compile(
    r"type\s*=\s*[\"']password[\"']|\b(login|log-in|signin|sign-in|sign_in|đăng nhập|authenticate|bcrypt|passport|"
    r"next-auth|jsonwebtoken|jwt\.(sign|verify)|check_password|password_hash|flask_login|LoginManager|"
    r"createUserWithEmailAndPassword|signInWithPassword)\b",
    re.IGNORECASE,
)
# Code that really checks a login in the app's files. The bare word "login" / "Đăng nhập" is NOT enough: a landing
# page has a "Đăng nhập" button or a /login link and needs no account to try.
_AUTH_CODE = re.compile(
    r"\b(bcrypt|bcryptjs|passport|next-auth|jsonwebtoken|jwt\.(sign|verify)|check_password|password_hash|"
    r"password_verify|flask_login|LoginManager|login_required|login_user|createUserWithEmailAndPassword|"
    r"signInWithPassword|signInWithEmailAndPassword|express-session|cookie-session|authenticate\s*\()"
    # a login handler: def login(...), function handleLogin(...), const signIn = async (...), app.post('/login'
    r"|\b(def|function)\s+(log_?in|sign_?in|handle_?log_?in|do_?log_?in|authenticate)\s*\("
    # (an object key "login: (v) => play()" of a sound map is not one)
    r"|\b(const|let|var)\s+(log_?in|sign_?in|handle_?log_?in|do_?log_?in)\s*=\s*(async\s*)?(function\b|\([^)]*\)\s*=>|\w+\s*=>)"
    r"|\b(sign_?in|handle_?log_?in|do_?log_?in)\s*[:=]\s*(async\s*)?(function\b|\([^)]*\)\s*=>|\w+\s*=>)"
    r"|\.(post|route|api_route)\(\s*[\"'`]/(api/)?(v\d/)?(auth/)?(login|signin|sign-in|dang-nhap)[\"'`]"
    # the typed password compared with a stored one: password === 'x', user.password == pw
    r"|\bpassword\s*[!=]==?\s*[\w\"'`]",
    re.IGNORECASE,
)
_PASSWORD_FIELD = re.compile(r"type\s*=\s*[\"']password[\"']", re.IGNORECASE)
# Plain pages: a password box there is only a login when some code checks it (a static mock-up form is not).
_PAGE_EXTS = {".html", ".htm"}

# Whole words only: DB_USER / SMTP_PASS / bypass are not an app login (a database or mail secret must never be
# shown as the demo account).
_B = r"(?<![A-Za-z0-9_])"
_E = r"(?![A-Za-z0-9_])"
_USER_KEY = _B + r"(?:user\s*name|username|user|e-?mail|login|account|tài\s*khoản|tên\s*đăng\s*nhập|người\s*dùng|帐号|账号|用户名|邮箱)" + _E
_PASS_KEY = _B + r"(?:pass\s*word|password|pass|pwd|mật\s*khẩu|mk|密码)" + _E
# "tài khoản demo: x", "default password: y"
_USER_KEY += r"(?:\s+(?:demo|thử|test|mặc\s*định|default|admin))?"
_PASS_KEY += r"(?:\s+(?:demo|thử|test|mặc\s*định|default))?"
# Markdown around the value: "**Username:** `admin`"
_VALUE = r"[`'\"*_]*\s*[`'\"*]*([^\s`'\"*,;|<>()\[\]]{1,80})[`'\"*]*"
_SEP = r"[*_]*\s*(?:[:=：]|là|is)[*_]*\s*"
# "user: admin, password: 123456" on one line (any order of the two, at most 80 chars between them)
_PAIR = re.compile(_USER_KEY + _SEP + _VALUE + r".{0,80}?" + _PASS_KEY + _SEP + _VALUE, re.IGNORECASE)
_PAIR_REV = re.compile(_PASS_KEY + _SEP + _VALUE + r".{0,80}?" + _USER_KEY + _SEP + _VALUE, re.IGNORECASE)
# "tài khoản admin / admin123", "login: admin/secret"
_SLASH = re.compile(r"(?:tài\s*khoản|account|login|đăng\s*nhập|credentials?)[^\n/]{0,30}?[:\s]\s*[`'\"*]*"
                    r"([\w.@+-]{2,80})[`'\"*]*\s*/\s*[`'\"*]*([^\s`'\"*/,;|]{2,80})", re.IGNORECASE)
# "manager@demo.local / Demo@123": an e-mail login followed by its password, anywhere on a line.
_Q = r"[`'\"*]*"
_SLASH_PASS = r"\s*/\s*" + _Q + r"([^\s`'\"*/,;|]{2,80})"
_EMAIL_SLASH = re.compile(_Q + r"([\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63})+)" + _Q + _SLASH_PASS)
# "- Manager: `boss` / `Boss#1`" -- only inside a section whose heading is about logging in / demo accounts.
_ROLE_SLASH = re.compile(r"^[\s>*|-]*[^:/\n]{1,30}:[*_]*\s*" + _Q + r"([\w.@+-]{2,80})" + _Q + _SLASH_PASS)
_HEADING = re.compile(r"^\s*#{1,6}\s+(.*)$")
_LOGIN_HEADING = re.compile(r"đăng\s*nhập|login|sign\s*-?in|tài\s*khoản|account|credential|demo|登录|账号|帐号",
                            re.IGNORECASE)
_USER_LINE = re.compile(r"^[\s>*#|-]*" + _USER_KEY + r"[*_\s]*" + _SEP + _VALUE, re.IGNORECASE)
_PASS_LINE = re.compile(r"^[\s>*#|-]*" + _PASS_KEY + r"[*_\s]*" + _SEP + _VALUE, re.IGNORECASE)
_PLACEHOLDER = re.compile(r"^(<.*>|\.\.\.|…|xxx+|\*+|your[_-]?\w*|example|\$\{.*\}|none|null|n/a|-)$", re.IGNORECASE)
# Bounded path (an unbounded one backtracked quadratically on a 100k-char run of URLs).
_URL = re.compile(r"\bhttps?://(?:localhost|127\.0\.0\.1)(?::\d+)?(?:/[^\s`'\")\]/]{0,80}){0,6}?/(?:login|signin|sign-in|dang-nhap|auth)\b[^\s`'\")\]]{0,200}",
                  re.IGNORECASE)


# Demo accounts set through environment variables (``SEED_ADMIN_PASSWORD``, ``process.env.ADMIN_USER || 'admin'``,
# ``os.getenv("DEMO_PASSWORD", "x")``). Only names that read like an app account, not a database/mail/API secret.
_ENV_REF = re.compile(
    r"(?:process\.)?env\.([A-Z][A-Z0-9_]{2,60})(?:\s*(?:\|\||\?\?)\s*['\"`]([^'\"`\n]{1,80})['\"`])?"
    r"|(?:getenv|environ\.get)\(\s*['\"]([A-Z][A-Z0-9_]{2,60})['\"](?:\s*,\s*['\"]([^'\"\n]{0,80})['\"])?"
    r"|environ\[\s*['\"]([A-Z][A-Z0-9_]{2,60})['\"]\s*\]"
)
_ENV_ACCOUNT = re.compile(r"ADMIN|SEED|DEMO|DEFAULT|INITIAL|LOGIN|ROOT_USER|SUPERUSER|TEST_USER|OWNER", re.IGNORECASE)
_ENV_OTHER = re.compile(r"DB|DATABASE|PG|POSTGRES|MYSQL|MONGO|REDIS|SMTP|MAIL|API|SECRET|JWT|TOKEN|KEY|S3|AWS|SMS",
                        re.IGNORECASE)
_ENV_USER = re.compile(r"USER(NAME)?|EMAIL|LOGIN|ACCOUNT", re.IGNORECASE)
_ENV_PASS = re.compile(r"PASS(WORD)?|PWD", re.IGNORECASE)
_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]{2,60})\s*=\s*['\"]?([^'\"#\r\n]*?)['\"]?\s*(?:#.*)?$", re.MULTILINE)
_ENV_FILES = re.compile(r"^\.env(\.(example|sample|local|development|template))?$", re.IGNORECASE)


def _env_kind(name: str) -> str:
    """"user" / "password" for an app-account variable, else ""."""
    if not _ENV_ACCOUNT.search(name) or _ENV_OTHER.search(re.sub(r"EMAIL|PASSWORD|PASS", "", name, flags=re.IGNORECASE)):
        return ""
    if _ENV_PASS.search(name):
        return "password"
    if _ENV_USER.search(name):
        return "user"
    return ""


def env_refs(text: str) -> Dict[str, str]:
    """``{VAR: default}`` of the account variables ``text`` reads (default "" when the code gives none)."""
    found: Dict[str, str] = {}
    for match in _ENV_REF.finditer(text or ""):
        name = match.group(1) or match.group(3) or match.group(5)
        default = match.group(2) or match.group(4) or ""
        if name and _env_kind(name) and (default or name not in found):
            found[name] = default.strip()
    return found


def env_values(text: str) -> Dict[str, str]:
    """``{VAR: value}`` of a .env-style file (placeholders dropped)."""
    out: Dict[str, str] = {}
    for name, value in _ENV_LINE.findall(text or ""):
        value = value.strip()
        if value and not _PLACEHOLDER.match(value) and not re.match(r"^(change|replace|set)[_-]?me", value, re.IGNORECASE):
            out[name] = value
    return out


def env_login(refs: Dict[str, str], values: Dict[str, Tuple[str, str]]) -> Optional[Dict[str, Any]]:
    """The env-variable account: ``{user_var, username, password_var, password, source}`` from the variables the
    code reads (``refs``, with defaults) and the values .env files give (``values``: VAR -> (value, file))."""
    users = [n for n in refs if _env_kind(n) == "user"]
    passwords = [n for n in refs if _env_kind(n) == "password"]
    if not passwords:
        return None
    password_var = passwords[0]
    user_var = next((u for u in users if u.split("_")[0] == password_var.split("_")[0]), users[0] if users else "")
    username, user_file = values.get(user_var, (refs.get(user_var, ""), "")) if user_var else ("", "")
    password, pass_file = values.get(password_var, (refs.get(password_var, ""), ""))
    return {"user_var": user_var, "username": (username or "")[:80], "password_var": password_var,
            "password": (password or "")[:80], "source": pass_file or user_file}


def _clean(value: str) -> str:
    return value.strip().strip(".:").strip()


# Words that sit where a value would ("Login: POST /api/auth", "**Tài khoản:** admin / **Mật khẩu:** x").
_NOT_VALUE = {"password", "pass", "pwd", "mật", "mk", "user", "username", "email", "true", "false", "get", "post", "put",
              "patch", "delete", "head", "options", "api", "http", "https"}


def _usable(user: str, password: str) -> bool:
    if not (user and password) or _PLACEHOLDER.match(user) or _PLACEHOLDER.match(password):
        return False
    for value in (user, password):
        if value.lower() in _NOT_VALUE or value.startswith(("/", "$", "{")):
            return False
    return True


def find_credentials(text: str, source: str = "answer") -> List[Dict[str, str]]:
    """Demo accounts written in ``text``: same-line pairs, "account x / y", and a user line followed by a password
    line (within 2 lines). Placeholders ("<password>", "your_password") are ignored."""
    found: List[Tuple[str, str]] = []
    login_section = False
    for line in (text or "").splitlines():
        heading = _HEADING.match(line)
        if heading:
            login_section = bool(_LOGIN_HEADING.search(heading.group(1)))
            continue
        if login_section:
            for match in _ROLE_SLASH.finditer(line):
                found.append((match.group(1), match.group(2)))
        for match in _EMAIL_SLASH.finditer(line):
            found.append((match.group(1), match.group(2)))
        for match in _PAIR.finditer(line):
            found.append((match.group(1), match.group(2)))
        for match in _PAIR_REV.finditer(line):
            found.append((match.group(2), match.group(1)))
        for match in _SLASH.finditer(line):
            found.append((match.group(1), match.group(2)))
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        user = _USER_LINE.match(line)
        if not user:
            continue
        for nxt in lines[i + 1:i + 3]:
            password = _PASS_LINE.match(nxt)
            if password:
                found.append((user.group(1), password.group(1)))
                break
    out: List[Dict[str, str]] = []
    seen = set()
    for user, password in found:
        user, password = _clean(user), _clean(password)
        if not _usable(user, password) or (user, password) in seen:
            continue
        seen.add((user, password))
        out.append({"username": user[:80], "password": password[:80], "source": source})
    return out[:MAX_CREDENTIALS]


def _walk(root: Path):
    count = 0
    for folder, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            count += 1
            if count > WALK_MAX_FILES:
                return
            yield Path(folder) / name


def _scan_order(root: Path, path: Path) -> int:
    """Docs first (they list the accounts), then files named like login code, then other source, tests last."""
    if DOC_NAMES.match(path.name):
        return 0
    rel = path.relative_to(root).as_posix()
    if _TEST_PATH.search(rel):
        return 3
    return 1 if _AUTH_PATH.search(rel) else 2


def _read(path: Path) -> str:
    try:
        raw = path.read_bytes()[:SCAN_MAX_BYTES]
    except OSError:
        return ""
    if b"\0" in raw:
        return ""
    return raw.decode("utf-8", errors="ignore")


def login_info(answer: str, output_dir: Any = None) -> Optional[Dict[str, Any]]:
    """``{"needs_login", "credentials", "login_url"}`` for a run, or None when it has nothing to do with a login
    (no login form in its files and no account in its answer)."""
    credentials = find_credentials(answer, "answer")
    needs_login = bool(_AUTH.search(answer or "")) and bool(credentials)
    urls = _URL.findall(answer or "")
    root = Path(str(output_dir)) if output_dir else None
    refs: Dict[str, str] = {}
    values: Dict[str, Tuple[str, str]] = {}
    auth_code = False  # code in the app's files that checks a login
    if root and root.is_dir():
        candidates = []
        for path in _walk(root):
            if _ENV_FILES.match(path.name):
                rel = path.relative_to(root).as_posix()
                for name, value in env_values(_read(path)).items():
                    # a real .env wins over the example
                    if name not in values or not path.name.lower().startswith(".env."):
                        values[name] = (value, rel)
            if DOC_NAMES.match(path.name) or path.suffix.lower() in SOURCE_EXTS:
                candidates.append(path)
        candidates.sort(key=lambda p: (_scan_order(root, p), len(p.parts), str(p)))
        for path in candidates[:SCAN_MAX_FILES]:
            is_doc = bool(DOC_NAMES.match(path.name))
            text = _read(path)
            if path.suffix.lower() in SOURCE_EXTS:
                for name, default in env_refs(text).items():
                    if default or name not in refs:
                        refs[name] = default
            suffix = path.suffix.lower()
            if not needs_login and suffix in SOURCE_EXTS:
                if _AUTH_CODE.search(text):
                    auth_code = True
                elif _PASSWORD_FIELD.search(text) and suffix not in _PAGE_EXTS:
                    auth_code = True  # a password box inside an app component (Login.vue, LoginForm.tsx)
                needs_login = auth_code
            if is_doc and len(credentials) < MAX_CREDENTIALS:
                rel = path.relative_to(root).as_posix()
                for item in find_credentials(text, rel):
                    if all((c["username"], c["password"]) != (item["username"], item["password"]) for c in credentials):
                        credentials.append(item)
    env = env_login(refs, values) if needs_login else None
    if env and env["username"] and env["password"] and len(credentials) < MAX_CREDENTIALS and             all((c["username"], c["password"]) != (env["username"], env["password"]) for c in credentials):
        credentials.append({"username": env["username"], "password": env["password"],
                            "source": env["source"] or env["password_var"]})
    if not needs_login:
        # No login to pass (a landing page, a static site): no account to show, even if a README lists one.
        return None
    info: Dict[str, Any] = {"needs_login": needs_login, "credentials": credentials[:MAX_CREDENTIALS],
                            "login_url": urls[0].rstrip(".,;:!?") if urls else ""}
    if env and not credentials:
        # No full account, but the app says how one is made: name the variables to set.
        info["env"] = env
    return info


def judge_fact(info: Optional[Dict[str, Any]]) -> str:
    """One run-facts line for the judge (the app's login and whether an account was reported)."""
    if not info or not info.get("needs_login"):
        return ""
    if info.get("credentials"):
        return "- login: the app has a login; a demo account was reported"
    return "- login: the app has a login but NO demo account (username/password) was reported"
