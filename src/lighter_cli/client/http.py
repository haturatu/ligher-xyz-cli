"""Small synchronous REST adapter used for public Lighter API requests."""
from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class APIError(RuntimeError):
    """An HTTP or transport error returned by Lighter."""


def request(base_url: str, path: str, params: dict[str, Any] | None = None, token: str | None = None,
            method: str = "GET", data: dict[str, Any] | None = None) -> Any:
    query = urlencode({key: value for key, value in (params or {}).items() if value is not None})
    target = f"{base_url.rstrip('/')}/{path.lstrip('/')}" + (f"?{query}" if query else "")
    body = None if data is None else urlencode(data).encode()
    headers = {"Accept": "application/json"}
    if body is not None: headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token: headers["Authorization"] = token
    try:
        with urlopen(Request(target, data=body, headers=headers, method=method), timeout=20) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        raise APIError(f"HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc
    except URLError as exc:
        raise APIError(f"cannot reach {target}: {exc.reason}") from exc
