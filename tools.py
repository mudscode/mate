"""Tools the Q&A model can call. Adding one = one decorated function; the schema is built from the signature.
Handlers get a ctx dict (asker, chat_id) first, then the model's arguments."""
import json
from datetime import datetime, timedelta

import db

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


def dispatch(name: str, args: dict, ctx: dict) -> str:
    fn = HANDLERS.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool {name}"})
    return json.dumps(fn(ctx, **args), default=str)


@tool("List upcoming events for this chat: deadlines, quizzes, exams, room/time changes, plans, recent announcements.",
      days_ahead=("integer", "How far ahead to look. 7 for 'this week', 60 for 'this semester'."))
def list_events(ctx, days_ahead):
    return db.list_events(days_ahead, chat_id=ctx.get("chat_id"))


@tool("Keyword search over the raw chat history and saved notes: who posted the slides, what the TA said, "
      "links, contact details.",
      query=("string", "A single keyword or short phrase."))
def search_messages(ctx, query):
    return {"messages": db.search_messages(query), "notes": db.search_notes(query, ctx.get("chat_id"))}


@tool("Everything said in the chat recently, oldest first. Use for 'what did I miss?' style questions and summarise.",
      hours=("integer", "How many hours back to look. 24 for 'today', 168 for 'this week'."))
def recent_messages(ctx, hours):
    since = (datetime.now(db.TZ) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M")
    return db.recent_messages(since, ctx.get("chat_id"))


@tool("Save a fact the group asked you to remember (a contact, a link, a rule, a preference). "
      "Use when someone says 'remember that ...'.",
      note=("string", "The fact, in one self-contained sentence."))
def remember(ctx, note):
    db.add_note(ctx.get("chat_id"), ctx.get("asker", "?"), note)
    return {"saved": note}
