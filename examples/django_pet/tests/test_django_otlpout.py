"""End-to-end test: a Django request produces OTLP records on stdout.

The plain Django test client bypasses the WSGI middleware in which Sentry
starts transactions, so the test drives ``WSGIHandler`` directly with a
synthetic WSGI environ. That still runs the full Django request/response cycle
(and Sentry's WSGI middleware) without depending on a live server thread.
"""

from __future__ import annotations

import io
import json
from typing import Any
from wsgiref.util import setup_testing_defaults

import pytest
import sentry_sdk
from django.core.handlers.wsgi import WSGIHandler
from google.protobuf.json_format import ParseDict
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from sentry_sdk.integrations.django import DjangoIntegration

from otlpout import OtlpOut


@pytest.fixture
def otlp() -> Any:
    buffer = io.StringIO()
    adapter = OtlpOut(
        "pet-django",
        stream=buffer,
        service_namespace="pets",
        deployment_environment="test",
        extra_resource_attributes={"component": "api"},
    )
    sentry_sdk.init(
        dsn=None,
        integrations=[DjangoIntegration(), adapter],
        traces_sample_rate=1.0,
        default_integrations=False,
        send_default_pii=True,
        auto_session_tracking=False,
        send_client_reports=False,
    )
    yield buffer
    sentry_sdk.flush(timeout=5)


def _wsgi_get(path: str, headers: dict[str, str] | None = None) -> tuple[str, bytes]:
    """Run a GET through Django's real WSGI handler and return (status, body)."""
    environ: dict[str, Any] = {}
    setup_testing_defaults(environ)
    environ["REQUEST_METHOD"] = "GET"
    environ["PATH_INFO"] = path
    environ["SERVER_NAME"] = "testserver"
    environ["SERVER_PORT"] = "80"
    environ["HTTP_HOST"] = "testserver"
    environ["REMOTE_ADDR"] = "10.0.0.1"
    for name, value in (headers or {}).items():
        environ["HTTP_" + name.upper().replace("-", "_")] = value

    captured: dict[str, str] = {}

    def start_response(status: str, response_headers: list[tuple[str, str]]) -> None:
        """Capture the WSGI status line emitted by the handler."""
        captured["status"] = status

    body = b"".join(WSGIHandler()(environ, start_response))
    return captured["status"], body


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


def _resource_attr(envelope: Any, key: str) -> str:
    """Return a resource's string attribute value, or an empty string."""
    for resource_spans in envelope.resource_spans:
        for item in resource_spans.resource.attributes:
            if item.key == key:
                return item.value.string_value
    return ""


def test_django_request_emits_span(otlp: Any) -> None:
    status, body = _wsgi_get("/pets/1/", {"X-Forwarded-For": "203.0.113.7, 10.0.0.1"})
    assert status.startswith("200")
    assert b"Rex" in body
    sentry_sdk.flush(timeout=5)

    text = otlp.getvalue()
    spans = _spans(text)
    assert spans, "the request should have produced an OTLP transaction"
    assert any("/pets/" in span.name for span in spans)
    assert any(_attr(span, "client.address") == "203.0.113.7" for span in spans)

    trace_envelopes = _envelopes(text, "resourceSpans", ExportTraceServiceRequest)
    assert any(
        _resource_attr(envelope, "service.name") == "pet-django"
        for envelope in trace_envelopes
    )

    logs = _envelopes(text, "resourceLogs", ExportLogsServiceRequest)
    assert logs, "the view's warning should have been mirrored as an OTLP log"
