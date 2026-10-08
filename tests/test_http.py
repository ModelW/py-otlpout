"""Tests for Sentry request/response -> OTLP HTTP semconv attributes."""

from typing import Any

from otlpout._http import http_attributes


def test_url_is_split_onto_semconv_attributes() -> None:
    event: dict[str, Any] = {
        "request": {"url": "https://example.com:8443/pets/1?q=1#frag"}
    }
    attrs = http_attributes(event)

    assert attrs["url.full"] == "https://example.com:8443/pets/1?q=1#frag"
    assert attrs["url.path"] == "/pets/1"
    assert attrs["url.query"] == "q=1"
    assert attrs["url.scheme"] == "https"
    assert attrs["server.address"] == "example.com"
    assert attrs["server.port"] == 8443
    # No invented scheme+host blob.
    assert "http.request.origin" not in attrs


def test_url_credentials_are_redacted() -> None:
    attrs = http_attributes({"request": {"url": "https://user:pass@example.com/p?q=1"}})

    assert attrs["url.full"] == "https://REDACTED:REDACTED@example.com/p?q=1"
    assert "pass" not in attrs["url.full"]
    assert attrs["server.address"] == "example.com"


def test_sensitive_query_parameters_are_redacted() -> None:
    attrs = http_attributes(
        {
            "request": {
                "url": "https://x.test/a?sig=abc&X-Amz-Signature=zzz&keep=1",
            }
        }
    )

    assert attrs["url.query"] == "sig=REDACTED&X-Amz-Signature=REDACTED&keep=1"
    assert "zzz" not in attrs["url.full"]


def test_empty_path_is_normalised() -> None:
    attrs = http_attributes({"request": {"url": "https://example.com"}})
    assert attrs["url.path"] == "/"
    assert attrs["url.full"] == "https://example.com/"


def test_headers_are_string_arrays_and_user_agent_is_not_duplicated() -> None:
    event: dict[str, Any] = {
        "request": {
            "headers": {
                "Referer": "https://ref.example.com/?x=1",
                "User-Agent": "curl/8.0",
                "X-Request-Id": "abc",
            }
        }
    }
    attrs = http_attributes(event)

    assert attrs["user_agent.original"] == "curl/8.0"
    assert attrs["http.request.header.referer"] == ["https://ref.example.com/?x=1"]
    assert attrs["http.request.header.x-request-id"] == ["abc"]
    # The registry models the User-Agent as `user_agent.original`, so it is not
    # repeated as a header.
    assert "http.request.header.user-agent" not in attrs
    # The invented referrer spelling is gone.
    assert "http.request.referrer" not in attrs


def test_server_address_prefers_the_forwarded_host() -> None:
    attrs = http_attributes(
        {
            "request": {
                "url": "http://internal.local/",
                "headers": {
                    "X-Forwarded-Host": "public.example.com:8443",
                    "Forwarded": 'for=1.2.3.4;host="origin.example.com"',
                },
            }
        }
    )

    assert attrs["server.address"] == "origin.example.com"
    assert "server.port" not in attrs


def test_protocol_version_is_read_from_the_server_environ() -> None:
    assert (
        http_attributes({"request": {"env": {"SERVER_PROTOCOL": "HTTP/1.1"}}})[
            "network.protocol.version"
        ]
        == "1.1"
    )
    assert (
        http_attributes({"request": {"env": {"SERVER_PROTOCOL": "HTTP/2"}}})[
            "network.protocol.version"
        ]
        == "2"
    )


def test_response_status_and_body_size() -> None:
    event: dict[str, Any] = {
        "request": {"url": "http://example.com/"},
        "contexts": {
            "response": {
                "status_code": 404,
                "body_size": 123,
                "headers": {"Content-Length": "123"},
            }
        },
    }
    attrs = http_attributes(event)

    assert attrs["http.response.status_code"] == 404
    assert attrs["http.response.body.size"] == 123
    assert attrs["http.response.header.content-length"] == ["123"]
    # A 4xx server span leaves the status unset, so no error.type either.
    assert "error.type" not in attrs


def test_server_error_sets_error_type() -> None:
    event: dict[str, Any] = {
        "request": {"url": "http://example.com/"},
        "contexts": {"response": {"status_code": 503}},
    }
    assert http_attributes(event)["error.type"] == "503"


def test_body_size_falls_back_to_content_length_header() -> None:
    event: dict[str, Any] = {
        "request": {"url": "http://example.com/"},
        "contexts": {"response": {"headers": {"content-length": "7"}}},
    }
    assert http_attributes(event)["http.response.body.size"] == 7


def test_annotated_header_values_are_skipped() -> None:
    class Marker:
        """Stands in for Sentry's ``AnnotatedValue`` (no textual wire value)."""

    event: dict[str, Any] = {
        "request": {"headers": {"Cookie": Marker(), "Accept": "text/html"}}
    }
    attrs = http_attributes(event)

    assert "http.request.header.cookie" not in attrs
    assert attrs["http.request.header.accept"] == ["text/html"]


def test_no_request_yields_no_attributes() -> None:
    assert http_attributes({}) == {}
