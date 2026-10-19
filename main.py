"""Entry point: starts a PAPER-ONLY session.

    python main.py                 # same as: python cli.py paper
    python main.py --duration 24h  # any `cli.py paper` option

The previous thread-based runtime (two parallel pipelines, see docs/AUDIT.md)
is no longer started from here; it remains in the git history.
"""

import sys

from cli import main

if __name__ == "__main__":
    sys.exit(main(["paper", *sys.argv[1:]]))
