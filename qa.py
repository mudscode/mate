"""Answer questions from memory. Function-calling loop: the model decides whether to look at the
events table, the raw chat history, or both, then writes a short answer."""
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI

import db

TZ = ZoneInfo("Asia/Karachi")
client = AsyncOpenAI()
MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

TOOLS = [
    {
        "type": "function",
        "name": "list_events",
        "description": "List upcoming class events: deadlines, quizzes, exams, room/time changes, recent announcements.",
        "parameters": {
            "type": "object",
            "properties": {"days_ahead": {"type": "integer",
                                          "description": "How far ahead to look in days. 7 for 'this week', 60 for 'this semester'."}},
            "required": ["days_ahead"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "search_messages",
        "description": "Keyword search over the raw chat history, for anything the events list can't answer "
                       "(who posted the slides, what the TA said about grading, a link someone shared).",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "A single keyword or short phrase."}},
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def _dispatch(name: str, args: dict) -> str:
    if name == "list_events":
        return json.dumps(db.list_events(args.get("days_ahead", 14)), default=str)
    if name == "search_messages":
        return json.dumps(db.search_messages(args.get("query", "")), default=str)
    return json.dumps({"error": f"unknown tool {name}"})


SYSTEM = """You are the memory of a university course group chat. Students ask you about deadlines,
quizzes, exams, room changes and things people said. Use the tools; never answer from guesswork.
Now is {now} (Asia/Karachi). Reply in 1-3 plain sentences, no markdown headers, no preamble.
If nothing matches, say so and suggest asking the instructor."""


async def answer(question: str, asker: str) -> str:
    now = datetime.now(TZ).strftime("%A %Y-%m-%d %H:%M")
    resp = await client.responses.create(
        model=MODEL,
        instructions=SYSTEM.format(now=now),
        tools=TOOLS,
        input=[{"role": "user", "content": f"{asker} asks: {question}"}],
    )
    for _ in range(6):  # tool-call rounds
        calls = [o for o in resp.output if o.type == "function_call"]
        if not calls:
            break
        outputs = [{"type": "function_call_output", "call_id": c.call_id,
                    "output": _dispatch(c.name, json.loads(c.arguments))} for c in calls]
        resp = await client.responses.create(
            model=MODEL,
            instructions=SYSTEM.format(now=now),
            tools=TOOLS,
            previous_response_id=resp.id,
            input=outputs,
        )
    return (resp.output_text or "").strip() or "I don't have anything on that."
