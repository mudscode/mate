# Mate

Mate is the memory of a class Discord server. People talk normally; it quietly remembers.

## What it does
- Silently extracts what matters from ordinary chat — deadlines, quizzes, exams, room changes, student
  plans (trips, study sessions) — and from dropped PDFs and screenshots. Reacts ✅, doesn't chatter.
- Answers from memory when asked: "when's the quiz?", "what's due this week?", "what did I miss?",
  and saves facts on request with "remember that ...".
- Mirrors every dated event into the server's native **Events** tab, and moves it when plans change.
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
- `!tick` – run the reminder check now (demo)
- Mention the bot, reply to it, or ask a question containing `?` and a hint word
  (when/where/what/which/who/how/deadline/due/remind/missed):
  - "@Mate what's due this week?"
  - "what did I miss?"
  - "@Mate remember that the TA's email is ta@uni.edu"

## Demo assets
- `seed_chat.txt` – paste into the class channel as one message; the bot extracts ~10 events from it
- `course_outline.pdf` – drop into the channel; adds the rest of the semester in one go
