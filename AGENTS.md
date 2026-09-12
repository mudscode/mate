# Mate — context for anyone (human or tool) working in this repo

## What this is
Mate is an agent that lives inside a university course Discord server and acts as the class's memory.
Students and the instructor talk normally. Mate silently extracts the facts that matter (quiz dates,
deadlines, exams, room changes, student plans like trips and study sessions, notes the group asks it to
keep, dated items in shared PDFs/screenshots) into SQLite, mirrors them into the server's Events tab,
answers questions like "when's the quiz?" or "what did I miss?" from memory, and posts reminders before
things are due without being asked.

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
- `tools.py`    `@tool` registry -> `TOOLS` / `dispatch`; `list_events` `search_messages` `recent_messages` `remember`
- `qa.py`       Responses API function-calling loop over `tools.TOOLS`, scoped to the asking channel
- `discord_events.py`  mirrors dated events into the server's native Events tab; updates on reschedule
- `db.py`       SQLite: messages, events (deduped by model-generated `key`), notes, reminders
- `try_extract.py`  offline extraction test, run this before touching Discord
- `PLAN.md`     timeline, cut lines, demo script, gotchas. Read it.

## Conventions
- Datetimes are ISO local strings `YYYY-MM-DDTHH:MM` in Asia/Karachi; string comparison orders them.
- Reasoning effort: `low` for chat lines, `medium` for documents. Model from `OPENAI_MODEL`, default `gpt-5-mini`.
- Event kinds: `deadline` `quiz` `exam` `class_change` `announcement` `plan`. `plan` is student-organised
  stuff (trips, study sessions, meetups) — Mate is the group's memory, not just course admin.
- Events dedupe on `(chat_id, kind, key)`. A reschedule updates in place and clears its reminders.
- Every dated event is mirrored as a native Discord scheduled event; the bot needs the **Manage Events**
  permission (invite permissions integer `283467942976`).
- `notes` table holds free-form facts from "remember that ..."; `search_messages` searches notes too.
- Adding a Q&A tool = one decorated function in `tools.py`. The schema is built from the signature.
- Reminders fire once at 24h and once at 2h before `due_at`.
- Heads-up: when a newly logged event lands on the same day as an existing one, Mate posts one
  unprompted line pointing out the clash.
- Question routing: a message is answered only if it contains `?` **and** a hint word
  (when/where/what/which/who/how/deadline/due/remind/missed). "anyone up for a trip Sunday?" is logged
  as a plan, not answered.

## Run
    cp .env.example .env   # fill DISCORD_BOT_TOKEN, OPENAI_API_KEY
    python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
    python try_extract.py  # sanity check extraction
    python bot.py

## Demo (4 min)
1. Channel is pre-seeded via `!backfill`. Ask "what's due this week?"
2. Instructor: "Quiz 3 moved to Thursday 9am." Bot reacts ✅. Ask again; answer changed, no duplicate,
   and the Events tab entry moved with it.
3. Drop `course_outline.pdf`. Bot reacts ✅; several events appear in `!schedule` and in the Events tab.
4. Student: "road trip Sunday, leaving 7am?" gets a ✅ too — and Mate posts a heads-up if it clashes.
5. `!tick` posts a reminder nobody asked for.
