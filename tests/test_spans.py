"""Tests for transaction -> resourceSpans conversion and span filtering."""

from typing import Any

from otlpout._spans import keep_http_spans, transaction_to_otlp


def _flat(attributes: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten an OTLP attribute list, unwrapping ``AnyValue``.

    ``arrayValue`` attributes (e.g. HTTP headers) become Python lists of their
    scalar elements; every other value becomes the single unwrapped scalar.
    """

    def unwrap(value: dict[str, Any]) -> Any:
        if "arrayValue" in value:
            return [unwrap(item) for item in value["arrayValue"]["values"]]
        return next(iter(value.values()))

    return {item["key"]: unwrap(item["value"]) for item in attributes}


def _scopes(event: dict[str, Any], adapter: Any) -> list[dict[str, Any]]:
    envelope = transaction_to_otlp(event, adapter)
    assert envelope is not None
    return envelope["resourceSpans"][0]["scopeSpans"]


def test_http_root_is_kept_and_non_http_children_dropped(
    make_adapter: Any, transaction_event: dict[str, Any]
) -> None:
    adapter, _ = make_adapter()
    scopes = _scopes(transaction_event, adapter)
    assert [scope["scope"]["name"] for scope in scopes] == ["sentry.transaction"]

    root = scopes[0]["spans"][0]
    assert root["traceId"] == "a" * 32
    assert root["spanId"] == "b" * 16
    assert "parentSpanId" not in root
    assert root["kind"] == 2  # SERVER
    assert root["name"] == "GET /pets/1"
    assert root["status"] == {"code": 1}
    assert root["startTimeUnixNano"] == "1704067200000000000"
    assert root["endTimeUnixNano"] == "1704067201000000000"

    attrs = _flat(root["attributes"])
    assert attrs["sentry.op"] == "http.server"
    assert attrs["sentry.transaction"] == "GET /pets/1"
    assert attrs["http.request.method"] == "GET"
    assert attrs["url.full"] == "http://example.com/pets/1?q=1#frag"
    assert attrs["url.path"] == "/pets/1"
    assert attrs["url.query"] == "q=1"
    assert attrs["url.scheme"] == "http"
    assert attrs["server.address"] == "example.com"
    assert attrs["user_agent.original"] == "Mozilla/5.0 (compatible; GPTBot/1.2)"
    assert attrs["http.request.header.referer"] == ["http://ref.example.com/?x=1"]
    assert "http.request.header.user-agent" not in attrs
    assert attrs["network.protocol.version"] == "1.1"
    assert attrs["http.response.status_code"] == "200"
    assert attrs["http.response.body.size"] == "42"
    assert attrs["client.address"] == "203.0.113.7"
    # The invented spellings the access-log pipeline never reads are gone.
    assert "http.request.origin" not in attrs
    assert "http.request.referrer" not in attrs
    # A 200 response is not an error.
    assert "error.type" not in attrs


def test_filter_can_keep_every_span(
    make_adapter: Any, transaction_event: dict[str, Any]
) -> None:
    adapter, _ = make_adapter(span_filter=lambda _op: True)
    scopes = _scopes(transaction_event, adapter)
    assert [scope["scope"]["name"] for scope in scopes] == [
        "sentry.transaction",
        "sentry.span",
    ]
    child = scopes[1]["spans"][0]
    assert child["parentSpanId"] == "b" * 16
    assert child["kind"] == 3  # CLIENT
    assert child["name"] == "SELECT 1"
    assert _flat(child["attributes"])["db.system"] == "postgresql"


def test_http_client_children_are_kept(
    make_adapter: Any, transaction_event: dict[str, Any]
) -> None:
    transaction_event["spans"][0]["op"] = "http.client"
    adapter, _ = make_adapter()
    scopes = _scopes(transaction_event, adapter)
    assert [scope["scope"]["name"] for scope in scopes] == [
        "sentry.transaction",
        "sentry.span",
    ]
    assert scopes[1]["spans"][0]["kind"] == 3


def test_non_http_transaction_is_dropped(
    make_adapter: Any, transaction_event: dict[str, Any]
) -> None:
    transaction_event["contexts"]["trace"]["op"] = "queue.task.celery"
    transaction_event["spans"] = []
    adapter, _ = make_adapter()
    assert transaction_to_otlp(transaction_event, adapter) is None


def test_no_children_omits_child_scope(
    make_adapter: Any, transaction_event: dict[str, Any]
) -> None:
    transaction_event["spans"] = []
    adapter, _ = make_adapter()
    assert len(_scopes(transaction_event, adapter)) == 1


def test_error_status_is_mapped(
    make_adapter: Any, transaction_event: dict[str, Any]
) -> None:
    transaction_event["contexts"]["trace"]["status"] = "internal_error"
    adapter, _ = make_adapter()
    root = _scopes(transaction_event, adapter)[0]["spans"][0]
    assert root["status"] == {"code": 2, "message": "internal_error"}


def test_keep_http_spans_predicate() -> None:
    assert keep_http_spans("http.server")
    assert keep_http_spans("http.client")
    assert not keep_http_spans("db")
    assert not keep_http_spans("queue.task.celery")
    assert not keep_http_spans(None)
