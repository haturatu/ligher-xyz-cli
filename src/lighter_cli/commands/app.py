"""Lighter CLI: REST/WS convenience commands plus official SDK signing."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import stat
import subprocess
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from lighter_cli.client.http import APIError, request
from lighter_cli.cli.output import render, table
from lighter_cli.commands.account import balance_rows, position_rows, render_accounts, render_balances, render_positions
from lighter_cli.commands.markets import render_overview
from lighter_cli.commands.order import ORDER_TYPES, TIFS
from lighter_cli.i18n import _, install_language, language_from_argv
from lighter_cli.infra import account_repo
from lighter_cli.services.order_inputs import limit_shape, market_shape, twap_minutes
from lighter_cli.lib import formatters

MAINNET = "https://mainnet.zklighter.elliot.ai"
TESTNET = "https://testnet.zklighter.elliot.ai"
CONFIG_PATH = Path(os.getenv("LIGHTER_CONFIG", Path.home() / ".config/lighter-cli/config.json"))
JSON_OUTPUT = False


def die(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def emit(value: Any) -> None:
    print(render(value, JSON_OUTPUT))


def config(testnet: bool = False) -> dict[str, Any]:
    try:
        account_repo.CONFIG_PATH = CONFIG_PATH
        accounts, default = account_repo.list_accounts(testnet)
        return {"accounts": accounts, "default": default}
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        die(f"cannot read {CONFIG_PATH}: {exc}")


def save(value: dict[str, Any], testnet: bool = False) -> None:
    account_repo.CONFIG_PATH = CONFIG_PATH
    account_repo.save_accounts(testnet, value.get("accounts", {}), value.get("default"))


def server_pid_path() -> Path:
    return CONFIG_PATH.with_name("server.pid")


def server_command(args: argparse.Namespace) -> None:
    path = server_pid_path()
    if args.server_action == "status":
        try:
            pid = int(path.read_text())
            os.kill(pid, 0)
            emit({"running": True, "pid": pid})
        except (OSError, ValueError):
            emit({"running": False})
        return
    if args.server_action == "stop":
        try:
            pid = int(path.read_text()); os.kill(pid, signal.SIGTERM); path.unlink(missing_ok=True)
            emit({"stopped": True, "pid": pid})
        except (OSError, ValueError):
            emit({"stopped": False, "message": "server is not running"})
        return
    if path.exists(): die("server PID file exists; run `lighter server status` or `lighter server stop`")
    cmd = [sys.executable, "-m", "lighter_cli.main"]
    if args.testnet: cmd.append("--testnet")
    if args.url: cmd.extend(["--url", args.url])
    if args.account: cmd.extend(["--account", args.account])
    cmd.extend(["watch", "book", args.market_name] if args.market_name else ["watch", "account"])
    CONFIG_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(CONFIG_PATH.with_name("server.log"), "ab") as log:
        process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    path.write_text(str(process.pid)); path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    emit({"started": True, "pid": process.pid, "log": str(CONFIG_PATH.with_name("server.log"))})


def bash_completion() -> str:
    """Completion contract mirrors @hl's public command tree."""
    return """# bash completion for lighter
_lighter_completion() {
  local cur prev words
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]}"
  words="account order asset markets referral completion"
  case "${COMP_WORDS[1]}" in
    account) words="add ls set-default remove positions orders balances portfolio" ;;
    order) words="ls limit market twap tpsl twap-cancel cancel cancel-all set-leverage configure" ;;
    asset) words="price book leverage" ;;
    markets) words="ls search" ;;
    referral) words="set status" ;;
    completion) words="bash" ;;
  esac
  if [[ "$cur" == -* ]]; then
    case "${COMP_WORDS[1]} ${COMP_WORDS[2]}" in
      "account positions"|"account orders"|"account balances"|"account portfolio"|"order ls") words="--user -w --watch" ;;
      "account remove") words="-f --force" ;;
      "order limit") words="--tif --reduce-only --stake --leverage --cross --isolated" ;;
      "order market") words="--reduce-only --slippage --stake --leverage --cross --isolated --ratio" ;;
      "order twap") words="--stake --reduce-only --leverage --cross --isolated" ;;
      "order tpsl") words="--tp --sl --ratio" ;;
      "order cancel-all") words="-y --yes --coin" ;;
      "order set-leverage") words="--cross --isolated" ;;
      "markets ls") words="--spot-only --perp-only --category --sort-by -w --watch" ;;
      "markets search") words="--spot-only --perp-only --category --sort-by" ;;
      *) words="--json --testnet --lang --help" ;;
    esac
    COMPREPLY=( $(compgen -W "$words" -- "$cur") )
  else
    COMPREPLY=( $(compgen -W "$words" -- "$cur") )
  fi
}
complete -F _lighter_completion lighter lt
"""


def endpoint(args: argparse.Namespace) -> str:
    return getattr(args, "url", None) or (TESTNET if args.testnet else MAINNET)


def get_account(args: argparse.Namespace, required: bool = True) -> dict[str, Any] | None:
    value = config(args.testnet)
    name = getattr(args, "account", None) or value.get("default")
    account = value["accounts"].get(name)
    if account is None and required:
        die("no account selected; run `lighter account add` or pass --account")
    return account


def http(args: argparse.Namespace, path: str, params: dict[str, Any] | None = None,
         token: str | None = None, method: str = "GET", data: dict[str, Any] | None = None) -> Any:
    try:
        return request(endpoint(args), path, params, token, method, data)
    except APIError as exc:
        die(str(exc))


def order_book_details(args: argparse.Namespace) -> list[dict[str, Any]]:
    result = http(args, "/api/v1/orderBookDetails", {"filter": "all"})
    return result.get("order_book_details", [])


def account_data(args: argparse.Namespace) -> dict[str, Any]:
    selected = get_account(args, required=getattr(args, "user", None) is None)
    index = getattr(args, "user", None) or selected["account_index"]
    payload = http(args, "/api/v1/account", {"by": "index", "value": index})
    accounts = payload.get("accounts", [])
    if not accounts:
        die(f"account {index} was not found")
    return accounts[0]


def display_account(args: argparse.Namespace, view: str) -> None:
    data = account_data(args)
    if JSON_OUTPUT:
        emit(data)
        return
    if view == "balances":
        render_balances(data, getattr(args, "_start", None) and time.perf_counter() - args._start)
        return
    if view == "positions":
        render_positions(data, getattr(args, "_start", None) and time.perf_counter() - args._start)
        return
    print(f"Account {data.get('account_index')}  Collateral: {data.get('collateral')}  Available: {data.get('available_balance')}")
    positions = data.get("positions", [])
    assets = data.get("assets", [])
    print("\nPositions")
    print(table([{key: item[key] for key in ("market", "size", "PnL")} for item in position_rows(data)]))
    print("\nAssets")
    print(table([{ "asset": item.get("symbol"), "balance": item.get("balance"), "locked": item.get("locked_balance")} for item in assets]))


def market(args: argparse.Namespace, selector: str) -> dict[str, Any]:
    if selector.isdecimal():
        for item in order_book_details(args):
            if int(item["market_id"]) == int(selector):
                return item
        die(f"unknown market id {selector}")
    for item in order_book_details(args):
        if item.get("symbol", "").upper() == selector.upper():
            return item
    die(f"unknown market {selector!r}; use `lighter market list`")


def integer(value: str, decimals: int, label: str) -> int:
    try:
        amount = Decimal(value)
    except InvalidOperation:
        die(f"invalid {label}: {value}")
    scaled = amount * (Decimal(10) ** decimals)
    if amount <= 0 or scaled != scaled.to_integral_value():
        die(f"{label} must be positive with at most {decimals} decimal places")
    return int(scaled)


def resolve_cancel(args: argparse.Namespace) -> tuple[str, int]:
    """Resolve hl-compatible optional cancel arguments against Lighter orders."""
    account = get_account(args)
    token = os.getenv("LIGHTER_AUTH_TOKEN") or account.get("auth_token")
    if not token:
        die("interactive cancel requires LIGHTER_AUTH_TOKEN or a configured auth token")
    orders = http(args, "/api/v1/accountActiveOrders", {"account_index": account["account_index"]}, token).get("orders", [])
    if not orders:
        die("no active orders")
    oid = getattr(args, "twap_id", None) or getattr(args, "oid", None)
    selected = next((order for order in orders if oid is not None and int(order.get("order_index", order.get("order_id", -1))) == int(oid)), None)
    if selected is None:
        if oid is not None:
            die(f"active order {oid} was not found")
        for index, order in enumerate(orders, 1):
            print(f"{index}: {order.get('order_index', order.get('order_id'))} market={order.get('market_index')}")
        try:
            selected = orders[int(input("select order: ")) - 1]
        except (ValueError, IndexError, EOFError):
            die("no order selected")
    market_id = selected.get("market_index")
    item = next((value for value in order_book_details(args) if int(value["market_id"]) == int(market_id)), None)
    if item is None:
        die(f"market {market_id} is unavailable")
    return str(item["symbol"]), int(selected.get("order_index", selected.get("order_id")))


def sdk_client(args: argparse.Namespace):
    account = get_account(args)
    key = os.getenv("LIGHTER_API_PRIVATE_KEY") or account.get("api_private_key")
    if not key:
        die("set LIGHTER_API_PRIVATE_KEY or configure an API private key")
    try:
        import lighter
    except ImportError:
        die("official lighter-sdk is missing; install this project with pip")
    return lighter.SignerClient(url=endpoint(args), account_index=int(account["account_index"]),
                                api_private_keys={int(account["api_key_index"]): key})


async def close_sdk(client: Any) -> None:
    await client.close()


async def signed_order(args: argparse.Namespace) -> dict[str, Any]:
    client = sdk_client(args)
    try:
        book = market(args, args.market_name)
        kind = ORDER_TYPES[args.kind]
        tif = 0 if args.kind in {"market", "stop-loss", "take-profit"} else TIFS[args.tif]
        expiry = 0 if args.kind == "market" else (args.expiry or -1)
        values = (int(book["market_id"]), args.client_order_id or int(time.time_ns() % 9_000_000_000),
                  integer(args.size, int(book["supported_size_decimals"]), "size"),
                  integer(args.price, int(book["supported_price_decimals"]), "price"), args.side == "sell", kind, tif,
                  args.reduce_only, 0 if args.trigger is None else integer(args.trigger, int(book["supported_price_decimals"]), "trigger"), expiry)
        leverage_result = None
        if getattr(args, "leverage", None):
            mode = client.ISOLATED_MARGIN_MODE if getattr(args, "isolated", False) else client.CROSS_MARGIN_MODE
            tx_type, tx_info, tx_hash, error = client.sign_update_leverage(int(book["market_id"]), int(10_000 / args.leverage), mode, nonce=-1)
            if error: die(error)
            leverage_result = {"tx_type": tx_type, "tx_hash": tx_hash, "tx_info": json.loads(tx_info)}
            if getattr(args, "execute", False):
                response = await client.send_tx(tx_type=tx_type, tx_info=tx_info)
                leverage_result["response"] = response.to_dict()
        if getattr(args, "execute", False):
            tx, response, error = await client.create_order(*values)
            if error: die(error)
            return {"transaction": tx.to_dict(), "response": response.to_dict()}
        tx_type, tx_info, tx_hash, error = client.sign_create_order(*values, nonce=args.nonce)
        if error: die(error)
        return {"dry_run": True, "leverage": leverage_result, "tx_type": tx_type, "tx_hash": tx_hash, "tx_info": json.loads(tx_info)}
    finally:
        await close_sdk(client)


async def signed_simple(args: argparse.Namespace, action: str) -> dict[str, Any]:
    client = sdk_client(args)
    try:
        if action == "cancel":
            book = market(args, args.market_name)
            if args.execute:
                tx, response, error = await client.cancel_order(int(book["market_id"]), args.order_id)
                if error: die(error)
                return {"transaction": tx.to_dict(), "response": response.to_dict()}
            result = client.sign_cancel_order(int(book["market_id"]), args.order_id, nonce=args.nonce)
        elif action == "cancel-all":
            market_id = 255 if args.market_name is None else int(market(args, args.market_name)["market_id"])
            result = client.sign_cancel_all_orders(client.CANCEL_ALL_TIF_IMMEDIATE, int(time.time() * 1000), market_id, nonce=args.nonce)
        else:
            book = market(args, args.market_name)
            mode = client.ISOLATED_MARGIN_MODE if args.mode == "isolated" else client.CROSS_MARGIN_MODE
            result = client.sign_update_leverage(int(book["market_id"]), int(10_000 / args.leverage), mode, nonce=args.nonce)
        tx_type, tx_info, tx_hash, error = result
        if error: die(error)
        if args.execute:
            response = await client.send_tx(tx_type=tx_type, tx_info=tx_info)
            return {"tx_hash": tx_hash, "response": response.to_dict()}
        return {"dry_run": True, "tx_type": tx_type, "tx_hash": tx_hash, "tx_info": json.loads(tx_info)}
    finally:
        await close_sdk(client)


async def signed_tpsl(args: argparse.Namespace) -> dict[str, Any]:
    """Sign Lighter-native reduce-only take-profit/stop-loss orders."""
    if args.tp is None and args.sl is None:
        die("provide --tp and/or --sl")
    if not 0 < args.ratio <= 1:
        die("ratio must be greater than 0 and at most 1")
    book = market(args, args.market_name)
    position = next((item for item in account_data(args).get("positions", []) if int(item.get("market_id", -1)) == int(book["market_id"])), None)
    if position is None:
        die(f"no open position for {args.market_name}")
    raw_size = Decimal(str(position.get("position", 0)))
    if not raw_size:
        die(f"no open position for {args.market_name}")
    client = sdk_client(args)
    try:
        size = integer(str(abs(raw_size) * Decimal(str(args.ratio))), int(book["supported_size_decimals"]), "position size")
        ask = raw_size > 0
        result = []
        for name, trigger, kind in (("take-profit", args.tp, client.ORDER_TYPE_TAKE_PROFIT), ("stop-loss", args.sl, client.ORDER_TYPE_STOP_LOSS)):
            if trigger is None:
                continue
            price = integer(str(trigger), int(book["supported_price_decimals"]), name)
            tx_type, tx_info, tx_hash, error = client.sign_create_order(int(book["market_id"]), int(time.time_ns() % 9_000_000_000), size, price, ask, kind, client.ORDER_TIME_IN_FORCE_IMMEDIATE_OR_CANCEL, True, price, -1, nonce=args.nonce)
            if error:
                die(error)
            result.append({"type": name, "tx_type": tx_type, "tx_hash": tx_hash, "tx_info": json.loads(tx_info)})
        return {"dry_run": True, "orders": result}
    finally:
        await close_sdk(client)


async def signed_close(args: argparse.Namespace) -> dict[str, Any]:
    if not 0 < args.ratio <= 1:
        die("ratio must be greater than 0 and at most 1")
    book = market(args, args.market_name)
    position = next((item for item in account_data(args).get("positions", []) if int(item.get("market_id", -1)) == int(book["market_id"])), None)
    if position is None or not Decimal(str(position.get("position", 0))):
        die(f"no open position for {args.market_name}")
    raw_size = Decimal(str(position["position"]))
    size = integer(str(abs(raw_size) * Decimal(str(args.ratio))), int(book["supported_size_decimals"]), "close size")
    is_ask = raw_size > 0
    price = Decimal(str(book.get("mark_price") or book.get("last_trade_price")))
    slippage = Decimal(str(args.slippage)) / 100
    worst_price = price * (1 - slippage if is_ask else 1 + slippage)
    client = sdk_client(args)
    try:
        tx_type, tx_info, tx_hash, error = client.sign_create_order(int(book["market_id"]), int(time.time_ns() % 9_000_000_000), size,
                                                                      integer(str(worst_price), int(book["supported_price_decimals"]), "price"), is_ask,
                                                                      client.ORDER_TYPE_MARKET, client.ORDER_TIME_IN_FORCE_IMMEDIATE_OR_CANCEL, True, 0, 0, nonce=args.nonce)
        if error: die(error)
        if args.execute:
            response = await client.send_tx(tx_type=tx_type, tx_info=tx_info)
            return {"tx_hash": tx_hash, "response": response.to_dict()}
        return {"dry_run": True, "tx_type": tx_type, "tx_hash": tx_hash, "tx_info": json.loads(tx_info)}
    finally:
        await close_sdk(client)


async def auth_token(args: argparse.Namespace) -> dict[str, str]:
    client = sdk_client(args)
    try:
        token, error = client.create_auth_token_with_expiry(args.expiry)
        if error:
            die(error)
        return {"authorization": token}
    finally:
        await close_sdk(client)


def watch(args: argparse.Namespace) -> None:
    try:
        import lighter
    except ImportError:
        die("official lighter-sdk is missing; install this project with pip")
    if args.watch_target == "book":
        id_ = int(market(args, args.market_name)["market_id"])
        client = lighter.WsClient(host=endpoint(args).replace("https://", ""), order_book_ids=[id_],
                                  on_order_book_update=lambda market_id, state: emit({"market_id": market_id, "book": state}))
    else:
        account = get_account(args)
        client = lighter.WsClient(host=endpoint(args).replace("https://", ""), account_ids=[int(account["account_index"])],
                                  on_account_update=lambda account_id, state: emit({"account_index": account_id, "account": state}))
    client.run()


def watch_markets(args: argparse.Namespace) -> None:
    """Refresh the Rich market board; Lighter has no all-markets WS channel."""
    try:
        while True:
            items = order_book_details(args)
            if args.market_filter != "all": items = [item for item in items if item.get("market_type") == args.market_filter]
            if JSON_OUTPUT: emit(items)
            else:
                print("\033[2J\033[H", end="")
                render_overview(items, http(args, "/api/v1/funding-rates").get("funding_rates", []), args.sort_by)
                print("\n更新間隔: 2秒  終了: Ctrl-C")
            time.sleep(2)
    except KeyboardInterrupt:
        return


def command(args: argparse.Namespace) -> None:
    if args.command == "server": server_command(args); return
    if args.command == "completion": print(bash_completion(), end=""); return
    if args.command == "market-list" and getattr(args, "watch", False): watch_markets(args); return
    if getattr(args, "watch", False):
        args.watch_target = "book" if getattr(args, "market_name", None) else "account"
        watch(args)
        return
    if args.command == "account-add":
        if args.name is None:
            try:
                args.name = input("account name: ").strip()
                args.account_index = int(input("account index: "))
                args.api_key_index = int(input("API key index: "))
            except (ValueError, EOFError):
                die("account add cancelled")
        value = config(args.testnet)
        value["accounts"][args.name] = {"account_index": args.account_index, "api_key_index": args.api_key_index}
        if args.api_private_key: value["accounts"][args.name]["api_private_key"] = args.api_private_key
        if args.auth_token: value["accounts"][args.name]["auth_token"] = args.auth_token
        if not value.get("default"): value["default"] = args.name
        save(value, args.testnet); emit({"added": args.name}); return
    if args.command == "account-list":
        value = config(args.testnet)
        if JSON_OUTPUT: emit(value)
        else: render_accounts(value["accounts"], value.get("default"), time.perf_counter() - args._start)
        return
    if args.command == "account-use":
        value = config(args.testnet)
        if args.name not in value["accounts"]: die(f"unknown account {args.name!r}")
        value["default"] = args.name; save(value, args.testnet); emit({"default": args.name}); return
    if args.command == "account-remove":
        value = config(args.testnet); value["accounts"].pop(args.name, None)
        if value.get("default") == args.name: value["default"] = next(iter(value["accounts"]), None)
        save(value, args.testnet); emit({"removed": args.name}); return
    if args.command == "account-show": display_account(args, "portfolio"); return
    if args.command == "account-snapshot":
        display_account(args, args.snapshot); return
    if args.command == "account-orders":
        account = get_account(args, required=getattr(args, "user", None) is None) or {}
        account_index = getattr(args, "user", None) or account.get("account_index")
        token = getattr(args, "token", None) or os.getenv("LIGHTER_AUTH_TOKEN") or account.get("auth_token")
        if not token: die("orders requires --token, LIGHTER_AUTH_TOKEN, or configured auth token")
        payload = http(args, "/api/v1/accountActiveOrders", {"account_index": account_index}, token)
        if JSON_OUTPUT: emit(payload)
        else:
            orders = payload.get("orders", [])
            emit([{ "id": item.get("order_index", item.get("order_id")), "market": item.get("market_index"),
                    "side": "sell" if item.get("is_ask") else "buy", "size": item.get("remaining_base_amount"),
                    "price": item.get("price"), "type": item.get("type"), "status": item.get("status")} for item in orders])
        return
    if args.command == "order-configure":
        value = config(args.testnet); order_config = value.setdefault("order", {"slippage": 1.0})
        if args.slippage is not None:
            if args.slippage < 0: die("slippage must not be negative")
            order_config["slippage"] = args.slippage; save(value, args.testnet)
            emit({"slippage": args.slippage, "updated": True})
        else: emit(order_config)
        return
    if args.command == "referral-status":
        account = get_account(args)
        token = getattr(args, "token", None) or os.getenv("LIGHTER_AUTH_TOKEN") or account.get("auth_token")
        emit(http(args, "/api/v1/referral/get", {"account_index": account["account_index"]}, token)); return
    if args.command == "referral-set":
        account = get_account(args)
        token = getattr(args, "token", None) or os.getenv("LIGHTER_AUTH_TOKEN") or account.get("auth_token")
        if not token: die("referral set requires an authorization token")
        emit(http(args, "/api/v1/referral/use", token=token, method="POST", data={"referral_code": args.code, "l1_address": args.l1_address or ""})); return
    if args.command == "market-list":
        items = order_book_details(args)
        if args.market_filter != "all": items = [item for item in items if item.get("market_type") == args.market_filter]
        if args.category and args.category != "*":
            items = [item for item in items if str(item.get("category", "")).lower() == args.category.lower()]
        if JSON_OUTPUT:
            emit(items)
        else:
            rates = http(args, "/api/v1/funding-rates").get("funding_rates", [])
            render_overview(items, rates, args.sort_by)
        return
    if args.command == "market-search":
        items = order_book_details(args)
        if args.market_filter != "all": items = [item for item in items if item.get("market_type") == args.market_filter]
        if args.category and args.category != "*":
            items = [item for item in items if str(item.get("category", "")).lower() == args.category.lower()]
        items = [item for item in items if args.query.lower() in str(item.get("symbol", "")).lower()]
        if JSON_OUTPUT: emit(items)
        else: render_overview(items, http(args, "/api/v1/funding-rates").get("funding_rates", []), args.sort_by)
        return
    if args.command == "market-book":
        payload = http(args, "/api/v1/orderBookOrders", {"market_id": market(args, args.market_name)["market_id"], "limit": args.limit})
        emit(payload if JSON_OUTPUT else formatters.book(payload)); return
    if args.command == "market-candles": emit(http(args, "/api/v1/candles", {"market_id": market(args, args.market_name)["market_id"], "resolution": args.resolution, "start_timestamp": args.start, "end_timestamp": args.end})); return
    if args.command == "asset-price":
        item = market(args, args.market_name)
        emit(item if JSON_OUTPUT else {"market": item.get("symbol"), "id": item.get("market_id"), "mark": item.get("mark_price"), "index": item.get("index_price"), "last": item.get("last_trade_price"), "24h change": item.get("daily_price_change")}); return
    if args.command == "asset-leverage":
        data = account_data(args); wanted = market(args, args.market_name)["market_id"]
        rows = [row for row in position_rows(data) if str(row.get("market")) == str(wanted) or str(row.get("market")).upper() == args.market_name.upper()]
        emit(rows if not JSON_OUTPUT else {"account": data, "market_id": wanted}); return
    if args.command == "api-get": emit(http(args, args.path, dict(part.split("=", 1) for part in args.param))); return
    if args.command == "watch": watch(args); return
    if args.command == "auth-token":
        emit(asyncio.run(auth_token(args)))
        return
    if args.command == "key-generate":
        import lighter; private_key, public_key, error = lighter.create_api_key()
        if error: die(error)
        emit({"private_key": private_key, "public_key": public_key}); return
    if args.command == "order-set-leverage":
        args.market_name, args.mode, args.nonce, args.execute = args.coin, ("isolated" if args.isolated else "cross"), -1, args.execute
        emit(asyncio.run(signed_simple(args, "leverage"))); return
    if args.command == "order-tpsl":
        args.market_name = args.coin
        emit(asyncio.run(signed_tpsl(args))); return
    if args.command == "order-market-close": emit(asyncio.run(signed_close(args))); return
    if args.command == "order-twap":
        book = market(args, args.coin)
        args.kind, args.market_name, args.tif, args.trigger, args.client_order_id = "twap", args.coin, "gtc", None, None
        args.side = "buy" if args.side == "long" else "sell"
        args.price = str(book.get("mark_price") or book.get("last_trade_price"))
        try:
            minutes = twap_minutes(str(args.interval), die)
        except ValueError:
            die("interval must be minutes or a comma-separated minute schedule")
        args.expiry = int(time.time() * 1000) + minutes * 60_000
        args.nonce = -1
        emit(asyncio.run(signed_order(args))); return
    if args.command in {"order-create", "order-limit", "order-market"}:
        if args.command == "order-limit":
            args.size, args.coin, args.price = limit_shape(args, die)
            args.kind, args.market_name, args.tif, args.trigger, args.expiry, args.client_order_id = "limit", args.coin, args.tif.lower(), None, None, None
            args.side = "buy" if args.side in {"buy", "long"} else "sell"
            if args.stake is not None:
                price = Decimal(args.price)
                multiplier = Decimal(args.leverage or 1) if args.side in {"buy", "sell"} else Decimal(args.leverage or 1)
                args.size = str(Decimal(str(args.stake)) * multiplier / price)
        if args.command == "order-market":
            if args.side == "close":
                if args.b is not None: die("close syntax: lighter order market close <coin>")
                args.market_name = args.a
                args.command = "order-market-close"
                emit(asyncio.run(signed_close(args))); return
            args.size, args.coin = market_shape(args, die)
            book = market(args, args.coin)
            mark = Decimal(str(book.get("mark_price") or book.get("last_trade_price")))
            slippage = Decimal(str(args.slippage)) / 100
            args.kind, args.market_name, args.tif, args.trigger, args.expiry, args.client_order_id = "market", args.coin, "ioc", None, None, None
            args.side = "buy" if args.side in {"buy", "long"} else "sell"
            args.price = str(mark * (1 + slippage if args.side == "buy" else 1 - slippage))
            if args.stake is not None:
                args.size = str(Decimal(str(args.stake)) * Decimal(args.leverage or 1) / mark)
        emit(asyncio.run(signed_order(args))); return
    if args.command == "order-cancel":
        args.market_name, args.order_id = resolve_cancel(args)
        emit(asyncio.run(signed_simple(args, "cancel"))); return
    if args.command == "order-cancel-all":
        args.market_name = args.coin
        emit(asyncio.run(signed_simple(args, "cancel-all"))); return
    if args.command == "trade-leverage": emit(asyncio.run(signed_simple(args, "leverage"))); return
    die("unsupported command")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lighter", formatter_class=argparse.RawTextHelpFormatter,
        description=_("Lighter DEX CLI"),
        epilog=f"""{_("Command tree:")}
  account add|ls|set-default|remove|positions|orders|balances|portfolio
  order ls|limit|market|tpsl|twap|twap-cancel|cancel|cancel-all|set-leverage|configure
  asset price|book|leverage
  markets ls|search
  referral set|status
  completion {_("Print shell completion script")}
{_("Examples:")}
  lighter account add <name> <account-index> <api-key-index>
  lighter order twap buy 1 BTC 30 --randomize
  lighter order twap-cancel BTC 12345
  lighter account positions --watch""",
    )
    p.add_argument("--json", action="store_true", help=_("Output in JSON format"))
    p.add_argument("--testnet", action="store_true", help=_("Use testnet"))
    p.add_argument("--lang", default=language_from_argv(), metavar="LANG", help=_("Display language (e.g. en, ja, zh, ko)"))
    sub = p.add_subparsers(dest="group", required=True)

    account = sub.add_parser("account", help=_("Account management and information"), formatter_class=argparse.RawTextHelpFormatter, epilog="Examples:\n  lighter account add\n  lighter account ls\n  lighter account positions --watch"); ac = account.add_subparsers(dest="command", required=True)
    x = ac.add_parser("add", help="アカウントを追加"); x.add_argument("name", nargs="?"); x.add_argument("account_index", type=int, nargs="?"); x.add_argument("api_key_index", type=int, nargs="?"); x.add_argument("--api-private-key"); x.add_argument("--auth-token"); x.set_defaults(command="account-add")
    ac.add_parser("ls", help="アカウント一覧").set_defaults(command="account-list")
    x = ac.add_parser("set-default", help="デフォルトアカウントを設定"); x.add_argument("name"); x.set_defaults(command="account-use")
    x = ac.add_parser("remove", help="アカウントを削除"); x.add_argument("name"); x.add_argument("-f", "--force", action="store_true"); x.set_defaults(command="account-remove")
    x = ac.add_parser("positions", help="ポジションを取得"); x.add_argument("--user", type=int, help="アカウントインデックス"); x.add_argument("-w", "--watch", action="store_true"); x.set_defaults(command="account-snapshot", snapshot="positions")
    x = ac.add_parser("orders", help="注文を取得"); x.add_argument("--user", type=int, help="アカウントインデックス"); x.add_argument("-w", "--watch", action="store_true"); x.set_defaults(command="account-orders")
    for name, help_text in (("balances", "残高を取得"), ("portfolio", "ポートフォリオを取得")):
        x = ac.add_parser(name, help=help_text); x.add_argument("--user", type=int, help="アカウントインデックス"); x.add_argument("-w", "--watch", action="store_true"); x.set_defaults(command="account-snapshot", snapshot=name)

    order = sub.add_parser("order", help=_("Order management and trading"), formatter_class=argparse.RawTextHelpFormatter, epilog="Examples:\n  lighter order ls\n  lighter order limit long 0.001 BTC 60000\n  lighter order twap short 1 BTC 30"); oc = order.add_subparsers(dest="command", required=True)
    x = oc.add_parser("ls", help="未約定注文一覧"); x.add_argument("--user", type=int); x.add_argument("-w", "--watch", action="store_true"); x.set_defaults(command="account-orders")
    x = oc.add_parser("limit", help="指値注文を出す (buy/sell = 現物, long/short = 先物)"); x.add_argument("side"); x.add_argument("a", nargs="?"); x.add_argument("b", nargs="?"); x.add_argument("c", nargs="?"); x.add_argument("--tif", default="gtc"); x.add_argument("--reduce-only", action="store_true"); x.add_argument("--stake", type=float); x.add_argument("--leverage", type=int); x.add_argument("--cross", action="store_true"); x.add_argument("--isolated", action="store_true"); x.set_defaults(command="order-limit", nonce=-1, execute=False)
    x = oc.add_parser("market", help="成行注文を出す (buy/sell = 現物, long/short/close = 先物)"); x.add_argument("side"); x.add_argument("a", nargs="?"); x.add_argument("b", nargs="?"); x.add_argument("--slippage", type=float, default=1.0); x.add_argument("--ratio", type=float, default=1.0); x.add_argument("--reduce-only", action="store_true"); x.add_argument("--stake", type=float); x.add_argument("--leverage", type=int); x.add_argument("--cross", action="store_true"); x.add_argument("--isolated", action="store_true"); x.set_defaults(command="order-market", nonce=-1, execute=False)
    x = oc.add_parser("twap", help="TWAP注文を出す (先物のみ: long/short を使用)"); x.add_argument("side"); x.add_argument("size"); x.add_argument("coin"); x.add_argument("interval"); x.add_argument("--reduce-only", action="store_true"); x.add_argument("--stake", type=float); x.add_argument("--leverage", type=int); x.add_argument("--cross", action="store_true"); x.add_argument("--isolated", action="store_true"); x.set_defaults(command="order-twap", nonce=-1, execute=False)
    x = oc.add_parser("tpsl", help="建玉のTP/SLトリガー注文を設定"); x.add_argument("coin"); x.add_argument("--tp", type=float); x.add_argument("--sl", type=float); x.add_argument("--ratio", type=float, default=1.0); x.add_argument("--nonce", type=int, default=-1); x.set_defaults(command="order-tpsl", market_name=None)
    x = oc.add_parser("twap-cancel", help="ネイティブTWAP注文をキャンセル"); x.add_argument("coin", nargs="?"); x.add_argument("twap_id", nargs="?", type=int); x.set_defaults(command="order-cancel", market_name=None, order_id=None, nonce=-1, execute=False)
    x = oc.add_parser("cancel", help="注文をキャンセル"); x.add_argument("oid", nargs="?", type=int); x.set_defaults(command="order-cancel", market_name=None, order_id=None, nonce=-1, execute=False)
    x = oc.add_parser("cancel-all", help="すべての注文をキャンセル"); x.add_argument("--coin"); x.add_argument("-y", "--yes", action="store_true"); x.set_defaults(command="order-cancel-all", market_name=None, nonce=-1, execute=False)
    x = oc.add_parser("set-leverage", help="レバレッジを設定"); x.add_argument("coin"); x.add_argument("leverage", type=int); x.add_argument("--cross", action="store_true"); x.add_argument("--isolated", action="store_true"); x.set_defaults(command="order-set-leverage", execute=False)
    x = oc.add_parser("configure", help="注文のデフォルトを設定"); x.add_argument("--slippage", type=float); x.set_defaults(command="order-configure")

    asset = sub.add_parser("asset", help=_("Asset-specific information"), formatter_class=argparse.RawTextHelpFormatter, epilog="Examples:\n  lighter asset price BTC\n  lighter asset book ETH --watch\n  lighter asset leverage BTC"); asc = asset.add_subparsers(dest="command", required=True)
    x = asc.add_parser("price", help="価格を取得"); x.add_argument("market_name"); x.add_argument("-w", "--watch", action="store_true"); x.set_defaults(command="asset-price")
    x = asc.add_parser("book", help="オーダーブックを取得"); x.add_argument("market_name"); x.add_argument("-w", "--watch", action="store_true"); x.set_defaults(command="market-book", limit=50)
    x = asc.add_parser("leverage", help="レバレッジ情報を取得"); x.add_argument("market_name"); x.add_argument("--user", type=int); x.add_argument("-w", "--watch", action="store_true"); x.set_defaults(command="asset-leverage")

    markets = sub.add_parser("markets", help=_("Market information"), formatter_class=argparse.RawTextHelpFormatter, epilog="Examples:\n  lighter markets ls\n  lighter markets search BTC"); mcs = markets.add_subparsers(dest="command", required=True)
    for name in ("ls",):
        x = mcs.add_parser(name, help="マーケット一覧"); x.add_argument("--spot-only", action="store_const", const="spot", dest="market_filter"); x.add_argument("--perp-only", action="store_const", const="perp", dest="market_filter"); x.add_argument("--category", nargs="?", const="*"); x.add_argument("--sort-by", default="volume"); x.add_argument("-w", "--watch", action="store_true"); x.set_defaults(command="market-list", market_filter="all")
    x = mcs.add_parser("search", help="部分一致でマーケットを検索"); x.add_argument("query"); x.add_argument("--spot-only", action="store_const", const="spot", dest="market_filter"); x.add_argument("--perp-only", action="store_const", const="perp", dest="market_filter"); x.add_argument("--category", nargs="?", const="*"); x.add_argument("--sort-by", default="volume"); x.set_defaults(command="market-search", market_filter="all")

    referral = sub.add_parser("referral", help=_("Referral management"), formatter_class=argparse.RawTextHelpFormatter, epilog="Examples:\n  lighter referral set MYCODE\n  lighter referral status"); rc = referral.add_subparsers(dest="command", required=True); rc.add_parser("set", help=_("Set referral code")).add_argument("code"); rc.choices["set"].add_argument("--l1-address"); rc.choices["set"].set_defaults(command="referral-set"); rc.add_parser("status", help=_("Get referral status")).set_defaults(command="referral-status")
    completion = sub.add_parser("completion", help=_("Print shell completion script"), formatter_class=argparse.RawTextHelpFormatter, epilog='Examples:\n  eval "$(lighter completion bash)"'); csc = completion.add_subparsers(dest="completion_shell", required=True); csc.add_parser("bash", help=_("Print bash completion script")).set_defaults(command="completion")
    return p


def main(argv: list[str] | None = None) -> None:
    global JSON_OUTPUT
    install_language(language_from_argv(sys.argv[1:] if argv is None else argv))
    args = parser().parse_args(argv)
    args._start = time.perf_counter()
    JSON_OUTPUT = args.json
    command(args)


if __name__ == "__main__":
    main()
