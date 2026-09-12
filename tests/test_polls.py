"""RSVP polls on plans: offline, with fake Discord objects and a stubbed extractor."""
import unittest
from datetime import datetime, timedelta

from mate import db, extract, handlers, hooks
from mate.config import TZ
from mate.features import polls
from tests.fakes import FakeMessage, fake_extract, fresh_db, run, world


def local(delta: timedelta) -> str:
    return (datetime.now(TZ) + delta).strftime("%Y-%m-%dT%H:%M")


def plan(due_at, key="murree-trip", title="Murree road trip"):
    return dict(key=key, title=title, kind="plan", due_at=due_at,
                details="Leaving from the main gate", confidence=0.8)


QUIZ = dict(key="quiz-2", title="Quiz 2", kind="quiz", due_at=local(timedelta(days=5)),
            details="Ch. 3-4", confidence=0.95)   # a different day: a clash would make Mate speak up on its own


class PollTests(unittest.TestCase):
    def setUp(self):
        fresh_db()
        self.guild, self.channel, self.sir, self.ali = world()
        self._real = extract.extract
        if polls.on_plan not in hooks.EVENT_LOGGED:          # test_ingest clears the registry in its setUp
            hooks.on_event_logged(polls.on_plan)

    def tearDown(self):
        extract.extract = self._real

    def stub(self, mapping):
        extract.extract = fake_extract(mapping)

    def ingest(self, text, author=None):
        m = FakeMessage(text, author or self.ali, self.channel)
        run(handlers.ingest(m))
        return m

    def polls_rows(self):
        with db.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM polls")]

    def test_new_plan_gets_one_poll(self):
        self.stub({"road trip": [plan(local(timedelta(days=2)))]})
        self.ingest("road trip to Murree the day after tomorrow, leaving early")
        self.assertEqual(len(self.channel.sent), 1)
        posted = self.channel.sent[0]
        self.assertIsNotNone(posted.poll)
        self.assertIn("Murree road trip", posted.poll.question)
        self.assertIn("In?", posted.poll.question)
        self.assertEqual([a.text for a in posted.poll.answers], ["I'm in 🙌", "Can't make it 😔"])

        rows = self.polls_rows()
        self.assertEqual(len(rows), 1)
        ev = db.list_events(60, self.guild.id)[0]
        self.assertEqual(rows[0]["event_id"], ev["id"])
        self.assertEqual(rows[0]["guild_id"], self.guild.id)
        self.assertEqual(rows[0]["chat_id"], self.channel.id)
        self.assertEqual(rows[0]["poll_message_id"], posted.id)

    def test_updated_plan_and_non_plan_post_no_poll(self):
        self.stub({"road trip": [plan(local(timedelta(days=2)))]})
        self.ingest("road trip to Murree on the weekend, leaving early")
        self.assertEqual(len(self.channel.sent), 1)

        self.stub({"road trip": [plan(local(timedelta(days=2, hours=1)))]})   # same key -> 'updated'
        self.ingest("road trip to Murree pushed an hour later, sorry")
        self.assertEqual(len(self.channel.sent), 1)                          # still just the first poll

        self.stub({"Quiz 2": [QUIZ]})
        self.ingest("Quiz 2 is on Friday next week, chapters 3 and 4", self.sir)
        self.assertEqual(len(self.channel.sent), 1)
        self.assertEqual([m.poll for m in self.channel.sent[1:]], [])
        self.assertEqual(len(self.polls_rows()), 1)

    def test_duration_is_clamped_to_discord_window(self):
        self.stub({"trip": [plan(local(timedelta(days=30)), key="far-trip", title="Northern areas trip")]})
        self.ingest("big trip up north next month, roughly 30 days out from now")
        self.assertEqual(self.channel.sent[0].poll.duration, timedelta(hours=168))

        self.stub({"study": [plan(local(timedelta(minutes=10)), key="soon-study", title="Library study session")]})
        self.ingest("study session in the library starting in ten minutes, come over")
        self.assertEqual(self.channel.sent[1].poll.duration, timedelta(hours=1))


if __name__ == "__main__":
    unittest.main()
