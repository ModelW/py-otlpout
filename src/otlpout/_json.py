"""Thread-safe, line-delimited JSON writer for OTLP records."""

from __future__ import annotations

import json
import sys
import threading
from typing import Any, TextIO


def dumps(obj: dict[str, Any]) -> str:
    """Serialise an OTLP object as compact single-line JSON."""
    return json.dumps(obj, separators=(",", ":"), default=str)


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
        """Serialise ``obj`` and write it as one flushed JSON line."""
        self.write_line(dumps(obj))

    def write_line(self, line: str) -> None:
        """Write an already-serialised JSON line and flush it for log drains."""
        stream = self._stream if self._stream is not None else sys.stdout
        with self._lock:
            stream.write(line)
            stream.write("\n")
            stream.flush()
