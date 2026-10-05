"""Management entry point for the pet Django project.

Wires Sentry + otlpout before Django starts so that ``runserver`` prints OTLP
records to stdout on every request.
"""

import os
import sys


def main() -> None:
    """Configure Django and Sentry, then run the management command."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "petdjango.settings")

    import django

    django.setup()

    from petdjango.telemetry import install

    install()

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
