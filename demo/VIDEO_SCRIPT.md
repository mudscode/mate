# Mate — two-minute demo video script

## Before you record (every take)
1. Start Mate in your own terminal: `. .venv/bin/activate && python bot.py` (wait for "Logged in as mate").
2. Fresh slate: `python scripts/reset.py`
3. In #general delete any old trip / poll / heads-up messages. In #cs-321 delete the old seed paste and PDF.
4. Paste `demo/seed_chat.txt` into #cs-321 as one message. Drop `demo/course_outline.pdf`. Wait for both ✅.
5. Wait ~2 minutes, open the server's Events tab, confirm ~14 entries.
6. Discord full screen, notifications off, phone with this script next to you. Record.

## The script (target 2:00)
| Time | Do | Type | Say |
|---|---|---|---|
| 0:00 | Show #cs-321 with the ✅s, click Events, scroll once | | This is a university class on Discord. Mate is the class's memory. It read this chat and the course outline PDF and built the whole semester's calendar on its own. Nobody ran a command. |
| 0:20 | Wait for the reply | `what's due this week?` | Ask it anything. It answers from what it remembers. |
| 0:35 | Show ✅, click Events, point at Quiz 3 | `Quiz 3 moved to Thursday 9am, same room.` | The instructor moves a date. Mate notices, updates the same event instead of adding a new one, and the calendar follows. |
| 0:55 | Switch to #general | `@everyone road trip to Murree on Wednesday? leaving 7am from the main gate` | Students make plans too. |
| 1:05 | Wait for ✅, heads-up, poll. Click a vote. | | It logs the trip, warns that it clashes with Quiz 2, and opens a poll so people can RSVP. Nobody asked it to. |
| 1:25 | Back to #cs-321, show ✅ | `kal lab hai 9 baje, Lab 2 mein, attendance zaroori hai` | It understands Roman Urdu. And every date the model proposes is checked in Python before it's trusted. |
| 1:40 | Show the reminder line | `!tick` | Before anything is due, it reminds the class by itself. This forces the check that normally runs every ten minutes. |
| 1:52 | React ❌ on the lab message, show 🗑️ | | Got something wrong? One click undoes it. Mate: an agent that listens, decides, acts, and stays quiet otherwise. |

## If something goes wrong mid-take
- Reply is slow: keep talking; a model call takes 5–10 s.
- No ✅ after 20 s: say "let me give it a second", wait; if still nothing, stop and retake from step 2.
- Wrong answer: react ❌ and say "and that's the undo", then continue.
- Never edit the database by hand during a take; reset and retake.

## After recording
- Repo: https://github.com/mudscode/mate (README has setup, features, testing).
- Submission blurb: see below.

## Submission blurb
Mate is an agent that lives inside a class's Discord server and acts as its memory. It reads ordinary chat and shared PDFs, decides on its own what matters (deadlines, quizzes, exams, room changes, student plans), logs it silently with a ✅, and keeps the server's own Events calendar up to date. It answers "when's the quiz?" and "what did I miss?" from memory, opens RSVP polls for plans, DMs personal reminders, warns about clashes, and reminds the class before things are due without being asked. Every date the model proposes is validated in Python; dedupe is by identity so a reschedule updates instead of duplicates; one ❌ reaction undoes anything it got wrong. Works in English and Roman Urdu. One Python process: discord.py, the OpenAI Responses API, SQLite. 70 offline tests, live model tests, and a 23-check end-to-end suite that drives the real bot through Discord.

## Likely judge questions
- **Why is this an agent and not a chatbot?** It acts without being prompted: decides what to log, edits the server calendar, opens polls, posts reminders and clash warnings on its own. The chat is the input, not a prompt box.
- **What if it's wrong?** Dates are validated in Python against the weekday named in the text; dedupe is by the thing, not the date; ❌ undoes a whole message; "@Mate forget the trip" or "quiz 3 is actually Friday" fix it by talking.
- **Does it only work for classes?** No. `!context` sets one sentence per server; the same code runs for a team or a club.
- **How do you test it?** Three levels: fakes-based unit tests, live model tests, and an end-to-end script where a second bot plays student and instructor in a scratch channel and checks everything Mate does.
- **Cost?** gpt-5-mini at low reasoning effort, one call per message that is long enough to matter; short chatter never hits the model.
