# Mate

Mate is the memory of a class Discord server. People talk normally; it quietly remembers.

## What it does
- Silently extracts what matters from ordinary chat — deadlines, quizzes, exams, room changes, student
  plans (trips, study sessions) — and from dropped PDFs and screenshots. Reacts ✅, doesn't chatter.
- Answers from memory when asked: "when's the quiz?", "what's due this week?", "what did I miss?",
  and saves facts on request with "remember that ...".
- Mirrors every dated event into the server's native **Events** tab, and moves it when plans change.
- Posts an RSVP poll when someone floats a plan, so nobody types +1 twenty times.
- Finds the files and links people shared: "where are the lecture 4 slides?" → filename, who posted it,
  and a jump link straight to the message.
- Sets private reminders: "remind me 2 hours before assignment 1" → a DM only you get, which follows the
  event if the instructor moves it.
- Drops a "This week" digest into the busiest channel on Sunday evening, grouped by day.
- Acts unprompted: reminders 24h and 2h before anything is due, plus a heads-up when a newly logged
  event clashes with something already on the same day.
- Dedupes by the thing, not the date: "Quiz 3 moved to Thursday" updates the existing event in place.

## Setup (10 min)
1. https://discord.com/developers/applications → New Application → Bot → Reset Token → copy.
   On the same Bot page, enable **Message Content Intent** (required; otherwise message text is empty).
2. OAuth2 → URL Generator → scope `bot` → permissions: View Channels, Send Messages, Read Message History,
   Add Reactions, Attach Files, **Manage Events** (needed for the Events tab mirror).
   Open the URL, add to your server.
3. Create roles named `Instructor` / `TA` on the server; give one teammate the Instructor role.
4. `cp .env.example .env` and fill in both tokens.
5. `python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && python bot.py`

## Seed the demo
Paste a real class chat into the channel (one message per line is fine), then `!backfill 300`.

## Commands
- `!backfill [n]` – extract events from the last n messages
- `!schedule [days]` – dump upcoming events (fallback for Q&A)
- `!digest` – this week's events grouped by day (same text as the Sunday post)
- `!tick` – run the reminder check now (demo)
- Mention the bot, reply to it, or ask a question containing `?` and a hint word
  (when/where/what/which/who/how/deadline/due/remind/missed):
  - "@Mate what's due this week?"
  - "what did I miss?"
  - "@Mate remember that the TA's email is ta@uni.edu"
  - "@Mate where are the lecture 4 slides?"
  - "@Mate remind me 2 hours before assignment 1"
  - "@Mate what reminders do I have?"
  - "@Mate did anyone RSVP to the trip?"

## Testing
- `scripts/test.sh` – offline suite; fake discord.py, throwaway DB, no network.
- `RUN_LIVE=1 scripts/test.sh` – also runs the tests that call the real model.
- `python scripts/e2e.py <channel_id>` – real Discord: a second tester bot posts and checks a running
  `bot.py`. Needs `MATE_TEST_BOT_TOKEN` and `MATE_TEST_BOT_IDS` in `.env`.
- `python scripts/reset.py` – fresh start: deletes `mate.db` and the bot's own scheduled events.
- `python scripts/try_extract.py` – eyeball extraction on sample lines before touching Discord.

## Layout
```
bot.py                 client, commands, 10-min loop
mate/
  config.py db.py extract.py qa.py tools.py
  handlers.py reminders.py discord_events.py hooks.py
  features/            polls.py resources.py personal_reminders.py digest.py
tests/                 fakes.py + unit tests (test_live.py needs RUN_LIVE=1)
scripts/               test.sh try_extract.py e2e.py reset.py
demo/                  seed_chat.txt course_outline.pdf
```
A feature is one file in `mate/features/`: it registers hooks and Q&A tools on import, owns its tables,
and is listed in `mate/features/__init__.py`. `bot.py` doesn't change.

## Demo assets
- `demo/seed_chat.txt` – paste into the class channel as one message; the bot extracts ~10 events from it
- `demo/course_outline.pdf` – drop into the channel; adds the rest of the semester in one go
