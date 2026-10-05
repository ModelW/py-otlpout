"""Map Sentry span status strings onto OTLP ``Status``."""

from __future__ import annotations

from typing import Any

_UNSET = {None, "", "unset"}


def otlp_status(status: Any) -> dict[str, Any]:
    """Return an OTLP ``Status`` for a Sentry status string.

    OTLP only distinguishes UNSET (0), OK (1) and ERROR (2). Every Sentry
    status other than ``ok``/``unset`` — the canonical gRPC codes such as
    ``internal_error``, ``unavailable`` or ``cancelled`` — is an error, and
    the original string is preserved verbatim as the status message.
    """
    if status is None:
        return {"code": 0}
    value = str(status).lower()
    if value in _UNSET:
        return {"code": 0}
    if value == "ok":
        return {"code": 1}
    return {"code": 2, "message": str(status)}
