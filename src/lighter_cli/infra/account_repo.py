"""Network-scoped account repository with encrypted-at-rest secrets.

The file is intentionally JSON rather than SQLite so it can migrate the
previous Lighter CLI configuration without a data-loss migration.  Private
values use ChaCha20 when PyCryptodome is available (it is a transitive SDK
dependency); a missing crypto backend is a hard error rather than plaintext
fallback.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import stat
import sys
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(os.getenv("LIGHTER_CONFIG", Path.home() / ".config/lighter-cli/config.json"))
_PREFIX = "enc_v1:"


def _key() -> bytes:
    # Per-user stable material. An explicit secret permits portable encrypted
    # configs without silently weakening local protection.
    material = os.getenv("LIGHTER_CONFIG_KEY") or f"{Path(sys.argv[0]).resolve()}:{os.getuid() if hasattr(os, 'getuid') else 'user'}"
    return hashlib.sha256(material.encode()).digest()


def _encrypt(value: str) -> str:
    try:
        from Crypto.Cipher import ChaCha20
    except ImportError as exc:  # pragma: no cover - packaging/runtime guard
        raise RuntimeError("encrypted account storage requires pycryptodome") from exc
    nonce = secrets.token_bytes(12)
    encrypted = ChaCha20.new(key=_key(), nonce=nonce).encrypt(value.encode())
    return _PREFIX + base64.urlsafe_b64encode(nonce).decode() + ":" + base64.urlsafe_b64encode(encrypted).decode()


def _decrypt(value: str) -> str:
    if not value.startswith(_PREFIX):
        return value
    from Crypto.Cipher import ChaCha20
    nonce, encrypted = value[len(_PREFIX):].split(":", 1)
    return ChaCha20.new(key=_key(), nonce=base64.urlsafe_b64decode(nonce)).decrypt(base64.urlsafe_b64decode(encrypted)).decode()


def _read() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {"version": 2, "networks": {"mainnet": {"accounts": {}, "default": None}, "testnet": {"accounts": {}, "default": None}}}
    payload = json.loads(CONFIG_PATH.read_text())
    # One-time in-memory migration from v1's global accounts object.
    if "networks" not in payload:
        accounts = payload.get("accounts", {})
        payload = {"version": 2, "networks": {"mainnet": {"accounts": accounts, "default": payload.get("default")}, "testnet": {"accounts": {}, "default": None}}}
    for name in ("mainnet", "testnet"):
        payload["networks"].setdefault(name, {"accounts": {}, "default": None})
    return payload


def _write(payload: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    CONFIG_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    CONFIG_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _network(testnet: bool) -> dict[str, Any]:
    return _read()["networks"]["testnet" if testnet else "mainnet"]


def list_accounts(testnet: bool) -> tuple[dict[str, dict[str, Any]], str | None]:
    network = _network(testnet)
    accounts: dict[str, dict[str, Any]] = {}
    for name, value in network["accounts"].items():
        accounts[name] = {key: (_decrypt(item) if key in {"api_private_key", "auth_token"} and isinstance(item, str) else item) for key, item in value.items()}
    return accounts, network.get("default")


def save_accounts(testnet: bool, accounts: dict[str, dict[str, Any]], default: str | None) -> None:
    payload = _read()
    secure: dict[str, dict[str, Any]] = {}
    for name, value in accounts.items():
        secure[name] = {key: (_encrypt(item) if key in {"api_private_key", "auth_token"} and isinstance(item, str) and not item.startswith(_PREFIX) else item) for key, item in value.items()}
    payload["networks"]["testnet" if testnet else "mainnet"] = {"accounts": secure, "default": default}
    _write(payload)
