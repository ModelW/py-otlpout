"""Root-logger handler that mirrors stdlib records through the otlpout integration."""

from __future__ import annotations

import logging
from typing import Any

import sentry_sdk

from otlpout._processor import IDENTIFIER

_installed = False


class OtlpLoggingHandler(logging.Handler):
    """Forward every stdlib log record to the current client's otlpout integration.

    The handler is attached unconditionally and decides nothing itself: the
    integration instance enforces the ``mirror_logging`` toggle and the
    logger allow/deny lists at emit time, so the per-client configuration
    keeps working even though the handler is installed only once.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)

    def emit(self, record: logging.LogRecord) -> None:
        """Hand ``record`` to otlpout, swallowing any exporter failure."""
        try:
            integration: Any = sentry_sdk.get_client().get_integration(IDENTIFIER)
            if integration is not None:
                integration.process_log_record(record)
        except Exception:
            self.handleError(record)


def install_logging_handler() -> None:
    """Attach the mirror handler to the root logger, once per process."""
    global _installed
    if _installed:
        return
    logging.getLogger().addHandler(OtlpLoggingHandler())
    _installed = True
