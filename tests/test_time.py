"""Tests for timestamp conversion to OTLP nanoseconds."""

from datetime import UTC, datetime

from otlpout._time import to_unix_nano


def test_epoch() -> None:
    assert to_unix_nano(datetime(1970, 1, 1, tzinfo=UTC)) == "0"


def test_datetime_to_nanos() -> None:
    assert to_unix_nano(datetime(1970, 1, 1, 0, 0, 1, tzinfo=UTC)) == "1000000000"


def test_microsecond_precision_is_exact() -> None:
    assert to_unix_nano(datetime(1970, 1, 1, 0, 0, 0, 1, tzinfo=UTC)) == "1000"


def test_naive_datetime_is_treated_as_utc() -> None:
    # Deliberately naive: the converter must treat a missing tz as UTC.
    assert to_unix_nano(datetime(1970, 1, 1, 0, 0, 1)) == "1000000000"  # noqa: DTZ001


def test_epoch_seconds() -> None:
    assert to_unix_nano(1.5) == "1500000000"


def test_iso_string() -> None:
    assert to_unix_nano("1970-01-01T00:00:01Z") == "1000000000"


def test_invalid_values_return_none() -> None:
    assert to_unix_nano(None) is None
    assert to_unix_nano("nonsense") is None
    assert to_unix_nano(True) is None
