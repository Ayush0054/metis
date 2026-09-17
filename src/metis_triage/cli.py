"""Metis command-line entry point."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from ._triage import load_config, main as github_triage
from .api import classify_issue


def main(argv=None):
    parser = argparse.ArgumentParser(prog="metis-triage", description="GitHub issue triage powered by Jev.")
    commands = parser.add_subparsers(dest="command", required=True)
    classify = commands.add_parser("classify", help="Classify an issue and print JSON; no GitHub writes.")
    classify.add_argument("--title", required=True)
    body = classify.add_mutually_exclusive_group()
    body.add_argument("--body", default="")
    body.add_argument("--body-file", type=Path)
    classify.add_argument("--repository", default="")
    classify.add_argument("--model")
    classify.add_argument("--config", type=Path)
    commands.add_parser("github", help="Triage the opened issue from GitHub Actions environment variables.")
    args = parser.parse_args(argv)
    try:
        if args.command == "github":
            github_triage()
        else:
            body_text = args.body_file.read_text(encoding="utf-8") if args.body_file else args.body
            result = classify_issue(
                args.title, body_text, repository=args.repository, model=args.model,
                config=load_config(args.config),
            )
            print(json.dumps(asdict(result), indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        # Unexpected payloads may contain user text; do not echo them to the log.
        message = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print(f"Metis failed: {message}", file=sys.stderr)
        return 1
