"""Tests for resource block construction."""

from typing import Any

from otlpout._resource import build_resource


def _flat(resource: dict[str, Any]) -> dict[str, Any]:
    """Flatten a resource's attribute list to a ``{key: value}`` mapping."""
    return {
        item["key"]: next(iter(item["value"].values()))
        for item in resource["attributes"]
    }


def test_configuration_values_win(make_adapter: Any) -> None:
    adapter, _ = make_adapter(
        service_namespace="pets",
        deployment_environment="prod",
        service_version="1.2.3",
        extra_resource_attributes={"component": "api"},
    )
    flat = _flat(
        build_resource(
            adapter,
            {
                "environment": "ignored",
                "release": "ignored",
                "server_name": "host",
                "sdk": {"version": "9.9"},
            },
        )
    )
    assert flat["service.name"] == "test-service"
    assert flat["service.namespace"] == "pets"
    assert flat["service.version"] == "1.2.3"
    assert flat["deployment.environment.name"] == "prod"
    assert flat["component"] == "api"
    assert flat["host.name"] == "host"
    assert flat["telemetry.sdk.name"] == "sentry"
    assert flat["telemetry.sdk.language"] == "python"
    assert flat["telemetry.sdk.version"] == "9.9"


def test_event_metadata_is_a_fallback(make_adapter: Any) -> None:
    adapter, _ = make_adapter()
    flat = _flat(
        build_resource(
            adapter,
            {
                "environment": "staging",
                "release": "rel-1",
                "sdk": {"version": "2.71.0"},
            },
        )
    )
    assert flat["deployment.environment.name"] == "staging"
    assert flat["service.version"] == "rel-1"


def test_extra_resource_attributes(make_adapter: Any) -> None:
    adapter, _ = make_adapter(extra_resource_attributes={"custom": "value"})
    assert _flat(build_resource(adapter))["custom"] == "value"
