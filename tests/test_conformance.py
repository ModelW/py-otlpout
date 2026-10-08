"""Hard, third-party conformance verification of the emitted OTLP/JSON.

Every emitted line is validated two ways: the official ``opentelemetry-proto``
messages must accept it (wire conformance), and every managed attribute must be
a registered, correctly-typed ``opentelemetry-semantic-conventions`` key
(semantic conformance). See :mod:`tests.conformance`.
"""

import json
import logging
from typing import Any

import sentry_sdk

from tests import conformance
from tests.otlp_helpers import parse_log_envelopes, parse_trace_envelopes


def _check(text: str) -> None:
    """Run the semantic-convention checks over every line of *text*."""
    for line in text.splitlines():
        if not line.strip():
            continue
        envelope = json.loads(line)
        where = line[:48]
        conformance.assert_semconv_conformant(envelope, where)
        conformance.assert_url_full_is_absolute(envelope, where)


def test_transaction_is_wire_and_semconv_conformant(
    make_adapter: Any, transaction_event: dict[str, Any]
) -> None:
    adapter, buffer = make_adapter()
    adapter.process_event(transaction_event)
    text = buffer.getvalue()

    assert parse_trace_envelopes(text), "the line must be valid OTLP"
    _check(text)


def test_event_and_log_are_wire_and_semconv_conformant(
    make_adapter: Any, exception_event: dict[str, Any]
) -> None:
    adapter, buffer = make_adapter()
    adapter.process_event(exception_event)
    adapter.process_log_record(
        logging.LogRecord("app.views", logging.WARNING, "app.py", 10, "hi", None, None)
    )
    text = buffer.getvalue()

    assert parse_log_envelopes(text), "the lines must be valid OTLP"
    _check(text)


def test_end_to_end_run_is_conformant(otlp: Any) -> None:
    _, buffer = otlp
    with sentry_sdk.start_transaction(name="GET /pets/1", op="http.server"):
        with sentry_sdk.start_span(op="db", name="SELECT 1"):
            pass
    sentry_sdk.capture_exception(ValueError("boom"))
    logging.getLogger("petdjango.views").warning("mirrored")
    sentry_sdk.flush(timeout=5)

    text = buffer.getvalue()
    assert parse_trace_envelopes(text)
    assert parse_log_envelopes(text)
    _check(text)


def test_header_attributes_are_string_arrays(
    make_adapter: Any, transaction_event: dict[str, Any]
) -> None:
    adapter, buffer = make_adapter()
    adapter.process_event(transaction_event)
    envelope = json.loads(buffer.getvalue())

    values = dict(conformance.iter_attributes(envelope))
    assert "arrayValue" in values["http.request.header.referer"]
    assert "arrayValue" in values["http.request.header.x-forwarded-for"]
    # The User-Agent is modelled as `user_agent.original`, not a header.
    assert "http.request.header.user-agent" not in values
    assert "user_agent.original" in values
