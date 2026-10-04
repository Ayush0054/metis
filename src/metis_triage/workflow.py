"""Class adapter for the existing issue-triage integration."""

from contextlib import redirect_stdout
from io import StringIO

from metis import Step, Workflow

from ._triage import load_config, main, validate_config


class IssueTriage(Workflow):
    name = "issue-triage"

    def default_config(self):
        return load_config()

    def validate_config(self, config):
        if set(config) - set(self.default_config()):
            raise ValueError("Unknown issue-triage configuration field.")
        validate_config(config)

    def matches(self, event, event_name=None):
        return (
            event_name in {None, "issues"}
            and "issue" in event and "pull_request" not in event
            and event.get("action") == "opened"
        )

    def build_steps(self):
        return (Step("triage", self.triage),)

    def triage(self, ctx):
        log = StringIO()
        with redirect_stdout(log):
            main(ctx.config, dry_run=ctx.dry_run, event=ctx.event,
                 repository=ctx.event["repository"]["full_name"])
        messages = log.getvalue().splitlines()
        if messages and messages[0].startswith("Skipped:"):
            ctx.skip(messages[0].removeprefix("Skipped: "))
        return {"messages": messages}
