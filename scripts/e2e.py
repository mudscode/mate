"""End-to-end test through real Discord, no hands: a second bot account ("tester") posts into a channel and
checks that the running Mate reacts, answers, dedupes, and mirrors to the Events tab.

Setup once: create a second application/bot in the Developer Portal, invite it with Send Messages +
Read Message History, then in .env set MATE_TEST_BOT_TOKEN=<its token> and MATE_TEST_BOT_IDS=<its user id>
(Mate treats messages from those ids as human). Restart bot.py after editing .env.

Run:  python scripts/e2e.py <channel_id>          (Mate must be running in another terminal)"""
import asyncio
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discord

from mate import config

CHANNEL = int(sys.argv[1]) if len(sys.argv) > 1 else None
TAG = "Quiz 42"                                  # distinctive so cleanup can find everything it made
TIMEOUT = 45


def weekday(days_ahead):
    return (datetime.now(config.TZ) + timedelta(days=days_ahead)).strftime("%A")


def db_rows():
    c = sqlite3.connect(config.DB_PATH)
    return c.execute("SELECT key,due_at,discord_event_id FROM events WHERE title LIKE ? AND status='active'", (f"%{TAG}%",)).fetchall()


async def wait_for(desc, cond, timeout=TIMEOUT):
    for _ in range(timeout):
        r = await cond()
        if r:
            print(f"  ok   {desc}")
            return r
        await asyncio.sleep(1)
    print(f"  FAIL {desc} (timed out after {timeout}s)")
    return None


async def main():
    if CHANNEL is None or not os.getenv("MATE_TEST_BOT_TOKEN"):
        sys.exit("usage: python scripts/e2e.py <channel_id>   (needs MATE_TEST_BOT_TOKEN in .env)")
    tester = discord.Client(intents=discord.Intents.default() | discord.Intents(message_content=True))
    results = {"failed": 0}

    @tester.event
    async def on_ready():
        ch = tester.get_channel(CHANNEL) or await tester.fetch_channel(CHANNEL)
        mate_ids = set()
        posted = []

        async def reacted(msg):
            m = await ch.fetch_message(msg.id)
            return any(str(r.emoji) == "✅" for r in m.reactions)

        async def replied_to(msg, needle):
            async for m in ch.history(limit=10, after=msg):
                if m.author.bot and m.author.id != tester.user.id and m.reference and m.reference.message_id == msg.id:
                    mate_ids.add(m.author.id)
                    return needle.lower() in m.content.lower() and m
            return None

        print("1. instructor-style announcement gets ✅ and lands in the DB + Events tab")
        m1 = await ch.send(f"{TAG} will be on {weekday(3)} 10am, chapters 1 and 2. Same room."); posted.append(m1)
        ok = await wait_for("✅ reaction", lambda: reacted(m1))
        rows = await wait_for("one DB row with a Discord event id", lambda: asyncio.sleep(0, result=(len(db_rows()) == 1 and db_rows()[0][2] is not None)))
        results["failed"] += (not ok) + (not rows)

        print("2. question is answered from memory")
        m2 = await ch.send(f"when is {TAG.lower()}?"); posted.append(m2)
        reply = await wait_for(f"reply mentioning {TAG}", lambda: replied_to(m2, TAG))
        results["failed"] += not reply
        if reply:
            print(f"       mate: {reply.content[:120]}")

        print("3. reschedule updates in place, no duplicate")
        before = db_rows()[0][1] if db_rows() else None
        m3 = await ch.send(f"{TAG} moved to {weekday(4)} 9am, same room."); posted.append(m3)
        ok = await wait_for("✅ reaction", lambda: reacted(m3))
        moved = await wait_for("still one row, due_at changed", lambda: asyncio.sleep(0, result=(len(db_rows()) == 1 and db_rows()[0][1] != before)))
        results["failed"] += (not ok) + (not moved)

        print("4. chatter is ignored")
        m4 = await ch.send("lol did anyone actually understand the semaphore example"); posted.append(m4)
        await asyncio.sleep(8)
        silent = not await reacted(m4)
        print(f"  {'ok  ' if silent else 'FAIL'} no reaction on chatter")
        results["failed"] += not silent

        print("cleanup")
        for m in posted:
            try:
                await m.delete()
            except discord.HTTPException:
                pass
        with sqlite3.connect(config.DB_PATH) as c:
            c.execute("DELETE FROM events WHERE title LIKE ?", (f"%{TAG}%",))
        await tester.close()

    await tester.start(os.environ["MATE_TEST_BOT_TOKEN"])

    # the scheduled event was created by Mate; delete it with Mate's own token
    mate = discord.Client(intents=discord.Intents.default())

    @mate.event
    async def on_ready():
        for g in mate.guilds:
            for e in await g.fetch_scheduled_events():
                if TAG in e.name and e.creator_id == mate.user.id:
                    await e.delete()
        await mate.close()

    await mate.start(os.environ["DISCORD_BOT_TOKEN"])
    print(f"\n{'ALL PASSED' if not results['failed'] else str(results['failed']) + ' CHECK(S) FAILED'}")
    sys.exit(1 if results["failed"] else 0)


asyncio.run(main())
