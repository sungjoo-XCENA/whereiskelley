import unittest

from country_codes import country_display_name, country_values_match, normalize_country_code


class CountryCodeTests(unittest.TestCase):
    def test_country_names_and_codes_normalize_to_iso_alpha_2(self):
        self.assertEqual(normalize_country_code("Hong Kong"), "HK")
        self.assertEqual(normalize_country_code("HK"), "HK")
        self.assertEqual(normalize_country_code("United States"), "US")
        self.assertEqual(normalize_country_code("UK"), "GB")
        self.assertEqual(normalize_country_code("대한민국"), "KR")
        self.assertEqual(normalize_country_code("일본"), "JP")

    def test_greater_china_uses_location_hints(self):
        self.assertEqual(normalize_country_code("Greater China", city="Hong Kong"), "HK")
        self.assertEqual(normalize_country_code("Greater China", city="Macau"), "MO")
        self.assertEqual(normalize_country_code("Greater China", city="Taipei"), "TW")
        self.assertEqual(normalize_country_code("Greater China", city="Shanghai"), "CN")

    def test_storage_codes_have_human_readable_display_names(self):
        self.assertEqual(country_display_name("HK"), "Hong Kong")
        self.assertEqual(country_display_name("TW"), "Taiwan")
        self.assertEqual(country_display_name("CN"), "China")

    def test_matching_compares_normalized_codes(self):
        self.assertTrue(country_values_match("HK", "Hong Kong"))
        self.assertTrue(country_values_match("일본", "Japan"))
        self.assertFalse(country_values_match("HK", "China"))


if __name__ == "__main__":
    unittest.main()
