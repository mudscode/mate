"""Sanity-check extraction without Discord: python scripts/try_extract.py  (needs OPENAI_API_KEY in .env)"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mate import extract

SAMPLES = [
    ("Sir", True,  "Quiz 3 will be on Monday 10am, chapters 5 and 6. Same room."),
    ("Ali", False, "anyone got the slides from today"),
    ("TA",  True,  "Assignment 2 deadline extended to Friday midnight, submit on LMS"),
    ("Sara",False, "i think quiz might be next week? not sure"),
    ("Sir", True,  "Tomorrow's lecture is in Room 204 instead of the lab"),
    ("Ali", False, "@everyone anyone up for a day road trip to Murree on Sunday? leaving 7am from the main gate"),
    ("Sara",False, "study session for quiz 2 at the library tomorrow 6pm, bring the slides"),
]

async def main():
    for sender, staff, text in SAMPLES:
        evs = await extract.extract(text, sender, datetime.now(extract.TZ), staff)
        print(f"\n> {text}")
        for e in evs:
            print(f"   {e.kind:13} {e.key:14} {e.due_at}  {e.title}  (conf {e.confidence})")
        if not evs:
            print("   (no event)")

asyncio.run(main())
