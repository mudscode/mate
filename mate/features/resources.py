"""resources feature: index every file and link dropped in chat, with a Discord jump link back to it.

"where are the lecture 4 slides?" -> the filename, who posted it, when, and a clickable jump_url.
Rows are keyed on (msg_id, title) so re-running !backfill never duplicates them.
"""
import re

from .. import db, hooks, tools

URL_RE = re.compile(r"https?://[^\s<>()\[\]{}\"']+")
DISCORD_CDN = ("cdn.discordapp.com", "media.discordapp.net")

SCHEMA = """
CREATE TABLE IF NOT EXISTS resources(
    id INTEGER PRIMARY KEY, guild_id INTEGER, chat_id INTEGER, msg_id INTEGER,
    jump_url TEXT, kind TEXT, title TEXT, sender TEXT, ts TEXT, context TEXT,
    UNIQUE(msg_id, title));
"""


def _ensure(c):
    c.executescript(SCHEMA)


def add(guild_id, chat_id, msg_id, jump_url, kind, title, sender, ts, context):
    with db.conn() as c:
        _ensure(c)
        c.execute("INSERT OR IGNORE INTO resources(guild_id,chat_id,msg_id,jump_url,kind,title,sender,ts,context) "
                  "VALUES(?,?,?,?,?,?,?,?,?)",
                  (guild_id, chat_id, msg_id, jump_url, kind, title, sender, ts, context))


def _links(message) -> list[str]:
    """http(s) URLs in the text, minus Discord CDN links to this message's own attachments."""
    own = {getattr(a, "url", None) for a in message.attachments}
    own |= {getattr(a, "proxy_url", None) for a in message.attachments}
    names = {getattr(a, "filename", "") for a in message.attachments}
    out, seen = [], set()
    for url in URL_RE.findall(message.content or ""):
        url = url.rstrip(".,);:!?")
        if url in own:
            continue
        if any(h in url for h in DISCORD_CDN) and any(n and n in url for n in names):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


@hooks.on_message_ingested
async def index(message):
    guild_id = message.guild.id if message.guild else None
    ts = message.created_at.astimezone(db.TZ).strftime("%Y-%m-%dT%H:%M")
    context = (message.content or "")[:120]
    sender = message.author.display_name
    for a in message.attachments:
        add(guild_id, message.channel.id, message.id, message.jump_url, "file", a.filename, sender, ts, context)
    for url in _links(message):
        add(guild_id, message.channel.id, message.id, message.jump_url, "link", url, sender, ts, context)


@tools.tool("Files and links people shared, with a jump_url to the original message. Use for 'where are the slides', "
            "'the link sir posted', 'that PDF'. Always include the jump_url in your answer.",
            query=("string", "A word from the filename, the link, or the message it was posted with."))
def find_resources(ctx, query):
    with db.conn() as c:
        _ensure(c)
        rows = c.execute(
            "SELECT title,kind,sender,ts,jump_url,context FROM resources "
            "WHERE guild_id IS ? AND (title LIKE ? OR context LIKE ?) ORDER BY ts DESC, id DESC LIMIT 8",
            (ctx.get("guild_id"), f"%{query}%", f"%{query}%")).fetchall()
    return [dict(r) for r in rows]


def setup(bot):
    with db.conn() as c:
        _ensure(c)
