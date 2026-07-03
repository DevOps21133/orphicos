"""Tests for the permissive fuzzywuzzy replacement in client/_engine.py.

windows-use's Desktop resolves window names via fuzzywuzzy.process.extractOne
(score_cutoff=70). Our difflib-based stub must keep that call working — these
tests exercise the stub exactly as service.py calls it.
"""
import sys
import unittest

import client._engine  # noqa: F401 — registers the stub in sys.modules

from fuzzywuzzy import process  # resolves to the stub


class FuzzStubTests(unittest.TestCase):
    def test_stub_is_ours_not_gpl_fuzzywuzzy(self):
        self.assertIn("OrphicOS wall stub", sys.modules["fuzzywuzzy.process"].__doc__)

    def test_app_name_matches_decorated_window_title(self):
        # The common real case: matching "notepad" against full window titles.
        titles = ["readme.txt - Notepad", "Inbox - Outlook", "Calculator"]
        matched = process.extractOne("notepad", titles, score_cutoff=70)
        self.assertIsNotNone(matched)
        self.assertEqual(matched[0], "readme.txt - Notepad")

    def test_exact_title_matches_itself(self):
        matched = process.extractOne("Calculator", ["Calculator", "Notepad"], score_cutoff=70)
        self.assertEqual(matched[0], "Calculator")

    def test_no_plausible_window_returns_none(self):
        matched = process.extractOne("spotify", ["readme.txt - Notepad", "Calculator"],
                                     score_cutoff=70)
        self.assertIsNone(matched)

    def test_result_shape_is_choice_and_int_score(self):
        choice, score = process.extractOne("calc", ["Calculator"], score_cutoff=0)
        self.assertEqual(choice, "Calculator")
        self.assertIsInstance(score, int)


if __name__ == "__main__":
    unittest.main()
