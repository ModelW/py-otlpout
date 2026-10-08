"""Convert Sentry error events and stdlib log records into OTLP ``resourceLogs``."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import sentry_sdk
from sentry_sdk.utils import logger

from otlpout._attributes import attributes, conform_value
from otlpout._ids import optional_span_id, span_id, trace_id
from otlpout._ip import client_address
from otlpout._resource import build_resource
from otlpout._time import to_unix_nano

if TYPE_CHECKING:
    from otlpout.integration import OtlpOut

EVENT_SCOPE = "sentry.event"

# Sentry level -> (OTLP severity number, severity text). OTLP reserves ranges
# per severity; the first number of each range is the canonical one.
_LEVELS: dict[str, tuple[int, str]] = {
    "debug": (5, "DEBUG"),
    "info": (9, "INFO"),
    "warning": (13, "WARN"),
    "error": (17, "ERROR"),
    "fatal": (21, "FATAL"),
    "critical": (21, "FATAL"),
}


def _severity_from_level(level: Any) -> tuple[int, str]:
    return _LEVELS.get(str(level or "").lower(), (17, "ERROR"))


def _severity_from_levelno(levelno: int) -> tuple[int, str]:
    if levelno >= logging.CRITICAL:
        return 21, "FATAL"
    if levelno >= logging.ERROR:
        return 17, "ERROR"
    if levelno >= logging.WARNING:
        return 13, "WARN"
    if levelno >= logging.INFO:
        return 9, "INFO"
    return 5, "DEBUG"


def _log_record(
    *,
    trace: str | None,
    span: str | None,
    moment: Any,
    severity_number: int,
    severity_text: str,
    body: str,
    attrs: dict[str, Any],
) -> dict[str, Any]:
    """Assemble a single OTLP ``LogRecord``, omitting empty optional fields."""
    record: dict[str, Any] = {
        "timeUnixNano": to_unix_nano(moment),
        "severityNumber": severity_number,
        "severityText": severity_text,
        "body": {"stringValue": body},
        "attributes": attributes(attrs),
    }
    if trace:
        record["traceId"] = trace
    if span:
        record["spanId"] = span
    return {key: value for key, value in record.items() if value is not None}


def _envelope(
    adapter: OtlpOut, event: dict[str, Any] | None, scope: str, record: dict[str, Any]
) -> dict[str, Any]:
    return {
        "resourceLogs": [
            {
                "resource": build_resource(adapter, event),
                "scopeLogs": [{"scope": {"name": scope}, "logRecords": [record]}],
            }
        ]
    }


def _frame_summary(frame: dict[str, Any]) -> str:
    """Render one Sentry stack frame as a short ``file:line in func`` string."""
    return f"{frame.get('filename')}:{frame.get('lineno')} in {frame.get('function')}"


def _event_body(event: dict[str, Any]) -> str:
    message = event.get("message")
    if message:
        return str(message)
    values = (event.get("exception") or {}).get("values") or []
    if values:
        last = values[-1]
        return f"{last.get('type', 'Exception')}: {last.get('value', '')}".strip(": ")
    return str(event.get("transaction") or "event")


def _event_logger(event: dict[str, Any]) -> str:
    """Return the instrumentation scope name for a captured event.

    The OTel Logs API records a logger name as the instrumentation scope's
    name (not as an attribute), so it is preferred over the generic fallback.
    """
    logentry = event.get("logentry") or {}
    return logentry.get("logger") or event.get("logger") or EVENT_SCOPE


def _event_attributes(event: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if event.get("event_id"):
        result["sentry.event_id"] = event["event_id"]
    values = (event.get("exception") or {}).get("values") or []
    if values:
        last = values[-1]
        if last.get("type"):
            result["exception.type"] = last["type"]
        if last.get("value"):
            result["exception.message"] = last["value"]
        frames = (last.get("stacktrace") or {}).get("frames") or []
        if frames:
            result["exception.stacktrace"] = "\n".join(
                _frame_summary(frame) for frame in frames
            )
    for key, value in (event.get("tags") or {}).items():
        name = str(key)
        result.setdefault(name, conform_value(name, value))
    return result


def event_to_otlp(event: dict[str, Any], adapter: OtlpOut) -> dict[str, Any]:
    """Convert a captured Sentry error/message into a single ``resourceLogs`` line."""
    trace_context = (event.get("contexts") or {}).get("trace") or {}
    severity_number, severity_text = _severity_from_level(event.get("level"))
    attrs = _event_attributes(event)
    address = client_address(event, adapter.ip_precedence)
    if address:
        attrs["client.address"] = address
    record = _log_record(
        trace=trace_id(trace_context.get("trace_id")),
        span=optional_span_id(trace_context.get("span_id")),
        moment=event.get("timestamp"),
        severity_number=severity_number,
        severity_text=severity_text,
        body=_event_body(event),
        attrs=attrs,
    )
    return _envelope(adapter, event, _event_logger(event), record)


def log_record_to_otlp(record: logging.LogRecord, adapter: OtlpOut) -> dict[str, Any]:
    """Convert a stdlib ``LogRecord`` into a single ``resourceLogs`` line.

    The record is correlated with whatever Sentry span is active at emit time,
    so mirrored logs join their trace in the collector.
    """
    severity_number, severity_text = _severity_from_levelno(record.levelno)
    attrs: dict[str, Any] = {
        "code.file.path": record.pathname,
        "code.line.number": record.lineno,
        "code.function.name": record.funcName,
        "thread.id": record.thread,
        "process.pid": record.process,
    }
    trace: str | None = None
    span: str | None = None
    try:
        current = sentry_sdk.get_current_span()
        if current is not None:
            trace = trace_id(current.trace_id)
            span = span_id(current.span_id)
    except Exception:  # correlation is best-effort
        logger.debug(
            "otlpout: could not correlate log record with a span",
            exc_info=True,
        )
    log = _log_record(
        trace=trace,
        span=span,
        moment=record.created,
        severity_number=severity_number,
        severity_text=severity_text,
        body=record.getMessage(),
        attrs=attrs,
    )
    return _envelope(adapter, None, record.name, log)
