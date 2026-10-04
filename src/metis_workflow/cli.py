"""Run user-defined workflow classes locally or from GitHub Actions."""

import argparse
import json
import os
import sys
from pathlib import Path

from ._http import required_env
from .config import load_manifest
from .loader import load_workflow
from .runner import run_workflows


def main(argv=None):
    parser = argparse.ArgumentParser(prog="metis-workflow", description="Run Jev-powered workflow classes.")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="List the workflows in a manifest.")
    listing.add_argument("--manifest", type=Path, required=True)
    for name in ("run", "github"):
        command = commands.add_parser(name, help="Run workflows from JSON input." if name == "run" else
                                      "Dispatch the GitHub Actions event.")
        source = command.add_mutually_exclusive_group()
        source.add_argument("--workflow-file", type=Path, help="Python file exporting a Workflow subclass.")
        source.add_argument("--manifest", type=Path, help="JSON manifest of workflow classes.")
        command.add_argument("--workflow", help="Select a name from the manifest.")
        command.add_argument("--config", type=Path, help="Plain JSON settings for --workflow-file.")
        command.add_argument("--dry-run", action="store_true", help="Ask write steps to suppress external changes.")
        if name == "run":
            command.add_argument("--event", type=Path, required=True, help="JSON input for this run.")
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            entries = load_manifest(args.manifest)
            print(json.dumps([{key: str(entry[key]) if key == "file" else entry[key]
                               for key in ("name", "file", "enabled")} for entry in entries], indent=2))
            return 0
        workflow_file, manifest, config_path = args.workflow_file, args.manifest, args.config
        selected, dry_run = args.workflow, args.dry_run
        event_name = None
        if args.command == "github":
            workspace = Path(os.environ.get("GITHUB_WORKSPACE", "."))
            def action_path(name):
                value = os.environ.get(name, "").strip()
                return workspace / value if value else None
            workflow_file = workflow_file or action_path("METIS_WORKFLOW_FILE")
            manifest = manifest or action_path("METIS_MANIFEST_PATH")
            config_path = config_path or action_path("METIS_CONFIG_PATH")
            selected = selected or os.environ.get("METIS_WORKFLOW", "").strip() or None
            mode = os.environ.get("METIS_DRY_RUN", "false").lower()
            if mode not in {"true", "false"}:
                raise ValueError("METIS_DRY_RUN must be true or false.")
            dry_run = dry_run or mode == "true"
            event_path = Path(required_env("GITHUB_EVENT_PATH"))
            event_name = required_env("GITHUB_EVENT_NAME")
        else:
            event_path = args.event
        if (workflow_file is None) == (manifest is None):
            raise ValueError("Choose exactly one workflow file or manifest.")
        if workflow_file and selected:
            raise ValueError("--workflow selects a name from a manifest.")
        if manifest and config_path:
            raise ValueError("Put workflow settings in the manifest; --config is for a single file.")
        event = json.loads(event_path.read_text(encoding="utf-8"))
        if not isinstance(event, dict):
            raise ValueError("Workflow input must be a JSON object.")
        if args.command == "github" and event["repository"]["full_name"] != required_env("GITHUB_REPOSITORY"):
            raise ValueError("Event repository does not match GITHUB_REPOSITORY.")
        if workflow_file:
            config = json.loads(config_path.read_text(encoding="utf-8")) if config_path else None
            if config is not None and not isinstance(config, dict):
                raise ValueError("Workflow configuration must be a JSON object.")
            workflow = load_workflow(workflow_file, config=config)
            result = (workflow.run(event=event, dry_run=dry_run) if workflow.matches(event, event_name)
                      else {"workflow": workflow.name, "status": "skipped", "reason": "Event does not match.",
                            "dry_run": dry_run})
        else:
            result = run_workflows(load_manifest(manifest), event, event_name=event_name,
                                   selected=selected, dry_run=dry_run)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        message = str(error) if isinstance(error, (RuntimeError, ValueError)) else type(error).__name__
        print(f"Metis Workflow failed: {message}", file=sys.stderr)
        return 1
