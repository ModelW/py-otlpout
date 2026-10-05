"""Pet FastAPI app used to exercise the otlpout integration."""

import logging

from fastapi import FastAPI

logger = logging.getLogger("petfastapi.app")

app = FastAPI()


@app.get("/pets/{pet_id}")
def pet_detail(pet_id: int) -> dict[str, object]:
    """Return a single pet, emitting a log record on the way."""
    logger.warning("fetching pet %s", pet_id)
    return {"id": pet_id, "name": "Rex"}
