import sys

import pytest

from agentdev.connections.secret_box import (
    SecretDecryptError,
    decrypt,
    encrypt,
    is_encrypted,
)

win = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows only")


def test_legacy_passthrough():
    assert decrypt("sk-legacy") == "sk-legacy"
    assert decrypt("") == ""
    assert not is_encrypted("sk-legacy")


def test_env_ref_and_empty_unchanged():
    assert encrypt("${ANTHROPIC_API_KEY}") == "${ANTHROPIC_API_KEY}"
    assert encrypt("") == ""


def test_plain_prefix():
    assert decrypt("plain:abc") == "abc"


@win
def test_roundtrip_unicode():
    for v in ["sk-123", "khóa-bí-mật-🔑"]:
        s = encrypt(v)
        assert s.startswith("dpapi:") and v not in s
        assert is_encrypted(s)
        assert decrypt(s) == v


@win
def test_tampered_raises():
    s = encrypt("secret")
    with pytest.raises(SecretDecryptError):
        decrypt(s[:-6] + "AAAAAA")
    with pytest.raises(SecretDecryptError):
        decrypt("dpapi:!!notbase64")
