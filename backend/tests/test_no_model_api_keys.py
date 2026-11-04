"""Guard: AgentDev runs every model on account sign-in only, never on API keys.

Models are reached through account connections on the Connections page: Claude via the
``claude`` CLI login, ChatGPT via the ``codex`` CLI login, Gemini via Google OAuth sign-in.
This test scans the shipped source for any trace of the old API-key way:

* model API-key environment variables (``GEMINI_API_KEY``, ``OPENAI_API_KEY`` ...);
* the ``AUTH_API_KEY`` identifier and ``api_key`` / ``apiKey`` identifiers in code;
* ``api_key:`` fields in YAML;
* user-facing text that mentions an API key ("API key", "khóa API", "API 密钥"); pure comment
  lines and sentences that only say no API key is needed ("No API key needed") are not hits.

Third-party skill docs (``workspace/skills``), tests, lock files and ``node_modules`` are
not scanned.

Allow-list (``ALLOWED_LINES``): a line is exempt only when it matches one of these exact
patterns, each of which exists because a third-party SDK forces an ``api_key``-named
parameter even though the request carries an OAuth Bearer token:

* ``genai.Client(api_key="oauth-placeholder", ...)`` - google-genai refuses to build a
  client without an API key. The value is a fixed dummy and the caller strips the
  ``x-goog-api-key`` header right after (``GeminiProvider._strip_api_key_header``), so the
  request is authenticated by the ``Authorization: Bearer <OAuth token>`` header only.

Do not widen the allow-list for convenience: remove the API-key code instead.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Paths (relative to the repo root, forward slashes) whose files are scanned.
SCAN_ROOTS = (
    "backend/agentdev",
    "workspace/functions",
    "workspace/workflows",
    "frontend/src",
)
SCAN_FILES = (".env.example",)

SCAN_SUFFIXES = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".json",
    ".yaml", ".yml", ".md", ".html", ".txt", ".toml", ".cfg", ".ini",
}

EXCLUDED_PARTS = {"node_modules", "__pycache__", "tests", "test", "__tests__", "dist", ".venv"}
EXCLUDED_PREFIXES = ("workspace/skills/",)
LOCK_FILE_NAMES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock", "poetry.lock"}
TEST_FILE_RE = re.compile(r"(^test_.*\.py$|_test\.py$|\.(spec|test)\.[jt]sx?$)")

RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "model API-key env var",
        re.compile(r"\b(?:ANTHROPIC|OPENAI|GEMINI|GOOGLE|AGENTDEV_VEO)_API_KEY\b"),
    ),
    ("AUTH_API_KEY identifier", re.compile(r"\bAUTH_API_KEY\b")),
    ("api_key identifier", re.compile(r"\bapi_key\b|\bapiKey\b")),
    (
        "API-key UI text",
        re.compile(r"(?<![\w-])api[ \-]?keys?\b|kh[oó]a\s+api|API\s*密钥", re.IGNORECASE),
    ),
)
UI_TEXT_RULE = "API-key UI text"
# A sentence that only says no API key is needed is compliant, not a hit.
NEGATED_UI_TEXT = re.compile(
    r"\b(?:no|without(?:\s+any)?|needs?\s+no|not\s+need)\s+(?:third-party\s+)?api[ \-]?keys?\b"
    r"|kh[oô]ng\s+c[aầ]n\s+(?:kh[oó]a\s+api|api[ \-]?key)"
    r"|无需\s*API",
    re.IGNORECASE,
)
COMMENT_LINE = re.compile(r"^(?:#|//|/?\*)")
# Only applied to YAML files.
YAML_API_KEY_FIELD = re.compile(r"^\s*(?:-\s*)?['\"]?api_key['\"]?\s*:")

# Exact, documented exemptions (see module docstring). Matched against the stripped line.
ALLOWED_LINES: tuple[re.Pattern[str], ...] = (
    re.compile(r"""^(?:\w+\s*=\s*)?genai\.Client\(api_key=(["'])oauth-placeholder\1(?:,.*)?\)$"""),
)


# Lines that mention API keys only to BLOCK them. Each entry is (file, exact text on the line, why). A line in
# any other file, or with any other text, is still a hit: adding a way to use a key cannot hide here.
BLOCKING_LINES: tuple[tuple[str, str, str], ...] = (
    ("backend/agentdev/connections/cli_auth.py", '_API_KEY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", '
     '"OPENAI_API_KEY", "CODEX_API_KEY")', "removed from the CLI environment so the account login is used"),
    ("backend/agentdev/connections/cli_auth.py", '"""Environment for spawning a CLI: API-key vars dropped so the '
     'account login is used."""', "docstring of that removal"),
    ("backend/agentdev/connections/account_info.py", '"mode": "chatgpt" if tokens else ("api_key" if '
     'auth.get("OPENAI_API_KEY") else None),', "detects a Codex CLI logged in with a key, to refuse it"),
    ("backend/agentdev/connections/account_info.py", 'mode = identity.get("mode") or ("api_key" if "api key" in text',
     "same detection from the CLI's own status text"),
    ("backend/agentdev/connections/account_info.py", 'if mode == "api_key":', "refuses that Codex login"),
    ("backend/agentdev/connections/account_info.py", 'info["detail"] = "Codex is signed in with an API key; sign in '
     'with ChatGPT instead (`codex login`)."', "the refusal message"),
    ("backend/agentdev/connections/autobind.py", "Older workflows describe each agent with ``provider: anthropic`` "
     "(plus an ``api_key`` that is", "docstring: old YAML keys are dropped"),
    ("backend/agentdev/connections/autobind.py", "Leftover ``api_key`` / ``base_url`` keys are dropped so no "
     "credential is ever read from YAML.", "docstring of that removal"),
    ("backend/agentdev/connections/autobind.py", '_LEGACY_KEYS = ("api_key", "base_url")', "keys dropped from old YAML"),
    ("backend/agentdev/connections/resolver.py", '"""Error for a connection saved by an older version (API key): it '
     'can only be replaced."""', "old saved connection -> sign in again"),
    ("backend/agentdev/connections/store.py", '"""Saved by an older version (API key): unusable until replaced by an '
     'account sign-in."""', "same, store side"),
    ("backend/agentdev/connections/store.py", '# Older versions saved API-key entries ("api_key" or no auth_type). '
     'They still load,', "old entries load (never deleted) only to ask for a new sign-in"),
    ("backend/agentdev/connections/store.py", 'auth_type=item.get("auth_type") or "api_key",', "same"),
    ("backend/agentdev/entity/configs/node/agent.py", '_REMOVED_CREDENTIAL_KEYS = ("api_key", "base_url")',
     "a node config with these keys is rejected"),
    ("frontend/src/utils/errorTranslate.js", "{ key: 'codex_not_account', re: /Codex is signed in with an API key/i },",
     "translates the refusal above"),
    ("frontend/src/views/LaunchView.vue", "[/invalid.?api.?key|incorrect api key|api key not valid|",
     "detects the CLI's 'Invalid API key - run /login' text (an expired sign-in) to say: sign in again"),
)


def _is_blocking_line(rel: str, stripped: str) -> bool:
    return any(rel == path and stripped.startswith(text) for path, text, _ in BLOCKING_LINES)


def _is_excluded(rel: str) -> bool:
    if rel.startswith(EXCLUDED_PREFIXES):
        return True
    parts = rel.split("/")
    if any(part in EXCLUDED_PARTS for part in parts[:-1]):
        return True
    name = parts[-1]
    return name in LOCK_FILE_NAMES or bool(TEST_FILE_RE.search(name))


def _candidate_files() -> list[str]:
    """Tracked plus new (untracked, not ignored) files under the scanned roots."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z",
             "--", *SCAN_ROOTS, *SCAN_FILES],
            cwd=REPO_ROOT, capture_output=True, check=True,
        ).stdout.decode("utf-8", "replace")
        files = [f for f in out.split("\0") if f]
    except (OSError, subprocess.CalledProcessError):
        files = []
        for root in SCAN_ROOTS:
            for dirpath, dirnames, filenames in os.walk(REPO_ROOT / root):
                dirnames[:] = [d for d in dirnames if d not in EXCLUDED_PARTS]
                for name in filenames:
                    files.append((Path(dirpath) / name).relative_to(REPO_ROOT).as_posix())
        files.extend(f for f in SCAN_FILES if (REPO_ROOT / f).is_file())
    result = []
    for rel in sorted(set(files)):
        if _is_excluded(rel):
            continue
        if rel in SCAN_FILES or Path(rel).suffix.lower() in SCAN_SUFFIXES:
            if (REPO_ROOT / rel).is_file():
                result.append(rel)
    return result


def _only_negated_mentions(line: str) -> bool:
    """True when every API-key mention on the line says one is *not* needed."""
    ui_rule = dict(RULES)[UI_TEXT_RULE]
    return not ui_rule.search(NEGATED_UI_TEXT.sub(" ", line))


def find_api_key_hits() -> list[str]:
    hits: list[str] = []
    for rel in _candidate_files():
        try:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        is_yaml = rel.endswith((".yaml", ".yml"))
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if any(allowed.match(stripped) for allowed in ALLOWED_LINES) or _is_blocking_line(rel, stripped):
                continue
            reasons = [name for name, rx in RULES if rx.search(line)]
            if UI_TEXT_RULE in reasons and (
                COMMENT_LINE.match(stripped) or _only_negated_mentions(line)
            ):
                reasons.remove(UI_TEXT_RULE)
            if is_yaml and YAML_API_KEY_FIELD.match(line):
                reasons.append("YAML api_key field")
            if reasons:
                hits.append(f"{rel}:{lineno}: [{', '.join(reasons)}] {stripped[:160]}")
    return hits


def test_allow_list_is_exact() -> None:
    allowed = ALLOWED_LINES[0]
    assert allowed.match('client = genai.Client(api_key="oauth-placeholder", http_options=opts)')
    assert allowed.match('genai.Client(api_key="oauth-placeholder")')
    assert not allowed.match('genai.Client(api_key=os.environ["GEMINI_API_KEY"])')
    assert not allowed.match('genai.Client(api_key=key)')
    assert not allowed.match('client = OpenAI(api_key="oauth-placeholder")')


def test_negated_ui_text_is_not_a_hit() -> None:
    assert _only_negated_mentions("Sign in with your account. No API key needed.")
    assert _only_negated_mentions("không cần khóa API")
    assert not _only_negated_mentions('"api_key": "API Key"')
    assert not _only_negated_mentions("No API key needed. Paste your API key here.")


def test_scanner_sees_the_source_tree() -> None:
    files = _candidate_files()
    assert any(f.startswith("backend/agentdev/") for f in files)
    assert any(f.startswith("frontend/src/") for f in files)
    assert not any(f.startswith("workspace/skills/") for f in files)


def test_no_model_api_keys_in_source() -> None:
    hits = find_api_key_hits()
    assert not hits, (
        "Models must run on account sign-in only (Connections page). Remove these API-key "
        "traces, or - only for an SDK that forces an api_key parameter while sending an OAuth "
        "Bearer token - add an exact, documented pattern to ALLOWED_LINES:\n" + "\n".join(hits)
    )


def test_blocking_lines_cannot_hide_a_new_key_path() -> None:
    assert not _is_blocking_line("backend/agentdev/connections/cli_auth.py", 'key = os.environ["OPENAI_API_KEY"]')
    assert not _is_blocking_line("backend/agentdev/other.py", '_LEGACY_KEYS = ("api_key", "base_url")')
