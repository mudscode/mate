# Mate

## Setup (10 min)
1. https://discord.com/developers/applications → New Application → Bot → Reset Token → copy.
   On the same Bot page, enable **Message Content Intent** (required; otherwise message text is empty).
2. OAuth2 → URL Generator → scope `bot` → permissions: View Channels, Send Messages, Read Message History,
   Add Reactions, Attach Files. Open the URL, add to your server.
3. Create roles named `Instructor` / `TA` on the server; give one teammate the Instructor role.
4. `cp .env.example .env` and fill in both tokens.
5. `python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && python bot.py`

## Seed the demo
Paste a real class chat into the channel (one message per line is fine), then `!backfill 300`.

## Commands
- `!backfill [n]` – extract events from the last n messages
- `!schedule [days]` – dump upcoming events (fallback for Q&A)
- `!tick` – run the reminder check now (demo)
- Mention the bot, reply to it, or ask a question ending in `?` to query memory.

## Demo assets
- `seed_chat.txt` – paste into the class channel as one message; the bot extracts ~10 events from it
- `course_outline.pdf` – drop into the channel; adds the rest of the semester in one go
