"""The process-global Sentry hook installed by the integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sentry_sdk.client import Client
from sentry_sdk.utils import logger

if TYPE_CHECKING:
    from sentry_sdk._types import Event, Hint
    from sentry_sdk.scope import Scope

IDENTIFIER = "otlpout"

_hooked = False


def install_event_hook() -> None:
    """Wrap ``Client._prepare_event`` so every prepared event reaches otlpout.

    A scope event processor is not usable here: interleaving is
    ``global_event_processors`` → global scope → isolation scope → current
    scope, and framework integrations attach the request/user context on
    *current-scope* processors that therefore run after any processor the
    integration could register. Wrapping ``Client._prepare_event`` runs after
    the SDK has finished populating the event (including ``request``/``user``)
    but before the envelope is built, for every client. Installed once per
    process; the wrapped function resolves its own client, so repeated
    ``sentry_sdk.init()`` calls each keep their configuration.
    """
    global _hooked
    if _hooked:
        return

    original = Client._prepare_event

    def _prepare_event(
        self: Any, event: Event, hint: Hint, scope: Scope | None
    ) -> Event | None:
        prepared = original(self, event, hint, scope)
        if prepared is not None:
            _route(self, prepared)
        return prepared

    _prepare_event._otlpout_hook = True  # type: ignore[attr-defined]
    Client._prepare_event = _prepare_event  # type: ignore[method-assign]
    _hooked = True


def _route(client: Any, event: Event) -> None:
    """Hand one prepared event to the client's otlpout integration.

    Swallows every failure so a bug in otlpout can never alter or block normal
    Sentry delivery.
    """
    try:
        integration = client.get_integration(IDENTIFIER)
        if integration is not None:
            integration.process_event(event)
    except Exception:
        logger.debug("otlpout: failed to export event", exc_info=True)
