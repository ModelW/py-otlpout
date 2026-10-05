"""Trace/span identifier normalisation for OTLP."""

from __future__ import annotations

import re
from typing import Any

_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID = re.compile(r"^[0-9a-f]{16}$")

ZERO_TRACE_ID = "0" * 32
ZERO_SPAN_ID = "0" * 16


def trace_id(value: Any) -> str:
    """Return a 32-character lowercase hex trace id, or 32 zeros when absent."""
    text = str(value).lower() if value else ""
    return text if _TRACE_ID.match(text) else ZERO_TRACE_ID


def span_id(value: Any) -> str:
    """Return a 16-character lowercase hex span id, or 16 zeros when absent."""
    text = str(value).lower() if value else ""
    return text if _SPAN_ID.match(text) else ZERO_SPAN_ID


def optional_span_id(value: Any) -> str | None:
    """Return a 16-character hex span id, or ``None`` when the value is unusable.

    Root spans have no parent, and OTLP expects ``parentSpanId`` to be omitted
    rather than zeroed in that case.
    """
    text = str(value).lower() if value else ""
    return text if _SPAN_ID.match(text) else None
