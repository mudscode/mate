"""Answer questions from memory. Function-calling loop: the model decides which tools to call
(events table, raw chat history, notes) and then writes a short answer."""
import json
from datetime import datetime

from openai import AsyncOpenAI

from . import tools
from .config import MODEL, TZ

_client = None


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI()
    return _client

SYSTEM = """You are Mate, the memory of a class group chat. Students ask you about deadlines, quizzes, exams,
room changes, plans, and things people said. Use the tools; never answer from guesswork.
Now is {now} (Asia/Karachi). Reply in 1-3 plain sentences, no markdown headers, no preamble.
For 'what did I miss' questions, summarise the recent messages in a few bullet-free sentences.
When a tool result has a jump_url, include it verbatim so the student can click it.
If nothing matches, say so and suggest asking the instructor.
{context}"""


async def answer(question: str, asker: str, guild_id: int | None = None, chat_id: int | None = None,
                 asker_id: int | None = None, guild=None, context: str = "") -> str:
    now = datetime.now(TZ).strftime("%A %Y-%m-%d %H:%M")
    ctx = {"asker": asker, "asker_id": asker_id, "guild_id": guild_id, "chat_id": chat_id, "guild": guild}
    about = f"About this group: {context}" if context else ""
    kwargs = dict(model=MODEL, instructions=SYSTEM.format(now=now, context=about), tools=tools.TOOLS)
    resp = await client().responses.create(input=[{"role": "user", "content": f"{asker} asks: {question}"}], **kwargs)
    for _ in range(6):  # tool-call rounds
        calls = [o for o in resp.output if o.type == "function_call"]
        if not calls:
            break
        outputs = [{"type": "function_call_output", "call_id": c.call_id,
                    "output": await tools.dispatch(c.name, json.loads(c.arguments), ctx)} for c in calls]
        resp = await client().responses.create(previous_response_id=resp.id, input=outputs, **kwargs)
    return (resp.output_text or "").strip() or "I don't have anything on that."
