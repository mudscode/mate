"""digest feature: the Sunday-evening "This week" post, unprompted.

Every Sunday at or after 18:00 Asia/Karachi, on its own, Mate drops a grouped-by-day rundown of
everything due in the next 7 days into each server's busiest channel — once per ISO week, tracked in
the `digests` table. `!digest` renders the same thing on demand (handy on stage).
"""
from datetime import datetime, timedelta

import discord

from .. import db, hooks
from ..config import TZ
from ..handlers import EMOJI, fmt_when

LIMIT = 1900                 # Discord caps a message at 2000; leave room for the truncation tail
BUSY_DAYS = 14               # how far back to look when picking "the channel this class actually uses"

SCHEMA = """CREATE TABLE IF NOT EXISTS digests(
    id INTEGER PRIMARY KEY, guild_id INTEGER, week TEXT, sent_at TEXT,
    UNIQUE(guild_id, week))"""


def _ensure():
    with db.conn() as c:
        c.execute(SCHEMA)


def _now() -> datetime:
    """Wall clock in Asia/Karachi. A module-level function so tests can pin it to a Sunday evening."""
    return datetime.now(TZ)


def render(guild_id) -> str | None:
    """The week's events grouped under one bold header per day, or None if the week is empty."""
    evs = [e for e in db.list_events(7, guild_id) if e["due_at"]]
    if not evs:
        return None
    lines, day, size = ["📅 This week"], None, len("📅 This week")
    for i, e in enumerate(evs):
        when, hhmm = fmt_when(e["due_at"]).split(", ")
        chunk = ([f"**{when}**"] if when != day else []) + \
                [f"  {EMOJI.get(e['kind'], '•')} {e['title']} — {hhmm}"]
        grew = sum(len(x) + 1 for x in chunk)
        tail = f"…and {len(evs) - i} more"
        if size + grew + len(tail) + 1 > LIMIT:
            lines.append(tail)
            break
        lines += chunk
        size += grew
        day = when
    return "\n".join(lines)


def _sent(guild_id, week) -> bool:
    with db.conn() as c:
        c.execute(SCHEMA)
        return c.execute("SELECT 1 FROM digests WHERE guild_id=? AND week=?", (guild_id, week)).fetchone() is not None


def _mark(guild_id, week):
    with db.conn() as c:
        c.execute(SCHEMA)
        c.execute("INSERT OR IGNORE INTO digests(guild_id,week,sent_at) VALUES(?,?,?)",
                  (guild_id, week, db.now_local()))


def _busiest_chat(guild_id, now: datetime):
    """The channel this server has been talking in most over the last two weeks, or None."""
    since = (now - timedelta(days=BUSY_DAYS)).strftime("%Y-%m-%dT%H:%M")
    with db.conn() as c:
        r = c.execute("SELECT chat_id, COUNT(*) FROM messages WHERE guild_id=? AND ts >= ? "
                      "GROUP BY chat_id ORDER BY 2 DESC LIMIT 1", (guild_id, since)).fetchone()
    return r["chat_id"] if r else None


@hooks.on_tick
async def weekly(bot) -> int:
    """Fired every 10 minutes. Posts at most one digest per server per ISO week. Returns how many went out."""
    now = _now()
    if now.weekday() != 6 or now.hour < 18:          # Sunday evening only
        return 0
    week = now.strftime("%G-W%V")
    posted = 0
    for guild in getattr(bot, "guilds", []):
        if _sent(guild.id, week):
            continue
        text = render(guild.id)
        if not text:
            continue
        chat_id = _busiest_chat(guild.id, now)
        channel = bot.get_channel(chat_id) if chat_id else None
        if channel is None:                          # nowhere sensible to post; try again next tick
            continue
        try:
            await channel.send(text)
        except discord.HTTPException as e:
            print(f"digest post failed for guild {guild.id}: {e}")
            continue
        _mark(guild.id, week)
        posted += 1
    return posted


def setup(bot):
    _ensure()

    @bot.command()
    async def digest(ctx):
        """This week's events, grouped by day. Same text the Sunday-evening post uses."""
        await ctx.send(render(ctx.guild.id if ctx.guild else None) or "Nothing on for this week.")
