"""Discord entry point. Run: python bot.py"""
import asyncio
import os

import discord
from discord.ext import commands, tasks

from mate import config, db, features, handlers, hooks, qa, reminders
from mate.handlers import EMOJI, fmt_when

intents = discord.Intents.default()
intents.message_content = True          # also enable "Message Content Intent" in the Developer Portal
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    db.init()
    if not reminder_loop.is_running():
        reminder_loop.start()
    print(f"Logged in as {bot.user}")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot and message.author.id not in config.TEST_BOT_IDS:
        return
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    replied_to_bot = (message.reference and isinstance(message.reference.resolved, discord.Message)
                      and message.reference.resolved.author == bot.user)
    if bot.user in message.mentions or replied_to_bot or handlers.looks_like_question(message.content):
        q = message.content.replace(bot.user.mention, "").strip()
        async with message.channel.typing():
            reply = await qa.answer(q, message.author.display_name, message.guild.id if message.guild else None,
                                    message.channel.id, message.author.id)
        await message.reply(reply, mention_author=False)
        return

    await handlers.ingest(message)


@bot.command()
async def backfill(ctx: commands.Context, limit: int = 500):
    """Read channel history from before the bot joined and extract events. !backfill 300"""
    msgs = [m async for m in ctx.channel.history(limit=limit, oldest_first=True) if not m.author.bot]
    counts = await asyncio.gather(*(handlers.ingest(m, react=False) for m in msgs))
    await ctx.send(f"Backfilled {len(msgs)} messages, found {sum(counts)} events.")


@bot.command()
async def schedule(ctx: commands.Context, days: int = 14):
    """Dump upcoming events. Fallback if Q&A misbehaves on stage."""
    evs = db.list_events(days, ctx.guild.id if ctx.guild else None)
    if not evs:
        return await ctx.send("Nothing upcoming.")
    await ctx.send("\n".join(f"{EMOJI.get(e['kind'], '•')} **{e['title']}** — {fmt_when(e['due_at'])}" for e in evs))


@bot.command()
async def tick(ctx: commands.Context):
    """Force the reminder check right now (demo)."""
    n = await reminders.run(bot)
    await hooks.fire(hooks.TICK, bot)
    await ctx.send(f"Reminder check done, sent {n}.")


@tasks.loop(minutes=10)
async def reminder_loop():
    await reminders.run(bot)
    await hooks.fire(hooks.TICK, bot)


features.setup_all(bot)

if __name__ == "__main__":
    bot.run(os.environ["DISCORD_BOT_TOKEN"])
