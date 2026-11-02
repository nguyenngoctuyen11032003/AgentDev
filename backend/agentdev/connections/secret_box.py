"""Encryption-at-rest helper for stored secrets (DPAPI on Windows, no extra deps)."""

from __future__ import annotations

import base64
import re
import sys

DPAPI_PREFIX = "dpapi:"
PLAIN_PREFIX = "plain:"
_ENV_REF = re.compile(r"^\$\{[^}]+\}$")


class SecretDecryptError(Exception):
    """Raised when an encrypted secret cannot be decrypted."""


def _blob(data: bytes):
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf, DATA_BLOB


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes

    blob_in, _keep, DATA_BLOB = _blob(data)
    blob_out = DATA_BLOB()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
    if not ok:
        raise SecretDecryptError("DPAPI operation failed (secret may belong to a different Windows user)")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def is_encrypted(stored: str) -> bool:
    return isinstance(stored, str) and stored.startswith(DPAPI_PREFIX)


def encrypt(plain: str) -> str:
    if not plain or _ENV_REF.match(plain):
        return plain
    if sys.platform != "win32":
        return PLAIN_PREFIX + plain
    raw = _dpapi(plain.encode("utf-8"), True)
    return DPAPI_PREFIX + base64.b64encode(raw).decode("ascii")


def decrypt(stored: str) -> str:
    if not stored:
        return stored
    if stored.startswith(PLAIN_PREFIX):
        return stored[len(PLAIN_PREFIX):]
    if stored.startswith(DPAPI_PREFIX):
        if sys.platform != "win32":
            raise SecretDecryptError("DPAPI secrets can only be decrypted on Windows")
        try:
            raw = base64.b64decode(stored[len(DPAPI_PREFIX):], validate=True)
            return _dpapi(raw, False).decode("utf-8")
        except SecretDecryptError:
            raise
        except Exception as exc:
            raise SecretDecryptError(f"Cannot decrypt stored secret: {exc}") from exc
    return stored
