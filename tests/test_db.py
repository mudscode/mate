import unittest
from types import SimpleNamespace as E

from mate import db
from tests.fakes import fresh_db

G = 100
mk = lambda key, title, kind, due, **kw: E(key=key, title=title, kind=kind, due_at=due, details=kw.get("details", ""), confidence=0.9)


class DedupeTests(unittest.TestCase):
    def setUp(self):
        fresh_db()

    def test_reschedule_by_key_updates_in_place(self):
        s1, id1 = db.upsert_event(mk("quiz-3", "Quiz 3", "quiz", "2026-09-21T10:00"), G, 1, 1)
        s2, id2 = db.upsert_event(mk("quiz-3", "Quiz 3 moved", "quiz", "2026-09-17T09:00"), G, 1, 2)
        self.assertEqual((s1, s2), ("inserted", "updated"))
        self.assertEqual(id1, id2)
        self.assertEqual(db.get_event(id1)["due_at"], "2026-09-17T09:00")

    def test_same_key_other_kind_other_channel_merges(self):
        db.upsert_event(mk("lecture-cancelled", "Lecture cancelled", "class_change", "2026-09-23T09:00"), G, 1, 1)
        s, _ = db.upsert_event(mk("lecture-cancelled", "Lecture cancelled", "announcement", "2026-09-23T09:00"), G, 2, 2)
        self.assertEqual(s, "updated")

    def test_same_kind_same_minute_merges_and_adopts_new_key(self):
        db.upsert_event(mk("midterm-2026-10-05", "Midterm exam (Ch. 1-6)", "exam", "2026-10-05T09:00"), G, 1, 1)
        s, eid = db.upsert_event(mk("midterm", "Midterm exam", "exam", "2026-10-05T09:00"), G, 1, 2)
        self.assertEqual(s, "updated")
        self.assertEqual(db.get_event(eid)["key"], "midterm")
        s, _ = db.upsert_event(mk("midterm", "Midterm exam", "exam", "2026-10-07T09:00"), G, 1, 3)
        self.assertEqual(s, "updated")
        self.assertEqual(len(db.list_events(90, G)), 1)

    def test_numbered_siblings_on_adjacent_days_stay_separate(self):
        db.upsert_event(mk("quiz-2", "Quiz 2 (Ch. 3 & 4)", "quiz", "2026-09-16T10:00"), G, 1, 1)
        s, _ = db.upsert_event(mk("quiz-42", "Quiz 42 (Ch. 1 & 2)", "quiz", "2026-09-15T10:00"), G, 1, 2)
        self.assertEqual(s, "inserted")
        s, _ = db.upsert_event(mk("quiz-3", "Quiz 3 (Ch. 5 & 6)", "quiz", "2026-09-17T10:00"), G, 1, 3)
        self.assertEqual(s, "inserted")
        self.assertEqual(len(db.list_events(30, G)), 3)

    def test_reschedule_clears_reminders(self):
        _, eid = db.upsert_event(mk("a1", "Assignment 1", "deadline", "2026-09-18T23:59"), G, 1, 1)
        db.mark_reminder(eid, "24h")
        db.upsert_event(mk("a1", "Assignment 1", "deadline", "2026-09-19T23:59"), G, 1, 2)
        with db.conn() as c:
            self.assertEqual(c.execute("select count(*) from reminders").fetchone()[0], 0)

    def test_same_day_clash_is_server_wide(self):
        db.upsert_event(mk("quiz-2", "Quiz 2", "quiz", "2026-09-16T10:00"), G, 1, 1)
        _, tid = db.upsert_event(mk("trip", "Murree road trip", "plan", "2026-09-16T07:00"), G, 2, 2)
        self.assertEqual([c["title"] for c in db.same_day_events(G, "2026-09-16T07:00", tid)], ["Quiz 2"])
        self.assertEqual(db.same_day_events(G, "2026-09-17T07:00", tid), [])

    def test_other_guild_is_invisible(self):
        db.upsert_event(mk("quiz-2", "Quiz 2", "quiz", "2099-09-16T10:00"), G, 1, 1)
        self.assertEqual(db.list_events(99999, G + 1), [])

    def test_notes_and_messages(self):
        db.add_note(G, 1, "Ali", "TA email is ta@uni.edu")
        db.add_message(G, 1, 5, "Sir", "slides are on LMS", "2026-09-12T10:00")
        self.assertEqual(db.search_notes("ta@uni", G)[0]["author"], "Ali")
        self.assertEqual(db.search_messages("LMS", G)[0]["sender"], "Sir")
        self.assertEqual(db.recent_messages("2026-09-12T00:00", G)[0]["text"], "slides are on LMS")

    def test_init_is_idempotent(self):
        db.init(); db.init()


if __name__ == "__main__":
    unittest.main()
