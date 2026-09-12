"""One module per feature. Each exposes setup(bot) to register commands/loops; hooks and tools register on import."""
from . import digest, personal_reminders, polls, resources

ALL = [polls, resources, personal_reminders, digest]


def setup_all(bot):
    for f in ALL:
        f.setup(bot)
