"""Environment and constants. Import this first; it loads .env."""
import base64
import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

TZ = ZoneInfo("Asia/Karachi")
MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
DB_PATH = os.getenv("MATE_DB", "mate.db")
STAFF_ROLES = {"Instructor", "TA", "Admin"}


def bot_id_from_token(token: str | None) -> int | None:
    """A Discord bot token starts with base64(user_id); decode it so tests need only the token."""
    if not token or "." not in token:
        return None
    head = token.split(".")[0]
    try:
        return int(base64.urlsafe_b64decode(head + "=" * (-len(head) % 4)))
    except (ValueError, TypeError):
        return None


# Bot accounts whose messages Mate treats as human (scripted end-to-end tests). Derived from the tester's
# token; MATE_TEST_BOT_IDS (comma-separated) still works as an override.
TEST_BOT_IDS = {int(x) for x in os.getenv("MATE_TEST_BOT_IDS", "").split(",") if x.strip()}
_tester = bot_id_from_token(os.getenv("MATE_TEST_BOT_TOKEN"))
if _tester:
    TEST_BOT_IDS.add(_tester)
