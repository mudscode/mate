"""Just enough of discord.py to drive handlers, hooks and features without a Discord connection.
Every side effect is recorded on the fake so tests can assert on it."""
import asyncio
import itertools
import os
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import discord

_ids = itertools.count(1000)


def fresh_db():
    """Point mate.db at a throwaway file and init it. Call at the top of every test."""
    from mate import db
    db.DB = os.path.join(tempfile.mkdtemp(), "test.db")
    db.init()
    return db.DB


def run(coro):
    return asyncio.run(coro)


class FakeUser:
    def __init__(self, name="Ali", uid=None, bot=False, roles=(), guild=None):
        self.display_name = self.name = name
        self.id = uid or next(_ids)
        self.bot = bot
        self.roles = [SimpleNamespace(name=r) for r in roles]
        self.guild = guild
        self.mention = f"<@{self.id}>"
        self.dms = []                                   # (content) sent via user.send()

    async def send(self, content=None, **kw):
        self.dms.append(content)
        return FakeMessage(content or "", author=self, channel=None)


class FakeScheduledEvent:
    def __init__(self, guild, **fields):
        self.guild = guild
        self.id = next(_ids)
        self.creator_id = guild.me.id
        self.edits = 0
        self.__dict__.update(fields)

    async def edit(self, **fields):
        self.edits += 1
        self.__dict__.update(fields)
        return self

    async def delete(self):
        self.guild.scheduled_events.pop(self.id, None)


class FakeGuild:
    def __init__(self, gid=1, owner=None, name="test-guild"):
        self.id, self.name = gid, name
        self.me = FakeUser("mate", bot=True)
        self.owner_id = owner.id if owner else -1
        self.scheduled_events = {}
        self.members = {}

    async def create_scheduled_event(self, **fields):
        se = FakeScheduledEvent(self, **fields)
        self.scheduled_events[se.id] = se
        return se

    async def fetch_scheduled_event(self, sid):
        if sid not in self.scheduled_events:
            raise discord.NotFound(SimpleNamespace(status=404, reason="nf"), "Unknown event")
        return self.scheduled_events[sid]

    async def fetch_scheduled_events(self):
        return list(self.scheduled_events.values())

    def get_member(self, uid):
        return self.members.get(uid)


class FakeChannel:
    def __init__(self, cid=10, guild=None, name="general"):
        self.id, self.guild, self.name = cid, guild, name
        self.sent = []                                  # FakeMessage objects Mate posted here
        self.pinned = []

    async def send(self, content=None, **kw):
        m = FakeMessage(content or "", author=self.guild.me if self.guild else FakeUser("mate", bot=True),
                        channel=self, poll=kw.get("poll"), embed=kw.get("embed"), file=kw.get("file"))
        self.sent.append(m)
        return m

    @asynccontextmanager
    async def typing(self):
        yield

    async def history(self, limit=100, oldest_first=False):
        for m in (self.sent if oldest_first else reversed(self.sent))[:limit]:
            yield m


class FakeAttachment:
    def __init__(self, data: bytes, content_type: str, filename="file.bin"):
        self.data, self.content_type, self.filename = data, content_type, filename
        self.url = f"https://cdn.example/{filename}"
        self.size = len(data)

    async def read(self):
        return self.data


class FakeMessage:
    def __init__(self, content, author, channel, attachments=(), created_at=None, mentions=(), **extra):
        self.content, self.author, self.channel = content, author, channel
        self.guild = channel.guild if channel else None
        self.id = next(_ids)
        self.attachments = list(attachments)
        self.created_at = created_at or datetime.now(timezone.utc)
        self.mentions = list(mentions)
        self.reference = None
        self.reactions_added = []
        self.replies = []
        self.pinned = False
        self.jump_url = f"https://discord.com/channels/{self.guild.id if self.guild else 0}/{channel.id if channel else 0}/{self.id}"
        self.__dict__.update(extra)

    async def add_reaction(self, emoji):
        self.reactions_added.append(str(emoji))

    async def reply(self, content=None, **kw):
        m = FakeMessage(content or "", author=self.guild.me if self.guild else None, channel=self.channel)
        self.replies.append(m)
        return m

    async def pin(self):
        self.pinned = True
        if self.channel:
            self.channel.pinned.append(self)


class FakeBot:
    """Stands in for commands.Bot: records registered commands and loops, resolves channels/users."""
    def __init__(self, guild):
        self.guild = guild
        self.user = guild.me
        self.commands = {}
        self.channels = {}
        self.users = {}

    def command(self, *a, **kw):
        def deco(fn):
            self.commands[fn.__name__] = fn
            return fn
        return deco

    def get_channel(self, cid):
        return self.channels.get(cid)

    def get_user(self, uid):
        return self.users.get(uid)

    async def fetch_user(self, uid):
        return self.users[uid]

    def get_guild(self, gid):
        return self.guild if gid == self.guild.id else None

    @property
    def guilds(self):
        return [self.guild]


def world(owner_is_staff=True):
    """A guild with one channel, an owner (instructor) and a student. Returns (guild, channel, owner, student)."""
    owner = FakeUser("Sir")
    guild = FakeGuild(owner=owner if owner_is_staff else None)
    owner.guild = guild
    student = FakeUser("Ali", guild=guild)
    channel = FakeChannel(guild=guild)
    guild.members = {owner.id: owner, student.id: student}
    return guild, channel, owner, student


def fake_extract(events_by_text):
    """Return an async stand-in for extract.extract: text substring -> list[Event]."""
    from mate.extract import Event

    async def _extract(text, sender, sent_at, is_staff=False, attachments=(), effort="low"):
        for needle, evs in events_by_text.items():
            if needle in text:
                return [Event(**e) if isinstance(e, dict) else e for e in evs]
        return []
    return _extract
