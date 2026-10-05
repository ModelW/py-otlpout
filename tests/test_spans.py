"""Tests for transaction -> resourceSpans conversion."""

from typing import Any

from otlpout._spans import transaction_to_otlp


def _flat(attributes: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten an OTLP attribute list to a ``{key: value}`` mapping."""
    return {item["key"]: next(iter(item["value"].values())) for item in attributes}


def test_root_and_children(
    make_adapter: Any, transaction_event: dict[str, Any]
) -> None:
    adapter, _ = make_adapter()
    scopes = transaction_to_otlp(transaction_event, adapter)["resourceSpans"][0][
        "scopeSpans"
    ]
    assert scopes[0]["scope"]["name"] == "sentry.transaction"
    assert scopes[1]["scope"]["name"] == "sentry.span"

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
    assert attrs["url.full"] == "http://example.com/pets/1"
    assert attrs["url.path"] == "/pets/1"
    assert attrs["http.request.origin"] == "http://example.com"
    assert attrs["http.request.referrer"] == "http://ref.example.com/?x=1"
    assert attrs["client.address"] == "203.0.113.7"

    child = scopes[1]["spans"][0]
    assert child["parentSpanId"] == "b" * 16
    assert child["kind"] == 3  # CLIENT
    assert child["name"] == "SELECT 1"
    assert _flat(child["attributes"])["db.system"] == "postgresql"


def test_no_children_omits_child_scope(
    make_adapter: Any, transaction_event: dict[str, Any]
) -> None:
    transaction_event["spans"] = []
    adapter, _ = make_adapter()
    scopes = transaction_to_otlp(transaction_event, adapter)["resourceSpans"][0][
        "scopeSpans"
    ]
    assert len(scopes) == 1


def test_error_status_is_mapped(
    make_adapter: Any, transaction_event: dict[str, Any]
) -> None:
    transaction_event["contexts"]["trace"]["status"] = "internal_error"
    adapter, _ = make_adapter()
    root = transaction_to_otlp(transaction_event, adapter)["resourceSpans"][0][
        "scopeSpans"
    ][0]["spans"][0]
    assert root["status"] == {"code": 2, "message": "internal_error"}
