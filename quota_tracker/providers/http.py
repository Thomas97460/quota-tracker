"""Shared HTTP utilities for provider active probes."""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def ssl_context() -> ssl.SSLContext:
    """Build an SSL context using the system CA bundle when available."""
    for env_name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        env_path = os.environ.get(env_name)
        if env_path and Path(env_path).exists():
            return ssl.create_default_context(cafile=env_path)
    for ca_path in (
        "/etc/ssl/certs/ca-certificates.crt",
        "/etc/ssl/cert.pem",
        "/etc/pki/tls/certs/ca-bundle.crt",
    ):
        if Path(ca_path).exists():
            return ssl.create_default_context(cafile=ca_path)
    return ssl.create_default_context()


def post_json(
    url: str,
    body: dict[str, Any],
    *,
    bearer_token: str | None = None,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    """POST a JSON body and return the parsed response dict."""
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds, context=ssl_context()) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            error_data: Any = json.loads(raw)
        except json.JSONDecodeError:
            error_data = raw[:1000]
        raise RuntimeError(f"HTTP {exc.code}: {error_data}") from exc
    if not payload.strip():
        return {}
    data = json.loads(payload)
    return data if isinstance(data, dict) else {"value": data}


def get_json(
    url: str,
    *,
    headers: dict[str, str],
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    """GET a URL with request headers and return the parsed JSON response."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds, context=ssl_context()) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            error_data: Any = json.loads(raw)
        except json.JSONDecodeError:
            error_data = raw[:1000]
        raise RuntimeError(f"HTTP {exc.code}: {error_data}") from exc
    if not payload.strip():
        return {}
    data = json.loads(payload)
    return data if isinstance(data, dict) else {"value": data}


def request_with_response_headers(
    url: str,
    *,
    method: str,
    headers: dict[str, str],
    body: dict[str, Any] | None = None,
    timeout_seconds: int = 20,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    """Execute an HTTP request and return (status_code, response_headers, body_dict)."""
    request_body = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=request_body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds, context=ssl_context()) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            status = resp.status
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        resp_headers = {k.lower(): v for k, v in exc.headers.items()}
        status = exc.code
    if not payload.strip():
        return status, resp_headers, {}
    try:
        parsed = json.loads(payload)
        body_data: dict[str, Any] = parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        body_data = {"raw": payload[:1000]}
    return status, resp_headers, body_data
