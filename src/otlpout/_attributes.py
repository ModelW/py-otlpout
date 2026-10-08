"""Conversion of Python values into OTLP ``AnyValue`` attributes."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from datetime import datetime
from typing import Any


def to_any_value(value: Any) -> dict[str, Any] | None:
    """Encode a Python value as an OTLP ``AnyValue``, or ``None`` to skip it.

    Unknown types degrade to their ``str()`` representation rather than being
    dropped, so unusual Sentry payloads still surface in the output.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        # OTLP/JSON encodes 64-bit integers as decimal strings.
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"bytesValue": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, datetime):
        return {"stringValue": value.isoformat()}
    if isinstance(value, Mapping):
        nested = [
            kv
            for item in value.items()
            if (kv := key_value(str(item[0]), item[1])) is not None
        ]
        return {"kvlistValue": {"values": nested}}
    if isinstance(value, (list, tuple, set, frozenset)):
        nested = [av for item in value if (av := to_any_value(item)) is not None]
        return {"arrayValue": {"values": nested}}
    return {"stringValue": str(value)}


def key_value(key: str, value: Any) -> dict[str, Any] | None:
    """Build an OTLP ``KeyValue``, or ``None`` when the value is null."""
    any_value = to_any_value(value)
    if any_value is None:
        return None
    return {"key": key, "value": any_value}


def attributes(mapping: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Build an OTLP attribute list from a mapping, dropping null values."""
    if not mapping:
        return []
    return [
        kv
        for item in mapping.items()
        if (kv := key_value(str(item[0]), item[1])) is not None
    ]


#: Sentry stores these span-data/tag values as strings although the OTel
#: registry declares them as integers.
_INTEGER_KEYS = frozenset(
    {
        "client.port",
        "http.request.body.size",
        "http.response.body.size",
        "http.response.status_code",
        "http.status_code",
        "server.port",
        "thread.id",
    }
)


def conform_value(key: str, value: Any) -> Any:
    """Coerce a Sentry value to the type the OTel registry declares for *key*.

    Sentry surfaces some numeric attributes as strings (``thread.id``,
    ``http.status_code``); copying them verbatim would produce a
    type-non-conformant OTLP attribute, so they are parsed back to integers.
    """
    if key in _INTEGER_KEYS and isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return value
    return value
