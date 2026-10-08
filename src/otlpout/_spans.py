"""Convert Sentry transaction events into OTLP ``resourceSpans`` payloads."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from otlpout._attributes import attributes
from otlpout._http import http_attributes
from otlpout._ids import ZERO_TRACE_ID, optional_span_id, span_id, trace_id
from otlpout._ip import client_address
from otlpout._resource import build_resource
from otlpout._status import otlp_status
from otlpout._time import to_unix_nano

if TYPE_CHECKING:
    from otlpout.integration import OtlpOut

ROOT_SCOPE = "sentry.transaction"
CHILD_SCOPE = "sentry.span"

#: Predicate deciding whether a span (by its Sentry operation) is emitted.
SpanFilter = Callable[[str | None], bool]

#: Attributes kept when an oversized record is reduced to fit the line budget.
#: The names mirror what access-log consumers parse (OpenTelemetry HTTP
#: semantic conventions), so a reduced record still renders a Combined Log
#: Format line.
CORE_ATTRIBUTE_KEYS = frozenset(
    {
        "sentry.op",
        "sentry.origin",
        "sentry.transaction",
        "http.request.method",
        "url.path",
        "url.full",
        "url.query",
        "url.scheme",
        "server.address",
        "server.port",
        "network.protocol.version",
        "http.response.status_code",
        "http.response.body.size",
        "error.type",
        "user_agent.original",
        "http.request.header.referer",
        "client.address",
    }
)


def keep_http_spans(op: str | None) -> bool:
    """Default span filter: keep only HTTP spans (``http.server``/``http.client``).

    The whole point of the stdout mirror is to feed an access-log pipeline
    (OnCrawl). Database, cache, template, signal and queue spans are already in
    Sentry in full detail; duplicating them here is what blows past the
    container's 16 KiB log-line limit. Pass ``span_filter=lambda _op: True`` to
    emit every span instead, or a custom predicate to keep something else.
    """
    return str(op or "").lower().startswith("http")


def _span_kind(op: Any) -> int:
    """Map a Sentry span operation to an OTLP ``SpanKind`` enum value."""
    value = str(op or "").lower()
    if value.startswith(("http.server", "server", "asgi", "wsgi")):
        return 2  # SERVER
    if value.startswith(("http.client", "http", "db", "cache", "rpc", "grpc")):
        return 3  # CLIENT
    if value.startswith(("queue", "producer", "publish")):
        return 4  # PRODUCER
    if value.startswith(("consumer", "receive")):
        return 5  # CONSUMER
    return 1  # INTERNAL


def _structural_attributes(source: dict[str, Any]) -> dict[str, Any]:
    """Collect the Sentry-specific operation metadata plus arbitrary span data."""
    result: dict[str, Any] = {}
    if source.get("op"):
        result["sentry.op"] = source["op"]
    if source.get("origin"):
        result["sentry.origin"] = source["origin"]
    for key, value in (source.get("data") or {}).items():
        result[str(key)] = value
    return result


def _build_span(
    *,
    trace: str,
    span: str,
    parent: str | None,
    name: str,
    kind: int,
    start: Any,
    end: Any,
    status: Any,
    attrs: dict[str, Any],
) -> dict[str, Any]:
    """Assemble a single OTLP ``Span``, omitting empty optional fields."""
    result: dict[str, Any] = {
        "traceId": trace,
        "spanId": span,
        "name": name or "span",
        "kind": kind,
        "startTimeUnixNano": to_unix_nano(start),
        "endTimeUnixNano": to_unix_nano(end),
        "attributes": attributes(attrs),
        "status": otlp_status(status),
    }
    if parent:
        result["parentSpanId"] = parent
    return {key: value for key, value in result.items() if value is not None}


def transaction_to_otlp(
    event: dict[str, Any], adapter: OtlpOut
) -> dict[str, Any] | None:
    """Convert a Sentry transaction (root span + children) to ``resourceSpans``.

    The root span lives in the ``sentry.transaction`` scope and each recorded
    child in the ``sentry.span`` scope, mirroring Sentry's own instrumentation
    names. HTTP semantic-convention attributes and the resolved client address
    are attached to the root span, which is the one carrying the request.

    ``adapter.span_filter`` decides which spans survive: by default only HTTP
    spans, which in practice means the ``http.server`` transaction root. Returns
    ``None`` when nothing survives, so no empty envelope is written.
    """
    contexts = event.get("contexts") or {}
    trace_context = contexts.get("trace") or {}
    root_trace = trace_id(trace_context.get("trace_id"))
    root_span = span_id(trace_context.get("span_id"))

    scope_spans: list[dict[str, Any]] = []

    if adapter.span_filter(trace_context.get("op")):
        root_attributes = _structural_attributes(trace_context)
        root_attributes.update(_tags(event.get("tags")))
        root_attributes.update(http_attributes(event))
        address = client_address(event, adapter.ip_precedence)
        if address:
            root_attributes["client.address"] = address
        if event.get("transaction"):
            root_attributes["sentry.transaction"] = event["transaction"]
        root = _build_span(
            trace=root_trace,
            span=root_span,
            parent=optional_span_id(trace_context.get("parent_span_id")),
            name=event.get("transaction")
            or trace_context.get("description")
            or "transaction",
            kind=_span_kind(trace_context.get("op")),
            start=event.get("start_timestamp"),
            end=event.get("timestamp"),
            status=trace_context.get("status"),
            attrs=root_attributes,
        )
        scope_spans.append({"scope": {"name": ROOT_SCOPE}, "spans": [root]})

    children: list[dict[str, Any]] = []
    for child in event.get("spans") or []:
        if not isinstance(child, dict) or not adapter.span_filter(child.get("op")):
            continue
        child_trace = trace_id(child.get("trace_id"))
        if child_trace == ZERO_TRACE_ID:
            child_trace = root_trace
        child_attributes = _structural_attributes(child)
        child_attributes.update(_tags(child.get("tags")))
        children.append(
            _build_span(
                trace=child_trace,
                span=span_id(child.get("span_id")),
                parent=optional_span_id(child.get("parent_span_id")) or root_span,
                name=str(child.get("description") or child.get("op") or "span"),
                kind=_span_kind(child.get("op")),
                start=child.get("start_timestamp"),
                end=child.get("timestamp"),
                status=child.get("status"),
                attrs=child_attributes,
            )
        )
    if children:
        scope_spans.append({"scope": {"name": CHILD_SCOPE}, "spans": children})

    if not scope_spans:
        return None

    return {
        "resourceSpans": [
            {"resource": build_resource(adapter, event), "scopeSpans": scope_spans}
        ]
    }


def reduce_envelope(obj: dict[str, Any]) -> dict[str, Any]:
    """Strip an envelope down so an oversized record can still be emitted.

    Only the attributes an access-log consumer needs are kept, and log bodies
    are cut to a bounded size. The result is still a valid OTLP envelope, unlike
    the mid-object truncation a container runtime would otherwise inflict.
    """
    for resource in obj.get("resourceSpans", []):
        for scope in resource.get("scopeSpans", []):
            for span in scope.get("spans", []):
                span["attributes"] = [
                    item
                    for item in span.get("attributes", [])
                    if item.get("key") in CORE_ATTRIBUTE_KEYS
                ]
    for resource in obj.get("resourceLogs", []):
        for scope in resource.get("scopeLogs", []):
            for record in scope.get("logRecords", []):
                record["attributes"] = [
                    item
                    for item in record.get("attributes", [])
                    if item.get("key") in CORE_ATTRIBUTE_KEYS
                ]
                body = record.get("body")
                if isinstance(body, dict):
                    text = body.get("stringValue")
                    if isinstance(text, str) and len(text) > 4096:
                        body["stringValue"] = text[:4096]
    return obj


def _tags(tags: Any) -> dict[str, Any]:
    """Return Sentry tags as a plain attribute mapping."""
    if not isinstance(tags, dict):
        return {}
    return {str(key): value for key, value in tags.items()}
