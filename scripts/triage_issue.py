#!/usr/bin/env python3
"""Run the bundled package from the GitHub Action without installing it."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from metis_triage.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["github"]))
