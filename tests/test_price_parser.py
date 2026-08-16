import unittest

from scripts.sync_search_api import parse_price_v2


class PriceParserTests(unittest.TestCase):
    def test_currency_code_is_not_detected_inside_wine_name(self):
        raw, value, currency = parse_price_v2(
            'P I N O T, N O I R, 2022, Domaine Bizot Marsannay "Clos du Roy", $1875',
            "USA",
        )
        self.assertEqual(raw, "1875")
        self.assertEqual(value, 1875)
        self.assertEqual(currency, "USD")

    def test_hong_kong_price_keeps_comma_separated_thousands_with_space(self):
        raw, value, currency = parse_price_v2(
            "William Kelley, Foucheres, 2018, HK$12, 888",
            "Greater China",
        )
        self.assertEqual(raw, "12888")
        self.assertEqual(value, 12888)
        self.assertEqual(currency, "HKD")

    def test_percentage_is_not_merged_into_price(self):
        raw, value, currency = parse_price_v2(
            "Moulin a Vent, 2021, William Kelley, 300, 100%Gamay",
            "Italy",
        )
        self.assertEqual(raw, "300")
        self.assertEqual(value, 300)
        self.assertEqual(currency, "EUR")


if __name__ == "__main__":
    unittest.main()
