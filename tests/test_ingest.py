"""Drives handlers.ingest end to end with fake Discord objects and a stubbed extractor (no network)."""
import unittest
from datetime import datetime, timedelta

from mate import db, extract, handlers, hooks
from tests.fakes import FakeAttachment, FakeMessage, fake_extract, fresh_db, run, world

NEXT_WEEK = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%dT10:00")
QUIZ = dict(key="quiz-2", title="Quiz 2", kind="quiz", due_at=NEXT_WEEK, details="Ch. 3-4, Room 104", confidence=0.95)
TRIP = dict(key="murree-trip", title="Murree road trip", kind="plan", due_at=NEXT_WEEK[:10] + "T07:00",
            details="Leaving 7am from the main gate", confidence=0.7)


class IngestTests(unittest.TestCase):
    def setUp(self):
        fresh_db()
        self.guild, self.channel, self.sir, self.ali = world()
        self._real = extract.extract
        extract.extract = fake_extract({"Quiz 2": [QUIZ], "road trip": [TRIP]})
        hooks.EVENT_LOGGED.clear(); hooks.MESSAGE_INGESTED.clear()

    def tearDown(self):
        extract.extract = self._real

    def test_logged_message_gets_tick_and_discord_event(self):
        m = FakeMessage("Quiz 2 will be on Wednesday 10am, chapters 3 and 4", self.sir, self.channel)
        self.assertEqual(run(handlers.ingest(m)), 1)
        self.assertEqual(m.reactions_added, ["✅"])
        ev = db.list_events(30, self.guild.id)[0]
        self.assertEqual(ev["title"], "Quiz 2")
        se = list(self.guild.scheduled_events.values())
        self.assertEqual(len(se), 1)
        self.assertEqual(se[0].location, "Room 104")
        self.assertEqual(db.get_event(ev["id"])["discord_event_id"], se[0].id)

    def test_short_or_noise_messages_are_silent(self):
        m = FakeMessage("lol ok", self.ali, self.channel)
        self.assertEqual(run(handlers.ingest(m)), 0)
        self.assertEqual(m.reactions_added, [])
        self.assertEqual(db.search_messages("lol", self.guild.id)[0]["sender"], "Ali")   # still stored

    def test_heads_up_on_same_day_clash_across_channels(self):
        run(handlers.ingest(FakeMessage("Quiz 2 will be on Wednesday 10am", self.sir, self.channel)))
        other = type(self.channel)(cid=11, guild=self.guild, name="offtopic")
        m = FakeMessage("@everyone road trip to Murree on Wednesday? leaving 7am", self.ali, other)
        run(handlers.ingest(m))
        self.assertEqual(m.reactions_added, ["✅"])
        self.assertEqual(len(other.sent), 1)
        self.assertIn("Heads up", other.sent[0].content)
        self.assertIn("Quiz 2", other.sent[0].content)

    def test_backfill_mode_does_not_react_or_speak(self):
        run(handlers.ingest(FakeMessage("Quiz 2 will be on Wednesday 10am", self.sir, self.channel)))
        m = FakeMessage("road trip Wednesday 7am", self.ali, self.channel)
        run(handlers.ingest(m, react=False))
        self.assertEqual(m.reactions_added, [])
        self.assertEqual(self.channel.sent, [])

    def test_reschedule_edits_existing_discord_event(self):
        run(handlers.ingest(FakeMessage("Quiz 2 will be on Wednesday 10am", self.sir, self.channel)))
        moved = dict(QUIZ, title="Quiz 2 moved", due_at=(datetime.now() + timedelta(days=8)).strftime("%Y-%m-%dT09:00"))
        extract.extract = fake_extract({"Quiz 2": [moved]})
        run(handlers.ingest(FakeMessage("Quiz 2 moved to Thursday 9am", self.sir, self.channel)))
        self.assertEqual(len(self.guild.scheduled_events), 1)
        self.assertEqual(list(self.guild.scheduled_events.values())[0].edits, 1)

    def test_hooks_fire_with_status(self):
        seen = []
        hooks.on_event_logged(lambda msg, ev, status: _rec(seen, ev["key"], status))
        run(handlers.ingest(FakeMessage("Quiz 2 will be on Wednesday 10am", self.sir, self.channel)))
        run(handlers.ingest(FakeMessage("Quiz 2 will be on Wednesday 10am again", self.sir, self.channel)))
        self.assertEqual(seen, [("quiz-2", "inserted"), ("quiz-2", "updated")])

    def test_attachment_is_passed_to_extractor(self):
        seen = {}
        async def spy(text, sender, sent_at, is_staff=False, attachments=(), effort="low"):
            seen.update(atts=list(attachments), effort=effort); return []
        extract.extract = spy
        m = FakeMessage("", self.sir, self.channel, attachments=[FakeAttachment(b"%PDF-1.4", "application/pdf")])
        run(handlers.ingest(m))
        self.assertEqual(seen["effort"], "medium")
        self.assertEqual(seen["atts"][0][1], "application/pdf")


async def _rec(seen, *x):
    seen.append(x)


if __name__ == "__main__":
    unittest.main()
