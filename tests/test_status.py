"""Tests for Sentry span status -> OTLP status mapping."""

import pytest

from otlpout._status import otlp_status


@pytest.mark.parametrize(
    ("sentry_status", "code"),
    [
        ("ok", 1),
        (None, 0),
        ("unset", 0),
        ("internal_error", 2),
        ("cancelled", 2),
        ("unknown", 2),
    ],
)
def test_status_mapping(sentry_status: str | None, code: int) -> None:
    assert otlp_status(sentry_status)["code"] == code


def test_error_status_preserves_message() -> None:
    assert otlp_status("internal_error") == {"code": 2, "message": "internal_error"}
