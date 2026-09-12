"""SQLite storage. All datetimes are ISO local strings 'YYYY-MM-DDTHH:MM' in Asia/Karachi,
so plain string comparison orders them. Memory is scoped per server (guild_id); chat_id is the
channel an item came from, used for posting reminders back where it belongs."""
import sqlite3, difflib
from contextlib import contextmanager
from datetime import datetime, timedelta

from .config import DB_PATH, TZ

DB = DB_PATH          # tests reassign this before init()


def now_local() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%dT%H:%M")


@contextmanager
def conn():
    """with conn() as c: ...   commits on success, always closes."""
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY, guild_id INTEGER, chat_id INTEGER, msg_id INTEGER UNIQUE,
            sender TEXT, text TEXT, ts TEXT, has_file INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY, guild_id INTEGER, chat_id INTEGER, title TEXT, kind TEXT,
            due_at TEXT, details TEXT, source_msg_id INTEGER, confidence REAL,
            created_at TEXT, status TEXT DEFAULT 'active', key TEXT, discord_event_id INTEGER);
        CREATE TABLE IF NOT EXISTS notes(
            id INTEGER PRIMARY KEY, guild_id INTEGER, chat_id INTEGER, author TEXT, note TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS reminders(
            id INTEGER PRIMARY KEY, event_id INTEGER, kind TEXT, sent_at TEXT,
            UNIQUE(event_id, kind));
        """)
        for table, col in (("events", "discord_event_id INTEGER"), ("events", "guild_id INTEGER"),
                           ("messages", "guild_id INTEGER"), ("notes", "guild_id INTEGER")):
            try:                                  # older DBs predate these columns
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass


def add_message(guild_id, chat_id, msg_id, sender, text, ts, has_file=False):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO messages(guild_id,chat_id,msg_id,sender,text,ts,has_file) VALUES(?,?,?,?,?,?,?)",
                  (guild_id, chat_id, msg_id, sender, text, ts, int(has_file)))


def _similar(a, b):
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def upsert_event(ev, guild_id, chat_id, source_msg_id) -> tuple[str, int]:
    """Insert, or update the existing active event with the same key (reschedules, corrections).
    Falls back to same kind + same minute, or same kind + near-identical title on the same day.
    Returns ('inserted' | 'updated', events.id)."""
    with conn() as c:
        rows = c.execute("SELECT * FROM events WHERE guild_id=? AND status='active'", (guild_id,)).fetchall()
        match = next((r for r in rows if r["key"] == ev.key), None)
        if match is None:
            for r in rows:
                if r["kind"] != ev.kind or not (ev.due_at and r["due_at"]):
                    continue
                same_day = abs((datetime.fromisoformat(ev.due_at) - datetime.fromisoformat(r["due_at"])).days) <= 1
                if r["due_at"] == ev.due_at or (same_day and _similar(ev.title, r["title"]) > 0.85):
                    match = r
                    break
        if match:
            c.execute("UPDATE events SET key=?, kind=?, title=?, due_at=?, details=?, source_msg_id=?, confidence=? WHERE id=?",
                      (ev.key, ev.kind, ev.title, ev.due_at, ev.details, source_msg_id, ev.confidence, match["id"]))
            if match["due_at"] != ev.due_at:
                c.execute("DELETE FROM reminders WHERE event_id=?", (match["id"],))
            return "updated", match["id"]
        cur = c.execute("INSERT INTO events(guild_id,chat_id,key,title,kind,due_at,details,source_msg_id,confidence,created_at) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (guild_id, chat_id, ev.key, ev.title, ev.kind, ev.due_at, ev.details, source_msg_id,
                         ev.confidence, now_local()))
        return "inserted", cur.lastrowid


def get_event(event_id):
    with conn() as c:
        r = c.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return dict(r) if r else None


def set_discord_event_id(event_id, discord_event_id):
    with conn() as c:
        c.execute("UPDATE events SET discord_event_id=? WHERE id=?", (discord_event_id, event_id))


def same_day_events(guild_id, due_at, exclude_id):
    """Other active events in this server on the same calendar day (for unprompted heads-ups)."""
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id,title,due_at FROM events WHERE guild_id=? AND status='active' AND id!=? AND substr(due_at,1,10)=?",
            (guild_id, exclude_id, due_at[:10]))]


def list_events(days_ahead=14, guild_id=None):
    now = now_local()
    until = (datetime.now(TZ) + timedelta(days=days_ahead)).strftime("%Y-%m-%dT%H:%M")
    q = "SELECT id,title,kind,due_at,details,confidence FROM events WHERE status='active' AND due_at BETWEEN ? AND ?"
    args = [now, until]
    if guild_id:
        q += " AND guild_id=?"; args.append(guild_id)
    with conn() as c:
        return [dict(r) for r in c.execute(q + " ORDER BY due_at", args)]


def search_messages(query, guild_id=None, limit=20):
    q, args = "SELECT sender,text,ts FROM messages WHERE text LIKE ?", [f"%{query}%"]
    if guild_id:
        q += " AND guild_id=?"; args.append(guild_id)
    with conn() as c:
        return [dict(r) for r in c.execute(q + " ORDER BY ts DESC LIMIT ?", args + [limit])]


def recent_messages(since, guild_id=None, limit=80):
    q, args = "SELECT sender,text,ts FROM messages WHERE ts >= ? AND text != ''", [since]
    if guild_id:
        q += " AND guild_id=?"; args.append(guild_id)
    with conn() as c:
        return [dict(r) for r in c.execute(q + " ORDER BY ts LIMIT ?", args + [limit])]


def add_note(guild_id, chat_id, author, note):
    with conn() as c:
        c.execute("INSERT INTO notes(guild_id,chat_id,author,note,created_at) VALUES(?,?,?,?,?)",
                  (guild_id, chat_id, author, note, now_local()))


def search_notes(query, guild_id=None, limit=10):
    q, args = "SELECT author,note,created_at FROM notes WHERE note LIKE ?", [f"%{query}%"]
    if guild_id:
        q += " AND guild_id=?"; args.append(guild_id)
    with conn() as c:
        return [dict(r) for r in c.execute(q + " ORDER BY created_at DESC LIMIT ?", args + [limit])]


def due_reminders():
    """Events needing a reminder: (event_row, '24h'|'2h')."""
    now = datetime.now(TZ)
    out = []
    with conn() as c:
        for kind, hours in (("24h", 24), ("2h", 2)):
            until = (now + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M")
            rows = c.execute("""SELECT e.* FROM events e WHERE e.status='active' AND e.due_at > ? AND e.due_at <= ?
                                AND NOT EXISTS (SELECT 1 FROM reminders r WHERE r.event_id=e.id AND r.kind=?)""",
                             (now.strftime("%Y-%m-%dT%H:%M"), until, kind)).fetchall()
            out += [(dict(r), kind) for r in rows]
    return out


def mark_reminder(event_id, kind):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO reminders(event_id,kind,sent_at) VALUES(?,?,?)", (event_id, kind, now_local()))
