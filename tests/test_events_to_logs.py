"""Tests for captured errors/messages -> resourceLogs conversion."""

from typing import Any

from otlpout._logs import event_to_otlp


def _flat(attributes: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten an OTLP attribute list to a ``{key: value}`` mapping."""
    return {item["key"]: next(iter(item["value"].values())) for item in attributes}


def test_exception_event(make_adapter: Any, exception_event: dict[str, Any]) -> None:
    adapter, _ = make_adapter()
    scope_logs = event_to_otlp(exception_event, adapter)["resourceLogs"][0][
        "scopeLogs"
    ][0]
    assert scope_logs["scope"]["name"] == "sentry.event"
    record = scope_logs["logRecords"][0]
    assert record["severityNumber"] == 17
    assert record["severityText"] == "ERROR"
    assert record["body"] == {"stringValue": "ValueError: boom"}
    assert record["traceId"] == "a" * 32
    assert record["spanId"] == "b" * 16
    attrs = _flat(record["attributes"])
    assert attrs["exception.type"] == "ValueError"
    assert attrs["exception.message"] == "boom"
    assert attrs["exception.stacktrace"] == "app.py:12 in run"
    assert attrs["sentry.event_id"] == "e" * 32


def test_message_event(make_adapter: Any) -> None:
    adapter, _ = make_adapter()
    event: dict[str, Any] = {
        "type": None,
        "level": "warning",
        "message": "hello",
        "timestamp": "2024-01-01T00:00:00Z",
        "contexts": {"trace": {"trace_id": "a" * 32, "span_id": "b" * 16}},
    }
    record = event_to_otlp(event, adapter)["resourceLogs"][0]["scopeLogs"][0][
        "logRecords"
    ][0]
    assert record["severityNumber"] == 13
    assert record["severityText"] == "WARN"
    assert record["body"] == {"stringValue": "hello"}
    assert record["timeUnixNano"] == "1704067200000000000"
