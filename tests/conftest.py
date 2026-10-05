"""Fixtures shared by the otlpout test-suite."""

from __future__ import annotations

import io
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
import sentry_sdk

from otlpout import OtlpOut

MakeAdapter = Callable[..., tuple[OtlpOut, io.StringIO]]


@pytest.fixture
def make_adapter() -> MakeAdapter:
    """Return a factory building an adapter wired to a fresh ``StringIO``."""

    def _make(**kwargs: Any) -> tuple[OtlpOut, io.StringIO]:
        """Build an adapter wired to a fresh ``StringIO`` buffer."""
        buffer = io.StringIO()
        kwargs.setdefault("service_name", "test-service")
        kwargs.setdefault("stream", buffer)
        return OtlpOut(**kwargs), buffer

    return _make


@pytest.fixture
def otlp(make_adapter: MakeAdapter) -> Iterator[tuple[OtlpOut, io.StringIO]]:
    """Initialise Sentry with a fresh otlpout integration and yield its buffer."""
    adapter, buffer = make_adapter(
        service_namespace="tests",
        deployment_environment="test",
        extra_resource_attributes={"component": "unit"},
    )
    sentry_sdk.init(
        dsn=None,
        integrations=[adapter],
        traces_sample_rate=1.0,
        default_integrations=False,
        auto_session_tracking=False,
        send_client_reports=False,
    )
    yield adapter, buffer
    sentry_sdk.flush(timeout=5)


@pytest.fixture
def transaction_event() -> dict[str, Any]:
    """Return a synthetic transaction event shaped like Sentry's in-memory one."""
    return {
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
                "data": {"url": "http://example.com/pets/1?q=1#frag"},
            }
        },
        "tags": {"http.method": "GET"},
        "request": {
            "url": "http://example.com/pets/1?q=1#frag",
            "method": "GET",
            "headers": {
                "Referer": "http://ref.example.com/?x=1",
                "X-Forwarded-For": "203.0.113.7, 10.0.0.1",
            },
        },
        "spans": [
            {
                "trace_id": "a" * 32,
                "span_id": "c" * 16,
                "parent_span_id": "b" * 16,
                "op": "db",
                "description": "SELECT 1",
                "start_timestamp": datetime(2024, 1, 1, tzinfo=UTC),
                "timestamp": datetime(2024, 1, 1, 0, 0, 1, tzinfo=UTC),
                "status": "ok",
                "data": {"db.system": "postgresql"},
                "tags": {"status": "ok"},
            }
        ],
        "sdk": {"version": "2.71.0"},
        "server_name": "test-host",
        "environment": "production",
    }


@pytest.fixture
def exception_event() -> dict[str, Any]:
    """Return a synthetic captured-exception event."""
    return {
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
                        "frames": [
                            {"filename": "app.py", "lineno": 12, "function": "run"}
                        ]
                    },
                }
            ]
        },
        "tags": {"environment": "production"},
        "sdk": {"version": "2.71.0"},
    }
