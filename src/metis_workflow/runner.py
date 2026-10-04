"""Dispatch configured workflows without knowing their domain logic."""

from .loader import load_workflow


def run_workflows(entries, event, *, event_name=None, selected=None, dry_run=False):
    if selected is not None and selected not in {entry["name"] for entry in entries}:
        raise ValueError("Selected workflow is not in this configuration.")
    results = []
    for entry in entries:
        if not entry["enabled"] or (selected is not None and selected != entry["name"]):
            continue
        options = {"name": entry["name"], "config": entry["config"]}
        workflow = load_workflow(entry["file"], **options)
        if workflow.matches(event, event_name):
            results.append(workflow.run(event=event, dry_run=dry_run))
    return results
