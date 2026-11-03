import base64
import json
from datetime import datetime, timedelta, timezone

from agentdev.connections import account_info as mod
from agentdev.connections.store import Connection


def _jwt(claims):
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"e30.{body}.sig"


def _future(days=1):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def test_claude_account_reads_profile_models_and_usage(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(
        mod,
        "detect_cli",
        lambda vendor: {
            "logged_in": True,
            "detail": "Logged in",
            "profile": {
                "email": "a@b.co",
                "authMethod": "claude.ai",
                "orgId": "org1",
                "orgName": "ACME  CORP",
                "subscriptionType": "max",
            },
        },
    )
    (tmp_path / ".claude.json").write_text(
        json.dumps(
            {
                "oauthAccount": {"accountUuid": "u1", "emailAddress": "a@b.co", "displayName": "Ann", "seatTier": "team_premium"},
                "cachedUsageUtilization": {
                    "accountUuid": "u1",
                    "fetchedAtMs": 1_700_000_000_000,
                    "utilization": {
                        "limits": [
                            {"kind": "session", "percent": 30, "resets_at": _future()},
                            {"kind": "weekly_all", "percent": 28, "resets_at": "2000-01-01T00:00:00+00:00"},
                        ]
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    catalog = tmp_path / "cache" / "model-catalog"
    catalog.mkdir(parents=True)
    models = [
        {"id": "claude-old", "name": "Old", "section": "overflow"},
        {"id": "claude-fable-5-1", "name": "Fable 5.1", "section": "main"},
    ]
    (catalog / "org1-abc-cc.json").write_text(
        json.dumps({"fetchedAt": 2, "catalog": {"config": {"models": models}}}), encoding="utf-8"
    )
    (catalog / "other-abc-cc.json").write_text(json.dumps({"fetchedAt": 9, "catalog": {"config": {"models": []}}}))

    info = mod.account_info(Connection(id="c", vendor="anthropic", label="c", auth_type="cli"))

    assert info["loggedIn"] is True
    assert info["authMethod"] == "Claude AI"
    assert (info["displayName"], info["email"], info["organization"]) == ("Ann", "a@b.co", "ACME CORP")
    assert (info["plan"], info["seat"]) == ("Claude Max", "Premium")
    assert [m["id"] for m in info["models"]] == ["claude-fable-5-1", "claude-old"]
    session, weekly = info["usage"]["windows"]
    assert session["percent"] == 30 and session["resetsAt"]
    assert weekly == {"kind": "weekly_all", "percent": 0, "resetsAt": None, "windowMinutes": None}


def test_claude_usage_from_another_account_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(mod, "detect_cli", lambda vendor: {"logged_in": True, "profile": {"email": "a@b.co"}})
    (tmp_path / ".claude.json").write_text(
        json.dumps(
            {
                "oauthAccount": {"accountUuid": "u2", "emailAddress": "a@b.co"},
                "cachedUsageUtilization": {"accountUuid": "u1", "utilization": {"limits": [{"kind": "session", "percent": 5}]}},
            }
        )
    )
    info = mod.account_info(Connection(id="c", vendor="anthropic", label="c", auth_type="cli"))
    assert info["usage"] is None


def test_codex_account_reads_identity_and_rate_limits_without_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    monkeypatch.setattr(
        mod, "detect_cli", lambda vendor: {"logged_in": True, "status_text": "Logged in using ChatGPT"}
    )
    claims = {
        "email": "dev@x.io",
        "name": "Dev",
        "https://api.openai.com/auth": {"chatgpt_plan_type": "pro", "organizations": [{"title": "X Inc", "is_default": True}]},
    }
    (tmp_path / "auth.json").write_text(
        json.dumps({"tokens": {"id_token": _jwt(claims), "access_token": "SECRET-ACCESS", "refresh_token": "SECRET-REFRESH"}})
    )
    day = tmp_path / "sessions" / "2026" / "11" / "02"
    day.mkdir(parents=True)
    reset = int((datetime.now(timezone.utc) + timedelta(hours=2)).timestamp())
    event = {
        "timestamp": "2026-11-02T10:00:00Z",
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "rate_limits": {
                "primary": {"used_percent": 12.4, "window_minutes": 300, "resets_at": reset},
                "secondary": {"used_percent": 40, "window_minutes": 10080, "resets_at": reset + 86400},
            },
        },
    }
    (day / "rollout-1.jsonl").write_text("{}\n" + json.dumps(event) + "\n", encoding="utf-8")

    info = mod.account_info(Connection(id="o", vendor="openai", label="o", auth_type="cli"))

    assert info["authMethod"] == "ChatGPT"
    assert (info["email"], info["displayName"], info["organization"], info["plan"]) == ("dev@x.io", "Dev", "X Inc", "ChatGPT Pro")
    assert [(w["kind"], w["percent"]) for w in info["usage"]["windows"]] == [("session", 12), ("weekly", 40)]
    assert "SECRET" not in json.dumps(info)


def test_logged_out_cli_and_oauth_connections(monkeypatch):
    monkeypatch.setattr(mod, "detect_cli", lambda vendor: {"logged_in": False, "detail": "Not logged in"})
    info = mod.account_info(Connection(id="o", vendor="openai", label="o", auth_type="cli"))
    assert info["loggedIn"] is False and info["email"] is None

    oauth = Connection(id="g", vendor="gemini", label="g", auth_type="oauth", secret=json.dumps({"email": "g@x.io", "access_token": "t"}))
    info = mod.account_info(oauth)
    assert (info["authMethod"], info["email"], info["loggedIn"]) == ("Google OAuth", "g@x.io", True)
    assert "access_token" not in json.dumps(info)
