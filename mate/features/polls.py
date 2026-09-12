"""RSVP polls on plans. When Mate logs a NEW `plan` (trip, study session, meetup) it posts a native
Discord poll in the same channel so classmates can click "I'm in" instead of typing +1 twenty times.
The poll closes when the plan starts (clamped to Discord's 1h..7d window)."""
from datetime import datetime, timedelta

import discord

from .. import db, hooks, tools
from ..config import TZ
from ..handlers import fmt_when

MIN_HOURS, MAX_HOURS = 1, 168        # Discord allows a poll to run between 1 hour and 7 days

SCHEMA = """CREATE TABLE IF NOT EXISTS polls(
    id INTEGER PRIMARY KEY, event_id INTEGER, guild_id INTEGER, chat_id INTEGER, poll_message_id INTEGER,
    created_at TEXT)"""


def _ensure():
    with db.conn() as c:
        c.execute(SCHEMA)


def _hours_until(due_at: str) -> int:
    """Whole hours from now (Asia/Karachi) until the plan starts, clamped to what Discord accepts."""
    due = datetime.fromisoformat(due_at)
    now = datetime.now(TZ).replace(tzinfo=None)
    return max(MIN_HOURS, min(MAX_HOURS, round((due - now).total_seconds() / 3600)))


@hooks.on_event_logged
async def on_plan(message, ev, status):
    if ev["kind"] != "plan" or status != "inserted" or message.channel is None or not ev["due_at"]:
        return
    poll = discord.Poll(question=f"{ev['title']} — {fmt_when(ev['due_at'])}. In?",
                        duration=timedelta(hours=_hours_until(ev["due_at"])))
    poll.add_answer(text="I'm in 🙌")
    poll.add_answer(text="Can't make it 😔")
    try:
        sent = await message.channel.send(poll=poll)
    except discord.HTTPException as e:            # polls need a normal text channel; never break ingest
        print(f"poll post failed for event {ev['id']}: {e}")
        return
    _ensure()
    with db.conn() as c:
        c.execute("INSERT INTO polls(event_id,guild_id,chat_id,poll_message_id,created_at) VALUES(?,?,?,?,?)",
                  (ev["id"], ev["guild_id"], ev["chat_id"], getattr(sent, "id", None), db.now_local()))


@tools.tool("The RSVP poll Mate posted for a student plan (trip, study session, meetup), with live vote counts "
            "and who voted. Use for 'who's coming to the trip?', 'how many are in for the study session?'.",
            query=("string", "A word or two from the plan's title, e.g. 'trip' or 'study session'."))
async def plan_poll(ctx, query):
    _ensure()
    with db.conn() as c:
        r = c.execute("""SELECT e.title, e.due_at, e.chat_id, p.poll_message_id
                         FROM events e LEFT JOIN polls p ON p.event_id = e.id
                         WHERE e.status='active' AND e.kind='plan' AND e.guild_id IS ? AND e.title LIKE ?
                         ORDER BY e.due_at LIMIT 1""",
                      (ctx.get("guild_id"), f"%{query}%")).fetchone()
    if r is None:
        return {"error": "no such plan"}
    out = {"title": r["title"], "due_at": r["due_at"], "poll_message_id": r["poll_message_id"], "chat_id": r["chat_id"]}
    guild = ctx.get("guild")
    if guild is not None and r["poll_message_id"]:          # live counts straight from Discord
        try:
            ch = guild.get_channel(r["chat_id"]) or await guild.fetch_channel(r["chat_id"])
            poll = (await ch.fetch_message(r["poll_message_id"])).poll
            out["answers"] = [{"text": a.text, "votes": a.vote_count,
                               "voters": [u.display_name async for u in a.voters()]} for a in poll.answers]
            out["total_votes"] = poll.total_votes
        except discord.HTTPException as e:
            out["error"] = f"poll unreadable: {e}"
    return out


def setup(bot):
    _ensure()
