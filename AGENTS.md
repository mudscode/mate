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
- Demo is today. Prefer the smallest change that makes the demo work. No new frameworks or dependencies.
- LLM provider is OpenAI (Responses API) and only OpenAI. Do not introduce any other provider or SDK.
- One Python process: discord.py + openai + sqlite3. No web server, no queue, no ngrok.
- Never let the model do date arithmetic that Python can check. Model proposes ISO datetime, Python validates.
- Silence is the feature: the bot reacts with ✅ when it logs something; it only replies when mentioned,
  replied to, or asked a question.

## Layout
- `bot.py`                  entry point: client, `!backfill` `!schedule` `!tick`, 10-min loop, `features.setup_all(bot)`
- `mate/config.py`          loads `.env`; `TZ` `MODEL` `DB_PATH` `STAFF_ROLES` `TEST_BOT_IDS`
- `mate/db.py`              SQLite: messages, events (deduped by model-generated `key`), notes, reminders
- `mate/extract.py`         message + attachments -> list[Event] via `responses.parse` + Pydantic schema
- `mate/qa.py`              Responses API function-calling loop over `tools.TOOLS`, scoped to the asker's server
- `mate/tools.py`           `@tool` registry -> `TOOLS` / `dispatch`; handlers get a ctx dict first
- `mate/handlers.py`        ingest (store, extract, react, heads-up), question routing, fires hooks
- `mate/reminders.py`       24h/2h nudges posted back to the channel the item came from
- `mate/discord_events.py`  mirrors dated events into the server's native Events tab; updates on reschedule
- `mate/hooks.py`           `on_event_logged` / `on_message_ingested` / `on_tick`; errors are printed, not raised
- `mate/features/`          `polls` `resources` `personal_reminders` `digest` `context` `memory_edit` `undo` — one file each
- `tests/`                  `fakes.py` (fake discord.py) + unit tests; `test_live.py` gated by `RUN_LIVE=1`
- `scripts/`                `test.sh` `try_extract.py` `e2e.py` `reset.py` `seed.py`
- `demo/`                   `seed_chat.txt` (paste as one message), `course_outline.pdf`, `VIDEO_SCRIPT.md`
- `PLAN.md`                 timeline, cut lines, demo script, gotchas. Read it.

## How to add a feature
1. One module in `mate/features/`. Register `@hooks.on_*` callbacks and `@tools.tool` functions at import time.
2. `def setup(bot)` runs its own `CREATE TABLE IF NOT EXISTS` and registers any `@bot.command()`.
3. Add the module to `ALL` in `mate/features/__init__.py`. `bot.py` never changes.
4. Write `tests/test_<name>.py` against `tests/fakes.py` — no Discord, no network.

## Testing
- `scripts/test.sh` — the offline suite: fakes for discord.py, a throwaway DB, no network.
- `RUN_LIVE=1 scripts/test.sh` — also runs `tests/test_live.py`, which makes real model calls.
- `python scripts/e2e.py` — real Discord: a second "tester" bot creates a scratch channel, plays student and
  instructor against a running `bot.py`, asserts 23 checks, and cleans up. Needs only `MATE_TEST_BOT_TOKEN`
  in `.env`; the tester's id is derived from the token.
- `python scripts/reset.py` — fresh start: deletes `mate.db` and every scheduled event this bot created,
  keeping per-server `!context`. `python scripts/seed.py` re-posts the demo chat and PDF.

## Conventions
- Datetimes are ISO local strings `YYYY-MM-DDTHH:MM` in Asia/Karachi; string comparison orders them.
- Reasoning effort: `low` for chat lines, `medium` for documents. Model from `OPENAI_MODEL`, default `gpt-5-mini`.
- Memory is scoped per server (`guild_id`); `chat_id` is the channel an item came from, used for posting back.
- Event kinds: `deadline` `quiz` `exam` `class_change` `announcement` `plan`. `plan` is student-organised
  stuff (trips, study sessions, meetups) — Mate is the group's memory, not just course admin.
- Events dedupe on the model's `key` within a server; fallback is same kind at the same minute, or a
  near-identical title within a day. A reschedule updates in place and clears its reminders.
- Every dated event is mirrored as a native Discord scheduled event; the bot needs the **Manage Events**
  permission (invite permissions integer `283467942976`).
- `notes` table holds free-form facts from "remember that ..."; `search_messages` searches notes too.
- Q&A tools: `list_events` `search_messages` `recent_messages` `remember` `remind_me` `my_reminders`
  `plan_poll` `find_resources` `update_event` `forget_event` `group_context`. Adding one = one decorated
  function; the schema is built from the signature.
- Features own their tables (`polls`, `resources`, `personal_reminders`, `digests`) and create them on demand.
- Reminders fire once at 24h and once at 2h before `due_at`, in-channel. Personal reminders are DMs and
  recompute their fire time every tick, so a rescheduled event drags them along.
- Heads-up: when a newly logged event lands on the same day as an existing one, Mate posts one
  unprompted line pointing out the clash.
- Question routing: a message is answered if it contains `?` **and** a hint word
  (when/where/what/which/who/how/deadline/due/remind/missed), or is a short question-word opener.
  "anyone up for a trip Sunday?" is logged as a plan, not answered.

- Chat may be English, Urdu or Roman Urdu; the prompt maps kal/parso/jumma etc., and `extract._plausible`
  checks the model's date against those words in Python. A deadline at 00:00 becomes 23:59 of the day before.
- `!context <one sentence>` per server is injected into both prompts (settings table). Same code, any group.
- Memory is editable by talking: `update_event` (Python-validated date) and `forget_event` (also removes the
  Discord event). Both resolve "quiz 3" / "the trip" to the soonest matching upcoming event.

- Undo: ❌ from the author or staff on a message Mate logged from supersedes its events, drops their
  polls/personal reminders, deletes the Discord events, and swaps ✅ for 🗑️. No message posted.

## Run
    cp .env.example .env   # fill DISCORD_BOT_TOKEN, OPENAI_API_KEY
    python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
    python scripts/try_extract.py  # sanity check extraction
    python bot.py

## Demo
Video (2 min): https://youtu.be/n8jtak_XPLg — script in `demo/VIDEO_SCRIPT.md`. Live version:
1. Channel is pre-seeded via `!backfill`. Ask "what's due this week?"
2. Instructor: "Quiz 3 moved to Thursday 9am." Bot reacts ✅. Ask again; answer changed, no duplicate,
   and the Events tab entry moved with it.
3. Drop `demo/course_outline.pdf`. Bot reacts ✅; several events appear in `!schedule` and in the Events tab.
4. Student: "road trip Sunday, leaving 7am?" gets a ✅ too — and Mate posts a heads-up if it clashes.
5. Student: "@Mate remind me 2 hours before assignment 1" → a DM later; "@Mate where are the slides?" →
   a jump link; a logged plan also gets an RSVP poll; `!digest` shows the week.
6. `!tick` posts a reminder nobody asked for.
