from __future__ import annotations

import ipaddress
import json
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .upstream import RadarNetworkBridge

DEFAULT_RESPONSE_LIMIT = 8 * 1024 * 1024
DEFAULT_USER_AGENT = (
    "EvidenceRadar-Editions/0.1 "
    "(+https://github.com/hoiyu915-droid/EvidenceRadar-Editions)"
)


class HttpSafetyError(ValueError):
    """Raised when a URL or response violates the network boundary."""


class ResponseTooLargeError(ValueError):
    """Raised when an HTTP response exceeds the configured byte budget."""


def _system_resolver(hostname: str, port: int | None) -> list[str]:
    try:
        records = socket.getaddrinfo(hostname, port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HttpSafetyError(f"hostname cannot be resolved: {hostname}") from exc
    return sorted({str(record[4][0]).split("%", 1)[0] for record in records})


def _public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.is_global


def validate_public_http_url(
    raw_url: str,
    *,
    resolver: Callable[[str, int | None], Iterable[str]] = _system_resolver,
) -> str:
    try:
        parsed = urlsplit(str(raw_url).strip())
        port = parsed.port
    except ValueError as exc:
        raise HttpSafetyError("URL is malformed") from exc
    if parsed.scheme.casefold() not in {"http", "https"}:
        raise HttpSafetyError("URL must use HTTP or HTTPS")
    if not parsed.hostname:
        raise HttpSafetyError("URL is missing a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise HttpSafetyError("URL must not contain user information")
    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").casefold()
    except UnicodeError as exc:
        raise HttpSafetyError("hostname is invalid") from exc
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        addresses = list(resolver(hostname, port))
    else:
        addresses = [hostname]
    if not addresses or any(not _public_address(address) for address in addresses):
        raise HttpSafetyError(f"hostname is not exclusively public: {hostname}")
    host = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None:
        host = f"{host}:{port}"
    return urlunsplit((parsed.scheme.casefold(), host, parsed.path or "/", parsed.query, ""))


def bounded_response_bytes(response: Any, *, limit: int = DEFAULT_RESPONSE_LIMIT) -> bytes:
    declared_raw = str(getattr(response, "headers", {}).get("Content-Length") or "").strip()
    if declared_raw:
        try:
            declared = int(declared_raw)
        except ValueError:
            declared = None
        if declared is not None and declared > limit:
            raise ResponseTooLargeError(
                f"response Content-Length {declared} exceeds {limit} bytes"
            )
    chunks: list[bytes] = []
    observed = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        data = bytes(chunk)
        observed += len(data)
        if observed > limit:
            raise ResponseTooLargeError(f"response body exceeds {limit} bytes")
        chunks.append(data)
    return b"".join(chunks)


def bounded_response_text(response: Any, *, limit: int = DEFAULT_RESPONSE_LIMIT) -> str:
    payload = bounded_response_bytes(response, limit=limit)
    encoding = str(getattr(response, "encoding", None) or "utf-8")
    try:
        return payload.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace")


@dataclass
class HttpResponse:
    url: str
    status_code: int
    text: str
    headers: dict[str, str]

    def json(self) -> Any:
        return json.loads(self.text)


class SafeHttpClient:
    """Small requests client with SSRF checks, bounded bodies, and explicit redirects."""

    def __init__(
        self,
        *,
        bridge: RadarNetworkBridge | None = None,
        timeout: float = 30.0,
        response_limit: int = DEFAULT_RESPONSE_LIMIT,
        user_agent: str = DEFAULT_USER_AGENT,
        max_redirects: int = 5,
    ) -> None:
        self.timeout = timeout
        self.response_limit = response_limit
        self.max_redirects = max_redirects
        self._validate_url = (
            bridge.validate_public_http_url
            if bridge and bridge.validate_public_http_url
            else validate_public_http_url
        )
        self._bounded_text = (
            bridge.bounded_response_text
            if bridge and bridge.bounded_response_text
            else bounded_response_text
        )
        self.session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.mount("http://", HTTPAdapter(max_retries=retry))
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json, application/xml, text/xml;q=0.9, */*;q=0.1",
            }
        )

    def get(self, url: str, *, params: dict[str, Any] | None = None) -> HttpResponse:
        current_url = self._validate_url(url)
        current_params = params
        for redirect_count in range(self.max_redirects + 1):
            response = self.session.get(
                current_url,
                params=current_params,
                timeout=self.timeout,
                stream=True,
                allow_redirects=False,
            )
            current_params = None
            if response.is_redirect or response.is_permanent_redirect:
                if redirect_count >= self.max_redirects:
                    raise HttpSafetyError("too many redirects")
                location = response.headers.get("Location")
                if not location:
                    raise HttpSafetyError("redirect response is missing Location")
                current_url = self._validate_url(urljoin(response.url, location))
                response.close()
                continue
            response.raise_for_status()
            text = self._bounded_text(response, limit=self.response_limit)
            headers = {str(k): str(v) for k, v in response.headers.items()}
            final_url = str(response.url)
            response.close()
            return HttpResponse(
                url=final_url,
                status_code=response.status_code,
                text=text,
                headers=headers,
            )
        raise HttpSafetyError("redirect loop")
