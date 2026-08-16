import unittest

from api import search


class SearchVenueNameTests(unittest.TestCase):
    def test_review_cross_is_not_part_of_venue_name(self):
        self.assertEqual(search.clean_venue_name("❌Restaurant Kozee"), "Restaurant Kozee")
        self.assertEqual(search.clean_venue_name("  × Restaurant Cataleya"), "Restaurant Cataleya")

    def test_ordinary_name_is_unchanged(self):
        self.assertEqual(search.clean_venue_name("L’Effervescence"), "L’Effervescence")


if __name__ == "__main__":
    unittest.main()
