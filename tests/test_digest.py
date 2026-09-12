"""The Sunday-evening digest: grouped rendering, the !digest command, and the unprompted weekly post."""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from mate import db
from mate.config import TZ
from mate.features import digest
from tests.fakes import FakeBot, FakeChannel, fresh_db, run, world


def _in(days, hour):
    """ISO local string `days` from now at `hour`:00 — inside the digest's 7-day window."""
    return (datetime.now(TZ) + timedelta(days=days)).strftime(f"%Y-%m-%dT{hour:02d}:00")


def _next(weekday, hour=18, minute=5):
    """The next occurrence of `weekday` (0=Mon) at that time, so the 14-day message window still covers now."""
    base = datetime.now(TZ)
    return (base + timedelta(days=(weekday - base.weekday()) % 7)).replace(
        hour=hour, minute=minute, second=0, microsecond=0)


class DigestTests(unittest.TestCase):
    def setUp(self):
        fresh_db()
        self.guild, self.channel, self.sir, self.ali = world()
        self.bot = FakeBot(self.guild)
        self.bot.channels = {self.channel.id: self.channel}
        self._real_now = digest._now

    def tearDown(self):
        digest._now = self._real_now

    def event(self, key, title, kind, due_at, chat_id=None):
        ev = SimpleNamespace(key=key, title=title, kind=kind, due_at=due_at, details="", confidence=0.9)
        db.upsert_event(ev, self.guild.id, chat_id or self.channel.id, 1)

    def two_events_one_day(self):
        self.event("quiz-3", "Quiz 3", "quiz", _in(2, 9))
        self.event("a1", "Assignment 1", "deadline", _in(2, 23))

    def chatter(self, channel, n):
        for i in range(n):
            db.add_message(self.guild.id, channel.id, next(_msg_ids), "Ali", f"msg {i}", db.now_local())

    def test_render_groups_a_day_and_is_none_when_empty(self):
        self.assertIsNone(digest.render(self.guild.id))
        self.two_events_one_day()
        text = digest.render(self.guild.id)
        lines = text.split("\n")
        self.assertEqual(lines[0], "📅 This week")
        self.assertEqual(len([l for l in lines if l.startswith("**")]), 1)        # one header for both
        self.assertIn("❓ Quiz 3 — 09:00", text)
        self.assertIn("📝 Assignment 1 — 23:00", text)
        self.assertIsNone(digest.render(999))                                     # other server, nothing

    def test_digest_command_sends_the_rendered_text(self):
        self.two_events_one_day()
        digest.setup(self.bot)
        ctx = SimpleNamespace(guild=self.guild, channel=self.channel, send=self.channel.send)
        run(self.bot.commands["digest"](ctx))
        self.assertEqual(len(self.channel.sent), 1)
        self.assertEqual(self.channel.sent[0].content, digest.render(self.guild.id))

    def test_command_says_so_when_the_week_is_empty(self):
        digest.setup(self.bot)
        ctx = SimpleNamespace(guild=self.guild, channel=self.channel, send=self.channel.send)
        run(self.bot.commands["digest"](ctx))
        self.assertEqual(self.channel.sent[0].content, "Nothing on for this week.")

    def test_sunday_evening_posts_once_to_the_busiest_channel(self):
        self.two_events_one_day()
        quiet = FakeChannel(cid=11, guild=self.guild, name="offtopic")
        self.bot.channels[quiet.id] = quiet
        self.chatter(self.channel, 3)
        self.chatter(quiet, 1)
        digest._now = lambda: _next(6)
        self.assertEqual(run(digest.weekly(self.bot)), 1)
        self.assertEqual(len(self.channel.sent), 1)
        self.assertEqual(quiet.sent, [])
        self.assertTrue(self.channel.sent[0].content.startswith("📅 This week"))
        self.assertEqual(run(digest.weekly(self.bot)), 0)                         # once per ISO week
        self.assertEqual(len(self.channel.sent), 1)

    def test_midweek_says_nothing(self):
        self.two_events_one_day()
        self.chatter(self.channel, 3)
        digest._now = lambda: _next(2)
        self.assertEqual(run(digest.weekly(self.bot)), 0)
        self.assertEqual(self.channel.sent, [])


_msg_ids = iter(range(90000, 99000))


if __name__ == "__main__":
    unittest.main()
