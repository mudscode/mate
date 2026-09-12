# Mate — Class Group Agent
AI Tinkerers "Agents, Everywhere" · Islamabad · 12 Sep 2026

## What it is
A bot added to an existing university course Telegram group. It reads the ordinary
noise (80 students, one instructor), silently pulls out the facts that matter
(deadlines, quiz dates, room changes, shared PDFs), keeps a running schedule in
SQLite, answers "when's the OS quiz?" from memory, and nudges the group on its own
before things are due. No commands, no app, no onboarding.

Users: students in shared course groups. Where it lives: inside the group chat they
already have open all day.

## Why it's an agent, not a chatbot
1. It decides what to log. Most messages are noise; it only acts on facts.
2. It remembers across sessions (SQLite), not just within one prompt.
3. It acts unprompted: scheduled check posts reminders before deadlines.
4. It reads attachments: a course-outline PDF or a timetable screenshot becomes
   ten structured events in one go.

## Stack (deliberately minimal)
| Layer | Choice |
|---|---|
| Chat | Telegram Bot API via `python-telegram-bot` v21 (async, long polling — no public URL needed) |
| LLM | OpenAI Python SDK, Responses API, `gpt-5-mini` (env-overridable), `reasoning.effort: low` for per-message extraction, `medium` for documents |
| Extraction | `client.responses.parse()` with a Pydantic schema (structured outputs) — one call per message, returns typed events or `[]` |
| Q&A | Responses API function calling with `previous_response_id` loop: `list_events`, `search_messages` |
| Storage | SQLite, one file, three tables |
| Scheduler | APScheduler running in the same asyncio loop as the bot; every 10 min |
| Attachments | PDF as base64 `input_file`, images as `input_image`, same extraction schema |
| Runs on | Your laptop for the demo. Optional later: any $5 VPS, same command. |

Python only. One process. No web server, no ngrok, no queue.

## Data model
```
messages(id, chat_id, tg_msg_id, sender, text, ts, has_file)
events(id, chat_id, title, kind[deadline|quiz|exam|class_change|announcement],
       due_at, details, source_msg_id, confidence, created_at, status[active|done|superseded])
reminders(id, event_id, kind[24h|2h], sent_at)
```

## Files
```
mate/
  bot.py        # telegram handlers: text, document, photo, mention; wires scheduler
  extract.py    # message/file -> list[Event] via responses.parse()
  qa.py         # function-calling loop with list_events / search_messages
  db.py         # sqlite helpers, dedupe (same title ±1 day = update, not insert)
  scheduler.py  # tick(): find events due in <24h / <2h without a reminder -> post
  try_extract.py  # offline extraction test
  .env          # DISCORD_BOT_TOKEN, OPENAI_API_KEY
```

## Behaviour rules (put these in the system prompt)
- Only extract an event if the message states a concrete date, day, or "tomorrow/next week" relative to message timestamp (Asia/Karachi). Vague ("soon") = no event.
- Instructor/admin messages get higher default confidence.
- React with an emoji on messages you logged (Telegram reactions), don't reply. Silence is the feature.
- Reply in chat only when @mentioned, replied-to, or the message is a question containing when/where/what/deadline/quiz/exam/due.
- Reminders: post once at 24h, once at 2h. Never repeat.
- Never invent a date. If the source says "Friday" resolve it deterministically in Python from the message timestamp, not in the model.

## Timeline (assumes pitch ~18:00; adjust to the real slot)
| Time | Do | Done when |
|---|---|---|
| 11:00–11:45 | BotFather: create bot, **/setprivacy → Disable**, add to a test group. venv, deps, `.env`. `db.py` schema. Echo handler proves the bot sees plain messages. | Bot logs every group message to `messages` table |
| 11:45–13:15 | `extract.py` + wire into `bot.py`. Emoji reaction on logged messages. Dedupe in `db.py`. | "Quiz 3 on Monday 10am, chapter 5" → row in `events`, ✅ reaction |
| 13:15–13:45 | Paste a real class chat into the channel, run `!backfill` | Demo DB has 10+ real events |
| 13:45–14:45 | `qa.py`: tool_runner answers "when's the quiz?", "anything due this week?" | Answers correctly from seeded DB |
| 14:45–15:30 | `scheduler.py` + `/tick` admin command to force a run on stage | Bot posts "Reminder: OS quiz tomorrow 10am, chapter 5" unprompted |
| 15:30–16:30 | PDF + image ingestion (course outline → many events at once) | Drop a PDF, get ✅ and N events |
| 16:30–17:30 | Rehearse demo twice, fix parsing misses, 5 slides | Demo runs clean end to end |
| 17:30– | Buffer. Do not add features here. | |

Solo build. Order of work is the order of the table above.

## Cut lines (decide at the clock, not by feeling)
- Behind at 14:45 → drop function-calling Q&A, answer with a plain `/schedule` command that dumps events.
- Behind at 15:30 → drop PDF/image; demo text-only.
- Never drop: extraction, scheduler nudge, replay of real data. Those three are the pitch.

## Demo script (4 minutes)
1. Show the real class group already seeded. Ask "what's due this week?" — answer from memory.
2. Teammate as instructor: "Quiz moved to Thursday 9am, same room." Bot reacts ✅. Ask again — the answer changed. Old event shows as superseded.
3. Drop the course outline PDF. Bot reacts, seven new events appear.
4. Run `/tick` (or set a deadline 23h out beforehand). Bot posts a reminder nobody asked for.
5. One line on the deterministic date resolution and dedupe, so judges trust the data.

## Known gotchas
- Privacy mode ON = bot sees nothing but commands. Disable it first, and re-add the bot to the group after changing it.
- Discord bot CAN read history from before it joined; `!backfill` uses that.
- Bot can't DM users who haven't started it. All nudges go to the group.
- Telegram sends PDFs as `document`, screenshots as `photo` (compressed) or `document`. Handle both.
- Timezone: store UTC, display Asia/Karachi. Resolve "Friday" in Python.
- Instructor repeats the same deadline three times. Dedupe by (kind, title similarity, due_at ±1 day).
- Per-message model calls: keep `reasoning.effort: "low"`, `max_tokens` ~1024, and don't call the model at all on messages under ~15 chars or pure emoji/stickers.

## DECISION: Discord instead of Telegram
Telegram login was a blocker. Discord is easier and the plan is otherwise unchanged.

- Setup: Developer Portal -> New Application -> Bot -> copy token. Under Bot, enable
  **Message Content Intent** (this is the Telegram privacy-mode equivalent; without it
  message text is empty). Invite via OAuth2 URL with bot scope + Read Messages,
  Send Messages, Add Reactions, Read Message History, Attach Files.
- Library: `discord.py` (async). Set `intents.message_content = True` on the client.
- Scheduler: `discord.ext.tasks.loop(minutes=10)` inside bot.py. APScheduler not needed.
- History: bot can read messages from before it joined via `channel.history()`.
  Replace `replay.py` with a `!backfill` admin command that pages history through extract.py.
  Seed the demo by pasting a real class chat into the channel, then run `!backfill`.
- Reactions: `await message.add_reaction("✅")`. Attachments: `await attachment.read()`
  gives bytes; PDF -> base64 document block, PNG/JPG -> image block.
- Q&A trigger: `bot.user in message.mentions` or message is a reply to the bot, or the
  question-word heuristic.
- Nudges go to the class channel (bot can DM server members, but keep it in-channel for the demo).
- WhatsApp ruled out: official Cloud API has no group support; unofficial libs risk bans.
  Slack works (Socket Mode) but is a weaker student story.
