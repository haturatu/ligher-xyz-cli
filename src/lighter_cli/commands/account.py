"""Account payload presentation shared by account commands and watch mode."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from typing import Any
from rich.console import Console
from rich.table import Table
from lighter_cli.i18n import _


def balance_rows(account: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"asset": asset.get("symbol"), "balance": asset.get("balance"), "locked": asset.get("locked_balance"),
             "margin": asset.get("margin_balance"), "mode": asset.get("margin_mode")} for asset in account.get("assets", [])]


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except InvalidOperation:
        return Decimal(0)


def _amount(value: Any) -> str:
    amount = _decimal(value)
    text = f"{amount:f}".rstrip("0").rstrip(".")
    return text or "0"


def render_balances(account: dict[str, Any], elapsed: float | None = None) -> None:
    """Render the compact balance view used by ``hl account balances``."""
    console = Console()
    collateral = _decimal(account.get("collateral"))
    console.print(_("Balances"))
    console.print(_("- Perpetual balance: ${balance:,.2f}").format(balance=collateral))
    table = Table(title=_("Spot balances"), header_style="bold cyan", show_lines=False)
    table.add_column(_("token"))
    table.add_column(_("total"), justify="right")
    table.add_column(_("hold"), justify="right")
    table.add_column(_("available"), justify="right")
    for asset in account.get("assets", []):
        total = _decimal(asset.get("balance"))
        hold = _decimal(asset.get("locked_balance"))
        table.add_row(str(asset.get("symbol", "-")), _amount(total), _amount(hold), _amount(total - hold))
    console.print(table)
    if elapsed is not None:
        console.print("\n" + _("Execution time: {seconds:.2f}s").format(seconds=elapsed))


def render_accounts(accounts: dict[str, dict[str, Any]], default: str | None, elapsed: float | None = None) -> None:
    console = Console()
    if not accounts:
        console.print(_("No accounts found. Run 'lighter account add'."))
        return
    table = Table(title=_("Accounts"), header_style="bold cyan")
    for title in (_("*"), _("Alias"), _("Account index"), _("API key index"), _("Type")):
        table.add_column(title)
    for name, account in accounts.items():
        table.add_row("*" if name == default else "", name, str(account.get("account_index", "-")), str(account.get("api_key_index", "-")), "trading" if account.get("api_private_key") else "read-only")
    console.print(table)
    if elapsed is not None:
        console.print("\n" + _("Execution time: {seconds:.2f}s").format(seconds=elapsed))


def render_positions(account: dict[str, Any], elapsed: float | None = None) -> None:
    console = Console()
    positions = [position for position in account.get("positions", []) if _decimal(position.get("position")) != 0]
    table = Table(title=_("Positions"), header_style="bold cyan")
    for title in (_("Coin"), _("Size"), _("Entry"), _("Value"), _("PnL"), _("Leverage"), _("Liq")):
        table.add_column(title, justify="right" if title != _("Coin") else "left")
    for item in positions:
        table.add_row(str(item.get("symbol", item.get("market_id", "-"))), _amount(item.get("position")), _amount(item.get("avg_entry_price")), _amount(item.get("position_value")), _amount(item.get("unrealized_pnl")), str(item.get("leverage") or "-"), _amount(item.get("liquidation_price")))
    console.print(table)
    if elapsed is not None:
        console.print("\n" + _("Execution time: {seconds:.2f}s").format(seconds=elapsed))


def position_rows(account: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"market": item.get("symbol", item.get("market_id")), "side": item.get("sign"), "size": item.get("position"),
             "entry": item.get("avg_entry_price"), "value": item.get("position_value"), "PnL": item.get("unrealized_pnl"),
             "leverage": item.get("leverage"), "liquidation": item.get("liquidation_price")} for item in account.get("positions", [])]
