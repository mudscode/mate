"""Mirror logged events into the server's native Discord "Events" tab. Best effort: never raises."""
import re
from datetime import datetime, timedelta

import discord

from .config import TZ
PLACE = re.compile(r"(Room|Lab|Hall|Auditorium|Library)[^,.;]*", re.I)
_warned = False                              # print the missing-permission line once per process


def _fields(ev: dict):
    start = datetime.fromisoformat(ev["due_at"]).replace(tzinfo=TZ)
    m = PLACE.search(ev["details"] or "")
    return (ev["title"][:100], start, start + timedelta(hours=1),
            (ev["details"] or "")[:1000], (m.group(0).strip() if m else "See #chat")[:100])


async def sync(guild, ev: dict) -> int | None:
    """Create or update the scheduled event mirroring `ev`. Returns its Discord id, or None."""
    if guild is None or not ev or not ev.get("due_at"):
        return None
    try:
        name, start, end, description, location = _fields(ev)
    except ValueError:
        return None
    if start < datetime.now(TZ) + timedelta(minutes=5):   # Discord rejects start times in the past
        return None

    try:
        if ev.get("discord_event_id"):
            try:
                se = await guild.fetch_scheduled_event(int(ev["discord_event_id"]))
            except discord.NotFound:
                se = None
            if se is not None:
                if (se.name != name or se.start_time != start or se.end_time != end
                        or (se.description or "") != description or se.location != location):
                    await se.edit(name=name, start_time=start, end_time=end,
                                  description=description, location=location)
                return se.id
        se = await guild.create_scheduled_event(
            name=name, start_time=start, end_time=end, entity_type=discord.EntityType.external,
            location=location, privacy_level=discord.PrivacyLevel.guild_only, description=description)
        return se.id
    except discord.Forbidden:
        global _warned
        if not _warned:
            _warned = True
            print("discord_events: missing Manage Events permission")
        return None
    except discord.HTTPException as e:
        print(f"discord_events: {e}")
        return None
