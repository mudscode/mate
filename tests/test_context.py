"""Per-server context: the !context command (show / set / clear / truncate) and the group_context tool."""
import unittest
from types import SimpleNamespace

from mate import db
from mate.features import context
from tests.fakes import FakeBot, fresh_db, run, world


class ContextTests(unittest.TestCase):
    def setUp(self):
        fresh_db()
        self.guild, self.channel, self.sir, self.ali = world()
        self.bot = FakeBot(self.guild)
        context.setup(self.bot)
        self.ctx = SimpleNamespace(guild=self.guild, channel=self.channel, send=self.channel.send)

    def cmd(self, **kw):
        run(self.bot.commands["context"](self.ctx, **kw))
        return self.channel.sent[-1].content

    def test_setting_it_stores_it_and_confirms(self):
        line = "This is the CS-321 Operating Systems class; the instructor is Dr. Ahmed."
        reply = self.cmd(text=line)
        self.assertEqual(db.get_setting(self.guild.id, "context"), line)
        self.assertEqual(reply, f"Got it. I'll read this server as: {line}")

    def test_no_text_reports_the_stored_value_or_an_example(self):
        self.assertIn("No context set.", self.cmd(text=""))
        self.cmd(text="Single Threaded, a hackathon team.")
        self.assertIn("Single Threaded, a hackathon team.", self.cmd(text=""))

    def test_clear_empties_it(self):
        self.cmd(text="A football club.")
        reply = self.cmd(text="clear")
        self.assertEqual(db.get_setting(self.guild.id, "context"), "")
        self.assertIn("Cleared", reply)
        self.assertIn("No context set.", self.cmd(text=""))

    def test_long_text_is_truncated(self):
        self.cmd(text="x" * 500)
        self.assertEqual(db.get_setting(self.guild.id, "context"), "x" * 300)

    def test_tool_returns_the_stored_value_for_this_server(self):
        self.cmd(text="A study group for MATH-204.")
        self.assertEqual(context.group_context({"guild_id": self.guild.id}),
                         {"context": "A study group for MATH-204."})
        self.assertEqual(context.group_context({"guild_id": 999}), {"context": ""})

    def test_dm_says_context_is_per_server(self):
        dm = SimpleNamespace(guild=None, channel=self.channel, send=self.channel.send)
        run(self.bot.commands["context"](dm, text="anything"))
        self.assertIn("per server", self.channel.sent[-1].content)
        self.assertEqual(db.get_setting(None, "context"), "")


if __name__ == "__main__":
    unittest.main()
