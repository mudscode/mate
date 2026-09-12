"""Hits the real OpenAI API. Skipped unless RUN_LIVE=1. Run: RUN_LIVE=1 python -m unittest tests.test_live"""
import os
import unittest
from datetime import datetime

from mate import config  # noqa: F401  (loads .env before we look at the key)
from tests.fakes import fresh_db, run

LIVE = os.getenv("RUN_LIVE") == "1" and os.getenv("OPENAI_API_KEY", "").startswith("sk-")


@unittest.skipUnless(LIVE, "set RUN_LIVE=1 to call the model")
class LiveTests(unittest.TestCase):
    def test_extract_resolves_weekday_deterministically(self):
        from mate import extract
        evs = run(extract.extract("Quiz 3 will be on Monday 10am, chapters 5 and 6.", "Sir", datetime.now(extract.TZ), True))
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0].key, "quiz-3")
        self.assertEqual(datetime.fromisoformat(evs[0].due_at).weekday(), 0)

    def test_noise_yields_nothing(self):
        from mate import extract
        self.assertEqual(run(extract.extract("anyone got the slides from today", "Ali", datetime.now(extract.TZ))), [])

    def test_qa_uses_memory(self):
        from mate import db, qa
        fresh_db()
        from types import SimpleNamespace as E
        db.upsert_event(E(key="quiz-2", title="Quiz 2", kind="quiz", due_at="2099-01-05T10:00", details="Ch 3-4", confidence=0.9), 7, 1, 1)
        db.add_note(7, 1, "Ali", "The TA's email is ta@uni.edu")
        self.assertIn("ta@uni.edu", run(qa.answer("what is the TA's email?", "Sara", 7, 1, 2)))


if __name__ == "__main__":
    unittest.main()
