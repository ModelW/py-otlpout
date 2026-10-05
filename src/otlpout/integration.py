"""The public Sentry integration that mirrors spans, errors and logs to stdout."""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

from sentry_sdk.integrations import Integration

from otlpout import _handler, _processor
from otlpout._json import LineWriter
from otlpout._logs import event_to_otlp, log_record_to_otlp
from otlpout._spans import transaction_to_otlp

DEFAULT_LOGGER_DENYLIST: tuple[str, ...] = (
    # Sentry transport I/O and per-query database logs would duplicate the
    # spans and errors the integration already emits.
    "sentry_sdk",
    "urllib3",
    "django.db.backends",
)


class OtlpOut(Integration):
    """Mirror everything Sentry traces to stdout as line-delimited OTLP/JSON.

    Pass an instance to ``sentry_sdk.init(integrations=[...])``. Transactions
    (root span plus children) become ``resourceSpans`` envelopes; captured
    errors/messages and mirrored ``logging`` records become ``resourceLogs``
    envelopes. Every line is a complete, schema-valid OTLP/JSON object.

    All configuration is constructor arguments; the integration reads no
    environment variables and installs nothing until Sentry calls
    :meth:`setup_once`.
    """

    identifier = _processor.IDENTIFIER

    def __init__(
        self,
        service_name: str,
        *,
        service_version: str | None = None,
        service_namespace: str | None = None,
        deployment_environment: str | None = None,
        stream: TextIO | None = None,
        mirror_logging: bool = True,
        sample_rate: float = 1.0,
        ip_precedence: tuple[str, ...] | None = None,
        extra_resource_attributes: Mapping[str, Any] | None = None,
        logger_denylist: Collection[str] = DEFAULT_LOGGER_DENYLIST,
        logger_allowlist: Collection[str] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        """Configure the integration.

        The named arguments mirror the OpenTelemetry resource semantic
        conventions; anything outside that vocabulary (a ``product`` or
        ``component`` taxonomy, say) goes through
        ``extra_resource_attributes`` rather than a bespoke parameter.

        :param service_name: Value of the ``service.name`` resource attribute.
        :param service_version: ``service.version``; falls back to the Sentry
            release.
        :param service_namespace: ``service.namespace``, the logical grouping
            the service belongs to (e.g. a product).
        :param deployment_environment: ``deployment.environment.name``; falls
            back to the event's environment.
        :param stream: Where JSON lines are written. Defaults to ``sys.stdout``
            resolved at write time.
        :param mirror_logging: Mirror stdlib ``logging`` records below
            ``ERROR`` (default ``True``).
        :param sample_rate: Fraction of records to emit, ``0.0``-``1.0``.
        :param ip_precedence: Header precedence passed to ipware for
            ``client.address`` resolution; defaults to ipware's list.
        :param extra_resource_attributes: Extra, non-standard attributes merged
            into every resource block (e.g. ``{"component": "api"}``).
        :param logger_denylist: Logger name prefixes never mirrored.
        :param logger_allowlist: When set, only these logger name prefixes are
            mirrored (overrides the denylist).
        :param rng: Random source used for sampling (injectable for tests).
        """
        self.service_name = service_name
        self.service_version = service_version
        self.service_namespace = service_namespace
        self.deployment_environment = deployment_environment
        self.mirror_logging = mirror_logging
        self.sample_rate = sample_rate
        self.ip_precedence = ip_precedence
        self.extra_resource_attributes: Mapping[str, Any] = (
            extra_resource_attributes or {}
        )
        self._writer = LineWriter(stream)
        self._denylist = tuple(logger_denylist)
        self._allowlist = (
            tuple(logger_allowlist) if logger_allowlist is not None else None
        )
        self._rng = rng or random.Random()  # noqa: S311 - reproducibility only, not security

    @staticmethod
    def setup_once() -> None:
        """Install the process-global event processor and logging mirror.

        Sentry calls this exactly once, before any event is captured. Both
        hooks resolve the current client's integration dynamically, so they
        survive repeated initialisation (as done by tests).
        """
        _processor.install_event_hook()
        _handler.install_logging_handler()

    def process_event(self, event: dict[str, Any]) -> None:
        """Convert one Sentry event into an OTLP/JSON line when relevant."""
        event_type = event.get("type")
        if event_type == "check_in":
            return
        if event_type == "transaction":
            self._emit(transaction_to_otlp(event, self))
        else:
            self._emit(event_to_otlp(event, self))

    def process_log_record(self, record: logging.LogRecord) -> None:
        """Mirror a stdlib log record when it passes the configured filters."""
        if not self.mirror_logging or record.levelno >= logging.ERROR:
            return
        if not self._logger_allowed(record.name):
            return
        self._emit(log_record_to_otlp(record, self))

    def _logger_allowed(self, name: str) -> bool:
        if self._allowlist is not None:
            return any(_prefix_match(name, item) for item in self._allowlist)
        return not any(_prefix_match(name, item) for item in self._denylist)

    def _emit(self, obj: dict[str, Any] | None) -> None:
        if obj is None:
            return
        if self.sample_rate < 1.0 and self._rng.random() >= self.sample_rate:
            return
        self._writer.write(obj)


def _prefix_match(name: str, prefix: str) -> bool:
    """Return whether ``name`` is ``prefix`` or a dotted descendant of it."""
    return name == prefix or name.startswith(prefix + ".")
