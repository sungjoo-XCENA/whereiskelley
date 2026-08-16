import io
import unittest
from unittest.mock import patch

import app


class FakeHandler:
    def __init__(self):
        self.status = None
        self.headers = {}
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.headers[name.lower()] = value

    def end_headers(self):
        pass


class PdfProxyTests(unittest.TestCase):
    @patch.object(app, "safe_remote_url", return_value=True)
    @patch.object(app.sync_search_api, "fetch_binary")
    def test_pdf_proxy_uses_fallback_after_non_pdf_response(self, fetch_binary, _safe_url):
        fetch_binary.side_effect = [
            (b"<html>not found</html>", "text/html", "https://example.com/missing.pdf"),
            (b"%PDF-1.7\ncontent", "application/pdf", "https://example.com/fallback.pdf"),
        ]
        handler = FakeHandler()

        app.pdf_file_response(
            handler,
            {
                "url": ["https://example.com/missing.pdf"],
                "fallbackUrls": ["https://example.com/fallback.pdf"],
                "filename": ["Chez Colin.pdf"],
            },
        )

        self.assertEqual(handler.status, 200)
        self.assertTrue(handler.wfile.getvalue().startswith(b"%PDF"))
        self.assertEqual(handler.headers["content-type"], "application/pdf")
        self.assertIn("Chez-Colin.pdf", handler.headers["content-disposition"])
        self.assertEqual(handler.headers["x-pdf-source"], "https://example.com/fallback.pdf")


if __name__ == "__main__":
    unittest.main()
