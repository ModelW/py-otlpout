"""Wire the otlpout integration into Sentry for local pet-project runs."""

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from otlpout import OtlpOut


def install() -> None:
    """Initialise Sentry so every Django request emits OTLP/JSON to stdout.

    No DSN is set: local development still produces trace and log records,
    which is exactly the point of the bridge. ``send_default_pii`` is on so the
    request (headers, client address) reaches the output.
    """
    sentry_sdk.init(
        dsn=None,
        integrations=[
            DjangoIntegration(),
            OtlpOut(
                service_name="pet-django",
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
