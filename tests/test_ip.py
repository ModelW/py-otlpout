"""Tests for client address resolution through ipware."""

from typing import Any

from otlpout._ip import client_address


def test_sentry_user_ip_is_preferred() -> None:
    event: dict[str, Any] = {
        "user": {"ip_address": "198.51.100.1"},
        "request": {"headers": {"X-Forwarded-For": "203.0.113.7"}},
    }
    assert client_address(event) == "198.51.100.1"


def test_x_forwarded_for_leftmost() -> None:
    event: dict[str, Any] = {
        "request": {"headers": {"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}}
    }
    assert client_address(event) == "203.0.113.7"


def test_provider_specific_header_is_supported() -> None:
    event: dict[str, Any] = {
        "request": {"headers": {"DO-Connecting-IP": "198.51.100.9"}}
    }
    assert client_address(event) == "198.51.100.9"


def test_remote_addr_fallback() -> None:
    event: dict[str, Any] = {"request": {"env": {"REMOTE_ADDR": "192.0.2.1"}}}
    assert client_address(event) == "192.0.2.1"


def test_no_request_returns_none() -> None:
    assert client_address({}) is None
