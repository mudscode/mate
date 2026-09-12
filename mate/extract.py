"""Turn one chat message (plus optional PDF/image attachments) into structured events.
One structured-output call. The model gets the message timestamp and weekday so relative
dates ('Friday', 'next week') resolve against the right anchor; Python then sanity-checks."""
import base64
import re
from datetime import datetime, timedelta
from typing import List, Literal, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from .config import MODEL, TZ

_client = None


def client() -> AsyncOpenAI:
    global _client                # lazy so importing the package never needs a key (tests)
    if _client is None:
        _client = AsyncOpenAI()
    return _client


class Event(BaseModel):
    key: str = Field(description="Stable slug for the THING, not its date: 'quiz-3', 'assignment-2', 'midterm', "
                                 "'lecture-room-change', 'murree-trip'. Never put a date in the key. A reschedule or correction of the same item MUST reuse the same key.")
    title: str = Field(description="Short, e.g. 'Quiz 3 (Ch. 5)', 'Assignment 2 due', 'Lecture moved to Room 204'")
    kind: Literal["deadline", "quiz", "exam", "class_change", "announcement", "plan"] = Field(
        description="plan = anything social or organised by students: trip, study session, meetup, party, match.")
    due_at: Optional[str] = Field(
        description="Local datetime 'YYYY-MM-DDTHH:MM' in Asia/Karachi. Resolve relative dates from the message "
                    "timestamp. If a day but no time is given use 23:59 for deadlines and 09:00 otherwise. "
                    "null only when no concrete date exists.")
    details: str = Field(description="Everything a student needs: chapters, room, format, submission link, etc.")
    confidence: float = Field(ge=0, le=1)


class Extraction(BaseModel):
    events: List[Event]


SYSTEM = """You are the memory of a class group chat (students plus instructor). Extract anything the group
will need to remember later: deadlines, quizzes, exams, class/room/time changes, announcements, and plans the
students make among themselves (trips, study sessions, meetups, parties, matches).

Extract an event ONLY when the message states something with a real date, day, or clear relative time
(tomorrow, Friday, next Monday, 'by end of week'). Vague talk ('quiz soon', 'we should study') is NOT an event.
Chit-chat, jokes, and complaints produce an empty list. A proposal with a concrete time ('road trip Sunday,
leaving 7am?') IS a plan, even if phrased as a question.

Messages marked [instructor/staff] are authoritative: extract with high confidence.
A student relaying an instructor ('sir said quiz is Monday') is medium confidence.
A student guessing ('I think the quiz is Monday?') is low confidence.

For a course outline, syllabus, or schedule document, extract every dated item as its own event.
Never invent dates. If a date is genuinely unspecified, set due_at to null."""


WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _plausible(e: Event, anchor: datetime, text: str = "") -> bool:
    """Python checks the model's date: window, and that it lands on the weekday / 'tomorrow' the text names."""
    if e.confidence < 0.5:
        return False
    if e.due_at is None:                      # undated facts live in the chat log, not the events table
        return False
    try:
        due = datetime.fromisoformat(e.due_at)
    except ValueError:
        return False
    a = anchor.replace(tzinfo=None)
    if not (a - timedelta(days=2) <= due <= a + timedelta(days=200)):
        return False
    t = text.lower()
    named = [i for i, w in enumerate(WEEKDAYS) if re.search(rf"\b{w[:3]}[a-z]*\b", t)]
    if len(named) == 1 and due.weekday() != named[0]:
        return False
    if "tomorrow" in t and due.date() != (a + timedelta(days=1)).date():
        return False
    return True


async def extract(text: str, sender: str, sent_at: datetime, is_staff: bool = False,
                  attachments: list[tuple[bytes, str]] = (), effort: str = "low") -> List[Event]:
    """attachments: list of (bytes, mime). effort: 'low' for chat lines, 'medium' for documents."""
    local = sent_at.astimezone(TZ)
    content = []
    for i, (data, mime) in enumerate(attachments):
        b64 = base64.standard_b64encode(data).decode()
        if mime == "application/pdf":
            content.append({"type": "input_file", "filename": f"attachment{i}.pdf",
                            "file_data": f"data:application/pdf;base64,{b64}"})
        elif mime.startswith("image/"):
            content.append({"type": "input_image", "image_url": f"data:{mime};base64,{b64}"})
    who = f"{sender} [instructor/staff]" if is_staff else sender
    content.append({"type": "input_text", "text":
        f"Message sent {local.strftime('%A %Y-%m-%d %H:%M')} (Asia/Karachi) by {who}:\n\n{text or '(no text; see attachment)'}"})

    resp = await client().responses.parse(
        model=MODEL,
        instructions=SYSTEM,
        reasoning={"effort": effort},
        input=[{"role": "user", "content": content}],
        text_format=Extraction,
    )
    if resp.output_parsed is None:
        return []
    return [e for e in resp.output_parsed.events if _plausible(e, local, text or '')]
