# otlpout

A generic [Sentry Python SDK](https://docs.sentry.io/platforms/python/)
integration that mirrors everything Sentry traces — transaction spans, captured
errors/messages and mirrored `logging` records — to **stdout as OTLP/JSON**.

Once you plug the integration into `sentry_sdk.init()`, structured OpenTelemetry
records are written, one complete OTLP/JSON envelope per line, ready to be
picked up by a log drain. Normal Sentry delivery is left completely untouched.

```python
import sentry_sdk
from otlpout import OtlpOut

sentry_sdk.init(
    dsn="https://...@o0.ingest.sentry.io/0",
    traces_sample_rate=1.0,
    integrations=[
        OtlpOut(
            service_name="my-api",
            service_namespace="my-product",
            deployment_environment="production",
            extra_resource_attributes={"component": "api"},
        ),
    ],
)
```

Everything is configured in code — `otlpout` reads **no environment variables**.

## Why an integration?

Sentry does not expose a native "Sentry span → OTLP" conversion: its
`OpenTelemetryIntegration` goes the other way around (OTel spans → Sentry), and
`OTLPIntegration` only configures an exporter for spans produced by an OTel SDK.
`otlpout` therefore builds the OTLP mapping explicitly, from the events Sentry
already produces, without adding a second OpenTelemetry SDK to your process.

## What gets emitted

| Sentry source                                                  | OTLP/JSON payload |
| -------------------------------------------------------------- | ----------------- |
| HTTP spans (by default the `http.server` transaction root)     | `resourceSpans`   |
| Captured error / message                                       | `resourceLogs`    |
| Mirrored `logging` records below `ERROR`                       | `resourceLogs`    |

Each line is a standalone, schema-valid OTLP/JSON object, so a log drain can
forward `resourceSpans` to a traces pipeline and `resourceLogs` to a logs
pipeline without a collector.

Only the spans selected by `span_filter` are emitted — by default HTTP spans,
which in practice means the `http.server` transaction root that access-log
consumers need. Sentry keeps the full span tree, so child spans (DB queries,
templates, signals, Celery tasks) are deliberately **not** duplicated here:
shipping them wastes an order of magnitude of volume *and* pushes records past
the 16 KiB container log-line limit, which truncates them into invalid JSON.
Pass `span_filter=lambda _op: True` to emit every span instead.

Records larger than `max_line_bytes` (default 16 KiB — containerd's
`max_container_log_line_size`) are reduced to their core attributes (log bodies
truncated); if still too large they are dropped with a warning rather than handed
to a runtime that would truncate them mid-object.

## Configuration

`OtlpOut(...)` accepts, among others:

| Argument                   | Meaning                                                          |
| -------------------------- | ---------------------------------------------------------------- |
| `service_name`             | `service.name` resource attribute (required).                    |
| `service_version`          | `service.version` (falls back to the Sentry release).            |
| `service_namespace`        | `service.namespace` — the logical grouping, e.g. a product.      |
| `deployment_environment`   | `deployment.environment.name` (falls back to the event's env).   |
| `stream`                   | Output stream; defaults to `sys.stdout` resolved at write time.  |
| `mirror_logging`           | Mirror stdlib `logging` records below `ERROR` (default `True`).  |
| `ip_precedence`            | Header precedence used to resolve `client.address` (ipware).     |
| `extra_resource_attributes`| Non-standard attributes merged into every resource block.        |
| `span_filter`              | Predicate `op -> bool` selecting emitted spans (default HTTP only). |
| `max_line_bytes`           | Per-line budget; oversized records are reduced, then dropped.    |

The named arguments mirror the OpenTelemetry resource semantic conventions.
Anything outside that vocabulary (a `product` or `component` taxonomy, for
instance) is passed through `extra_resource_attributes` instead of a bespoke
parameter.

## Running the pets locally

Both pet projects wire Sentry + otlpout *outside* their tests, so a real
server prints one OTLP/JSON object per line to stdout as you browse:

```bash
# Django — Django's own request logs go to stderr, OTLP to stdout
cd examples/django_pet
uv run python manage.py runserver 127.0.0.1:8000 --noreload

# in another terminal
curl -s http://127.0.0.1:8000/pets/42/ -H 'X-Forwarded-For: 203.0.113.7, 10.0.0.1'
```

```bash
# FastAPI
cd examples/fastapi_pet
uv run uvicorn petfastapi.server:app --port 8001

# in another terminal
curl -s http://127.0.0.1:8001/pets/42 -H 'X-Forwarded-For: 203.0.113.7, 10.0.0.1'
```

To print only the OTLP records (Django logs to stderr):

```bash
uv run python manage.py runserver 127.0.0.1:8000 --noreload 2>/dev/null | grep '^{'
```

## Development

The repository is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/):

* `src/otlpout/` — the library.
* `examples/django_pet/` — a pet Django project with `pytest-django` tests.
* `examples/fastapi_pet/` — a pet FastAPI project with `TestClient` tests.

```bash
make format lint test        # library
make test-django test-fastapi # pet projects
```

Branching follows a `develop`-only git-flow: `develop` is the default branch and
all work happens on `feature/*` branches.
