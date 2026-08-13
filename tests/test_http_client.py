from __future__ import annotations

import pytest

from evidenceradar_editions.http_client import HttpSafetyError, validate_public_http_url


def test_public_url_validation_normalizes_and_strips_fragment() -> None:
    value = validate_public_http_url(
        "HTTPS://Example.COM/path?q=1#fragment",
        resolver=lambda _host, _port: ["93.184.216.34"],
    )
    assert value == "https://example.com/path?q=1"


def test_public_url_validation_rejects_private_dns_answer() -> None:
    with pytest.raises(HttpSafetyError, match="not exclusively public"):
        validate_public_http_url(
            "https://example.test/",
            resolver=lambda _host, _port: ["127.0.0.1"],
        )
