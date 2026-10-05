"""End-to-end integration tests against the real Sentry SDK (no DSN)."""

import logging
from typing import Any

import sentry_sdk

from otlpout._handler import OtlpLoggingHandler
from tests.otlp_helpers import parse_trace_envelopes


def _init(adapter: Any) -> None:
    """Initialise Sentry with ``adapter`` and fully deterministic options."""
    sentry_sdk.init(
        dsn=None,
        integrations=[adapter],
        traces_sample_rate=1.0,
        default_integrations=False,
        auto_session_tracking=False,
        send_client_reports=False,
    )


def test_emits_without_dsn(otlp: Any) -> None:
    _, buffer = otlp
    with sentry_sdk.start_transaction(name="txn", op="manual"):
        pass
    sentry_sdk.flush(timeout=5)
    assert len(parse_trace_envelopes(buffer.getvalue())) == 1


def test_logging_handler_installed_once(otlp: Any) -> None:
    handlers = [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, OtlpLoggingHandler)
    ]
    assert len(handlers) == 1


def test_reinit_honours_new_configuration(make_adapter: Any) -> None:
    first, first_buffer = make_adapter(service_name="first")
    _init(first)
    second, second_buffer = make_adapter(service_name="second")
    _init(second)
    with sentry_sdk.start_transaction(name="txn", op="manual"):
        pass
    sentry_sdk.flush(timeout=5)
    assert "txn" in second_buffer.getvalue()
    assert "txn" not in first_buffer.getvalue()


def test_check_in_is_skipped(make_adapter: Any) -> None:
    adapter, buffer = make_adapter()
    adapter.process_event({"type": "check_in"})
    assert buffer.getvalue() == ""


def test_sampling_can_drop_everything(
    make_adapter: Any, transaction_event: dict[str, Any]
) -> None:
    adapter, buffer = make_adapter(sample_rate=0.0)
    adapter.process_event(transaction_event)
    assert buffer.getvalue() == ""


def test_event_hook_installed_once(otlp: Any) -> None:
    from sentry_sdk.client import Client

    assert getattr(Client._prepare_event, "_otlpout_hook", False) is True
