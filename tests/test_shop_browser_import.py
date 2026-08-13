import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from wine_shop_db import connect_shop


PROFILE_HTML = """
<html><head><title>Di Jin Wines SA | Wine-Searcher</title>
<script type="application/ld+json">{
  "@context":"https://schema.org", "@type":"LiquorStore",
  "name":"Di Jin Wines SA", "url":"https://www.di-jin-wines.com/en/",
  "address":{"addressLocality":"Geneva","addressCountry":"Switzerland"}
}</script></head><body><h1>Di Jin Wines SA</h1></body></html>
"""


class ShopBrowserImportTests(unittest.TestCase):
    def signed_headers(self, merchant_id, html, password="secret"):
        timestamp = str(int(time.time()))
        return {
            "x-whereiskelley-timestamp": timestamp,
            "x-whereiskelley-signature": app.shop_browser_signature(
                timestamp, merchant_id, html, secret=password
            ),
        }

    def test_signed_browser_profile_is_saved_to_existing_shop_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shops.sqlite"
            payload = {
                "merchantId": 33938,
                "finalUrl": "https://www.wine-searcher.com/merchant/33938-di-jin-wines-sa",
                "html": PROFILE_HTML,
                "progress": {"checked": 1, "total": 10, "complete": True},
            }
            with patch.object(app, "ADMIN_PASSWORD", "secret"), patch.object(app, "shop_atomic_progress"):
                result, status = app.import_browser_merchant(
                    payload, self.signed_headers(33938, PROFILE_HTML), db_path
                )
            self.assertEqual(status, 200)
            self.assertTrue(result["saved"])
            con = connect_shop(db_path)
            try:
                row = con.execute(
                    "select name,website_url from merchants where wine_searcher_id=33938"
                ).fetchone()
                self.assertEqual(row["name"], "Di Jin Wines SA")
                self.assertEqual(row["website_url"], "https://www.di-jin-wines.com/en/")
            finally:
                con.close()

    def test_verification_page_is_not_saved(self):
        html = "<html><body>Press and hold to prove you are human</body></html>"
        with patch.object(app, "ADMIN_PASSWORD", "secret"):
            result, status = app.import_browser_merchant(
                {"merchantId": 2, "html": html}, self.signed_headers(2, html)
            )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "verification_required")


if __name__ == "__main__":
    unittest.main()
