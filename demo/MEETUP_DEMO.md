# Mate at AI Tinkerers Islamabad / Rawalpindi, October Demo Meetup

Saturday 17 October 2026, 2 to 5 PM PKT. Slide-free, live code, about 5 minutes plus questions (confirm with the host).
Their rule: answer "how did you build this", never "why should someone use it".

## Pitch, 30 seconds

Mate is a Discord bot that acts as a class's memory. Students and the instructor talk normally. Mate silently
pulls out anything with a date, puts it in SQLite and the server's Events tab, answers "when's the quiz?" from
memory, and reminds people before things are due without being asked. One Python process, one model, one
SQLite file. Agent, not chatbot: it decides what to log, remembers across sessions, and acts unprompted.

## Three features, live, about 2.5 minutes

Paste these from a text file. Keep the bot log visible in a second window so the room sees the calls happen.

1. **Log and reschedule.** The thesis in one minute.
   - Type: `Quiz 4 is on Thursday 10am, chapters 7 and 8. Room 104.`
   - Expect: only a ✅. Open the Events tab, the entry is there with the room as location.
   - Type: `Quiz 4 moved to Friday 11am, same room.`
   - Expect: ✅, the Events entry moves, still one entry. Say: the key is the thing, not the date, so this is an edit.
2. **Ask in Roman Urdu, no mention.**
   - Type: `quiz kab hai?`
   - Expect: a reply naming Friday 11:00. Say: Python checked the weekday the model proposed before it was stored.
3. **Cancel and undo.** Three ways to correct an agent that writes on its own.
   - Type: `study session for quiz 4 Friday 6pm at the library?`
   - Expect: ✅, a heads-up that it lands on the quiz day, an RSVP poll.
   - Type: `the study session is canceled`
   - Expect: ✅ only. Poll gone, Events entry gone, no new plan.
   - React ❌ on the Quiz 4 message. Expect: ✅ becomes 🗑️, Events entry gone. Nothing posted.

## Code to show, about 90 seconds, font 20pt or larger

- `mate/extract.py`, `_plausible` and `day_words_match`: the model proposes, Python decides.
- `mate/db.py`, `_match`: key, then same minute, then similar title with numbers agreeing.
- `mate/hooks.py` and `mate/tools.py` together: the entire framework, 97 lines. Scroll it once.

## Builder takeaways, about 60 seconds, pick what fits the clock

1. **A second account on the real platform tests the agent.** `scripts/e2e.py` is a tester bot that creates a
   scratch channel, plays student and instructor, asserts 23 checks against the running bot, and cleans up.
   It found what fakes could not: a shared lock starving a live message behind Discord's rate limit, Quiz 42
   merging into Quiz 2, the model writing Thursday on a Wednesday, and this week a regression in two hours.
   Say "scripted second account", not "autonomous agent"; it is scripted.
2. **No framework. Own the hundred lines.** Core 817 lines, hooks plus tool registry 97, seven features 690,
   tests 1552. Every feature is one file that registers at import. When it breaks you can read all of it.
3. **Code validates what the model proposes.** Dates are checked against the weekday in the text, a window,
   the midnight rule. The same pattern fits amounts, IDs, names. It is why a small model is enough.
4. **Context engineering is also subtraction.** Adding the weekday name to the message anchor fixed dates.
   Adding a list of what Mate already remembered made it worse: a lab became the quiz. The e2e run decided.

## Numbers, if asked

47 commits. 80 offline tests, 4 live model tests, 23 end-to-end checks. Model gpt-5-mini via the Responses API,
structured outputs for extraction, function calling for Q&A. Reasoning effort low for chat, medium for PDFs.
Dependencies: discord.py, openai, pydantic, python-dotenv.

## Not shown, one sentence each if asked

- `!backfill` and the PDF: one model call per message and Discord allows about five Events creations a minute.
- Reminders, personal DMs, the Sunday digest: time-based, nothing to see live. `!tick` forces the check.
- The hackathon video: against the rules, and the live thing is better.

## Checklist

Night before
- `python scripts/reset.py` so memory and the Events tab are empty. It keeps `!context`.
- Check `!context` reads as the CS-321 sentence. Set it if not.
- Optional: paste `demo/seed_chat.txt` as one message so the Events tab is not empty on stage. Its dates are
  after 17 October and do not collide with the live messages above.
- `scripts/test.sh` green. Run `python scripts/e2e.py` once against the running bot: 23/23.

Before walking up
- Exactly one `bot.py` running. Check with `ps`. Two processes on one token double every action.
- `.env` key works (the bot reads it once at start; restart after any change).
- Terminal font up, bot log window open, the messages file open, Discord zoomed in.
- Phone hotspot ready as a second network.

Fallbacks
- Model slow or down: `!schedule` lists memory with no model call. Say so and keep going.
- Events tab did not update: it mirrors last and is rate-limited; show the `!schedule` line instead.
- A message was mis-logged: ❌ it. That is the undo demo anyway.
