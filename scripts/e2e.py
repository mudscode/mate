"""End-to-end test through real Discord, no hands. A second bot account ("tester") creates a scratch channel,
plays student and instructor, and checks that the running Mate reacts, answers, dedupes, polls, links,
reminds, and mirrors to the Events tab. Then it deletes everything it made (channel, DB rows, Discord events).

One-time setup: Developer Portal -> New Application "mate-tester" -> Bot -> Reset Token, and enable
Message Content Intent on that Bot page. Invite it with
View Channels, Send Messages, Read Message History, Attach Files, Manage Messages, Manage Channels,
Manage Events. Put MATE_TEST_BOT_TOKEN=<token> in .env. Restart bot.py once so it learns the tester's id.

Run (Mate must be running):  python scripts/e2e.py            # --keep to leave the channel for inspection
                                                              # --guild NAME if the tester is in several servers"""
import argparse
import asyncio
import io
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discord

from mate import config

MATE_ID = config.bot_id_from_token(os.environ["DISCORD_BOT_TOKEN"])
TAG = "42"                         # every title the run creates contains this, so cleanup can find it
CHANNEL = "mate-e2e"
TIMEOUT = 60

args = argparse.ArgumentParser()
args.add_argument("--keep", action="store_true", help="don't delete the channel / rows afterwards")
args.add_argument("--guild", help="server name if the tester is in more than one")
opts = args.parse_args()

results = []


def check(desc, ok, extra=""):
    results.append(ok)
    print(f"  {'ok  ' if ok else 'FAIL'} {desc}{'  ' + extra if extra else ''}")
    return ok


def weekday(days):
    return (datetime.now(config.TZ) + timedelta(days=days)).strftime("%A")


def sql(q, *a):
    with sqlite3.connect(config.DB_PATH) as c:
        return c.execute(q, a).fetchall()


async def poll_until(cond, timeout=TIMEOUT):
    for _ in range(timeout):
        r = await cond()
        if r:
            return r
        await asyncio.sleep(1)
    return None


class Run:
    def __init__(self, client, ch):
        self.c, self.ch = client, ch

    async def reacted(self, msg):
        return await poll_until(lambda: self._has_tick(msg))

    async def _has_tick(self, msg):
        m = await self.ch.fetch_message(msg.id)
        return any(str(r.emoji) == "✅" for r in m.reactions)

    async def from_mate(self, after, want=None, reply_to=None, poll=False, timeout=TIMEOUT):
        """First message Mate posted after `after` that matches; None on timeout."""
        async def find():
            async for m in self.ch.history(limit=20, after=after, oldest_first=True):
                if m.author.id != MATE_ID:
                    continue
                if reply_to and not (m.reference and m.reference.message_id == reply_to.id):
                    continue
                if poll and m.poll is None:
                    continue
                if want and want.lower() not in (m.content or "").lower():
                    continue
                return m
            return None
        return await poll_until(find, timeout)

    async def say(self, text, **kw):
        return await self.ch.send(text, **kw)

    async def ask(self, text):
        return await self.say(f"<@{MATE_ID}> {text}")

    async def scenarios(self):
        print("1. announcement -> ✅, DB row, Events tab")
        m = await self.say(f"Quiz {TAG} will be on {weekday(3)} 10am, chapters 1 and 2. Room 104.")
        check("✅ reaction", await self.reacted(m))
        rows = await poll_until(lambda: asyncio.sleep(0, result=sql("SELECT due_at, discord_event_id FROM events WHERE chat_id=? AND status='active' AND title LIKE ?", self.ch.id, f"%Quiz {TAG}%")))
        check("one event row", bool(rows) and len(rows) == 1)
        deid = rows[0][1] if rows else None
        ok = await poll_until(lambda: asyncio.sleep(0, result=sql("SELECT discord_event_id FROM events WHERE chat_id=? AND title LIKE ?", self.ch.id, f"%Quiz {TAG}%")[0][0]))
        evs = await self.ch.guild.fetch_scheduled_events()
        check("mirrored to Events tab", any(f"Quiz {TAG}" in e.name for e in evs))

        print("2. question -> answer from memory")
        q = await self.say(f"when is quiz {TAG}?")
        r = await self.from_mate(q, want=f"quiz {TAG}", reply_to=q)
        check("reply names the quiz", r is not None, (r.content[:90] if r else ""))

        print("3. reschedule -> same row, new date, Events entry moved, no duplicate")
        before = sql("SELECT due_at FROM events WHERE chat_id=? AND title LIKE ?", self.ch.id, f"%Quiz {TAG}%")[0][0]
        m = await self.say(f"Quiz {TAG} moved to {weekday(4)} 9am, same room.")
        check("✅ reaction", await self.reacted(m))
        moved = await poll_until(lambda: asyncio.sleep(0, result=(lambda r: r and len(r) == 1 and r[0][0] != before)(sql("SELECT due_at FROM events WHERE chat_id=? AND status='active' AND title LIKE ?", self.ch.id, f"%Quiz {TAG}%"))))
        check("one row, date changed", bool(moved))
        evs = await self.ch.guild.fetch_scheduled_events()
        check("still one Events entry", sum(f"Quiz {TAG}" in e.name for e in evs) == 1)

        print("4. chatter -> silence")
        m = await self.say("lol did anyone actually understand the semaphore example")
        await asyncio.sleep(10)
        check("no reaction, no reply", not await self._has_tick(m) and await self.from_mate(m, timeout=1) is None)

        print("5. plan on the quiz day -> ✅, heads-up, RSVP poll")
        m = await self.say(f"@everyone study session {TAG} at the library on {weekday(4)} 6pm, bring the slides")
        check("✅ reaction", await self.reacted(m))
        check("heads-up mentions the quiz", (await self.from_mate(m, want="heads up")) is not None)
        check("poll posted", (await self.from_mate(m, poll=True)) is not None)

        print("6. file drop -> resource indexed -> jump link in the answer")
        f = discord.File(io.BytesIO(b"slide 1\nslide 2\n"), filename=f"lecture{TAG}_slides.txt")
        m = await self.say(f"lecture {TAG} slides", file=f)
        await poll_until(lambda: asyncio.sleep(0, result=sql("SELECT 1 FROM resources WHERE msg_id=?", m.id)))
        check("resource row", bool(sql("SELECT 1 FROM resources WHERE msg_id=?", m.id)))
        q = await self.ask(f"where are the lecture {TAG} slides?")
        r = await self.from_mate(q, want="discord.com/channels/", reply_to=q)
        check("answer has a jump link", r is not None, (r.content[:90] if r else ""))

        print("7. personal reminder -> DB row for the asker")
        q = await self.ask(f"remind me 2 hours before quiz {TAG}")
        r = await self.from_mate(q, reply_to=q)
        row = sql("SELECT p.user_id FROM personal_reminders p JOIN events e ON e.id=p.event_id WHERE e.chat_id=? AND e.title LIKE ?", self.ch.id, f"%Quiz {TAG}%")
        check("reminder stored for the tester", bool(row) and row[0][0] == self.c.user.id, (r.content[:90] if r else ""))

        print("8. commands")
        m = await self.say("!schedule 30")
        check("!schedule lists the quiz", (await self.from_mate(m, want=f"quiz {TAG}")) is not None)
        m = await self.say("!digest")
        check("!digest renders the week", (await self.from_mate(m, want="this week")) is not None)
        m = await self.say("!tick")
        check("!tick runs", (await self.from_mate(m, want="reminder check done")) is not None)

    async def cleanup(self):
        n = 0
        for e in await self.ch.guild.fetch_scheduled_events():
            if TAG in e.name and e.creator_id == MATE_ID:
                await e.delete(); n += 1
        with sqlite3.connect(config.DB_PATH) as c:
            ids = [r[0] for r in c.execute("SELECT id FROM events WHERE chat_id=?", (self.ch.id,))]
            for t in ("polls", "personal_reminders"):
                c.executemany(f"DELETE FROM {t} WHERE event_id=?", [(i,) for i in ids])
            for t in ("events", "messages", "resources", "notes"):
                c.execute(f"DELETE FROM {t} WHERE chat_id=?", (self.ch.id,))
        await self.ch.delete(reason="mate e2e cleanup")
        print(f"cleanup: channel deleted, {len(ids)} events, {n} Discord events removed")


async def main():
    token = os.getenv("MATE_TEST_BOT_TOKEN")
    if not token:
        sys.exit("MATE_TEST_BOT_TOKEN missing in .env (see the docstring)")
    intents = discord.Intents.default(); intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        guild = discord.utils.get(client.guilds, name=opts.guild) if opts.guild else (client.guilds[0] if client.guilds else None)
        if guild is None:
            sys.exit("tester bot is not in any server (or --guild name is wrong)")
        if guild.get_member(MATE_ID) is None:
            print(f"warning: Mate ({MATE_ID}) not visible in {guild.name}; is it running and invited?")
        ch = discord.utils.get(guild.text_channels, name=CHANNEL) or await guild.create_text_channel(CHANNEL, reason="mate e2e")
        print(f"server: {guild.name}   channel: #{ch.name} ({ch.id})   tester: {client.user}   mate id: {MATE_ID}\n")
        run = Run(client, ch)
        try:
            await run.scenarios()
        finally:
            if not opts.keep:
                await run.cleanup()
            await client.close()

    try:
        await client.start(token)
    except discord.PrivilegedIntentsRequired:
        sys.exit("the tester bot needs Message Content Intent: Developer Portal -> mate-tester -> Bot -> "
                 "Privileged Gateway Intents -> enable Message Content Intent -> Save, then rerun")
    passed, total = sum(results), len(results)
    print(f"\n{passed}/{total} checks passed" + ("" if passed == total else "   <-- FAILURES"))
    sys.exit(0 if passed == total else 1)


asyncio.run(main())
