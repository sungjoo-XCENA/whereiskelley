import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import guide_collect as guide


class WineDiscoveryTests(unittest.TestCase):
    def parsed_lines(self, text):
        return [
            guide.clean_text(line)
            for line in guide.candidate_text_lines(text)
            if guide.likely_wine_line(line, [])
        ]

    def test_rejects_event_package_prices(self):
        text = """
        Valentine's Day event
        Seven course dinner with three glasses of wine pairing NT$8,888 per person
        Eight course celebration menu with four glasses of wine pairing NT$10,888 per person
        Krug Champagne masterclass ticket NT$12,888
        Christmas dinner package with Champagne NT$9,888
        Reservation deposit NT$2,000
        """
        lines = self.parsed_lines(text)
        confidence, reason, needs_review = guide.source_confidence(
            "https://example.com/en/event",
            "html",
            text,
            lines,
            80,
        )
        self.assertEqual(lines, [])
        self.assertIn("Event", reason)
        self.assertFalse(needs_review)
        self.assertLess(confidence, 120)

    def test_accepts_distinct_high_end_wine_rows(self):
        text = """
        2018 Domaine de la Romanee-Conti La Tache, Vosne-Romanee EUR 6500
        NV Krug Grande Cuvee Champagne EUR 450
        2019 Domaine Leflaive Puligny-Montrachet EUR 1200
        2018 Domaine Leroy Musigny Grand Cru EUR 8000
        2017 Chateau Margaux Pauillac EUR 1900
        2015 Domaine Armand Rousseau Gevrey-Chambertin EUR 2500
        """
        lines = self.parsed_lines(text)
        confidence, reason, needs_review = guide.source_confidence(
            "https://example.com/wine-list.pdf",
            "pdf",
            text,
            lines,
            100,
        )
        self.assertGreaterEqual(len(set(lines)), 5)
        self.assertEqual(reason, "")
        self.assertFalse(needs_review)
        self.assertGreaterEqual(confidence, 120)

    def test_short_candidate_is_review_not_found(self):
        text = """
        NV Krug Grande Cuvee Champagne EUR 450
        2019 Domaine Leflaive Puligny-Montrachet EUR 1200
        """
        lines = self.parsed_lines(text)
        _confidence, reason, needs_review = guide.source_confidence(
            "https://example.com/wine-list.pdf",
            "pdf",
            text,
            lines,
            100,
        )
        self.assertIn("Fewer than five", reason)
        self.assertTrue(needs_review)

    def test_rejected_event_page_is_not_saved_as_review(self):
        html = """
        <html><body>
        <h1>Champagne dinner event</h1>
        <p>Seven course menu with Krug pairing EUR 1200 per person</p>
        </body></html>
        """
        with mock.patch.object(guide, "fetch_text", return_value=(html, "text/html")), mock.patch.object(
            guide, "save_wine_source"
        ) as save_source:
            result = guide.scan_wine_source(
                None,
                {"id": 1},
                "https://example.com/events/champagne-dinner",
                [],
                100,
            )
        self.assertEqual(result[0], 0)
        self.assertFalse(result[3])
        save_source.assert_not_called()


if __name__ == "__main__":
    unittest.main()
