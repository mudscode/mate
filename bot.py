"""Discord entry point. Run: python bot.py"""
import asyncio
import os
import re
from datetime import datetime

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()                            # must run before importing extract/qa: they build the OpenAI client at import

import db
import discord_events
import extract
import qa

intents = discord.Intents.default()
intents.message_content = True          # also enable "Message Content Intent" in the Developer Portal
bot = commands.Bot(command_prefix="!", intents=intents)

STAFF_ROLES = {"Instructor", "TA", "Admin"}
QUESTION_HINTS = ("when", "where", "what", "which", "who", "how", "deadline", "due", "remind", "missed", "miss")
EMOJI = {"deadline": "📝", "quiz": "❓", "exam": "📚", "class_change": "🔁", "announcement": "📢", "plan": "🎒"}
sem = asyncio.Semaphore(6)               # cap concurrent model calls during backfill
db_lock = asyncio.Lock()                 # upsert + Discord-event sync must not interleave across messages
QUESTION_STARTERS = ("when", "where", "what", "whats", "what's", "who", "how", "is", "are", "does", "did", "any")


def is_staff(member) -> bool:
    guild = getattr(member, "guild", None)
    if guild is not None and guild.owner_id == member.id:   # server owner counts as instructor (solo demo)
        return True
    return any(r.name in STAFF_ROLES for r in getattr(member, "roles", []))


def looks_like_question(text: str) -> bool:
    """A question aimed at memory ('when is the quiz?'), not a plan phrased as a question ('trip on Sunday?')."""
    t = text.lower().strip()
    words = t.split()
    if not words or len(words) > 20:
        return False
    if "?" in t and any(re.search(rf"\b{h}\b", t) for h in QUESTION_HINTS):
        return True
    return words[0] in QUESTION_STARTERS and len(words) <= 8 and words[1:2] != ["a"]   # "what's coming", not "what a day"


async def ingest(message: discord.Message, react: bool = True) -> int:
    atts = []
    for a in message.attachments:
        mime = (a.content_type or "").split(";")[0]
        if mime == "application/pdf" or mime.startswith("image/"):
            atts.append((await a.read(), mime))
    ts = message.created_at.astimezone(db.TZ).strftime("%Y-%m-%dT%H:%M")
    guild_id = message.guild.id if message.guild else None
    db.add_message(guild_id, message.channel.id, message.id, message.author.display_name, message.content, ts, bool(atts))

    if not atts and len(message.content.strip()) < 15:
        return 0
    async with sem:
        events = await extract.extract(message.content, message.author.display_name, message.created_at,
                                       is_staff(message.author), atts, effort="medium" if atts else "low")
    heads_up, ids = None, []
    async with db_lock:
        for e in events:
            status, eid = db.upsert_event(e, guild_id, message.channel.id, message.id)
            ids.append(eid)
            if status == "inserted" and heads_up is None:
                clash = db.same_day_events(guild_id, e.due_at, eid)
                if clash:
                    day = datetime.fromisoformat(e.due_at).strftime("%a %d %b")
                    heads_up = f"Heads up: **{e.title}** lands on the same day as **{clash[0]['title']}** ({day})."
    if events and react:
        try:
            await message.add_reaction("✅")
        except discord.HTTPException:
            pass
        if heads_up:                          # the one time Mate speaks without being asked mid-chat
            await message.channel.send(heads_up)
    for eid in ids:                           # mirror to the Events tab last: Discord rate-limits these calls
        async with db_lock:
            deid = await discord_events.sync(message.guild, db.get_event(eid))
            if deid is not None:
                db.set_discord_event_id(eid, deid)
    return len(events)


@bot.event
async def on_ready():
    db.init()
    if not reminder_loop.is_running():
        reminder_loop.start()
    print(f"Logged in as {bot.user}")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    replied_to_bot = (message.reference and isinstance(message.reference.resolved, discord.Message)
                      and message.reference.resolved.author == bot.user)
    if bot.user in message.mentions or replied_to_bot or looks_like_question(message.content):
        q = message.content.replace(bot.user.mention, "").strip()
        async with message.channel.typing():
            reply = await qa.answer(q, message.author.display_name, message.guild.id if message.guild else None,
                                    message.channel.id)
        await message.reply(reply, mention_author=False)
        return

    await ingest(message)


@bot.command()
async def backfill(ctx: commands.Context, limit: int = 500):
    """Read channel history from before the bot joined and extract events. !backfill 300"""
    msgs = [m async for m in ctx.channel.history(limit=limit, oldest_first=True) if not m.author.bot]
    counts = await asyncio.gather(*(ingest(m, react=False) for m in msgs))
    await ctx.send(f"Backfilled {len(msgs)} messages, found {sum(counts)} events.")


@bot.command()
async def schedule(ctx: commands.Context, days: int = 14):
    """Dump upcoming events. Fallback if Q&A misbehaves on stage."""
    evs = db.list_events(days, ctx.guild.id if ctx.guild else None)
    if not evs:
        return await ctx.send("Nothing upcoming.")
    lines = [f"{EMOJI.get(e['kind'], '•')} **{e['title']}** — "
             f"{datetime.fromisoformat(e['due_at']).strftime('%a %d %b, %H:%M') if e['due_at'] else 'no date'}" for e in evs]
    await ctx.send("\n".join(lines))


@bot.command()
async def tick(ctx: commands.Context):
    """Force the reminder check right now (demo)."""
    n = await run_reminders()
    await ctx.send(f"Reminder check done, sent {n}.")


async def run_reminders() -> int:
    sent = 0
    for ev, kind in db.due_reminders():
        channel = bot.get_channel(ev["chat_id"])
        if channel is None:
            continue
        when = datetime.fromisoformat(ev["due_at"]).strftime("%a %d %b, %H:%M")
        lead = "tomorrow" if kind == "24h" else "in about 2 hours"
        await channel.send(f"{EMOJI.get(ev['kind'], '⏰')} Reminder: **{ev['title']}** is {lead} ({when}). {ev['details']}")
        db.mark_reminder(ev["id"], kind)
        sent += 1
    return sent


@tasks.loop(minutes=10)
async def reminder_loop():
    await run_reminders()


if __name__ == "__main__":
    bot.run(os.environ["DISCORD_BOT_TOKEN"])
