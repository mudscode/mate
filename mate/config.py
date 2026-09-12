"""Environment and constants. Import this first; it loads .env."""
import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

TZ = ZoneInfo("Asia/Karachi")
MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
DB_PATH = os.getenv("MATE_DB", "mate.db")
STAFF_ROLES = {"Instructor", "TA", "Admin"}
# Bot accounts whose messages Mate treats as human (for scripted end-to-end tests). Comma-separated ids.
TEST_BOT_IDS = {int(x) for x in os.getenv("MATE_TEST_BOT_IDS", "").split(",") if x.strip()}
