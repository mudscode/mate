# Mate at AI Tinkerers Islamabad / Rawalpindi, October Demo Meetup

Saturday 17 October 2026, 2 to 5 PM PKT. Slide-free, live code, about 5 minutes plus questions (confirm with the host).
Their rule: answer "how did you build this", never "why should someone use it". A diagram is allowed when it
explains the work; no code walkthrough, there is no time for it. Three live beats, then three images.

## Pitch, 25 seconds

"I'm Mudassir. Side project. Mate is a Discord bot that acts as a class's memory. People talk normally, it
silently remembers anything with a date, puts it in the server's Events tab, answers from memory, and reminds
people before things are due without being asked. One Python process, one SQLite file, one model. Let me show
you three things and then four lessons."

## Three live beats, about 2 minutes

Paste from `demo/live_messages.txt` (the five lines below, in order). Bot log visible in a second window. Talk only while something is happening.

| Clock | Paste | Expect | Say |
|---|---|---|---|
| 0:25 | `Quiz 4 is on Thursday 10am, chapters 7 and 8. Room 104.` | ✅ only; Events tab entry with room | "It read that. Only a tick. Nothing posted. It's in the server's own calendar." |
| 0:50 | `Quiz 4 moved to Friday 11am, same room.` | ✅; same entry moved, still one | "Each thing gets a stable name, never a date, so a reschedule is an edit." |
| 1:15 | `quiz kab hai?` | reply naming Friday 11:00 | "No mention, Roman Urdu. Python checked that date against the weekday in the text before it was stored." |
| 1:40 | `study session for quiz 4 Friday 6pm at the library?` | ✅, heads-up about the quiz day, RSVP poll | "A plan, a clash warning, and a poll so nobody types plus-one twenty times." |
| 2:05 | `the study session is canceled`, then ❌ on the Quiz 4 message | poll and entry gone; ✅ becomes 🗑️ | "Cancelled and undone. An agent that writes on its own has to be cheap to correct." |

## Three builder takeaways, about 2 minutes, one image each

Images: `~/Downloads/Mate-takeaway-1.png` to `-3.png` (rendered from the diagrams; regenerate if the wording changes).
Full "what to say" per image, the pushback answers, setup, delivery and Q&A are in `~/Downloads/Mate-demo-pack.pdf` (one document).

1. **Your first user should be an agent.** Fakes test logic; an agent that acts as the user and judges the
   result tests the agent, on the real platform. `scripts/e2e.py` is a second bot that plays student and
   instructor against the running Mate, judges 23 outcomes, four minutes, cleans up. Found four bugs no fake
   could show: lock starvation behind Discord's rate limit, Quiz 42 merged into Quiz 2, Thursday on a
   Wednesday's date, a regression caught two hours after it was made. Today the user is scripted; say so. The
   lesson is one agent as user and judge. Defence: "that's an integration test" → yes, with the platform in
   the loop; the bugs were platform behaviour. "Flaky because of the model" → the flake is the finding.
2. **Own the hundred lines.** No orchestration framework. Hooks plus tool registry are 97 lines; core 817;
   seven features 690, one file each; tests 1552. Not "no abstractions", but abstractions small enough to read
   in full when they break. Defence: "frameworks save time" → the first hour, yes; the cost shows up three
   layers down. "Doesn't scale to a team" → probably; this is where to start, not where to end.
3. **More context can make it worse.** Adding the weekday name to the timestamp fixed dates. Adding a list of
   what Mate already remembered made a new lab come back as the existing quiz. Both were "more context"; the
   e2e run decided. Defence: "more relevant context always helps" → relevance to you and influence on the
   model are different things; measure. "Prompt wording problem" → tried; what held was removing the list and
   a code guard against key reuse across kinds.

## Close, 10 seconds

"It's on GitHub, mudscode/mate. The e2e tester is the file I'd steal first. Happy to talk about any of the three."

## Say / do not say

Say: "side project", "I built", "it broke when"; one sentence then show; the numbers (97, 23, four bugs, two
hours); the limits before anyone asks (scripted, small, single process); the model and API once.

Do not say: the hackathon placing or any ranking; "revolutionary", "powered by AI"; a feature list; "sorry it's
slow"; anything you must read off the screen; "it's a chatbot that".

## Not shown, one sentence each if asked

- `!backfill` and the PDF: one model call per message and Discord allows about five Events creations a minute.
- Reminders, personal DMs, the Sunday digest: time-based, nothing to see live. `!tick` forces the check.
- The hackathon video: against the rules, and the live thing is better.

## Checklist

Night before
- `python scripts/reset.py` so memory and the Events tab are empty. It keeps `!context`.
- Check `!context` reads as the CS-321 sentence. Set it if not.
- Optional: paste `demo/seed_chat.txt` as one message so the Events tab is not empty on stage. Its dates are
  after 17 October and do not collide with the live messages above (six events, none on Thu 22 or Fri 23).
- `scripts/test.sh` green. `python scripts/e2e.py` against the running bot: 23/23. Keep its output for the talk.

Before walking up
- Exactly one `bot.py` running. Check with `ps`. Two processes on one token double every action.
- `.env` key works (the bot reads it once at start; restart after any change).
- Discord zoomed in, bot log window open, the messages file open, the three images open in an image viewer.
- Phone hotspot ready as a second network.

If it breaks
- Model slow: keep talking, then `!schedule`. "That's the no-model fallback. Memory is a table."
- Events tab lagging: it mirrors last because Discord rate-limits it. Say exactly that; it is takeaway 1's bug.
- Something mis-logged: ❌ it. "This is the undo."
- Discord down: skip the beats, start at the diagrams with last night's e2e output.
