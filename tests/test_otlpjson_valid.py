"""Validate that every emitted line is genuine, schema-valid OTLP/JSON."""

import logging
from typing import Any

import sentry_sdk

from tests.otlp_helpers import parse_log_envelopes, parse_trace_envelopes


def test_full_run_produces_valid_otlp(otlp: Any) -> None:
    _, buffer = otlp
    with sentry_sdk.start_transaction(name="GET /pets/1", op="http.server"):
        with sentry_sdk.start_span(op="db", name="SELECT 1"):
            pass
    sentry_sdk.capture_exception(ValueError("boom"))
    logging.getLogger("petdjango.views").warning("mirrored")
    sentry_sdk.flush(timeout=5)

    traces = parse_trace_envelopes(buffer.getvalue())
    logs = parse_log_envelopes(buffer.getvalue())
    assert len(traces) == 1
    assert len(logs) == 2
