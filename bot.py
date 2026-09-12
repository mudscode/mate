"""Discord entry point. Run: python bot.py"""
import asyncio
import os
from datetime import datetime

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()                            # must run before importing extract/qa: they build the OpenAI client at import

import db
import extract
import qa

intents = discord.Intents.default()
intents.message_content = True          # also enable "Message Content Intent" in the Developer Portal
bot = commands.Bot(command_prefix="!", intents=intents)

STAFF_ROLES = {"Instructor", "TA", "Admin"}
QUESTION_HINTS = ("when", "where", "what", "which", "deadline", "due", "quiz", "exam", "assignment", "?")
EMOJI = {"deadline": "📝", "quiz": "❓", "exam": "📚", "class_change": "🔁", "announcement": "📢"}
sem = asyncio.Semaphore(6)               # cap concurrent model calls during backfill


def is_staff(member) -> bool:
    guild = getattr(member, "guild", None)
    if guild is not None and guild.owner_id == member.id:   # server owner counts as instructor (solo demo)
        return True
    return any(r.name in STAFF_ROLES for r in getattr(member, "roles", []))


def looks_like_question(text: str) -> bool:
    t = text.lower()
    return t.endswith("?") or (len(t.split()) <= 15 and any(h in t for h in QUESTION_HINTS) and "?" in t)


async def ingest(message: discord.Message, react: bool = True) -> int:
    atts = []
    for a in message.attachments:
        mime = (a.content_type or "").split(";")[0]
        if mime == "application/pdf" or mime.startswith("image/"):
            atts.append((await a.read(), mime))
    ts = message.created_at.astimezone(db.TZ).strftime("%Y-%m-%dT%H:%M")
    db.add_message(message.channel.id, message.id, message.author.display_name, message.content, ts, bool(atts))

    if not atts and len(message.content.strip()) < 15:
        return 0
    async with sem:
        events = await extract.extract(message.content, message.author.display_name, message.created_at,
                                       is_staff(message.author), atts, effort="medium" if atts else "low")
    for e in events:
        db.upsert_event(e, message.channel.id, message.id)
    if events and react:
        try:
            await message.add_reaction("✅")
        except discord.HTTPException:
            pass
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
            reply = await qa.answer(q, message.author.display_name)
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
    evs = db.list_events(days, chat_id=ctx.channel.id)
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
