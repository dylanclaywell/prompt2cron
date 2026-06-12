"""Anthropic API key storage.

The key is stored in the operating system's credential store via ``keyring``
(Windows Credential Manager, macOS Keychain, or the Linux Secret Service). A key
saved there takes precedence over the ANTHROPIC_API_KEY environment variable,
which remains a fallback. The key is never written to disk in plaintext.
"""

from __future__ import annotations

import os

import keyring
from keyring.errors import KeyringError

SERVICE = "prompt2cron"
USERNAME = "anthropic_api_key"

ENV_VAR = "ANTHROPIC_API_KEY"


class KeyStoreError(Exception):
    """Raised when the OS credential store can't be used."""


def keyring_available() -> bool:
    """True if a real (non-failing) keyring backend is configured."""
    backend = keyring.get_keyring()
    return "fail.Keyring" not in f"{type(backend).__module__}.{type(backend).__name__}"


def get_stored_key() -> str | None:
    """Return the key from the keychain, or None."""
    try:
        key = keyring.get_password(SERVICE, USERNAME)
    except KeyringError:
        return None
    return key.strip() if key and key.strip() else None


def get_api_key() -> str | None:
    """Resolve the effective key: stored (keychain) first, then the env var."""
    return get_stored_key() or (os.environ.get(ENV_VAR) or "").strip() or None


def key_source() -> str | None:
    """Where the effective key comes from: 'keyring', 'env', or None."""
    if get_stored_key():
        return "keyring"
    if (os.environ.get(ENV_VAR) or "").strip():
        return "env"
    return None


def save_api_key(key: str) -> None:
    """Store the key in the OS credential store.

    Raises KeyStoreError if no usable keyring backend is available.
    """
    if not keyring_available():
        raise KeyStoreError(
            "No system credential store is available on this machine."
        )
    try:
        keyring.set_password(SERVICE, USERNAME, key.strip())
    except KeyringError as exc:
        raise KeyStoreError(f"Could not save to the credential store: {exc}") from exc


def clear_api_key() -> None:
    """Remove the saved key from the keychain (env var, if any, remains)."""
    try:
        keyring.delete_password(SERVICE, USERNAME)
    except KeyringError:
        pass  # not set, or backend unavailable — nothing to remove
