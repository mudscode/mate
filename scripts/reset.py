"""Fresh start: delete the SQLite file and every Discord scheduled event this bot created.
The per-server context sentences (!context) are kept. Run: python scripts/reset.py
Then paste demo/seed_chat.txt into the class channel and drop demo/course_outline.pdf."""
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discord

from mate import config, db

kept = []
if os.path.exists(config.DB_PATH):
    try:
        kept = sqlite3.connect(config.DB_PATH).execute("SELECT guild_id, key, value FROM settings").fetchall()
    except sqlite3.OperationalError:
        pass
    os.remove(config.DB_PATH)
    print(f"removed {config.DB_PATH}")
db.init()
for g, k, v in kept:
    db.set_setting(g, k, v)
print(f"kept {len(kept)} setting(s)")

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
