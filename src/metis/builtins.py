"""Dispatch GitHub events to workflows, using the same runner as custom code."""

from contextlib import redirect_stdout
from io import StringIO

from metis_triage._triage import main as triage_issue

from .engine import Step, Workflow
from .pr_screening import workflow as pr_workflow


def issue_step(ctx):
    log = StringIO()
    with redirect_stdout(log):
        triage_issue(ctx.config, dry_run=ctx.dry_run, event=ctx.event,
                     repository=ctx.event["repository"]["full_name"])
    messages = log.getvalue().splitlines()
    if messages and messages[0].startswith("Skipped:"):
        ctx.skip(messages[0].removeprefix("Skipped: "))
    return {"messages": messages}


def run_workflows(entries, event, *, event_name=None, selected=None, dry_run=False):
    if selected is not None and selected not in {entry["name"] for entry in entries}:
        raise ValueError("Selected workflow is not in this configuration.")
    results = []
    for entry in entries:
        if not entry["enabled"] or (selected is not None and selected != entry["name"]):
            continue
        uses = entry["uses"]
        if uses == "issue-triage":
            matches = "issue" in event and "pull_request" not in event and event.get("action") == "opened"
            matches = matches and event_name in {None, "issues"}
            workflow = Workflow(entry["name"], (Step("triage", issue_step),))
        else:
            matches = "pull_request" in event and event.get("action") in {
                "opened", "reopened", "synchronize", "edited", "ready_for_review"
            }
            matches = matches and event_name in {None, "pull_request_target"}
            workflow = pr_workflow(entry["name"])
        if matches:
            results.append(workflow.run(event=event, config=entry["config"], dry_run=dry_run))
    return results
