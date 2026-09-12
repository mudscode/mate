"""Plug-in points. A feature module registers async callbacks here at import time; bot.py never changes.
    @hooks.on_event_logged      async def f(message, event_row: dict, status: 'inserted'|'updated')
    @hooks.on_message_ingested  async def f(message)          # every non-command, non-question message
    @hooks.on_tick              async def f(bot)              # every 10 minutes and on !tick
Errors in a hook are printed and swallowed so one feature can't take the bot down."""
import traceback

EVENT_LOGGED = []
MESSAGE_INGESTED = []
TICK = []


def on_event_logged(fn):
    EVENT_LOGGED.append(fn)
    return fn


def on_message_ingested(fn):
    MESSAGE_INGESTED.append(fn)
    return fn


def on_tick(fn):
    TICK.append(fn)
    return fn


async def fire(callbacks, *args):
    for cb in callbacks:
        try:
            await cb(*args)
        except Exception:
            print(f"hook {cb.__module__}.{cb.__name__} failed:")
            traceback.print_exc()
