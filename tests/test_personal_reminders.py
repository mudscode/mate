"""Personal DM reminders: the tool that sets one, and the tick that delivers it. No network, no Discord."""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from mate import db
from mate.config import TZ
from mate.features import personal_reminders as pr
from tests.fakes import FakeBot, fresh_db, run, world


def in_hours(h: float) -> str:
    return (datetime.now(TZ) + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M")


class PersonalReminderTests(unittest.TestCase):
    def setUp(self):
        fresh_db()
        self.guild, self.channel, self.sir, self.ali = world()
        self.bot = FakeBot(self.guild)
        self.bot.users = {self.ali.id: self.ali}
        self.bot.channels = {self.channel.id: self.channel}
        pr.setup(self.bot)
        self.ctx = {"asker": self.ali.display_name, "asker_id": self.ali.id,
                    "guild_id": self.guild.id, "chat_id": self.channel.id}

    def add_event(self, key, title, due_at, kind="deadline"):
        ev = SimpleNamespace(key=key, title=title, kind=kind, due_at=due_at, details="", confidence=0.9)
        return db.upsert_event(ev, self.guild.id, self.channel.id, 1)[1]

    def rows(self):
        with db.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM personal_reminders")]

    def test_remind_me_stores_a_row(self):
        self.add_event("assignment-1", "Assignment 1", in_hours(1))
        out = pr.remind_me(self.ctx, what="assignment 1", hours_before=2)
        self.assertTrue(out["ok"])
        self.assertEqual(out["title"], "Assignment 1")
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["user_id"], self.ali.id)
        self.assertEqual(rows[0]["hours_before"], 2)
        self.assertIsNone(rows[0]["sent_at"])

    def test_tick_dms_once(self):
        self.add_event("assignment-1", "Assignment 1", in_hours(1))
        pr.remind_me(self.ctx, what="assignment 1", hours_before=2)     # fire time already passed
        self.assertEqual(run(pr.run(self.bot)), 1)
        self.assertEqual(len(self.ali.dms), 1)
        self.assertIn("Assignment 1", self.ali.dms[0])
        self.assertEqual(run(pr.run(self.bot)), 0)                      # marked sent, never repeats
        self.assertEqual(len(self.ali.dms), 1)

    def test_not_due_yet_stays_quiet(self):
        self.add_event("assignment-1", "Assignment 1", in_hours(5))
        pr.remind_me(self.ctx, what="assignment 1", hours_before=2)
        self.assertEqual(run(pr.run(self.bot)), 0)
        self.assertEqual(self.ali.dms, [])

    def test_no_match_is_an_error_and_stores_nothing(self):
        self.add_event("assignment-1", "Assignment 1", in_hours(1))
        out = pr.remind_me(self.ctx, what="quantum midterm", hours_before=2)
        self.assertIn("no matching event", out["error"])
        self.assertEqual(self.rows(), [])

    def test_my_reminders_lists_pending(self):
        due = in_hours(30)
        self.add_event("assignment-1", "Assignment 1", due)
        pr.remind_me(self.ctx, what="Assignment 1", hours_before=2)
        mine = pr.my_reminders(self.ctx)
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0], {"title": "Assignment 1", "due_at": due, "hours_before": 2})

    def test_anonymous_asker_and_silly_leads_are_rejected(self):
        self.add_event("assignment-1", "Assignment 1", in_hours(5))
        self.assertIn("error", pr.remind_me(dict(self.ctx, asker_id=None), what="assignment 1", hours_before=2))
        self.assertIn("error", pr.remind_me(self.ctx, what="assignment 1", hours_before=0))
        self.assertIn("error", pr.remind_me(self.ctx, what="assignment 1", hours_before=800))
        self.assertEqual(self.rows(), [])


if __name__ == "__main__":
    unittest.main()
