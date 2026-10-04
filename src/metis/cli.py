"""Discover, scaffold, and run Metis workflows."""

import argparse
import json
import os
import sys
from pathlib import Path

from ._http import required_env

from .runner import run_workflows
from .config import BUILTINS, load_manifest, template
from .loader import load_workflow


def main(argv=None):
    parser = argparse.ArgumentParser(prog="metis", description="Compose and run Jev-powered workflows.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("workflows", help="List built-in workflows.")
    init = commands.add_parser("init", help="Create an editable workflow manifest.")
    init.add_argument("workflow", choices=BUILTINS)
    init.add_argument("--output", type=Path, default=Path(".github/metis-workflows.json"))
    run = commands.add_parser("run", help="Run built-ins or a trusted local Python workflow.")
    run.add_argument("workflow", nargs="?")
    run.add_argument("--config", type=Path)
    run.add_argument("--event", type=Path, help="JSON input; otherwise GITHUB_EVENT_PATH.")
    run.add_argument("--workflow-file", type=Path, help="Trusted Python file exporting a workflow class.")
    run.add_argument("--dry-run", action="store_true", help="Pass dry_run to steps; write steps must honor it.")
    github = commands.add_parser("github", help="Dispatch the GitHub Actions event.")
    github.add_argument("--config", type=Path)
    github.add_argument("--workflow")
    github.add_argument("--workflow-file", type=Path)
    github.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "workflows":
            print("issue-triage   Label issues and request missing bug-report details.\n"
                  "Custom workflows: use --workflow-file or a file entry in a manifest.")
            return 0
        if args.command == "init":
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as output:
                output.write(json.dumps(template(args.workflow), indent=2) + "\n")
            print(f"Created {args.output}. Edit the configuration, then run with --config.")
            return 0
        event_path = getattr(args, "event", None) or Path(required_env("GITHUB_EVENT_PATH"))
        event = json.loads(event_path.read_text(encoding="utf-8"))
        if not isinstance(event, dict):
            raise ValueError("Workflow input must be a JSON object.")
        if args.command == "github" and event["repository"]["full_name"] != required_env("GITHUB_REPOSITORY"):
            raise ValueError("Event repository does not match GITHUB_REPOSITORY.")
        dry_run = args.dry_run
        path = args.config
        selected = args.workflow
        workflow_file = args.workflow_file
        if args.command == "github":
            workspace = Path(os.environ.get("GITHUB_WORKSPACE", "."))
            custom = os.environ.get("METIS_CONFIG_PATH", "").strip()
            path = path or (workspace / custom if custom else None)
            selected = selected or os.environ.get("METIS_WORKFLOW", "").strip() or None
            custom_workflow = os.environ.get("METIS_WORKFLOW_FILE", "").strip()
            workflow_file = workflow_file or (workspace / custom_workflow if custom_workflow else None)
            raw_dry_run = os.environ.get("METIS_DRY_RUN", "false").lower()
            if raw_dry_run not in {"true", "false"}:
                raise ValueError("METIS_DRY_RUN must be true or false.")
            dry_run = dry_run or raw_dry_run == "true"
        if workflow_file:
            if selected:
                raise ValueError("Select a workflow name or a workflow file, not both.")
            config = json.loads(path.read_text(encoding="utf-8")) if path else None
            if config is not None and not isinstance(config, dict):
                raise ValueError("Workflow configuration must be a JSON object.")
            workflow = load_workflow(workflow_file, config=config)
            event_name = os.environ.get("GITHUB_EVENT_NAME") if args.command == "github" else None
            result = (workflow.run(event=event, dry_run=dry_run) if workflow.matches(event, event_name)
                      else {"workflow": workflow.name, "status": "skipped", "reason": "Event does not match."})
        else:
            result = run_workflows(load_manifest(path), event, selected=selected, dry_run=dry_run,
                                   event_name=os.environ.get("GITHUB_EVENT_NAME") if args.command == "github" else None)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        message = str(error) if isinstance(error, (RuntimeError, ValueError)) else type(error).__name__
        print(f"Metis failed: {message}", file=sys.stderr)
        return 1
