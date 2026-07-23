"""Normalize the flexible order syntax shared with the ``hl`` CLI."""
from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable


def limit_shape(args: Namespace, fail: Callable[[str], None]) -> tuple[str, str, str]:
    parts = [part for part in (args.a, args.b, args.c) if part is not None]
    if args.stake is not None:
        if len(parts) == 2:
            return "0", parts[0], parts[1]
        fail("stake syntax: lighter order limit <side> <coin> <price> --stake <usd>")
    if len(parts) != 3:
        fail("syntax: lighter order limit <side> <size> <coin> <price>")
    return parts[0], parts[1], parts[2]


def market_shape(args: Namespace, fail: Callable[[str], None]) -> tuple[str, str]:
    parts = [part for part in (args.a, args.b) if part is not None]
    if args.stake is not None:
        if len(parts) == 1:
            return "0", parts[0]
        fail("stake syntax: lighter order market <side> <coin> --stake <usd>")
    if len(parts) != 2:
        fail("syntax: lighter order market <side> <size> <coin>")
    return parts[0], parts[1]


def twap_minutes(value: str, fail: Callable[[str], None]) -> int:
    try:
        return max(int(part) for part in value.split(","))
    except ValueError:
        fail("interval must be minutes or a comma-separated minute schedule")
        raise AssertionError("fail must not return")
