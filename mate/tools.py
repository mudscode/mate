"""Tools the Q&A model can call. Adding one = one decorated function; the schema is built from the signature.
Handlers get a ctx dict (asker, asker_id, guild_id, chat_id, guild) first, then the model's arguments.
`guild` is the live discord.Guild (None in offline tests); handlers may be async."""
import inspect
import json
from datetime import datetime, timedelta

from . import db

TOOLS = []       # Responses API function schemas
HANDLERS = {}    # name -> python callable


def tool(description: str, **params):
    """params: name=(json_type, description). All params are required (strict mode)."""
    def deco(fn):
        TOOLS.append({
            "type": "function", "name": fn.__name__, "description": description, "strict": True,
            "parameters": {"type": "object", "additionalProperties": False, "required": list(params),
                           "properties": {k: {"type": t, "description": d} for k, (t, d) in params.items()}},
        })
        HANDLERS[fn.__name__] = fn
        return fn
    return deco


async def dispatch(name: str, args: dict, ctx: dict) -> str:
    fn = HANDLERS.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool {name}"})
    out = fn(ctx, **args)
    if inspect.isawaitable(out):
        out = await out
    return json.dumps(out, default=str)


@tool("List upcoming events for this chat: deadlines, quizzes, exams, room/time changes, plans, recent announcements.",
      days_ahead=("integer", "How far ahead to look. 7 for 'this week', 60 for 'this semester'."))
def list_events(ctx, days_ahead):
    return db.list_events(days_ahead, ctx.get("guild_id"))


@tool("Keyword search over the raw chat history and saved notes: who posted the slides, what the TA said, "
      "links, contact details.",
      query=("string", "A single keyword or short phrase."))
def search_messages(ctx, query):
    g = ctx.get("guild_id")
    return {"messages": db.search_messages(query, g), "notes": db.search_notes(query, g)}


@tool("Everything said in the chat recently, oldest first. Use for 'what did I miss?' style questions and summarise.",
      hours=("integer", "How many hours back to look. 24 for 'today', 168 for 'this week'."))
def recent_messages(ctx, hours):
    since = (datetime.now(db.TZ) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M")
    return db.recent_messages(since, ctx.get("guild_id"))


@tool("Save a fact the group asked you to remember (a contact, a link, a rule, a preference). "
      "Use when someone says 'remember that ...'.",
      note=("string", "The fact, in one self-contained sentence."))
def remember(ctx, note):
    db.add_note(ctx.get("guild_id"), ctx.get("chat_id"), ctx.get("asker", "?"), note)
    return {"saved": note}
