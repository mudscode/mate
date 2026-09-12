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
