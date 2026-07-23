"""Market table mappers and the rich market overview."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from rich.console import Console
from rich.table import Table

from lighter_cli.lib.formatters import book, markets
from lighter_cli.i18n import _


def _number(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except InvalidOperation:
        return Decimal(0)


def _usd(value: Any) -> str:
    number = _number(value)
    if number >= 1_000_000_000:
        return f"${number / 1_000_000_000:.2f}B"
    if number >= 1_000_000:
        return f"${number / 1_000_000:.2f}M"
    if number >= 1_000:
        return f"${number / 1_000:.2f}K"
    return f"${number:,.2f}"


def _price(value: Any) -> str:
    number = _number(value)
    return f"${number:,.6f}".rstrip("0").rstrip(".")


def _rate(value: Any) -> str:
    number = _number(value) * 100
    return f"{number:+.6f}".rstrip("0").rstrip(".") + "%"


def render_overview(items: list[dict[str, Any]], rates: list[dict[str, Any]], sort_by: str = "volume") -> None:
    """Render a compact Japanese market board similar to `hl markets ls`."""
    perps = [item for item in items if item.get("market_type") == "perp"]
    spots = [item for item in items if item.get("market_type") == "spot"]
    rate_by_market = {int(rate["market_id"]): rate["rate"] for rate in rates if rate.get("exchange") == "lighter"}
    table = Table(title=_("Perpetual markets"), header_style="bold cyan", show_lines=False)
    table.add_column(_("Asset"), style="bold")
    table.add_column(_("Pair"))
    table.add_column(_("Price"), justify="right")
    table.add_column("24h%", justify="right")
    table.add_column(_("Volume"), justify="right")
    table.add_column(_("Funding rate"), justify="right")
    table.add_column(_("Open interest"), justify="right")
    sort_keys = {
        "volume": lambda value: _number(value.get("daily_quote_token_volume")),
        "oi": lambda value: _number(value.get("open_interest")) * _number(value.get("mark_price")),
        "price": lambda value: _number(value.get("mark_price")),
        "change": lambda value: _number(value.get("daily_price_change")),
        "coin": lambda value: str(value.get("symbol", "")).lower(),
        "funding": lambda value: _number(rate_by_market.get(int(value["market_id"]), 0)),
    }
    if sort_by not in sort_keys:
        raise ValueError(_("sort-by must be volume, oi, price, change, funding, or coin"))
    reverse = sort_by != "coin"
    for item in sorted(perps, key=sort_keys[sort_by], reverse=reverse):
        leverage = int(10_000 / int(item.get("min_initial_margin_fraction") or 10_000))
        change = _number(item.get("daily_price_change"))
        change_style = "green" if change >= 0 else "red"
        oi_usd = _number(item.get("open_interest")) * _number(item.get("mark_price"))
        table.add_row(str(item.get("symbol")), f"{item.get('symbol')}/USDC {leverage}x", _price(item.get("mark_price")),
                      f"[{change_style}]{change:+.2f}%[/{change_style}]", _usd(item.get("daily_quote_token_volume")),
                      _rate(rate_by_market.get(int(item["market_id"]), 0)), _usd(oi_usd))
    console = Console()
    console.print(_("Markets: perpetual {perps} / spot {spots}").format(perps=len(perps), spots=len(spots)))
    console.print(table)

__all__ = ["book", "markets", "render_overview"]
