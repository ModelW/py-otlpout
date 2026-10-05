"""Thread-safe, line-delimited JSON writer for OTLP records."""

from __future__ import annotations

import json
import sys
import threading
from typing import Any, TextIO


class LineWriter:
    """Serialise OTLP objects to one JSON line each on a possibly late-bound stream.

    The stream defaults to ``sys.stdout`` *resolved at write time* rather than
    captured at construction time. This keeps the writer compatible with
    pytest's ``capsys`` (which swaps ``sys.stdout`` after import) and with
    callers that emit before stdout is redirected.
    """

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream
        self._lock = threading.Lock()

    def write(self, obj: dict[str, Any]) -> None:
        """Write ``obj`` as a single JSON line and flush it for log drains."""
        stream = self._stream if self._stream is not None else sys.stdout
        line = json.dumps(obj, separators=(",", ":"), default=str)
        with self._lock:
            stream.write(line)
            stream.write("\n")
            stream.flush()
