"""SQLite storage. All datetimes are ISO local strings 'YYYY-MM-DDTHH:MM' in Asia/Karachi,
so plain string comparison orders them correctly."""
import sqlite3, difflib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DB = "mate.db"
TZ = ZoneInfo("Asia/Karachi")


def now_local() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%dT%H:%M")


def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY, chat_id INTEGER, msg_id INTEGER UNIQUE,
            sender TEXT, text TEXT, ts TEXT, has_file INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY, chat_id INTEGER, title TEXT, kind TEXT,
            due_at TEXT, details TEXT, source_msg_id INTEGER, confidence REAL,
            created_at TEXT, status TEXT DEFAULT 'active', key TEXT);
        CREATE TABLE IF NOT EXISTS notes(
            id INTEGER PRIMARY KEY, chat_id INTEGER, author TEXT, note TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS reminders(
            id INTEGER PRIMARY KEY, event_id INTEGER, kind TEXT, sent_at TEXT,
            UNIQUE(event_id, kind));
        """)


def add_message(chat_id, msg_id, sender, text, ts, has_file=False):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO messages(chat_id,msg_id,sender,text,ts,has_file) VALUES(?,?,?,?,?,?)",
                  (chat_id, msg_id, sender, text, ts, int(has_file)))


def _similar(a, b):
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def upsert_event(ev, chat_id, source_msg_id) -> str:
    """Insert, or update the existing active event with the same key (reschedules, corrections).
    Falls back to a near-identical title on the same day. Returns 'inserted' | 'updated'."""
    with conn() as c:
        rows = c.execute("SELECT * FROM events WHERE chat_id=? AND kind=? AND status='active'",
                         (chat_id, ev.kind)).fetchall()
        match = next((r for r in rows if r["key"] == ev.key), None)
        if match is None:
            for r in rows:
                same_day = ev.due_at and r["due_at"] and abs(
                    (datetime.fromisoformat(ev.due_at) - datetime.fromisoformat(r["due_at"])).days) <= 1
                same_minute = ev.due_at and r["due_at"] == ev.due_at
                if same_minute or (same_day and _similar(ev.title, r["title"]) > 0.85):
                    match = r
                    break
        if match:
            c.execute("UPDATE events SET key=?, title=?, due_at=?, details=?, source_msg_id=?, confidence=? WHERE id=?",
                      (ev.key, ev.title, ev.due_at, ev.details, source_msg_id, ev.confidence, match["id"]))
            if match["due_at"] != ev.due_at:
                c.execute("DELETE FROM reminders WHERE event_id=?", (match["id"],))
            return "updated"
        c.execute("INSERT INTO events(chat_id,key,title,kind,due_at,details,source_msg_id,confidence,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                  (chat_id, ev.key, ev.title, ev.kind, ev.due_at, ev.details, source_msg_id, ev.confidence, now_local()))
        return "inserted"


def list_events(days_ahead=14, chat_id=None):
    now = now_local()
    until = (datetime.now(TZ) + timedelta(days=days_ahead)).strftime("%Y-%m-%dT%H:%M")
    week_ago = (datetime.now(TZ) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M")
    q = """SELECT id,title,kind,due_at,details,confidence FROM events WHERE status='active'
           AND ((due_at BETWEEN ? AND ?) OR (due_at IS NULL AND created_at >= ?))"""
    args = [now, until, week_ago]
    if chat_id:
        q += " AND chat_id=?"; args.append(chat_id)
    q += " ORDER BY due_at IS NULL, due_at"
    with conn() as c:
        return [dict(r) for r in c.execute(q, args)]


def search_messages(query, limit=20):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT sender,text,ts FROM messages WHERE text LIKE ? ORDER BY ts DESC LIMIT ?",
            (f"%{query}%", limit))]


def recent_messages(since, chat_id=None, limit=80):
    q, args = "SELECT sender,text,ts FROM messages WHERE ts >= ? AND text != ''", [since]
    if chat_id:
        q += " AND chat_id=?"; args.append(chat_id)
    with conn() as c:
        return [dict(r) for r in c.execute(q + " ORDER BY ts LIMIT ?", args + [limit])]


def add_note(chat_id, author, note):
    with conn() as c:
        c.execute("INSERT INTO notes(chat_id,author,note,created_at) VALUES(?,?,?,?)", (chat_id, author, note, now_local()))


def search_notes(query, chat_id=None, limit=10):
    q, args = "SELECT author,note,created_at FROM notes WHERE note LIKE ?", [f"%{query}%"]
    if chat_id:
        q += " AND chat_id=?"; args.append(chat_id)
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
