import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import nonprofit_grants as ng  # noqa: E402


def rec(**kw):
    base = {"id": "a", "name": "X", "url": "https://us.fundsforngos.org/type-of-grantgrant/x/", "source": "fundsforngos-us",
            "deadline": None, "status": "unknown", "relevant": True, "state": "", "tags": [], "summary": "", "funder": "",
            "amount_text": "", "verified": False}
    base.update(kw)
    return base


class T(unittest.TestCase):
    def setUp(self):
        ng.today = lambda: dt.date(2026, 11, 24)

    def test_dates_and_status(self):
        self.assertEqual(ng.parse_date("10/31/2026"), dt.date(2026, 10, 31))
        self.assertEqual(ng.status_for("2026-11-23"), "closed")
        self.assertEqual(ng.status_for("2026-11-24"), "open")
        self.assertEqual(ng.status_for(None), "unknown")

    def test_sections(self):
        self.assertEqual(ng.section(rec()), "us")
        self.assertEqual(ng.section(rec(url="https://www.fundsforngos.org/all-proposals/sample/", source="fundsforngos")), "skip")
        self.assertEqual(ng.section(rec(url="https://www.fundsforngos.org/how-to-apply/x/", source="fundsforngos")), "international")
        self.assertEqual(ng.section(rec(source="ictworks", url="https://ictworks.org/a", name="Apply Now: $5K for AI")), "lead")
        self.assertEqual(ng.section(rec(source="ictworks", url="https://ictworks.org/b", name="An essay about AI")), "skip")

    def test_hai_relevance_respects_state_and_closed(self):
        self.assertTrue(ng.hai_relevant(rec(status="open")))
        self.assertFalse(ng.hai_relevant(rec(status="closed")))
        self.assertFalse(ng.hai_relevant(rec(status="open", state="Delaware")))
        self.assertTrue(ng.hai_relevant(rec(status="open", state="Massachusetts")))

    def test_summaries_are_not_stored(self):
        store = ng.merge({}, [rec(summary="copied text from another site")])
        self.assertEqual(store["a"]["summary"], "")

    def test_table_escapes_pipes_and_brackets(self):
        out = ng.table([rec(name="A | B [x]", funder="F|G")], ["name", "funder"])
        self.assertIn("A / B (x)", out)
        self.assertNotIn("F|G", out)


if __name__ == "__main__":
    unittest.main()
