"""Third-party conformance checks for emitted OTLP/JSON.

Two layers, both leaning on official OpenTelemetry packages:

* **Wire conformance** is proven elsewhere by parsing each line with the
  ``opentelemetry-proto`` messages (see :mod:`tests.otlp_helpers`).
* **Semantic-convention conformance** is proven here against the official
  ``opentelemetry-semantic-conventions`` registry: every emitted attribute that
  lives in an OpenTelemetry namespace this project claims to speak must be a
  registered attribute (or a documented dynamic template such as
  ``http.request.header.<key>``), and its OTLP value type must match the type
  the registry declares.

The registry ships keys as plain strings (no type objects), so the value type
expected for the keys we emit is declared in :data:`EXPECTED_TYPES`; the dynamic
templates are always ``string[]``.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from collections.abc import Iterator

#: Namespaces this project is responsible for. A key under one of them MUST be a
#: registered semantic-convention attribute (or a template / explicit custom
#: extension); keys outside them are treated as custom/pass-through data.
MANAGED_PREFIXES = (
    "client.",
    "code.",
    "deployment.",
    "error.",
    "exception.",
    "host.",
    "http.",
    "log.",
    "network.",
    "process.",
    "server.",
    "service.",
    "telemetry.",
    "thread.",
    "url.",
    "user_agent.",
)

#: Deliberate custom extensions under a managed namespace, kept by design.
ALLOWED_CUSTOM_KEYS = frozenset({"user_agent.synthetic.bot_category"})

#: OTLP ``AnyValue`` kind the registry declares for the keys this project emits.
EXPECTED_TYPES: dict[str, str] = {
    "client.address": "stringValue",
    "code.file.path": "stringValue",
    "code.function.name": "stringValue",
    "code.line.number": "intValue",
    "deployment.environment.name": "stringValue",
    "error.type": "stringValue",
    "exception.message": "stringValue",
    "exception.stacktrace": "stringValue",
    "exception.type": "stringValue",
    "host.name": "stringValue",
    "http.request.body.size": "intValue",
    "http.request.method": "stringValue",
    "http.response.body.size": "intValue",
    "http.response.status_code": "intValue",
    "http.route": "stringValue",
    "network.protocol.version": "stringValue",
    "process.pid": "intValue",
    "server.address": "stringValue",
    "server.port": "intValue",
    "service.name": "stringValue",
    "service.namespace": "stringValue",
    "service.version": "stringValue",
    "telemetry.sdk.language": "stringValue",
    "telemetry.sdk.name": "stringValue",
    "telemetry.sdk.version": "stringValue",
    "thread.id": "intValue",
    "url.full": "stringValue",
    "url.path": "stringValue",
    "url.query": "stringValue",
    "url.scheme": "stringValue",
    "user_agent.name": "stringValue",
    "user_agent.original": "stringValue",
    "user_agent.synthetic.type": "stringValue",
    "user_agent.version": "stringValue",
}


def _collect_registry() -> tuple[set[str], set[str]]:
    """Return ``(registered_keys, template_prefixes)`` from the OTel registry."""
    keys: set[str] = set()
    templates: set[str] = set()

    for package_name in (
        "opentelemetry.semconv.attributes",
        "opentelemetry.semconv._incubating.attributes",
    ):
        package = importlib.import_module(package_name)

        for module_info in pkgutil.iter_modules(package.__path__):
            module = importlib.import_module(f"{package_name}.{module_info.name}")

            for name in dir(module):
                if not name.isupper():
                    continue
                value = getattr(module, name)
                if not isinstance(value, str):
                    continue
                if name.endswith("_TEMPLATE"):
                    templates.add(value + ".")
                else:
                    keys.add(value)

    return keys, templates


REGISTERED_KEYS, TEMPLATE_PREFIXES = _collect_registry()


def _pairs(attributes: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(key, value)`` for an OTLP attribute list."""
    for attribute in attributes or []:
        key = attribute.get("key")
        value = attribute.get("value")
        if isinstance(key, str) and isinstance(value, dict):
            yield key, value


def iter_attributes(envelope: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield every ``(key, value)`` attribute of an OTLP/JSON envelope."""
    for resource_spans in envelope.get("resourceSpans", []) or []:
        yield from _pairs((resource_spans.get("resource") or {}).get("attributes"))
        for scope_span in resource_spans.get("scopeSpans", []) or []:
            for span in scope_span.get("spans", []) or []:
                yield from _pairs(span.get("attributes"))

    for resource_logs in envelope.get("resourceLogs", []) or []:
        yield from _pairs((resource_logs.get("resource") or {}).get("attributes"))
        for scope_log in resource_logs.get("scopeLogs", []) or []:
            for record in scope_log.get("logRecords", []) or []:
                yield from _pairs(record.get("attributes"))


def first_string(value: dict[str, Any]) -> str | None:
    """Return the (first) string of an OTLP ``AnyValue``, or ``None``."""
    if "stringValue" in value:
        return value["stringValue"]
    items = value.get("arrayValue", {}).get("values", [])
    if items and "stringValue" in items[0]:
        return items[0]["stringValue"]
    return None


def assert_semconv_conformant(envelope: dict[str, Any], where: str) -> None:
    """Assert every managed attribute is a registered, correctly-typed semconv key."""
    violations: list[str] = []

    for key, value in iter_attributes(envelope):
        if key in ALLOWED_CUSTOM_KEYS:
            continue
        if key in REGISTERED_KEYS:
            expected = EXPECTED_TYPES.get(key)
            if expected is not None and expected not in value:
                violations.append(f"{key!r} must be {expected}, got {sorted(value)}")
        elif any(key.startswith(prefix) for prefix in TEMPLATE_PREFIXES):
            if "arrayValue" not in value:
                violations.append(
                    f"{key!r} is a string[] template and must use arrayValue, "
                    f"got {sorted(value)}"
                )
        elif key.startswith(MANAGED_PREFIXES):
            violations.append(
                f"{key!r} lives in an OpenTelemetry namespace this project "
                "manages but is not a registered semantic-convention attribute"
            )

    if violations:
        report = "\n  - ".join(violations)
        message = f"{where}: semantic-convention violations:\n  - {report}"
        raise AssertionError(message)


def assert_url_full_is_absolute(envelope: dict[str, Any], where: str) -> None:
    """Assert every ``url.full`` is an absolute URL (RFC 3986)."""
    for key, value in iter_attributes(envelope):
        if key != "url.full":
            continue
        url = first_string(value)
        if url is None:
            continue
        parts = urlsplit(url)
        assert parts.scheme, f"{where}: url.full MUST be absolute, got {url!r}"
        assert parts.netloc, f"{where}: url.full MUST be absolute, got {url!r}"
