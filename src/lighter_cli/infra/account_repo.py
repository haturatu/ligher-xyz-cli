"""SQLite account repository with encrypted secret fields.

This is deliberately modelled after the ``hl`` account store: account data is
network-scoped, kept in a local SQLite database, and sensitive fields are
encrypted individually before they enter the database.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sqlite3
import stat
from pathlib import Path
from typing import Any

DB_PATH = Path(os.getenv("LIGHTER_CONFIG", Path.home() / ".config/ligher-xyz-cli/accounts.db"))
_PREFIX = "enc_v1:"


def _key() -> bytes:
    # The database path, unlike ``sys.argv[0]``, stays stable whether the CLI
    # is launched as ``lighter``, ``lt``, or ``python -m``.
    material = os.getenv("LIGHTER_CONFIG_KEY") or f"{DB_PATH.resolve()}:{os.getuid() if hasattr(os, 'getuid') else 'user'}"
    return hashlib.sha256(material.encode()).digest()


def _encrypt(value: str) -> str:
    try:
        from Crypto.Cipher import ChaCha20
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("encrypted account storage requires pycryptodome") from exc
    nonce = secrets.token_bytes(12)
    encrypted = ChaCha20.new(key=_key(), nonce=nonce).encrypt(value.encode())
    return f"{_PREFIX}{base64.urlsafe_b64encode(nonce).decode()}:{base64.urlsafe_b64encode(encrypted).decode()}"


def _decrypt(value: str | None) -> str | None:
    if value is None or not value.startswith(_PREFIX):
        return value
    from Crypto.Cipher import ChaCha20
    nonce, encrypted = value[len(_PREFIX):].split(":", 1)
    return ChaCha20.new(key=_key(), nonce=base64.urlsafe_b64decode(nonce)).decrypt(base64.urlsafe_b64decode(encrypted)).decode()


def _connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    DB_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE IF NOT EXISTS accounts (
            network TEXT NOT NULL CHECK(network IN ('mainnet', 'testnet')),
            alias TEXT NOT NULL,
            account_index INTEGER NOT NULL,
            api_key_index INTEGER NOT NULL,
            api_private_key TEXT,
            auth_token TEXT,
            is_default INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (network, alias)
        )"""
    )
    connection.commit()
    return connection


def list_accounts(testnet: bool) -> tuple[dict[str, dict[str, Any]], str | None]:
    network = "testnet" if testnet else "mainnet"
    connection = _connection()
    rows = connection.execute("SELECT * FROM accounts WHERE network = ? ORDER BY is_default DESC, alias", (network,)).fetchall()
    connection.close()
    accounts = {
        row["alias"]: {
            "account_index": row["account_index"],
            "api_key_index": row["api_key_index"],
            **({"api_private_key": _decrypt(row["api_private_key"])} if row["api_private_key"] else {}),
            **({"auth_token": _decrypt(row["auth_token"])} if row["auth_token"] else {}),
        }
        for row in rows
    }
    default = next((row["alias"] for row in rows if row["is_default"]), None)
    return accounts, default


def save_accounts(testnet: bool, accounts: dict[str, dict[str, Any]], default: str | None) -> None:
    network = "testnet" if testnet else "mainnet"
    connection = _connection()
    try:
        connection.execute("BEGIN")
        connection.execute("DELETE FROM accounts WHERE network = ?", (network,))
        for alias, account in accounts.items():
            connection.execute(
                """INSERT INTO accounts
                   (network, alias, account_index, api_key_index, api_private_key, auth_token, is_default)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    network, alias, int(account["account_index"]), int(account["api_key_index"]),
                    _encrypt(str(account["api_private_key"])) if account.get("api_private_key") else None,
                    _encrypt(str(account["auth_token"])) if account.get("auth_token") else None,
                    int(alias == default),
                ),
            )
        connection.commit()
    finally:
        connection.close()
