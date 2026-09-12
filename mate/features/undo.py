"""undo feature: one-click undo for anything Mate logged from a message.

Mate writes memory silently — it reads a line, decides there is a fact in it, and reacts ✅. That is the
right default, but it is also the one place where being wrong is annoying: a joke logged as a quiz, a
"maybe Friday?" turned into a deadline, an outline PDF that produced five events nobody wanted. Asking the
model to undo it ("forget the quiz") works, but it costs a sentence, a model call, and a guess at which row
was meant.

So: react ❌ to the message Mate reacted ✅ to, and everything that message produced disappears. The
message is the handle — `events.source_msg_id` already records which message each row came from, so no new
table is needed. Undo is the same cleanup memory_edit.forget_event does, applied to every row at once:
rows go status='superseded' (never deleted — the message stays in memory, only the derived fact goes),
their polls and personal reminders are dropped, and each mirrored Discord scheduled event is deleted.

Only the message's author or staff may undo, so one student cannot wipe another's plans. Nothing is posted
in the channel: Mate swaps its ✅ for 🗑️ and says nothing. Silence is the feature, in both directions.
"""
import sqlite3
import traceback

import discord

from .. import db, handlers

_bot = None                      # set by setup(); the raw-reaction listener gets no bot argument


async def forget_message(guild, message_id) -> int:
    """Undo everything logged from one message. Supersedes its active events, drops their polls and
    personal reminders, deletes the mirrored Discord events. Returns how many events were forgotten."""
    with db.conn() as c:
        rows = c.execute("SELECT id, discord_event_id FROM events WHERE source_msg_id=? AND status='active'",
                         (message_id,)).fetchall()
        for r in rows:
            c.execute("UPDATE events SET status='superseded' WHERE id=?", (r["id"],))
            for table in ("polls", "personal_reminders"):     # feature tables; a fresh DB may not have them
                try:
                    c.execute(f"DELETE FROM {table} WHERE event_id=?", (r["id"],))
                except sqlite3.OperationalError:
                    pass

    if guild is not None:
        for r in rows:
            if not r["discord_event_id"]:
                continue
            try:
                se = await guild.fetch_scheduled_event(int(r["discord_event_id"]))
                await se.delete()
            except (discord.NotFound, discord.HTTPException) as e:
                print(f"undo: can't delete scheduled event {r['discord_event_id']}: {e}")
    return len(rows)


async def on_raw_reaction_add(payload):
    """❌ on a message Mate logged from = undo it. Raw, so it works on messages from before this run."""
    try:
        if str(payload.emoji) != "❌" or payload.guild_id is None:
            return
        if _bot is None or payload.user_id == _bot.user.id:
            return

        with db.conn() as c:
            rows = c.execute("SELECT id, discord_event_id FROM events WHERE source_msg_id=? AND status='active'",
                             (payload.message_id,)).fetchall()
        if not rows:                                   # nothing was logged from this message: stay silent
            print(f"undo: nothing active logged from message {payload.message_id}")
            return

        channel = _bot.get_channel(payload.channel_id) or await _bot.fetch_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        guild = getattr(channel, "guild", None) or _bot.get_guild(payload.guild_id)
        reactor = payload.member or (guild.get_member(payload.user_id) if guild else None)
        if reactor is None:
            print(f"undo: can't resolve reactor {payload.user_id}")
            return
        if reactor.id != message.author.id and not handlers.is_staff(reactor):
            print(f"undo: {reactor.display_name} may not undo {message.author.display_name}'s message")
            return                                     # only the person who said it, or staff, may undo it

        n = await forget_message(guild, payload.message_id)
        print(f"undo: forgot {n} event(s) from message {payload.message_id} on ❌ by {reactor.display_name}")
        try:
            await message.remove_reaction("✅", _bot.user)
            await message.add_reaction("🗑️")           # the only acknowledgement; nothing is posted
        except discord.HTTPException:
            pass
    except Exception:
        print("undo: reaction handler failed:")
        traceback.print_exc()


def setup(bot):
    """Nothing to create: undo works on the events table db.init() already made."""
    global _bot
    _bot = bot
    bot.add_listener(on_raw_reaction_add, "on_raw_reaction_add")
