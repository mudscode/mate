"""Seed a channel for the demo without pasting by hand: the tester bot posts demo/seed_chat.txt as one message
and drops demo/course_outline.pdf, then waits for Mate's ✅ on both and prints !schedule.
Run (Mate must be running):  python scripts/seed.py [--channel cs-321] [--guild NAME]
Note: the posts show the tester bot as author. For the stage channel you may prefer to paste as yourself."""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discord

from mate import config  # noqa: F401  loads .env

ROOT = Path(__file__).resolve().parents[1]
args = argparse.ArgumentParser()
args.add_argument("--channel", default="cs-321")
args.add_argument("--guild")
opts = args.parse_args()


async def wait_tick(ch, msg, timeout=90):
    for _ in range(timeout):
        m = await ch.fetch_message(msg.id)
        if any(str(r.emoji) == "✅" for r in m.reactions):
            return True
        await asyncio.sleep(1)
    return False


async def main():
    intents = discord.Intents.default(); intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        guild = discord.utils.get(client.guilds, name=opts.guild) if opts.guild else client.guilds[0]
        ch = discord.utils.get(guild.text_channels, name=opts.channel)
        if ch is None:
            sys.exit(f"no channel #{opts.channel} in {guild.name}")
        m1 = await ch.send((ROOT / "demo/seed_chat.txt").read_text().strip())
        print("seed chat posted;", "✅" if await wait_tick(ch, m1) else "no ✅ within 90s")
        m2 = await ch.send(file=discord.File(ROOT / "demo/course_outline.pdf"))
        print("outline pdf posted;", "✅" if await wait_tick(ch, m2) else "no ✅ within 90s")
        await ch.send("!schedule 120")
        await asyncio.sleep(5)
        async for m in ch.history(limit=3):
            if m.author.bot and m.author.id != client.user.id:
                print("\n" + m.content)
                break
        await client.close()

    await client.start(os.environ["MATE_TEST_BOT_TOKEN"])


asyncio.run(main())
