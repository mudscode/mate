"""Unprompted nudges: 24h and 2h before anything is due, posted to the channel the item came from."""
from . import db
from .handlers import EMOJI, fmt_when


async def run(bot) -> int:
    sent = 0
    for ev, kind in db.due_reminders():
        channel = bot.get_channel(ev["chat_id"])
        if channel is None:
            continue
        lead = "tomorrow" if kind == "24h" else "in about 2 hours"
        await channel.send(f"{EMOJI.get(ev['kind'], '⏰')} Reminder: **{ev['title']}** is {lead} ({fmt_when(ev['due_at'])}). {ev['details']}")
        db.mark_reminder(ev["id"], kind)
        sent += 1
    return sent
