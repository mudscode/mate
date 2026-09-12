#!/usr/bin/env sh
# Offline suite (no network):  scripts/test.sh
# Plus live model calls:       RUN_LIVE=1 scripts/test.sh
cd "$(dirname "$0")/.." && exec .venv/bin/python -m unittest discover -s tests -t . -v "$@"
