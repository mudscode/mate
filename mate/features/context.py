"""context feature: one sentence about this group, injected into both the extraction and Q&A prompts.

`!context This is the CS-321 Operating Systems class; the instructor is Dr. Ahmed.` is stored per server
in `settings`; handlers.py and bot.py already pass it to extract.extract and qa.answer, so the same code
reads a class, a hackathon team or a football club correctly.
"""
from .. import db, tools

KEY = "context"
MAX = 300
EXAMPLE = ("No context set. Try: !context This is the CS-321 Operating Systems class; "
           "the instructor is Dr. Ahmed.")


@tools.tool("The one-line description of this group set with !context (course name, instructor, what the "
            "group is for).")
def group_context(ctx):
    return {"context": db.get_setting(ctx.get("guild_id"), KEY)}


def setup(bot):
    @bot.command()
    async def context(ctx, *, text: str = ""):
        """Show, set or clear this server's one-line description of the group."""
        if ctx.guild is None:
            await ctx.send("Context is per server — run !context in the server's channel, not in a DM.")
            return
        text = (text or "").strip()
        if not text:
            current = db.get_setting(ctx.guild.id, KEY)
            await ctx.send(f"I read this server as: {current}" if current else EXAMPLE)
            return
        if text.lower() == "clear":
            db.set_setting(ctx.guild.id, KEY, "")
            await ctx.send("Cleared. I'll go back to reading this server as a generic group.")
            return
        text = text[:MAX]
        db.set_setting(ctx.guild.id, KEY, text)
        await ctx.send(f"Got it. I'll read this server as: {text}")
