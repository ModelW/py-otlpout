# AGENTS.md

## Testing

- Full library suite: `uv run pytest` (~0.2s, timeout 60000ms)
- Django pet suite: `cd examples/django_pet && uv run pytest` (~1s, timeout 60000ms)
- FastAPI pet suite: `cd examples/fastapi_pet && uv run pytest` (~1s, timeout 60000ms)
- Static analysis: `uv run python -m ruff format --check .` then
  `uv run python -m ruff check .` then `uv run python -m mypy .`
- Always: redirect output to a temp file; silent on success; dump failures only.
- Last measured: 2026-10-08, library suite 0.13s.
