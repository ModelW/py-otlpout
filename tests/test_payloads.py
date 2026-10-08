"""Exact, flat payload tests.

Each test feeds one deterministic input through the conversion and compares the
*entire* output payload to a literal expected payload. The emitted payload is
additionally parsed with the third-party ``opentelemetry-proto`` messages, and a
separate test checks every attribute key against the third-party
``opentelemetry-semantic-conventions`` registry.
"""

import importlib
import logging
import pkgutil
from datetime import UTC, datetime
from typing import Any

from google.protobuf.json_format import ParseDict
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

from otlpout._logs import event_to_otlp, log_record_to_otlp
from otlpout._spans import transaction_to_otlp
from otlpout.integration import OtlpOut

ADAPTER = OtlpOut(
    "test-service",
    service_namespace="tests",
    deployment_environment="test",
    extra_resource_attributes={"component": "unit"},
)

# --------------------------------------------------------------------------- #
# Transaction
# --------------------------------------------------------------------------- #

TRANSACTION_INPUT: dict[str, Any] = {
    "type": "transaction",
    "transaction": "GET /pets/1",
    "start_timestamp": datetime(2024, 1, 1, tzinfo=UTC),
    "timestamp": datetime(2024, 1, 1, 0, 0, 1, tzinfo=UTC),
    "contexts": {
        "trace": {
            "trace_id": "a" * 32,
            "span_id": "b" * 16,
            "parent_span_id": None,
            "op": "http.server",
            "origin": "auto.http.django",
            "status": "ok",
        },
        "response": {
            "status_code": 200,
            "body_size": 42,
            "headers": {"Content-Type": "application/json"},
        },
    },
    "tags": {"http.method": "GET"},
    "request": {
        "url": "http://example.com/pets/1?q=1#frag",
        "method": "GET",
        "env": {"SERVER_PROTOCOL": "HTTP/1.1"},
        "headers": {
            "Referer": "http://ref.example.com/?x=1",
            "User-Agent": "Mozilla/5.0 (compatible; GPTBot/1.2)",
            "X-Forwarded-For": "203.0.113.7, 10.0.0.1",
        },
    },
    "sdk": {"version": "2.71.0"},
    "server_name": "test-host",
    "environment": "production",
}

TRANSACTION_OUTPUT: dict[str, Any] = {
    "resourceSpans": [
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "test-service"}},
                    {"key": "service.namespace", "value": {"stringValue": "tests"}},
                    {
                        "key": "deployment.environment.name",
                        "value": {"stringValue": "test"},
                    },
                    {"key": "telemetry.sdk.name", "value": {"stringValue": "sentry"}},
                    {
                        "key": "telemetry.sdk.language",
                        "value": {"stringValue": "python"},
                    },
                    {
                        "key": "telemetry.sdk.version",
                        "value": {"stringValue": "2.71.0"},
                    },
                    {"key": "host.name", "value": {"stringValue": "test-host"}},
                    {"key": "component", "value": {"stringValue": "unit"}},
                ]
            },
            "scopeSpans": [
                {
                    "scope": {"name": "sentry.transaction"},
                    "spans": [
                        {
                            "traceId": "a" * 32,
                            "spanId": "b" * 16,
                            "name": "GET /pets/1",
                            "kind": 2,
                            "startTimeUnixNano": "1704067200000000000",
                            "endTimeUnixNano": "1704067201000000000",
                            "attributes": [
                                {
                                    "key": "sentry.op",
                                    "value": {"stringValue": "http.server"},
                                },
                                {
                                    "key": "sentry.origin",
                                    "value": {"stringValue": "auto.http.django"},
                                },
                                {
                                    "key": "http.method",
                                    "value": {"stringValue": "GET"},
                                },
                                {
                                    "key": "url.full",
                                    "value": {
                                        "stringValue": "http://example.com/pets/1?q=1#frag"
                                    },
                                },
                                {
                                    "key": "url.path",
                                    "value": {"stringValue": "/pets/1"},
                                },
                                {"key": "url.query", "value": {"stringValue": "q=1"}},
                                {"key": "url.scheme", "value": {"stringValue": "http"}},
                                {
                                    "key": "server.address",
                                    "value": {"stringValue": "example.com"},
                                },
                                {
                                    "key": "http.request.method",
                                    "value": {"stringValue": "GET"},
                                },
                                {
                                    "key": "user_agent.original",
                                    "value": {
                                        "stringValue": "Mozilla/5.0 (compatible; GPTBot/1.2)"
                                    },
                                },
                                {
                                    "key": "http.request.header.referer",
                                    "value": {
                                        "arrayValue": {
                                            "values": [
                                                {
                                                    "stringValue": "http://ref.example.com/?x=1"
                                                }
                                            ]
                                        }
                                    },
                                },
                                {
                                    "key": "http.request.header.x-forwarded-for",
                                    "value": {
                                        "arrayValue": {
                                            "values": [
                                                {"stringValue": "203.0.113.7, 10.0.0.1"}
                                            ]
                                        }
                                    },
                                },
                                {
                                    "key": "network.protocol.version",
                                    "value": {"stringValue": "1.1"},
                                },
                                {
                                    "key": "http.response.status_code",
                                    "value": {"intValue": "200"},
                                },
                                {
                                    "key": "http.response.body.size",
                                    "value": {"intValue": "42"},
                                },
                                {
                                    "key": "http.response.header.content-type",
                                    "value": {
                                        "arrayValue": {
                                            "values": [
                                                {"stringValue": "application/json"}
                                            ]
                                        }
                                    },
                                },
                                {
                                    "key": "client.address",
                                    "value": {"stringValue": "203.0.113.7"},
                                },
                                {
                                    "key": "sentry.transaction",
                                    "value": {"stringValue": "GET /pets/1"},
                                },
                            ],
                            "status": {"code": 1},
                        }
                    ],
                }
            ],
        }
    ]
}

# --------------------------------------------------------------------------- #
# Captured exception
# --------------------------------------------------------------------------- #

EXCEPTION_INPUT: dict[str, Any] = {
    "type": None,
    "level": "error",
    "event_id": "e" * 32,
    "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
    "contexts": {
        "trace": {"trace_id": "a" * 32, "span_id": "b" * 16, "parent_span_id": None}
    },
    "exception": {
        "values": [
            {
                "type": "ValueError",
                "value": "boom",
                "stacktrace": {
                    "frames": [{"filename": "app.py", "lineno": 12, "function": "run"}]
                },
            }
        ]
    },
    "tags": {"environment": "production"},
    "sdk": {"version": "2.71.0"},
}

EXCEPTION_OUTPUT: dict[str, Any] = {
    "resourceLogs": [
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "test-service"}},
                    {"key": "service.namespace", "value": {"stringValue": "tests"}},
                    {
                        "key": "deployment.environment.name",
                        "value": {"stringValue": "test"},
                    },
                    {"key": "telemetry.sdk.name", "value": {"stringValue": "sentry"}},
                    {
                        "key": "telemetry.sdk.language",
                        "value": {"stringValue": "python"},
                    },
                    {
                        "key": "telemetry.sdk.version",
                        "value": {"stringValue": "2.71.0"},
                    },
                    {"key": "component", "value": {"stringValue": "unit"}},
                ]
            },
            "scopeLogs": [
                {
                    "scope": {"name": "sentry.event"},
                    "logRecords": [
                        {
                            "timeUnixNano": "1704067200000000000",
                            "severityNumber": 17,
                            "severityText": "ERROR",
                            "body": {"stringValue": "ValueError: boom"},
                            "attributes": [
                                {
                                    "key": "sentry.event_id",
                                    "value": {"stringValue": "e" * 32},
                                },
                                {
                                    "key": "exception.type",
                                    "value": {"stringValue": "ValueError"},
                                },
                                {
                                    "key": "exception.message",
                                    "value": {"stringValue": "boom"},
                                },
                                {
                                    "key": "exception.stacktrace",
                                    "value": {"stringValue": "app.py:12 in run"},
                                },
                                {
                                    "key": "environment",
                                    "value": {"stringValue": "production"},
                                },
                            ],
                            "traceId": "a" * 32,
                            "spanId": "b" * 16,
                        }
                    ],
                }
            ],
        }
    ]
}

# --------------------------------------------------------------------------- #
# Mirrored stdlib log record
# --------------------------------------------------------------------------- #

LOG_RECORD_INPUT = logging.LogRecord(
    "app.views", logging.WARNING, "app.py", 10, "hi %s", ("bob",), None
)
LOG_RECORD_INPUT.thread = 123
LOG_RECORD_INPUT.process = 456
LOG_RECORD_INPUT.created = 1704067200.0

LOG_OUTPUT: dict[str, Any] = {
    "resourceLogs": [
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "test-service"}},
                    {"key": "service.namespace", "value": {"stringValue": "tests"}},
                    {
                        "key": "deployment.environment.name",
                        "value": {"stringValue": "test"},
                    },
                    {"key": "telemetry.sdk.name", "value": {"stringValue": "sentry"}},
                    {
                        "key": "telemetry.sdk.language",
                        "value": {"stringValue": "python"},
                    },
                    {
                        "key": "telemetry.sdk.version",
                        "value": {"stringValue": "2.71.0"},
                    },
                    {"key": "component", "value": {"stringValue": "unit"}},
                ]
            },
            "scopeLogs": [
                {
                    "scope": {"name": "app.views"},
                    "logRecords": [
                        {
                            "timeUnixNano": "1704067200000000000",
                            "severityNumber": 13,
                            "severityText": "WARN",
                            "body": {"stringValue": "hi bob"},
                            "attributes": [
                                {
                                    "key": "code.file.path",
                                    "value": {"stringValue": "app.py"},
                                },
                                {
                                    "key": "code.line.number",
                                    "value": {"intValue": "10"},
                                },
                                {"key": "thread.id", "value": {"intValue": "123"}},
                                {"key": "process.pid", "value": {"intValue": "456"}},
                            ],
                        }
                    ],
                }
            ],
        }
    ]
}


# --------------------------------------------------------------------------- #
# Third-party validation
# --------------------------------------------------------------------------- #


def _parse_trace(payload: dict[str, Any]) -> ExportTraceServiceRequest:
    """Parse *payload* with the official OTLP trace protobuf message."""
    message = ExportTraceServiceRequest()
    ParseDict(payload, message)
    return message


def _parse_logs(payload: dict[str, Any]) -> ExportLogsServiceRequest:
    """Parse *payload* with the official OTLP logs protobuf message."""
    message = ExportLogsServiceRequest()
    ParseDict(payload, message)
    return message


def _registry() -> tuple[set[str], set[str]]:
    """Registered keys and dynamic template prefixes from the OTel registry."""
    keys: set[str] = set()
    templates: set[str] = set()

    for package_name in (
        "opentelemetry.semconv.attributes",
        "opentelemetry.semconv._incubating.attributes",
    ):
        package = importlib.import_module(package_name)
        for info in pkgutil.iter_modules(package.__path__):
            module = importlib.import_module(f"{package_name}.{info.name}")
            for name in dir(module):
                if not name.isupper():
                    continue
                value = getattr(module, name)
                if not isinstance(value, str):
                    continue
                if name.endswith("_TEMPLATE"):
                    templates.add(value + ".")
                else:
                    keys.add(value)

    return keys, templates


def _attribute_keys(payload: dict[str, Any]) -> list[str]:
    """Every attribute key in an OTLP/JSON envelope."""
    keys: list[str] = []

    def collect(attributes: Any) -> None:
        keys.extend(attribute["key"] for attribute in attributes or [])

    for resource in payload.get("resourceSpans", []):
        collect((resource.get("resource") or {}).get("attributes"))
        for scope in resource.get("scopeSpans", []):
            for span in scope.get("spans", []):
                collect(span.get("attributes"))
    for resource in payload.get("resourceLogs", []):
        collect((resource.get("resource") or {}).get("attributes"))
        for scope in resource.get("scopeLogs", []):
            for record in scope.get("logRecords", []):
                collect(record.get("attributes"))

    return keys


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_transaction_payload_is_exact() -> None:
    output = transaction_to_otlp(TRANSACTION_INPUT, ADAPTER)

    assert output == TRANSACTION_OUTPUT
    assert _parse_trace(output).resource_spans


def test_exception_payload_is_exact() -> None:
    output = event_to_otlp(EXCEPTION_INPUT, ADAPTER)

    assert output == EXCEPTION_OUTPUT
    assert _parse_logs(output).resource_logs


def test_log_payload_is_exact() -> None:
    output = log_record_to_otlp(LOG_RECORD_INPUT, ADAPTER)

    assert output == LOG_OUTPUT
    assert _parse_logs(output).resource_logs


def test_attributes_are_registered_semconv_keys() -> None:
    keys, templates = _registry()
    custom_keys = {"component", "environment"}
    custom_prefixes = ("sentry.",)

    for payload in (TRANSACTION_OUTPUT, EXCEPTION_OUTPUT, LOG_OUTPUT):
        for key in _attribute_keys(payload):
            if key in keys or key in custom_keys or key.startswith(custom_prefixes):
                continue
            assert any(key.startswith(prefix) for prefix in templates), (
                f"{key!r} is not a registered OTel attribute"
            )
