import unittest

from mate.handlers import looks_like_question


class RoutingTests(unittest.TestCase):
    def test_questions_go_to_qa(self):
        for q in ["when is the quiz?", "what's due this week?", "who is the TA?", "what did I miss?",
                  "what's comming", "when is the quiz", "is the lab tomorrow"]:
            self.assertTrue(looks_like_question(q), q)

    def test_plans_and_chatter_get_logged(self):
        for t in ["@everyone anyone up for a day road trip on Sunday? leaving 7am", "anyone got the slides?",
                  "what a day lol", "Quiz 3 will be on Monday 10am", "lol did anyone understand the semaphore example"]:
            self.assertFalse(looks_like_question(t), t)


if __name__ == "__main__":
    unittest.main()


class UrduDateCheckTests(unittest.TestCase):
    """Python validates the model's date against Roman Urdu day words too."""
    def _ev(self, due):
        from mate.extract import Event
        return Event(key="quiz-3", title="Quiz 3", kind="quiz", due_at=due, details="", confidence=0.9)

    def test_kal_and_jumma(self):
        from datetime import datetime
        from mate.extract import TZ, _plausible
        sat = datetime(2026, 9, 12, 12, 0, tzinfo=TZ)
        self.assertTrue(_plausible(self._ev("2026-09-13T10:00"), sat, "kal quiz hai 10 baje"))
        self.assertFalse(_plausible(self._ev("2026-09-14T10:00"), sat, "kal quiz hai 10 baje"))
        self.assertTrue(_plausible(self._ev("2026-09-14T10:00"), sat, "parso quiz hai 10 baje"))
        self.assertTrue(_plausible(self._ev("2026-09-18T23:59"), sat, "assignment jumma tak submit karni hai"))
        self.assertFalse(_plausible(self._ev("2026-09-17T23:59"), sat, "assignment jumma tak submit karni hai"))

    def test_midnight_deadline_belongs_to_the_named_day(self):
        from datetime import datetime
        from mate.extract import TZ, _plausible
        sat = datetime(2026, 9, 12, 12, 0, tzinfo=TZ)
        e = self._ev("2026-09-19T00:00"); e.kind = "deadline"
        self.assertTrue(_plausible(e, sat, "assignment jumma raat 12 baje tak"))
        self.assertEqual(e.due_at, "2026-09-18T23:59")
        past = self._ev("2026-09-12T00:00"); past.kind = "deadline"
        self.assertFalse(_plausible(past, sat, "assignment jumma raat 12 baje tak"))

    def test_announcement_dated_now_is_not_an_event(self):
        from datetime import datetime
        from mate.extract import TZ, _plausible
        now = datetime(2026, 9, 12, 15, 42, tzinfo=TZ)
        e = self._ev("2026-09-12T15:42"); e.kind = "announcement"
        self.assertFalse(_plausible(e, now, "Slides for lecture 4 are on LMS now."))
        e2 = self._ev("2026-09-14T10:00"); e2.kind = "announcement"
        self.assertTrue(_plausible(e2, now, "Guest lecture on Monday 10am"))
