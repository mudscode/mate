"""memory_edit feature: talk to the memory to fix it.

Mate's other half writes memory automatically (handlers.ingest -> extract -> db.upsert_event). Sometimes it
writes the wrong thing, or the world changes in a way nobody restates cleanly: "quiz 3 is actually on Friday
9am", "forget the trip". These two tools let the Q&A model reach into the events table for exactly one row.

Two things keep that safe. First, the model never picks the row by id — it passes words, and we resolve them
to the soonest upcoming active event in this server, so the worst case is editing the wrong quiz, not the
wrong server. Second, Python owns the calendar: the model proposes an ISO datetime and `_check_due_at` re-parses
it, rejects anything malformed, in the past, or absurdly far out. The model resolving "Friday" is a suggestion,
not an authority.

Updates go through db.upsert_event with the row's own key, so they take the existing-key path: the row updates
in place, fired reminders for it are cleared (it will be announced again at its new time), and personal
reminders — which recompute their fire time from due_at every tick — follow along on their own.
"""
import sqlite3
from datetime import datetime, timedelta
from types import SimpleNamespace

import discord

from .. import db, discord_events, tools
from ..config import TZ
from ..extract import WEEKDAYS, day_words_match

MIN_LEAD = timedelta(minutes=5)      # Discord refuses scheduled events that start now-ish; so do we
MAX_AHEAD = timedelta(days=365)      # a one-semester course; further out is the model mis-reading a year


def _find_event(guild_id, what: str):
    """Soonest upcoming active event whose title or key contains `what` (case-insensitive).

    Same shape as personal_reminders._find_event, but selects the whole row: an edit needs the key, kind,
    details and source_msg_id to rebuild the event, and discord_event_id to clean up the mirrored one.
    """
    needle = f"%{(what or '').strip().lower()}%"
    with db.conn() as c:
        row = c.execute(
            "SELECT * FROM events WHERE guild_id IS ? AND status='active' AND due_at IS NOT NULL "
            "AND due_at >= ? AND (LOWER(title) LIKE ? OR LOWER(key) LIKE ?) ORDER BY due_at LIMIT 1",
            (guild_id, db.now_local(), needle, needle)).fetchone()
    return dict(row) if row else None


def _check_due_at(s: str) -> tuple[str | None, str | None]:
    """Validate a model-proposed datetime. Returns (clean_iso, None) or (None, reason)."""
    s = (s or "").strip()
    try:
        due = datetime.fromisoformat(s)
    except ValueError:
        return None, "new_due_at must look like 2026-09-18T09:00 (YYYY-MM-DDTHH:MM)"
    if due.strftime("%Y-%m-%dT%H:%M") != s:            # seconds, offsets, a bare date: not our format
        return None, "new_due_at must look like 2026-09-18T09:00 (YYYY-MM-DDTHH:MM)"
    now = datetime.now(TZ).replace(tzinfo=None)
    if due < now + MIN_LEAD:
        return None, "that time is in the past; give the upcoming date"
    if due > now + MAX_AHEAD:
        return None, "that is more than a year away; check the year"
    return s, None


@tools.tool("Correct something Mate remembered: a new date/time and/or a new title for one existing event. "
            "Use when someone says 'X is actually on Friday', 'the deadline moved to 5pm', "
            "'rename that to Quiz 3'. Pass '' for a field that should not change. new_due_at must be "
            "'YYYY-MM-DDTHH:MM' in Asia/Karachi; resolve 'Friday' relative to now yourself and Mate will "
            "validate it.",
            what=("string", "Words from the name of the event to correct, e.g. 'quiz 3' or 'the trip'."),
            new_due_at=("string", "The corrected date and time as 'YYYY-MM-DDTHH:MM' in Asia/Karachi, "
                                  "or '' to leave the time alone."),
            new_title=("string", "The corrected name of the event, or '' to leave the name alone."))
async def update_event(ctx, what, new_due_at, new_title):
    new_due_at, new_title = (new_due_at or "").strip(), (new_title or "").strip()
    if not new_due_at and not new_title:
        return {"error": "nothing to change; give a new date or a new title"}
    row = _find_event(ctx.get("guild_id"), what)
    if row is None:
        return {"error": "no matching event; use the name from the schedule"}
    if new_due_at:
        new_due_at, why = _check_due_at(new_due_at)
        if why:
            return {"error": why}
        due = datetime.fromisoformat(new_due_at)
        if not day_words_match(ctx.get("question", ""), due, datetime.now(TZ).replace(tzinfo=None)):
            return {"error": f"{new_due_at} is a {WEEKDAYS[due.weekday()].title()}, which does not match the day "
                             "named in the request; recompute the date from today and try again"}

    obj = SimpleNamespace(key=row["key"], title=new_title or row["title"], kind=row["kind"],
                          due_at=new_due_at or row["due_at"], details=row["details"], confidence=1.0)
    db.upsert_event(obj, ctx.get("guild_id"), row["chat_id"], row["source_msg_id"])

    if ctx.get("guild") is not None:                   # keep the native Discord event in step
        deid = await discord_events.sync(ctx["guild"], db.get_event(row["id"]))
        if deid is not None:
            db.set_discord_event_id(row["id"], deid)
    return {"ok": True, "title": obj.title, "old_due_at": row["due_at"], "due_at": obj.due_at}


@tools.tool("Remove one remembered event when it is cancelled or was logged by mistake: "
            "'forget the trip', 'the quiz is cancelled'.",
            what=("string", "Words from the name of the event to forget, e.g. 'the trip' or 'quiz 3'."))
async def forget_event(ctx, what):
    row = _find_event(ctx.get("guild_id"), what)
    if row is None:
        return {"error": "no matching event; use the name from the schedule"}

    with db.conn() as c:
        c.execute("UPDATE events SET status='superseded' WHERE id=?", (row["id"],))
        for table in ("personal_reminders", "polls"):         # feature tables; a fresh DB may not have them
            try:
                c.execute(f"DELETE FROM {table} WHERE event_id=?", (row["id"],))
            except sqlite3.OperationalError:
                pass

    if row["discord_event_id"] and ctx.get("guild") is not None:
        try:
            se = await ctx["guild"].fetch_scheduled_event(int(row["discord_event_id"]))
            await se.delete()
        except (discord.NotFound, discord.HTTPException) as e:
            print(f"memory_edit: can't delete scheduled event {row['discord_event_id']}: {e}")
    return {"ok": True, "title": row["title"], "due_at": row["due_at"]}


def setup(bot):
    """Nothing to create: both tools work on tables db.init() already made."""
    pass
