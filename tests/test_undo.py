"""undo: ❌ on a message Mate logged from wipes what it logged. Offline — no Discord, no model calls."""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from mate import db, discord_events
from mate.config import TZ
from mate.features import polls
from mate.features import undo
from tests.fakes import FakeBot, FakeMessage, fresh_db, run, world


def in_days(days: float, hour=10) -> str:
    return (datetime.now(TZ) + timedelta(days=days)).strftime(f"%Y-%m-%dT{hour:02d}:00")


class UndoTests(unittest.TestCase):
    def setUp(self):
        fresh_db()
        self.guild, self.channel, self.sir, self.ali = world()
        self.bot = FakeBot(self.guild)
        self.bot.channels = {self.channel.id: self.channel}
        undo.setup(self.bot)
        self.msg = FakeMessage("Quiz 2 on Wednesday 10am", self.sir, self.channel)
        self.e1 = self.add_event("quiz-2", "Quiz 2", in_days(2))
        self.e2 = self.add_event("quiz-2-prep", "Quiz 2 revision session", in_days(1), kind="plan")
        self.deid = self.mirror(self.e1)
        self.msg.reactions_added.append("✅")            # Mate's own ack, the way handlers.ingest leaves it

    # helpers ------------------------------------------------------------
    def add_event(self, key, title, due_at, kind="quiz"):
        ev = SimpleNamespace(key=key, title=title, kind=kind, due_at=due_at, details="", confidence=0.9)
        return db.upsert_event(ev, self.guild.id, self.channel.id, self.msg.id)[1]

    def mirror(self, eid):
        deid = run(discord_events.sync(self.guild, db.get_event(eid)))
        db.set_discord_event_id(eid, deid)
        return deid

    def payload(self, user, emoji="❌", message=None, member=True):
        m = message or self.msg
        return SimpleNamespace(emoji=emoji, guild_id=self.guild.id, channel_id=self.channel.id,
                              message_id=m.id, user_id=user.id, member=user if member else None)

    def statuses(self):
        return sorted(db.get_event(e)["status"] for e in (self.e1, self.e2))

    # 0 ------------------------------------------------------------------
    def test_setup_registers_the_raw_reaction_listener(self):
        self.assertIn(undo.on_raw_reaction_add, self.bot.listeners["on_raw_reaction_add"])

    # 1 ------------------------------------------------------------------
    def test_author_reacting_x_forgets_everything_from_that_message(self):
        polls.setup(self.bot)                            # so the polls table exists to be cleaned
        with db.conn() as c:
            c.execute("INSERT INTO polls(event_id,guild_id,chat_id,poll_message_id,created_at) VALUES(?,?,?,?,?)",
                      (self.e1, self.guild.id, self.channel.id, 1, db.now_local()))
        self.assertEqual(len(self.guild.scheduled_events), 1)

        run(undo.on_raw_reaction_add(self.payload(self.sir)))

        self.assertEqual(self.statuses(), ["superseded", "superseded"])
        self.assertEqual(db.list_events(30, self.guild.id), [])
        self.assertEqual(self.guild.scheduled_events, {})
        self.assertIn("✅", self.msg.reactions_removed)
        self.assertNotIn("✅", self.msg.reactions_added)
        self.assertIn("🗑️", self.msg.reactions_added)
        self.assertEqual(self.channel.sent, [])          # nothing posted: silence is the feature
        with db.conn() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM polls").fetchone()[0], 0)

    def test_undo_works_on_a_fresh_db_without_the_feature_tables(self):
        run(undo.on_raw_reaction_add(self.payload(self.sir)))
        self.assertEqual(self.statuses(), ["superseded", "superseded"])

    def test_staff_can_undo_someone_elses_message(self):
        other = FakeMessage("Trip to Murree on Sunday 7am", self.ali, self.channel)
        eid = db.upsert_event(SimpleNamespace(key="trip-murree", title="Murree trip", kind="plan",
                                              due_at=in_days(3), details="", confidence=0.9),
                             self.guild.id, self.channel.id, other.id)[1]
        other.reactions_added.append("✅")

        run(undo.on_raw_reaction_add(self.payload(self.sir, message=other)))

        self.assertEqual(db.get_event(eid)["status"], "superseded")
        self.assertIn("🗑️", other.reactions_added)

    def test_member_none_falls_back_to_the_guild_member(self):
        run(undo.on_raw_reaction_add(self.payload(self.sir, member=False)))
        self.assertEqual(self.statuses(), ["superseded", "superseded"])

    # 2 ------------------------------------------------------------------
    def test_a_non_author_non_staff_student_cannot_undo(self):
        run(undo.on_raw_reaction_add(self.payload(self.ali)))

        self.assertEqual(self.statuses(), ["active", "active"])
        self.assertEqual(len(db.list_events(30, self.guild.id)), 2)
        self.assertEqual(len(self.guild.scheduled_events), 1)
        self.assertEqual(self.msg.reactions_removed, [])
        self.assertEqual(self.msg.reactions_added, ["✅"])

    # 3 ------------------------------------------------------------------
    def test_x_on_a_message_with_no_events_does_nothing(self):
        chat = FakeMessage("lol same", self.ali, self.channel)
        run(undo.on_raw_reaction_add(self.payload(self.ali, message=chat)))
        self.assertEqual(self.statuses(), ["active", "active"])
        self.assertEqual(chat.reactions_added, [])
        self.assertEqual(chat.reactions_removed, [])

    # 4 ------------------------------------------------------------------
    def test_a_different_emoji_is_ignored(self):
        run(undo.on_raw_reaction_add(self.payload(self.sir, emoji="✅")))
        self.assertEqual(self.statuses(), ["active", "active"])
        self.assertEqual(self.msg.reactions_added, ["✅"])
        self.assertEqual(len(self.guild.scheduled_events), 1)

    def test_a_dm_reaction_with_no_guild_is_ignored(self):
        p = self.payload(self.sir)
        p.guild_id = None
        run(undo.on_raw_reaction_add(p))
        self.assertEqual(self.statuses(), ["active", "active"])

    # 5 ------------------------------------------------------------------
    def test_mates_own_x_reaction_is_ignored(self):
        run(undo.on_raw_reaction_add(self.payload(self.bot.user)))
        self.assertEqual(self.statuses(), ["active", "active"])
        self.assertEqual(self.msg.reactions_added, ["✅"])

    # 6 ------------------------------------------------------------------
    def test_forget_message_is_callable_directly_and_counts_events(self):
        n = run(undo.forget_message(self.guild, self.msg.id))
        self.assertEqual(n, 2)
        self.assertEqual(self.statuses(), ["superseded", "superseded"])
        self.assertEqual(self.guild.scheduled_events, {})
        self.assertEqual(run(undo.forget_message(self.guild, self.msg.id)), 0)   # idempotent


if __name__ == "__main__":
    unittest.main()
