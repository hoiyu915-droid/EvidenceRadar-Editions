import unittest
from datetime import date

from evidenceradar_editions.http import (
    ResponseTooLargeError,
    UnsafeUrlError,
    bounded_response_bytes,
    validate_public_http_url,
)
from evidenceradar_editions.utils import period_overlaps


class FakeResponse:
    def __init__(self, chunks, content_length=None):
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)
        self._chunks = chunks

    def iter_content(self, chunk_size=65536):
        yield from self._chunks


class SafetyTests(unittest.TestCase):
    def test_url_boundary_rejects_private_and_credentials(self):
        with self.assertRaises(UnsafeUrlError):
            validate_public_http_url("http://127.0.0.1/private")
        with self.assertRaises(UnsafeUrlError):
            validate_public_http_url("https://user:secret@example.org/")
        value = validate_public_http_url(
            "HTTPS://Example.ORG/path#fragment",
            resolver=lambda host, port: ["93.184.216.34"],
        )
        self.assertEqual(value, "https://example.org/path")

    def test_bounded_response_enforces_declared_and_observed_size(self):
        with self.assertRaises(ResponseTooLargeError):
            bounded_response_bytes(FakeResponse([], content_length=10), limit=9)
        with self.assertRaises(ResponseTooLargeError):
            bounded_response_bytes(FakeResponse([b"12345", b"67890"]), limit=9)
        self.assertEqual(bounded_response_bytes(FakeResponse([b"abc"]), limit=3), b"abc")

    def test_month_precision_overlaps_requested_day(self):
        self.assertTrue(
            period_overlaps(date(2026, 8, 1), "MONTH", date(2026, 8, 13), date(2026, 8, 13))
        )
        self.assertFalse(
            period_overlaps(date(2026, 7, 1), "MONTH", date(2026, 8, 13), date(2026, 8, 13))
        )
