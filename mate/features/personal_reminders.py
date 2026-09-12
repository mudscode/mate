"""personal_reminders feature: "remind me 2 hours before assignment 1" -> a DM at that time.

The class-wide reminders in mate/reminders.py shout in the channel at fixed 24h/2h leads. This one is
per-student and per-event: a student asks in chat, Mate stores (user, event, hours_before) and DMs only
them. Nothing is posted to the channel, so the silence rule holds.

Fire times are never stored. Every tick recomputes `due_at - hours_before` from the event row, so when
the instructor moves a quiz and handlers.ingest updates the event in place, the personal reminder moves
with it automatically — no rescheduling code, no stale rows to clean up.
"""
from datetime import datetime, timedelta

import discord

from .. import db, hooks, tools
from ..config import TZ

MAX_HOURS = 720          # 30 days; anything larger is the model mis-parsing "2 weeks before" style asks

SCHEMA = """
CREATE TABLE IF NOT EXISTS personal_reminders(
    id INTEGER PRIMARY KEY, user_id INTEGER, event_id INTEGER, hours_before REAL,
    created_at TEXT, sent_at TEXT,
    UNIQUE(user_id, event_id, hours_before));
"""


def _ensure(c):
    c.executescript(SCHEMA)


def _fires_at(due_at: str, hours_before: float) -> str:
    """ISO local string for 'hours_before' hours before due_at. Naive in, naive out: same clock, same TZ."""
    return (datetime.fromisoformat(due_at) - timedelta(hours=float(hours_before))).strftime("%Y-%m-%dT%H:%M")


def _fmt_hours(h: float) -> str:
    return str(int(h)) if float(h) == int(float(h)) else f"{float(h):g}"


def _find_event(guild_id, what: str):
    """Soonest upcoming active event whose title or key contains `what` (case-insensitive)."""
    needle = f"%{(what or '').strip().lower()}%"
    with db.conn() as c:
        _ensure(c)
        row = c.execute(
            "SELECT id,title,due_at FROM events WHERE guild_id IS ? AND status='active' AND due_at IS NOT NULL "
            "AND due_at >= ? AND (LOWER(title) LIKE ? OR LOWER(key) LIKE ?) ORDER BY due_at LIMIT 1",
            (guild_id, db.now_local(), needle, needle)).fetchone()
    return dict(row) if row else None


@tools.tool("Set a private reminder for the person asking: Mate DMs only them, a chosen number of hours before "
            "one event. Use for 'remind me 2 hours before assignment 1', 'ping me the night before the quiz'.",
            what=("string", "Words from the event's name, e.g. 'assignment 1' or 'quiz 3'."),
            hours_before=("number", "How many hours before it is due to send the DM. 2 for 'two hours before', "
                                    "24 for 'the day before'."))
def remind_me(ctx, what, hours_before):
    uid = ctx.get("asker_id")
    if uid is None:
        return {"error": "I don't know who you are here; ask me in the server so I can DM you."}
    try:
        hours = float(hours_before)
    except (TypeError, ValueError):
        return {"error": "hours_before must be a number of hours."}
    if hours <= 0 or hours > MAX_HOURS:
        return {"error": f"hours_before must be more than 0 and at most {MAX_HOURS}."}
    ev = _find_event(ctx.get("guild_id"), what)
    if ev is None:
        return {"error": "no matching event; try the exact name from the schedule"}
    with db.conn() as c:
        _ensure(c)
        c.execute("INSERT OR IGNORE INTO personal_reminders(user_id,event_id,hours_before,created_at) VALUES(?,?,?,?)",
                  (uid, ev["id"], hours, db.now_local()))
    return {"ok": True, "title": ev["title"], "due_at": ev["due_at"], "fires_at": _fires_at(ev["due_at"], hours)}


@tools.tool("The private DM reminders the person asking has already set, soonest first. "
            "Use for 'what reminders do I have?'.")
def my_reminders(ctx):
    uid = ctx.get("asker_id")
    if uid is None:
        return {"error": "I don't know who you are here."}
    with db.conn() as c:
        _ensure(c)
        rows = c.execute(
            "SELECT e.title AS title, e.due_at AS due_at, p.hours_before AS hours_before "
            "FROM personal_reminders p JOIN events e ON e.id=p.event_id "
            "WHERE p.user_id=? AND p.sent_at IS NULL AND e.status='active' ORDER BY e.due_at",
            (uid,)).fetchall()
    return [dict(r) for r in rows]


@hooks.on_tick
async def run(bot) -> int:
    """DM every student whose personal reminder has come due. Fire times are computed here, not stored,
    so a rescheduled event drags its reminders along with it. Returns how many DMs went out."""
    now = db.now_local()
    with db.conn() as c:
        _ensure(c)
        rows = [dict(r) for r in c.execute(
            "SELECT p.id AS id, p.user_id AS user_id, p.hours_before AS hours_before, "
            "e.title AS title, e.due_at AS due_at "
            "FROM personal_reminders p JOIN events e ON e.id=p.event_id "            # a deleted event drops out
            "WHERE p.sent_at IS NULL AND e.status='active' AND e.due_at IS NOT NULL ORDER BY e.due_at")]
    sent = 0
    for r in rows:
        if now < _fires_at(r["due_at"], r["hours_before"]):
            continue
        uid = r["user_id"]
        try:
            user = bot.get_user(uid) or await bot.fetch_user(uid)
        except Exception as e:                          # left the server, deleted account
            print(f"personal reminder: can't resolve user {uid}: {e}")
            continue
        when = datetime.fromisoformat(r["due_at"]).strftime("%a %d %b, %H:%M")
        try:
            await user.send(f"⏰ {r['title']} is at {when}. "
                            f"You asked me to remind you {_fmt_hours(r['hours_before'])}h before.")
        except discord.Forbidden:                       # DMs closed; leave it pending in case they open them
            print(f"personal reminder: {uid} has DMs closed, skipping")
            continue
        with db.conn() as c:
            c.execute("UPDATE personal_reminders SET sent_at=? WHERE id=?", (db.now_local(), r["id"]))
        sent += 1
    return sent


def setup(bot):
    with db.conn() as c:
        _ensure(c)
