"""Pet views used to exercise the otlpout integration."""

import logging

from django.http import HttpRequest, JsonResponse

logger = logging.getLogger("petdjango.views")


def pet_detail(request: HttpRequest, pet_id: int) -> JsonResponse:
    """Return a single pet, emitting a log record on the way."""
    logger.warning("fetching pet %s", pet_id)
    return JsonResponse({"id": pet_id, "name": "Rex"})
