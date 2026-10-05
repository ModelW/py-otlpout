"""Tests for the stdlib logging mirror."""

import logging
from typing import Any

from otlpout._json import LineWriter
from otlpout._logs import log_record_to_otlp


def _flat(attributes: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten an OTLP attribute list to a ``{key: value}`` mapping."""
    return {item["key"]: next(iter(item["value"].values())) for item in attributes}


def test_log_record_conversion(make_adapter: Any) -> None:
    adapter, _ = make_adapter()
    record = logging.LogRecord(
        "app.views", logging.WARNING, "app.py", 10, "hi %s", ("bob",), None
    )
    log = log_record_to_otlp(record, adapter)["resourceLogs"][0]["scopeLogs"][0][
        "logRecords"
    ][0]
    assert log["severityNumber"] == 13
    assert log["severityText"] == "WARN"
    assert log["body"] == {"stringValue": "hi bob"}
    attrs = _flat(log["attributes"])
    assert attrs["logger.name"] == "app.views"
    assert attrs["code.file.path"] == "app.py"
    assert attrs["code.line.number"] == "10"


def test_mirrors_below_error_and_drops_denied(otlp: Any) -> None:
    _, buffer = otlp
    logging.getLogger("app.views").warning("kept")
    logging.getLogger("app.views").error("dropped-level")
    logging.getLogger("urllib3").warning("dropped-name")
    text = buffer.getvalue()
    assert "kept" in text
    assert "dropped-level" not in text
    assert "dropped-name" not in text


def test_allowlist_overrides_denylist(make_adapter: Any) -> None:
    adapter, _ = make_adapter(logger_allowlist=["app"])
    assert adapter._logger_allowed("app.views")
    assert not adapter._logger_allowed("other.module")


def test_line_writer_uses_stdout_at_write_time(capsys: Any) -> None:
    LineWriter().write({"a": 1})
    assert capsys.readouterr().out.strip() == '{"a":1}'
