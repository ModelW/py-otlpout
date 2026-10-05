"""Tests for OTLP AnyValue encoding."""

from otlpout._attributes import attributes, key_value, to_any_value


def test_scalar_encoding() -> None:
    assert to_any_value(True) == {"boolValue": True}
    assert to_any_value(3) == {"intValue": "3"}
    assert to_any_value(1.5) == {"doubleValue": 1.5}
    assert to_any_value("x") == {"stringValue": "x"}


def test_null_is_skipped() -> None:
    assert to_any_value(None) is None
    assert key_value("k", None) is None


def test_nested_values() -> None:
    assert to_any_value(["a", 1]) == {
        "arrayValue": {"values": [{"stringValue": "a"}, {"intValue": "1"}]}
    }
    assert to_any_value({"a": 1}) == {
        "kvlistValue": {"values": [{"key": "a", "value": {"intValue": "1"}}]}
    }


def test_unknown_types_degrade_to_string() -> None:
    class Weird:
        def __str__(self) -> str:
            return "weird"

    assert to_any_value(Weird()) == {"stringValue": "weird"}


def test_attribute_list_drops_null_values() -> None:
    assert attributes({"a": 1, "b": None}) == [{"key": "a", "value": {"intValue": "1"}}]
    assert attributes(None) == []
