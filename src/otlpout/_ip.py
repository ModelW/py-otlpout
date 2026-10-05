"""Resolve the real client address from Sentry's request context via ipware."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from python_ipware import ModernIpWare

if TYPE_CHECKING:
    from collections.abc import Iterable


def _normalise_headers(headers: Any) -> dict[str, Any]:
    """Expand Sentry headers into the ``HTTP_*``/underscored keys ipware expects.

    Sentry stores request headers with their original capitalisation (e.g.
    ``X-Forwarded-For``); ipware's precedence list matches on ``HTTP_X_...``
    and ``X_...`` spellings, so each header is published under both.
    """
    meta: dict[str, Any] = {}
    if isinstance(headers, dict):
        items: Iterable[Any] = headers.items()
    elif headers:
        items = headers
    else:
        return meta
    for item in items:
        try:
            key, value = item
        except (TypeError, ValueError):
            continue
        underscored = str(key).upper().replace("-", "_")
        meta[underscored] = value
        meta[f"HTTP_{underscored}"] = value
    return meta


def client_address(
    event: dict[str, Any], precedence: tuple[str, ...] | None = None
) -> str | None:
    """Return the originating client IP, or ``None`` when it cannot be found.

    Sentry's own extraction ignores provider-specific headers such as
    ``DO-Connecting-IP``; delegating to ipware (whose default precedence list
    contains them, along with ``cf-connecting-ip`` and friends) resolves the
    real client instead of an ingress address. When Sentry already computed
    ``user.ip_address``, that value is preferred.
    """
    user = event.get("user") or {}
    known = user.get("ip_address")
    if known:
        return str(known)

    request = event.get("request") or {}
    meta = _normalise_headers(request.get("headers"))
    env = request.get("env") or {}
    if isinstance(env, dict) and env.get("REMOTE_ADDR"):
        meta["REMOTE_ADDR"] = env["REMOTE_ADDR"]
    if not meta:
        return None
    result, _ = ModernIpWare(precedence=precedence).get_client_ip(meta)
    return str(result) if result is not None else None
