import base64
import io
import json
import sys
import tempfile
import types
import unittest
import zipfile
from argparse import Namespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch

from scripts.wine_shop_collect import (
    external_website,
    parse_merchant_profile,
    product_from_text,
    structured_products,
    crawl_merchant_inventory,
    DomainSlots,
    RobotsPolicy,
    AccessCircuit,
    corksy_config_from_html,
    corksy_products_from_payload,
    parse_csv_products,
    parse_pdf_products,
    parse_xlsx_products,
    run_inventory,
    select_inventory_merchants,
    save_inventory_result,
)
from wine_shop_db import connect_shop, ensure_shop_db, upsert_product


class WineShopCollectorTests(unittest.TestCase):
    def test_inventory_uses_multiple_processes_with_one_database_writer(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/robots.txt":
                    body, content_type = b"User-agent: *\nAllow: /\n", "text/plain"
                elif self.path == "/":
                    body, content_type = b'<a href="/wine-list">Wine list</a>', "text/html"
                elif self.path == "/wine-list":
                    body = b"<p>2011 Chateau Rayas Chateauneuf du Pape EUR 1,700</p>"
                    content_type = "text/html"
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("content-type", content_type)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                db_path = Path(temp_dir) / "shops.sqlite"
                ensure_shop_db(db_path)
                con = connect_shop(db_path)
                base = f"http://127.0.0.1:{server.server_port}"
                for index in range(4):
                    con.execute(
                        "insert into merchants(wine_searcher_id,name,normalized_name,website_url) values(?,?,?,?)",
                        (index + 1, f"Shop {index}", f"shop {index}", base),
                    )
                con.commit()
                con.close()
                args = Namespace(
                    db=str(db_path), stale_days=14, merchant_id=0, resume=False, limit=0,
                    country="", per_domain=2, workers=4, processes=2, max_pages=5, depth=2,
                )
                with patch("scripts.wine_shop_collect.atomic_progress"):
                    run_inventory(args)
                con = connect_shop(db_path)
                try:
                    statuses = [row[0] for row in con.execute(
                        "select inventory_status from merchants order by id"
                    )]
                    self.assertEqual(statuses, ["found"] * 4)
                    self.assertEqual(
                        con.execute("select count(*) from merchant_products where active=1").fetchone()[0],
                        4,
                    )
                finally:
                    con.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_inventory_country_filter_only_selects_requested_country(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shops.sqlite"
            ensure_shop_db(db_path)
            con = connect_shop(db_path)
            try:
                con.executemany(
                    "insert into merchants(wine_searcher_id,name,normalized_name,website_url,country) values(?,?,?,?,?)",
                    [
                        (1, "Hong Kong Shop", "hong kong shop", "https://hk.test", "HK"),
                        (2, "US Shop", "us shop", "https://us.test", "US"),
                    ],
                )
                con.commit()
                args = Namespace(merchant_id=0, country="HK", resume=False, limit=0)
                merchants = select_inventory_merchants(con, args, "2026-08-01T00:00:00+00:00")
            finally:
                con.close()

            self.assertEqual([merchant["name"] for merchant in merchants], ["Hong Kong Shop"])

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

    def test_corksy_widget_config_and_products_are_structured(self):
        widget = base64.b64encode(json.dumps({
            "collectionId": "71b2a32c-b972-4a27-bd0c-3ea8dc97cc6a",
        }).encode()).decode()
        html = f"""
        <script>window.Parameters = {{ExternalUid: 'public-app-key'}};</script>
        <div data-widget-config="{widget}"></div><script src="gocorksy-products.js"></script>
        """
        config = corksy_config_from_html(html)
        self.assertEqual(config["app_key"], "public-app-key")
        self.assertEqual(config["collection_ids"], ["71b2a32c-b972-4a27-bd0c-3ea8dc97cc6a"])
        payload = {
            "data": {"searchVariantsV2": {"totalCount": 1, "nodes": [{
                "productId": "product-1", "productName": "Volcano Rosé 750ml",
                "pageItemUrl": "volcano-rose-750ml",
                "product": {"nodes": [{"variants": {"nodes": [{
                    "id": "variant-1", "name": "750 ml", "price": "30.00",
                    "discountPrice": "0.00", "pageItemUrl": "volcano-rose-750ml",
                    "available": "10",
                }]}}]},
            }]}}
        }
        products, total = corksy_products_from_payload(payload, "https://volcanowinery.com/wines")
        self.assertEqual(total, 1)
        self.assertEqual(products[0]["price_value"], 30.0)
        self.assertEqual(products[0]["currency"], "USD")
        self.assertEqual(products[0]["source_url"], "https://volcanowinery.com/wine/volcano-rose-750ml")

    def test_dynamic_corksy_catalog_is_crawled_end_to_end(self):
        widget = base64.b64encode(json.dumps({"collectionId": "collection-1"}).encode()).decode()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/robots.txt":
                    body, content_type = b"User-agent: *\nAllow: /\n", "text/plain"
                elif self.path == "/":
                    body, content_type = b'<a href="/wines">Wines</a>', "text/html"
                elif self.path == "/wines":
                    body = (
                        f"<script>window.Parameters={{ExternalUid:'app-key'}};</script>"
                        f"<div data-widget-config=\"{widget}\"></div>"
                        '<script src="gocorksy-products.js"></script>'
                    ).encode()
                    content_type = "text/html"
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("content-type", content_type)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                return

        login = {"status": 200, "body": json.dumps({"accessToken": "token"}).encode()}
        graph = {"status": 200, "body": json.dumps({
            "data": {"searchVariantsV2": {"totalCount": 1, "nodes": [{
                "productId": "p1", "productName": "Volcano Rosé 750ml",
                "pageItemUrl": "volcano-rose-750ml",
                "product": {"nodes": [{"variants": {"nodes": [{
                    "id": "v1", "name": "Default", "price": "30.00",
                    "discountPrice": "0.00", "pageItemUrl": "volcano-rose-750ml",
                    "available": "5",
                }]}}]},
            }]}}
        }).encode()}
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            slots = DomainSlots(2)
            with patch("scripts.wine_shop_collect.post_json", side_effect=[login, graph]):
                result = crawl_merchant_inventory(
                    {"id": 1, "website_url": base}, max_pages=5, max_depth=2,
                    domain_slots=slots, robots=RobotsPolicy(slots),
                )
            self.assertEqual(result["status"], "found")
            self.assertEqual(result["sources"][0]["platform"], "corksy")
            products = [item for items in result["products"].values() for item in items]
            self.assertEqual(len(products), 1)
            self.assertEqual(products[0]["raw_name"], "Volcano Rosé 750ml")
        finally:
            server.shutdown()
            server.server_close()

    def test_pdf_csv_and_xlsx_price_lists_remain_supported(self):
        fake_reader = types.SimpleNamespace(
            pages=[types.SimpleNamespace(extract_text=lambda: "2011 Chateau Rayas Chateauneuf du Pape EUR 1,700")]
        )
        fake_module = types.SimpleNamespace(PdfReader=lambda _stream: fake_reader)
        with patch.dict(sys.modules, {"pypdf": fake_module}):
            pdf_products, error = parse_pdf_products(b"pdf", "https://shop.test/list.pdf")
        self.assertFalse(error)
        self.assertEqual(pdf_products[0]["price_value"], 1700.0)

        csv_products = parse_csv_products(
            b"2011,Chateau Rayas,Chateauneuf du Pape,EUR 1700\n",
            "https://shop.test/list.csv",
        )
        self.assertEqual(csv_products[0]["currency"], "EUR")

        shared = b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>2011 Chateau Rayas Chateauneuf du Pape EUR 1700</t></si></sst>'
        sheet = b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c t="s"><v>0</v></c></row></sheetData></worksheet>'
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("xl/sharedStrings.xml", shared)
            archive.writestr("xl/worksheets/sheet1.xml", sheet)
        xlsx_products = parse_xlsx_products(stream.getvalue(), "https://shop.test/list.xlsx")
        self.assertEqual(xlsx_products[0]["price_value"], 1700.0)

    def test_script_or_long_prose_is_not_saved_as_a_product(self):
        self.assertIsNone(product_from_text(
            "window.document function() Burgundy 2021 EUR 1000 schema.org",
            "https://merchant.test/wines",
        ))
        self.assertIsNone(product_from_text(
            "At the vineyard's high elevation, we see wintertime temperatures drop to around 38 degrees "
            "which is low enough to satisfy the grapes chill hour requirements of a cumulative 150 hours "
            "below 45 degrees. In the summer, temperatures warm to the high 70s, perfect for ripening our "
            "Pinot noir, Symphony, Syrah and Cayuga White grapes.",
            "https://merchant.test/vineyard",
        ))
        self.assertIsNone(product_from_text(
            "In late 2007 the winery decided to expand the vineyard further to include the vinifera vines "
            "Pinot noir and Syrah.",
            "https://merchant.test/vineyard",
        ))

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
