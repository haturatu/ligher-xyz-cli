"""Map Lighter API payloads to stable CLI table rows."""
from __future__ import annotations
from typing import Any


def markets(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"market": item.get("symbol"), "id": item.get("market_id"), "type": item.get("market_type"),
             "mark": item.get("mark_price"), "index": item.get("index_price"), "last": item.get("last_trade_price"),
             "24h change": item.get("daily_price_change"), "open interest": item.get("open_interest")} for item in items]


def book(payload: dict[str, Any]) -> list[dict[str, Any]]:
    asks = [{"side": "ask", "price": item.get("price"), "size": item.get("remaining_base_amount", item.get("size"))} for item in payload.get("asks", [])]
    bids = [{"side": "bid", "price": item.get("price"), "size": item.get("remaining_base_amount", item.get("size"))} for item in payload.get("bids", [])]
    return asks + bids
