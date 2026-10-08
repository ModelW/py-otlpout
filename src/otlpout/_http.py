"""Derive OTLP HTTP attributes from Sentry's request and response context.

The names and value types follow the OpenTelemetry HTTP semantic conventions
for a stable HTTP *server* span:

* Required: ``http.request.method``, ``url.path``, ``url.scheme``.
* Conditionally required: ``url.query`` (if one was received),
  ``http.response.status_code`` and ``error.type`` (on a failed request).
* Recommended: ``client.address``, ``network.protocol.version``,
  ``server.address``/``server.port`` and ``user_agent.original``.
* Opt-in: the request and response headers, as
  ``http.request.header.<name>`` / ``http.response.header.<name>`` typed as a
  single-item string array (the registry type is ``string[]``), plus
  ``url.full`` and the request/response body sizes.

Bespoke spellings such as ``http.request.origin`` or ``http.request.referrer``
are deliberately not emitted, and the User-Agent header is not repeated as a
header because the conventions already model it as ``user_agent.original``.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

_HTTP_PREFIX = "HTTP/"

#: Query parameter names whose values the OTel URL conventions require
#: redacted. Matching is case-sensitive, as the spec mandates.
_SENSITIVE_QUERY_PARAMS = frozenset(
    {
        "X-Amz-Signature",
        "X-Amz-Credential",
        "X-Amz-Security-Token",
        "sig",
        "X-Goog-Signature",
    }
)

#: Header already modelled as ``user_agent.original``; not repeated as a header.
_USER_AGENT = "user-agent"


def _as_text(value: Any) -> str | None:
    """Return a header value as text, or ``None`` when it has no wire value.

    Sentry occasionally replaces a sensitive header with an ``AnnotatedValue``
    marker rather than a string; those carry no value to mirror and are skipped.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _normalise_headers(raw: Any) -> dict[str, str]:
    """Normalise a Sentry header mapping to lower-cased ``{name: value}`` pairs."""
    if isinstance(raw, dict):
        items: Any = raw.items()
    elif raw:
        try:
            items = list(raw)
        except TypeError:
            return {}
    else:
        return {}

    result: dict[str, str] = {}
    for item in items:
        try:
            key, value = item
        except (TypeError, ValueError):
            continue
        text = _as_text(value)
        if text is not None:
            result[str(key).lower()] = text
    return result


def _redacted_netloc(parts: SplitResult) -> str:
    """Return *parts*' netloc with any userinfo replaced.

    ``url.full`` MUST NOT contain credentials passed via the URL (RFC 3986
    ``user:password@host``); the OTel URL conventions require them redacted.
    """
    if parts.username is None and parts.password is None:
        return str(parts.netloc)
    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if _port(parts) is not None:
        host = f"{host}:{_port(parts)}"
    return f"REDACTED:REDACTED@{host}"


def _redact_query(query: str) -> str:
    """Redact the values of the OTel-mandated sensitive query parameters."""
    if not query:
        return query
    redacted: list[str] = []
    for pair in query.split("&"):
        key, separator, _ = pair.partition("=")
        if key in _SENSITIVE_QUERY_PARAMS and separator:
            redacted.append(f"{key}=REDACTED")
        else:
            redacted.append(pair)
    return "&".join(redacted)


def _port(parts: SplitResult) -> int | None:
    """Return *parts*' port, or ``None`` when absent or invalid."""
    try:
        return parts.port
    except ValueError:
        return None


def _add_url(result: dict[str, Any], parts: SplitResult) -> None:
    """Add the URL-derived attributes for *parts* to *result*.

    ``url.full`` is the absolute URL (query and fragment included, sensitive
    query parameters and userinfo redacted); the path, query and scheme are
    also stored under their own semantic-convention attributes.
    """
    path = parts.path or "/"
    query = _redact_query(parts.query)
    result["url.full"] = urlunsplit(
        (parts.scheme, _redacted_netloc(parts), path, query, parts.fragment)
    )
    result["url.path"] = path
    if query:
        result["url.query"] = query
    if parts.scheme:
        result["url.scheme"] = parts.scheme


def _forwarded_host(headers: dict[str, str]) -> str | None:
    """Return the ``host`` parameter of a ``Forwarded`` header, if present."""
    forwarded = headers.get("forwarded")
    if not forwarded:
        return None
    for element in forwarded.split(","):
        for pair in element.split(";"):
            key, _, value = pair.partition("=")
            if key.strip().lower() == "host":
                return value.strip().strip('"')
    return None


def _add_server(
    result: dict[str, Any], headers: dict[str, str], parts: SplitResult
) -> None:
    """Add ``server.address``/``server.port``.

    A server span SHOULD report the original host behind any reverse proxy, so
    ``Forwarded#host`` and ``X-Forwarded-Host`` take precedence over the request
    URL (which Sentry usually builds from the ``Host`` header).
    """
    candidate = _forwarded_host(headers) or headers.get("x-forwarded-host")
    source = urlsplit(f"//{candidate}") if candidate else parts
    if source.hostname:
        result["server.address"] = source.hostname
    port = _port(source)
    if port is not None:
        result["server.port"] = port


def _protocol_version(request: dict[str, Any]) -> str | None:
    """Return the HTTP version (``"1.1"``, ``"2"``) from the server environ.

    WSGI integrations keep the raw environ under ``request.env``; ASGI only
    stores ``REMOTE_ADDR`` there, so the attribute is simply left unset when the
    version is unknown (the conventions say it SHOULD NOT be set then).
    """
    env = request.get("env")
    if not isinstance(env, dict):
        return None
    raw = env.get("SERVER_PROTOCOL") or env.get("HTTP_VERSION")
    if not raw:
        return None
    text = str(raw)
    if text.upper().startswith(_HTTP_PREFIX):
        return text[len(_HTTP_PREFIX) :]
    return text


def _body_size(source: dict[str, Any], *keys: str) -> int | None:
    """Return the first integer-valued *keys* of *source*, or ``None``."""
    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


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


def _add_headers(result: dict[str, Any], headers: dict[str, str], prefix: str) -> None:
    """Add *headers* as single-item string-array attributes under *prefix*."""
    for name, value in headers.items():
        result[f"{prefix}.{name}"] = [value]


def _request_attributes(
    result: dict[str, Any],
    request: dict[str, Any],
    headers: dict[str, str],
    parts: SplitResult | None,
) -> None:
    """Add the request-side HTTP attributes."""
    if parts is not None:
        _add_url(result, parts)
        _add_server(result, headers, parts)

    if method := request.get("method"):
        result["http.request.method"] = method

    if user_agent := headers.get(_USER_AGENT):
        result["user_agent.original"] = user_agent
    # The User-Agent is already modelled as `user_agent.original`, so it is not
    # repeated as a header (the conventions say capturing it is not recommended).
    _add_headers(
        result,
        {name: value for name, value in headers.items() if name != _USER_AGENT},
        "http.request.header",
    )

    if protocol := _protocol_version(request):
        result["network.protocol.version"] = protocol
    if (size := _body_size(headers, "content-length")) is not None:
        result["http.request.body.size"] = size


def _response_attributes(result: dict[str, Any], event: dict[str, Any]) -> None:
    """Add the response-side HTTP attributes."""
    response = (event.get("contexts") or {}).get("response") or {}
    response_headers = _normalise_headers(response.get("headers"))

    status = _response_status(event)
    if status is not None:
        result["http.response.status_code"] = status
        if status >= 500:
            # The HTTP conventions set error.type to the status code for a
            # failed request (a server span leaves 4xx statuses unset).
            result["error.type"] = str(status)

    size = _body_size(response, "body_size", "content_length")
    if size is None:
        size = _body_size(response_headers, "content-length")
    if size is not None:
        result["http.response.body.size"] = size

    _add_headers(result, response_headers, "http.response.header")


def http_attributes(event: dict[str, Any]) -> dict[str, Any]:
    """Return the OTLP HTTP semantic-convention attributes for an event."""
    request = event.get("request") or {}
    if not request:
        return {}

    result: dict[str, Any] = {}
    headers = _normalise_headers(request.get("headers"))
    parts = urlsplit(str(request["url"])) if request.get("url") else None
    _request_attributes(result, request, headers, parts)
    _response_attributes(result, event)
    return result
