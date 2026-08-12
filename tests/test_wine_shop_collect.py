import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from scripts.wine_shop_collect import (
    external_website,
    parse_merchant_profile,
    product_from_text,
    structured_products,
    crawl_merchant_inventory,
    DomainSlots,
    RobotsPolicy,
    AccessCircuit,
    save_inventory_result,
)
from wine_shop_db import connect_shop, ensure_shop_db, upsert_product


class WineShopCollectorTests(unittest.TestCase):
    def test_repeated_access_denials_open_the_scan_circuit(self):
        circuit = AccessCircuit(threshold=3)
        self.assertFalse(circuit.record({"status": 403}))
        self.assertFalse(circuit.record({"status": 429}))
        self.assertIn("blocked 3 consecutive", circuit.record({"status": 403}))
        self.assertTrue(circuit.blocked())

    def test_temporary_inventory_failure_keeps_last_known_products_active(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shops.sqlite"
            ensure_shop_db(db_path)
            con = connect_shop(db_path)
            try:
                merchant_id = con.execute(
                    "insert into merchants(wine_searcher_id,name,normalized_name,website_url,inventory_status) values(1,'Shop','shop','https://shop.test','found')"
                ).lastrowid
                source_id = con.execute(
                    "insert into merchant_sources(merchant_id,source_type,source_url,status) values(?,'html','https://shop.test/wines','found')",
                    (merchant_id,),
                ).lastrowid
                upsert_product(con, merchant_id, source_id, {
                    "source_key": "rayas", "source_url": "https://shop.test/wines",
                    "raw_name": "Chateau Rayas", "raw_text": "Chateau Rayas EUR 1000",
                    "wine_name": "Chateau Rayas", "price_value": 1000, "currency": "EUR",
                })
                save_inventory_result(con, {
                    "merchant_id": merchant_id, "status": "review", "sources": [],
                    "products": {}, "error": "temporary timeout",
                })
                active = con.execute(
                    "select active from merchant_products where merchant_id=?", (merchant_id,)
                ).fetchone()[0]
                source_status = con.execute(
                    "select status from merchant_sources where id=?", (source_id,)
                ).fetchone()[0]
                self.assertEqual(active, 1)
                self.assertEqual(source_status, "found")
            finally:
                con.close()

    def test_external_redirect_resolves_to_official_website(self):
        links = [
            (
                "/redirect?url=https%3A%2F%2F120west58wine.com%2Fpages%2Fshop-wine",
                "Visit website",
            )
        ]
        self.assertEqual(
            external_website(links, "https://www.wine-searcher.com/merchant/108376"),
            "https://120west58wine.com/pages/shop-wine",
        )

    def test_profile_parser_saves_merchant_and_official_site(self):
        html = """
        <html><head><title>Di Jin Wines SA | Wine-Searcher</title>
        <script type="application/ld+json">{
          "@context":"https://schema.org", "@type":"LiquorStore",
          "name":"Di Jin Wines SA", "url":"https://www.di-jin-wines.com/en/",
          "address":{"addressLocality":"Geneva","addressCountry":"Switzerland"}
        }</script></head><body><h1>Di Jin Wines SA</h1></body></html>
        """
        profile = parse_merchant_profile(
            html,
            "https://www.wine-searcher.com/merchant/33938",
        )
        self.assertEqual(profile["name"], "Di Jin Wines SA")
        self.assertEqual(profile["website_url"], "https://www.di-jin-wines.com/en/")
        self.assertEqual(profile["city"], "Geneva")

    def test_unstructured_row_requires_wine_evidence_and_price_or_vintage(self):
        product = product_from_text(
            "2021 Vosne-Romanee Domaine Mugneret-Gibourg HK$12,888",
            "https://merchant.test/list.pdf",
        )
        self.assertEqual(product["vintage"], "2021")
        self.assertEqual(product["currency"], "HKD")
        self.assertEqual(product["price_value"], 12888.0)
        self.assertIsNone(product_from_text("Welcome to our Burgundy dinner", "https://merchant.test/event"))

    def test_percentage_is_not_merged_into_the_price(self):
        product = product_from_text(
            "Moulin a Vent 2021 William Kelley 300, 100% Gamay",
            "https://merchant.test/list",
        )
        self.assertEqual(product["vintage"], "2021")
        self.assertEqual(product["price_value"], 300.0)

    def test_last_real_number_is_used_after_vintage_and_bottle_size(self):
        product = product_from_text(
            "2021 Vosne-Romanee 750 ml HK$12,888",
            "https://merchant.test/list.pdf",
        )
        self.assertEqual(product["price_value"], 12888.0)
        self.assertEqual(product["size_ml"], 750)

    def test_structured_product_can_be_saved_without_visible_price(self):
        products = structured_products(
            [{"@type": "Product", "name": "Krug Grande Cuvee", "url": "/products/krug"}],
            "https://merchant.test/shop",
        )
        self.assertEqual(len(products), 1)
        self.assertIsNone(products[0]["price_value"])

    def test_official_site_html_inventory_is_crawled_end_to_end(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/robots.txt":
                    body = b"User-agent: *\nAllow: /\n"
                    content_type = "text/plain"
                elif self.path == "/":
                    body = b'<a href="/wine-list">Wine list</a>'
                    content_type = "text/html"
                elif self.path == "/wine-list":
                    body = b"<p>2011 Chateau Rayas Chateauneuf du Pape EUR 1,700</p>"
                    content_type = "text/html"
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("content-type", content_type)
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            slots = DomainSlots(2)
            result = crawl_merchant_inventory(
                {"id": 1, "website_url": base},
                max_pages=10,
                max_depth=3,
                domain_slots=slots,
                robots=RobotsPolicy(slots),
            )
            self.assertEqual(result["status"], "found")
            products = [item for items in result["products"].values() for item in items]
            self.assertEqual(len(products), 1)
            self.assertEqual(products[0]["price_value"], 1700.0)
            self.assertEqual(products[0]["currency"], "EUR")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
