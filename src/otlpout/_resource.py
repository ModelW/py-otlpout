"""Build OTLP ``resource`` blocks from adapter configuration and event metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import sentry_sdk

from otlpout._attributes import attributes

if TYPE_CHECKING:
    from otlpout.integration import OtlpOut


def build_resource(
    adapter: OtlpOut, event: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return the OTLP ``resource`` shared by every record of an event.

    The named attributes follow the OpenTelemetry resource semantic
    conventions. Configuration wins over event metadata for the values the
    caller set explicitly (version, namespace, environment); event data fills
    the gaps so that ``release``/``environment``/``server_name`` still reach
    the output when the adapter left them unset. Anything outside the standard
    vocabulary is supplied through ``extra_resource_attributes`` and merged
    last, so a caller can override a convention value if they really mean to.
    """
    metadata = event or {}
    sdk = metadata.get("sdk") or {}
    values: dict[str, Any] = {
        "service.name": adapter.service_name,
        "service.namespace": adapter.service_namespace,
        "service.version": adapter.service_version or metadata.get("release"),
        "deployment.environment.name": adapter.deployment_environment
        or metadata.get("environment"),
        "telemetry.sdk.name": "sentry",
        "telemetry.sdk.language": "python",
        "telemetry.sdk.version": sdk.get("version") or sentry_sdk.VERSION,
        "host.name": metadata.get("server_name"),
    }
    values.update(adapter.extra_resource_attributes)
    return {"attributes": attributes(values)}
