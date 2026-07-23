"""Human-readable table output with a JSON mode for scripts."""
from __future__ import annotations

import json
from typing import Any


def _scalar(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (dict, list)):
        return f"[{len(value)} items]" if isinstance(value, list) else "{…}"
    return str(value)


def table(rows: list[dict[str, Any]], columns: list[tuple[str, str]] | None = None) -> str:
    if not rows:
        return "(empty)"
    columns = columns or [(key, key) for key in rows[0]]
    widths = [max(len(label), *[len(_scalar(row.get(key))) for row in rows]) for key, label in columns]
    lines = ["  ".join(label.ljust(width) for (_, label), width in zip(columns, widths)),
             "  ".join("-" * width for width in widths)]
    lines.extend("  ".join(_scalar(row.get(key)).ljust(width) for (key, _), width in zip(columns, widths)) for row in rows)
    return "\n".join(lines)


def render(value: Any, json_mode: bool = False) -> str:
    if json_mode:
        return json.dumps(value, indent=2, default=lambda item: item.to_dict() if hasattr(item, "to_dict") else str(item))
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return table(value)
        return "\n".join(_scalar(item) for item in value) or "(empty)"
    if isinstance(value, dict):
        scalars = {key: item for key, item in value.items() if not isinstance(item, (dict, list))}
        nested = {key: item for key, item in value.items() if isinstance(item, (dict, list))}
        lines = [f"{key}: {_scalar(item)}" for key, item in scalars.items()]
        for key, item in nested.items():
            lines.append(f"{key}: {_scalar(item)}")
        return "\n".join(lines) or "(empty)"
    return _scalar(value)
