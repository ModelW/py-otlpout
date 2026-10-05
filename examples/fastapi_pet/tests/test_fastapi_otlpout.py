"""End-to-end test: a FastAPI request produces OTLP records on stdout."""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
import sentry_sdk
from fastapi.testclient import TestClient
from google.protobuf.json_format import ParseDict
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from petfastapi.app import app
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from otlpout import OtlpOut


@pytest.fixture
def otlp() -> Any:
    buffer = io.StringIO()
    adapter = OtlpOut(
        "pet-fastapi",
        stream=buffer,
        service_namespace="pets",
        deployment_environment="test",
        extra_resource_attributes={"component": "api"},
    )
    sentry_sdk.init(
        dsn=None,
        integrations=[StarletteIntegration(), FastApiIntegration(), adapter],
        traces_sample_rate=1.0,
        default_integrations=False,
        send_default_pii=True,
        auto_session_tracking=False,
        send_client_reports=False,
    )
    yield buffer
    sentry_sdk.flush(timeout=5)


def _envelopes(text: str, key: str, message_type: Any) -> list[Any]:
    """Parse every JSON line containing ``key`` into ``message_type`` protos."""
    parsed: list[Any] = []
    for line in text.splitlines():
        obj = json.loads(line)
        if key not in obj:
            continue
        message = message_type()
        ParseDict(obj, message)  # raises if the line is not valid OTLP/JSON
        parsed.append(message)
    return parsed


def _spans(text: str) -> list[Any]:
    """Return every span across all trace envelopes in ``text``."""
    envelopes = _envelopes(text, "resourceSpans", ExportTraceServiceRequest)
    return [
        span
        for envelope in envelopes
        for scope in envelope.resource_spans
        for span in scope.scope_spans[0].spans
    ]


def _attr(span: Any, key: str) -> str:
    """Return a span's string attribute value, or an empty string."""
    for item in span.attributes:
        if item.key == key:
            return item.value.string_value
    return ""


def test_fastapi_request_emits_span(otlp: Any) -> None:
    response = TestClient(app).get(
        "/pets/1", headers={"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}
    )
    assert response.status_code == 200
    sentry_sdk.flush(timeout=5)

    text = otlp.getvalue()
    spans = _spans(text)
    assert spans, "the request should have produced an OTLP transaction"
    assert any(_attr(span, "client.address") == "203.0.113.7" for span in spans)
    assert any(_attr(span, "http.request.method") == "GET" for span in spans)
    assert any(_attr(span, "url.path") == "/pets/1" for span in spans)

    logs = _envelopes(text, "resourceLogs", ExportLogsServiceRequest)
    assert logs, "the route's warning should have been mirrored as an OTLP log"
