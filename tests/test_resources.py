"""Resource indexing: every file and link dropped in chat becomes a row with a jump link back to it."""
import unittest

from mate import extract, handlers, hooks
from mate.features import resources
from tests.fakes import FakeAttachment, FakeMessage, fake_extract, fresh_db, run, world

SLIDES = "lecture4_slides.pdf"


class ResourceTests(unittest.TestCase):
    def setUp(self):
        fresh_db()
        self.guild, self.channel, self.sir, self.ali = world()
        self._real = extract.extract
        extract.extract = fake_extract({})                    # no network
        if resources.index not in hooks.MESSAGE_INGESTED:     # other tests clear the registry
            hooks.on_message_ingested(resources.index)
        resources.setup(None)

    def tearDown(self):
        extract.extract = self._real

    def post(self, text, attachments=(), author=None, channel=None):
        m = FakeMessage(text, author or self.sir, channel or self.channel, attachments=attachments)
        run(handlers.ingest(m))
        return m

    def ctx(self, guild_id=None):
        return {"guild_id": self.guild.id if guild_id is None else guild_id}

    def test_file_and_link_are_indexed_with_jump_url(self):
        m = self.post("Slides for lecture 4, also see https://example.com/reading",
                      attachments=[FakeAttachment(b"%PDF-1.4", "application/pdf", SLIDES)])
        rows = resources.find_resources(self.ctx(), "")
        self.assertEqual(len(rows), 2)
        by_kind = {r["kind"]: r for r in rows}
        self.assertEqual(by_kind["file"]["title"], SLIDES)
        self.assertEqual(by_kind["link"]["title"], "https://example.com/reading")
        for r in rows:
            self.assertEqual(r["jump_url"], m.jump_url)
            self.assertEqual(r["sender"], "Sir")
            self.assertTrue(r["context"].startswith("Slides for lecture 4"))

    def test_find_resources_matches_and_is_scoped_to_the_guild(self):
        m = self.post("here you go", attachments=[FakeAttachment(b"%PDF-1.4", "application/pdf", SLIDES)])
        rows = resources.find_resources(self.ctx(), "slides")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], SLIDES)
        self.assertEqual(rows[0]["jump_url"], m.jump_url)
        self.assertEqual(resources.find_resources(self.ctx(guild_id=999), "slides"), [])

    def test_reingesting_the_same_message_does_not_duplicate(self):
        m = FakeMessage("notes plus https://example.com/reading", self.sir, self.channel,
                        attachments=[FakeAttachment(b"%PDF-1.4", "application/pdf", SLIDES)])
        run(handlers.ingest(m))
        run(handlers.ingest(m))                               # !backfill over the same history
        self.assertEqual(len(resources.find_resources(self.ctx(), "")), 2)

    def test_cdn_link_to_own_attachment_is_dropped(self):
        att = FakeAttachment(b"%PDF-1.4", "application/pdf", SLIDES)
        att.url = f"https://cdn.discordapp.com/attachments/1/2/{SLIDES}"
        self.post(f"slides: {att.url}", attachments=[att])
        rows = resources.find_resources(self.ctx(), "")
        self.assertEqual([r["kind"] for r in rows], ["file"])


if __name__ == "__main__":
    unittest.main()
