"""Fresh start: delete the SQLite file and every Discord scheduled event this bot created.
Run: python scripts/reset.py   (asks nothing; only touches the bot's own events)"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discord

from mate import config

if os.path.exists(config.DB_PATH):
    os.remove(config.DB_PATH)
    print(f"removed {config.DB_PATH}")

client = discord.Client(intents=discord.Intents.default())


@client.event
async def on_ready():
    for g in client.guilds:
        n = 0
        for e in await g.fetch_scheduled_events():
            if e.creator_id == client.user.id:
                await e.delete(); n += 1
        print(f"{g.name}: deleted {n} scheduled events")
    await client.close()


client.run(os.environ["DISCORD_BOT_TOKEN"], log_handler=None)
