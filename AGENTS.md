# Mate — context for anyone (human or tool) working in this repo

## What this is
Mate is an agent that lives inside a university course Discord server and acts as the class's memory.
Students and the instructor talk normally. Mate silently extracts the facts that matter (quiz dates,
deadlines, exams, room changes, dated items in shared PDFs/screenshots) into SQLite, answers questions
like "when's the quiz?" from memory, and posts reminders before things are due without being asked.

Built solo for the AI Tinkerers "Agents, Everywhere" hackathon, Islamabad, 12 Sep 2026. Team: Single Threaded.
Pitch: it decides what to log, remembers across sessions, and acts unprompted. Agent, not chatbot.

## Hard constraints
- Deadline is today. Prefer the smallest change that makes the demo work. No refactors, no new frameworks.
- LLM provider is OpenAI (Responses API) and only OpenAI. Do not introduce any other provider or SDK.
- One Python process: discord.py + openai + sqlite3. No web server, no queue, no ngrok.
- Never let the model do date arithmetic that Python can check. Model proposes ISO datetime, Python validates.
- Silence is the feature: the bot reacts with ✅ when it logs something; it only replies when mentioned,
  replied to, or asked a question.

## Layout
- `bot.py`      Discord client, handlers, `!backfill` `!schedule` `!tick`, 10-min reminder loop
- `extract.py`  message + attachments -> list[Event] via `responses.parse` + Pydantic schema
- `qa.py`       Responses API function-calling loop over `list_events` / `search_messages`
- `db.py`       SQLite: messages, events (deduped by model-generated `key`), reminders
- `try_extract.py`  offline extraction test, run this before touching Discord
- `PLAN.md`     timeline, cut lines, demo script, gotchas. Read it.

## Conventions
- Datetimes are ISO local strings `YYYY-MM-DDTHH:MM` in Asia/Karachi; string comparison orders them.
- Reasoning effort: `low` for chat lines, `medium` for documents. Model from `OPENAI_MODEL`, default `gpt-5-mini`.
- Events dedupe on `(chat_id, kind, key)`. A reschedule updates in place and clears its reminders.
- Reminders fire once at 24h and once at 2h before `due_at`.

## Run
    cp .env.example .env   # fill DISCORD_BOT_TOKEN, OPENAI_API_KEY
    python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
    python try_extract.py  # sanity check extraction
    python bot.py

## Demo (4 min)
1. Channel is pre-seeded via `!backfill`. Ask "what's due this week?"
2. Instructor: "Quiz 3 moved to Thursday 9am." Bot reacts ✅. Ask again; answer changed, no duplicate.
3. Drop the course outline PDF. Bot reacts, several events appear in `!schedule`.
4. `!tick` posts a reminder nobody asked for.
