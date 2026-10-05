"""ASGI entry point that wires otlpout into Sentry for local runs.

Tests initialise Sentry themselves, so the integration lives here rather than
in ``petfastapi/app.py`` to keep the app import side-effect free.
"""

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from otlpout import OtlpOut
from petfastapi.app import app

sentry_sdk.init(
    dsn=None,  # no DSN: local runs still emit OTLP/JSON to stdout
    integrations=[
        StarletteIntegration(),
        FastApiIntegration(),
        OtlpOut(
            service_name="pet-fastapi",
            service_namespace="pets",
            deployment_environment="local",
            extra_resource_attributes={"component": "api"},
        ),
    ],
    traces_sample_rate=1.0,
    default_integrations=False,
    send_default_pii=True,
    auto_session_tracking=False,
    send_client_reports=False,
)

__all__ = ["app"]
