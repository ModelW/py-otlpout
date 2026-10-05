"""Timestamp helpers: normalise Sentry timestamps to OTLP nanoseconds."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def to_unix_nano(value: Any) -> str | None:
    """Convert a Sentry timestamp to a decimal string of Unix nanoseconds.

    Sentry events carry ``datetime`` objects in memory, but envelopes,
    structured logs and some integrations use epoch seconds (``float``) or
    RFC 3339 strings. All three shapes are accepted; ``None`` or an
    unparseable value yields ``None``.

    The result is a string because OTLP/JSON represents 64-bit integers as
    decimal strings, and integer math avoids the float drift that
    ``.timestamp() * 1e9`` introduces on microsecond-precision datetimes.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        delta = moment - _EPOCH
        nanos = (
            delta.days * 86_400 + delta.seconds
        ) * 1_000_000_000 + delta.microseconds * 1_000
        return str(nanos)
    if isinstance(value, (int, float)):
        return str(round(value * 1_000_000_000))
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return to_unix_nano(parsed)
    return None
