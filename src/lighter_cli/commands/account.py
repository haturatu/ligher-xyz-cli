"""Account payload presentation shared by account commands and watch mode."""
from __future__ import annotations
from typing import Any


def balance_rows(account: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"asset": asset.get("symbol"), "balance": asset.get("balance"), "locked": asset.get("locked_balance"),
             "margin": asset.get("margin_balance"), "mode": asset.get("margin_mode")} for asset in account.get("assets", [])]


def position_rows(account: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"market": item.get("symbol", item.get("market_id")), "side": item.get("sign"), "size": item.get("position"),
             "entry": item.get("avg_entry_price"), "value": item.get("position_value"), "PnL": item.get("unrealized_pnl"),
             "leverage": item.get("leverage"), "liquidation": item.get("liquidation_price")} for item in account.get("positions", [])]
