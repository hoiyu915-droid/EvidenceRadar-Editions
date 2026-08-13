from __future__ import annotations

import ipaddress
import json
import socket
from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_RESPONSE_LIMIT = 32 * 1024 * 1024
MAX_REDIRECTS = 5
USER_AGENT = (
    "EvidenceRadar-Editions/0.2 "
    "(+https://github.com/hoiyu915-droid/EvidenceRadar-Editions)"
)


class UnsafeUrlError(ValueError):
    """Raised before an unsafe or unresolvable HTTP target is requested."""


class ResponseTooLargeError(ValueError):
    """Raised when a response exceeds its declared or observed byte budget."""


Resolver = Callable[[str, int | None], Iterable[str]]


def _system_resolver(hostname: str, port: int | None) -> list[str]:
    try:
        records = socket.getaddrinfo(
            hostname,
            port or 443,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"hostname cannot be resolved: {hostname}") from exc
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
    resolver: Resolver = _system_resolver,
) -> str:
    """Normalize a public HTTP(S) URL and reject local/private targets.

    Call this again for every redirect hop. Requiring every DNS answer to be
    globally routable prevents mixed public/private answers from becoming a
    DNS-rebinding bypass.
    """

    try:
        parsed = urlsplit(str(raw_url).strip())
        port = parsed.port
    except ValueError as exc:
        raise UnsafeUrlError("URL is malformed") from exc
    if parsed.scheme.casefold() not in {"http", "https"}:
        raise UnsafeUrlError("URL must use HTTP or HTTPS")
    if not parsed.hostname:
        raise UnsafeUrlError("URL is missing a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeUrlError("URL must not contain user information")
    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").casefold()
    except UnicodeError as exc:
        raise UnsafeUrlError("hostname is invalid") from exc
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        addresses = list(resolver(hostname, port))
    else:
        addresses = [hostname]
    if not addresses or any(not _public_address(address) for address in addresses):
        raise UnsafeUrlError(f"hostname is not exclusively public: {hostname}")
    host = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None:
        host = f"{host}:{port}"
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            host,
            parsed.path or "/",
            parsed.query,
            "",
        )
    )


def _declared_length(response: requests.Response) -> int | None:
    raw = str(response.headers.get("Content-Length") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def bounded_response_bytes(
    response: requests.Response,
    *,
    limit: int = DEFAULT_RESPONSE_LIMIT,
) -> bytes:
    declared = _declared_length(response)
    if declared is not None and declared > limit:
        raise ResponseTooLargeError(
            f"response Content-Length {declared} exceeds {limit} bytes"
        )
    chunks: list[bytes] = []
    observed = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        observed += len(chunk)
        if observed > limit:
            raise ResponseTooLargeError(f"response body exceeds {limit} bytes")
        chunks.append(bytes(chunk))
    return b"".join(chunks)


class HttpClient:
    """Bounded, redirect-aware client for the fixed public source adapters."""

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        timeout: int = 30,
        response_limit: int = DEFAULT_RESPONSE_LIMIT,
        resolver: Resolver = _system_resolver,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.response_limit = response_limit
        self.resolver = resolver
        if session is None:
            retry = Retry(
                total=3,
                connect=3,
                read=3,
                status=3,
                backoff_factor=0.4,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset({"GET"}),
                respect_retry_after_header=True,
                # Redirects are handled manually so every hop is revalidated.
                redirect=0,
                raise_on_redirect=False,
            )
            self.session.mount("https://", HTTPAdapter(max_retries=retry))
            self.session.mount("http://", HTTPAdapter(max_retries=retry))
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.session.headers.setdefault(
            "Accept", "application/json, application/xml, text/xml, */*"
        )

    def get_bytes(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> bytes:
        current = validate_public_http_url(url, resolver=self.resolver)
        current_params = params
        byte_limit = self.response_limit if limit is None else limit
        if byte_limit < 1:
            raise ValueError("response byte limit must be positive")
        for redirect_count in range(MAX_REDIRECTS + 1):
            with self.session.get(
                current,
                params=current_params,
                timeout=self.timeout,
                allow_redirects=False,
                stream=True,
            ) as response:
                if response.is_redirect or response.is_permanent_redirect:
                    if redirect_count >= MAX_REDIRECTS:
                        raise UnsafeUrlError("too many HTTP redirects")
                    location = str(response.headers.get("Location") or "").strip()
                    if not location:
                        raise UnsafeUrlError("HTTP redirect is missing Location")
                    current = validate_public_http_url(
                        urljoin(response.url, location), resolver=self.resolver
                    )
                    current_params = None
                    continue
                response.raise_for_status()
                return bounded_response_bytes(response, limit=byte_limit)
        raise UnsafeUrlError("too many HTTP redirects")

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        payload = self.get_bytes(url, params=params, limit=limit)
        data = json.loads(payload.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("expected JSON object")
        return data
