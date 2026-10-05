"""Derive OTLP HTTP attributes from Sentry's request context."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit


def _headers(request: dict[str, Any]) -> dict[str, Any]:
    """Normalise Sentry request headers to a lower-cased mapping."""
    raw = request.get("headers") or {}
    if isinstance(raw, dict):
        return {str(key).lower(): value for key, value in raw.items()}
    try:
        return {str(key).lower(): value for key, value in raw}
    except (TypeError, ValueError):
        return {}


def http_attributes(event: dict[str, Any]) -> dict[str, Any]:
    """Return the OTLP HTTP semantic-convention attributes for an event.

    Only the subset Sentry reliably exposes is emitted: the (query- and
    fragment-stripped) URL, method, referrer, origin and response status. The
    referrer is kept verbatim, query string included.
    """
    request = event.get("request") or {}
    if not request:
        return {}
    result: dict[str, Any] = {}
    url = request.get("url")
    if url:
        parts = urlsplit(str(url))
        result["url.full"] = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, "", "")
        )
        result["url.path"] = parts.path
        result["http.request.origin"] = f"{parts.scheme}://{parts.netloc}"
    method = request.get("method")
    if method:
        result["http.request.method"] = method
    referrer = _headers(request).get("referer")
    if referrer:
        result["http.request.referrer"] = referrer
    status = _response_status(event)
    if status is not None:
        result["http.response.status_code"] = status
    return result


def _response_status(event: dict[str, Any]) -> int | None:
    contexts = event.get("contexts") or {}
    response = contexts.get("response") or {}
    status = response.get("status_code")
    if status is None:
        status = (event.get("tags") or {}).get("http.status_code")
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None
