"""Symmetric encryption for connector tokens held in SQLite.

This guards against the database file leaking on its own — a backup, a volume
snapshot — without the key. It offers nothing against anyone who can read the
backend's environment, and it is not a substitute for scoping connections to a
user, which this application does not yet do.
"""

import base64
import logging
import os

from Crypto.Cipher import AES

logger = logging.getLogger(__name__)

_PREFIX = "v1"
_NONCE_BYTES = 12
_warned = False


def _key() -> bytes | None:
    raw = os.getenv("CONNECTOR_TOKEN_SECRET", "").strip()
    if not raw:
        return None
    try:
        key = base64.b64decode(raw)
    except Exception:
        logger.warning("CONNECTOR_TOKEN_SECRET is not valid base64; storing tokens in plaintext")
        return None
    if len(key) not in (16, 24, 32):
        logger.warning("CONNECTOR_TOKEN_SECRET must decode to 16, 24 or 32 bytes; storing tokens in plaintext")
        return None
    return key


def _warn_once():
    global _warned
    if not _warned:
        logger.warning(
            "CONNECTOR_TOKEN_SECRET is not set - connector OAuth tokens will be stored "
            "in plaintext. Set it to base64 of 32 random bytes before deploying."
        )
        _warned = True


def encrypt(plaintext: str | None) -> str | None:
    if plaintext is None:
        return None
    key = _key()
    if key is None:
        _warn_once()
        return plaintext
    nonce = os.urandom(_NONCE_BYTES)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))
    return ":".join([
        _PREFIX,
        base64.b64encode(nonce).decode(),
        base64.b64encode(ciphertext + tag).decode(),
    ])


def decrypt(value: str | None) -> str | None:
    """Return the plaintext.

    A value without the version prefix is passed through unchanged, so enabling
    encryption on an existing database does not strand tokens written before the
    key existed.
    """
    if value is None:
        return None
    parts = value.split(":", 2)
    if len(parts) != 3 or parts[0] != _PREFIX:
        return value
    key = _key()
    if key is None:
        raise RuntimeError(
            "Stored connector token is encrypted but CONNECTOR_TOKEN_SECRET is not set. "
            "Restore the key, or disconnect and reconnect the account."
        )
    nonce = base64.b64decode(parts[1])
    blob = base64.b64decode(parts[2])
    ciphertext, tag = blob[:-16], blob[-16:]
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")
