"""What happens to a message: store it, extract events, react, heads-up, mirror to Discord Events, fire hooks."""
import asyncio
import re
from datetime import datetime

import discord

from . import db, discord_events, extract, hooks
from .config import STAFF_ROLES, TEST_BOT_IDS

QUESTION_HINTS = ("when", "where", "what", "which", "who", "how", "deadline", "due", "remind", "missed", "miss")
QUESTION_STARTERS = ("when", "where", "what", "whats", "what's", "who", "how", "is", "are", "does", "did", "any")
EMOJI = {"deadline": "📝", "quiz": "❓", "exam": "📚", "class_change": "🔁", "announcement": "📢", "plan": "🎒"}

sem = asyncio.Semaphore(6)               # cap concurrent model calls during backfill
db_lock = asyncio.Lock()                 # upsert + Discord-event sync must not interleave across messages


def is_staff(member) -> bool:
    guild = getattr(member, "guild", None)
    if guild is not None and guild.owner_id == member.id:   # server owner counts as instructor (solo demo)
        return True
    if member.id in TEST_BOT_IDS:                           # the e2e tester posts as the instructor
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


def fmt_when(due_at: str) -> str:
    return datetime.fromisoformat(due_at).strftime("%a %d %b, %H:%M")


async def ingest(message: discord.Message, react: bool = True) -> int:
    """Store the message, extract events, react ✅ if any, post a heads-up on a same-day clash,
    mirror to the Events tab, and fire feature hooks. Returns the number of events found."""
    atts = []
    for a in message.attachments:
        mime = (a.content_type or "").split(";")[0]
        if mime == "application/pdf" or mime.startswith("image/"):
            atts.append((await a.read(), mime))
    ts = message.created_at.astimezone(db.TZ).strftime("%Y-%m-%dT%H:%M")
    guild_id = message.guild.id if message.guild else None
    db.add_message(guild_id, message.channel.id, message.id, message.author.display_name, message.content, ts, bool(atts))
    await hooks.fire(hooks.MESSAGE_INGESTED, message)

    if not atts and len(message.content.strip()) < 15:
        return 0
    async with sem:
        events = await extract.extract(message.content, message.author.display_name, message.created_at,
                                       is_staff(message.author), atts, effort="medium" if atts else "low",
                                       context=db.get_setting(guild_id, "context"))
    heads_up, logged = None, []
    async with db_lock:
        for e in events:
            status, eid = db.upsert_event(e, guild_id, message.channel.id, message.id)
            logged.append((eid, status))
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
    for eid, status in logged:
        await hooks.fire(hooks.EVENT_LOGGED, message, db.get_event(eid), status)
    for eid, _ in logged:                     # mirror to the Events tab last: Discord rate-limits these calls
        async with db_lock:
            deid = await discord_events.sync(message.guild, db.get_event(eid))
            if deid is not None:
                db.set_discord_event_id(eid, deid)
    return len(events)
