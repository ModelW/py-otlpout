"""Shared helpers to parse and validate OTLP/JSON produced by the integration."""

from __future__ import annotations

import json
from typing import Any

from google.protobuf.json_format import ParseDict
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)


def parse_trace_envelopes(text: str) -> list[Any]:
    """Return every ``resourceSpans`` line in ``text`` parsed as a proto request.

    Parsing via ``opentelemetry-proto`` proves the line is genuine OTLP/JSON
    rather than merely well-formed JSON.
    """
    return [
        _parse(line, "resourceSpans", ExportTraceServiceRequest)
        for line in _lines(text, "resourceSpans")
    ]


def parse_log_envelopes(text: str) -> list[Any]:
    """Return every ``resourceLogs`` line in ``text`` parsed as a proto request."""
    return [
        _parse(line, "resourceLogs", ExportLogsServiceRequest)
        for line in _lines(text, "resourceLogs")
    ]


def _lines(text: str, key: str) -> list[dict[str, Any]]:
    """Select the raw JSON objects containing ``key`` from ``text``."""
    selected: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        obj = json.loads(line)
        if key in obj:
            selected.append(obj)
    return selected


def _parse(obj: dict[str, Any], key: str, message_type: Any) -> Any:
    """Parse one envelope object into ``message_type`` and assert its shape."""
    message = message_type()
    ParseDict(obj, message)
    if set(obj) != {key}:
        problem = f"expected only {key!r} in envelope, got {sorted(obj)}"
        raise AssertionError(problem)
    return message
