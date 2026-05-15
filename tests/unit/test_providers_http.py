"""Unit tests for shared HTTP utilities."""

from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from quota_tracker.providers.http import (
    get_json,
    post_json,
    request_with_response_headers,
    ssl_context,
)


def test_ssl_context_basic() -> None:
    # Just verify it returns an SSLContext without crashing.
    ctx = ssl_context()
    assert ctx is not None


@patch("urllib.request.urlopen")
def test_post_json_success(mock_urlopen: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"status": "ok"}'
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    res = post_json("http://example.com", {"key": "val"}, bearer_token="secret")
    assert res == {"status": "ok"}

    args, kwargs = mock_urlopen.call_args
    req = args[0]
    assert req.get_full_url() == "http://example.com"
    assert req.get_method() == "POST"
    assert req.get_header("Authorization") == "Bearer secret"
    assert req.get_header("Content-type") == "application/json"


@patch("urllib.request.urlopen")
def test_post_json_http_error(mock_urlopen: MagicMock) -> None:
    mock_err = urllib.error.HTTPError("http://example.com", 401, "Unauthorized", {}, MagicMock())
    mock_err.read = MagicMock(return_value=b'{"error": "invalid_token"}')
    mock_urlopen.side_effect = mock_err

    with pytest.raises(RuntimeError, match="HTTP 401: {'error': 'invalid_token'}"):
        post_json("http://example.com", {})


@patch("urllib.request.urlopen")
def test_get_json_success(mock_urlopen: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"foo": "bar"}'
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    res = get_json("http://example.com", headers={"X-Test": "yes"})
    assert res == {"foo": "bar"}


@patch("urllib.request.urlopen")
def test_request_with_response_headers_success(mock_urlopen: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"data": 123}'
    mock_resp.headers = {"X-RateLimit-Limit": "100"}
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    status, headers, body = request_with_response_headers(
        "http://example.com", method="PUT", headers={}, body={"x": 1}
    )
    assert status == 200
    assert headers == {"x-ratelimit-limit": "100"}
    assert body == {"data": 123}


@patch("urllib.request.urlopen")
def test_request_with_response_headers_error(mock_urlopen: MagicMock) -> None:
    mock_err = urllib.error.HTTPError(
        "http://example.com", 500, "Internal Error", {"X-Err": "fatal"}, MagicMock()
    )
    mock_err.read = MagicMock(return_value=b"Server error text")
    mock_urlopen.side_effect = mock_err

    status, headers, body = request_with_response_headers(
        "http://example.com", method="GET", headers={}
    )
    assert status == 500
    assert headers == {"x-err": "fatal"}
    assert body == {"raw": "Server error text"}


@patch("urllib.request.urlopen")
def test_post_json_empty_payload(mock_urlopen: MagicMock) -> None:
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"  "
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    res = post_json("http://example.com", {})
    assert res == {}
