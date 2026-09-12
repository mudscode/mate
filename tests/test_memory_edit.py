"""memory_edit: correcting and forgetting one remembered event. Offline — no Discord, no model calls."""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from mate import db, discord_events
from mate.config import TZ
from mate.features import memory_edit as me
from mate.features import personal_reminders as pr
from tests.fakes import FakeBot, fresh_db, run, world


def in_days(days: float, hour=9) -> str:
    return (datetime.now(TZ) + timedelta(days=days)).strftime(f"%Y-%m-%dT{hour:02d}:00")


class MemoryEditTests(unittest.TestCase):
    def setUp(self):
        fresh_db()
        self.guild, self.channel, self.sir, self.ali = world()
        self.bot = FakeBot(self.guild)
        me.setup(self.bot)
        self.ctx = {"asker": self.ali.display_name, "asker_id": self.ali.id, "guild_id": self.guild.id,
                    "chat_id": self.channel.id, "guild": self.guild}

    def add_event(self, key, title, due_at, kind="quiz"):
        ev = SimpleNamespace(key=key, title=title, kind=kind, due_at=due_at, details="", confidence=0.9)
        return db.upsert_event(ev, self.guild.id, self.channel.id, 1)[1]

    def mirror(self, eid):
        """Create the native Discord event for this row, the way handlers.ingest does."""
        deid = run(discord_events.sync(self.guild, db.get_event(eid)))
        db.set_discord_event_id(eid, deid)
        return self.guild.scheduled_events[deid]

    def row(self, eid):
        return db.get_event(eid)

    def reminders(self, eid):
        with db.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM reminders WHERE event_id=?", (eid,))]

    # 1 ------------------------------------------------------------------
    def test_update_moves_the_date_keeps_the_title_and_resyncs(self):
        eid = self.add_event("quiz-3", "Quiz 3", in_days(2))
        se = self.mirror(eid)
        db.mark_reminder(eid, "24h")                      # already announced at the old time
        new = in_days(4, hour=9)

        out = run(me.update_event(self.ctx, what="quiz 3", new_due_at=new, new_title=""))

        self.assertTrue(out["ok"])
        self.assertEqual(out["title"], "Quiz 3")          # '' left the name alone
        self.assertEqual(out["due_at"], new)
        row = self.row(eid)
        self.assertEqual(row["due_at"], new)
        self.assertEqual(row["title"], "Quiz 3")
        self.assertEqual(row["status"], "active")
        self.assertEqual(self.reminders(eid), [])         # will be announced again at the new time
        self.assertEqual(se.edits, 1)
        self.assertEqual(se.start_time, datetime.fromisoformat(new).replace(tzinfo=TZ))
        self.assertEqual(len(self.guild.scheduled_events), 1)

    def test_update_can_rename_without_touching_the_date(self):
        due = in_days(2)
        eid = self.add_event("quiz-3", "Quiz", due)
        out = run(me.update_event(self.ctx, what="quiz", new_due_at="", new_title="Quiz 3"))
        self.assertTrue(out["ok"])
        self.assertEqual(self.row(eid)["title"], "Quiz 3")
        self.assertEqual(self.row(eid)["due_at"], due)

    # 2 ------------------------------------------------------------------
    def test_bad_dates_are_rejected_and_change_nothing(self):
        due = in_days(3)
        eid = self.add_event("quiz-3", "Quiz 3", due)
        bad = [(datetime.now(TZ) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),   # past
               "Friday 9am",                                                       # malformed
               in_days(730)]                                                       # two years out
        for value in bad:
            out = run(me.update_event(self.ctx, what="quiz 3", new_due_at=value, new_title="Renamed"))
            self.assertIn("error", out, value)
            self.assertEqual(self.row(eid)["due_at"], due, value)
            self.assertEqual(self.row(eid)["title"], "Quiz 3", value)

    def test_empty_update_is_rejected(self):
        self.add_event("quiz-3", "Quiz 3", in_days(3))
        self.assertIn("error", run(me.update_event(self.ctx, what="quiz 3", new_due_at="", new_title="")))

    # 3 ------------------------------------------------------------------
    def test_no_match_is_an_error(self):
        self.add_event("quiz-3", "Quiz 3", in_days(3))
        out = run(me.update_event(self.ctx, what="quantum midterm", new_due_at=in_days(4), new_title=""))
        self.assertIn("no matching event", out["error"])
        out = run(me.forget_event(self.ctx, what="quantum midterm"))
        self.assertIn("no matching event", out["error"])

    # 4 ------------------------------------------------------------------
    def test_forget_supersedes_the_row_and_deletes_the_discord_event(self):
        eid = self.add_event("trip-museum", "Museum trip", in_days(3), kind="plan")
        self.mirror(eid)
        pr.setup(self.bot)                                # the personal_reminders table exists here
        with db.conn() as c:
            c.execute("INSERT INTO personal_reminders(user_id,event_id,hours_before,created_at) VALUES(?,?,?,?)",
                      (self.ali.id, eid, 2, db.now_local()))

        out = run(me.forget_event(self.ctx, what="trip"))

        self.assertTrue(out["ok"])
        self.assertEqual(out["title"], "Museum trip")
        self.assertEqual(self.row(eid)["status"], "superseded")
        self.assertEqual(db.list_events(30, self.guild.id), [])
        self.assertEqual(self.guild.scheduled_events, {})
        with db.conn() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM personal_reminders").fetchone()[0], 0)

    # 5 ------------------------------------------------------------------
    def test_forget_without_a_guild_still_works(self):
        eid = self.add_event("trip-museum", "Museum trip", in_days(3), kind="plan")
        out = run(me.forget_event(dict(self.ctx, guild=None), what="museum"))
        self.assertTrue(out["ok"])
        self.assertEqual(self.row(eid)["status"], "superseded")
        self.assertEqual(db.list_events(30, self.guild.id), [])

    def test_update_without_a_guild_still_works(self):
        eid = self.add_event("quiz-3", "Quiz 3", in_days(2))
        new = in_days(5)
        out = run(me.update_event(dict(self.ctx, guild=None), what="quiz 3", new_due_at=new, new_title=""))
        self.assertTrue(out["ok"])
        self.assertEqual(self.row(eid)["due_at"], new)
        self.assertEqual(self.guild.scheduled_events, {})


if __name__ == "__main__":
    unittest.main()


class DayWordTests(unittest.TestCase):
    def test_update_rejects_a_date_on_the_wrong_weekday(self):
        from datetime import datetime, timedelta
        from types import SimpleNamespace
        from mate import db
        from mate.features import memory_edit
        from tests.fakes import fresh_db, run
        fresh_db()
        due = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%dT10:00")
        db.upsert_event(SimpleNamespace(key="quiz-9", title="Quiz 9", kind="quiz", due_at=due, details="", confidence=0.9), 1, 1, 1)
        target = datetime.now() + timedelta(days=5)
        wrong_day = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][(target.weekday() + 1) % 7]
        ctx = {"guild_id": 1, "guild": None, "question": f"quiz 9 is actually on {wrong_day} 11am"}
        out = run(memory_edit.update_event(ctx, "quiz 9", target.strftime("%Y-%m-%dT11:00"), ""))
        self.assertIn("error", out)
        self.assertEqual(db.get_event(1)["due_at"], due)
