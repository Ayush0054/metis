"""A custom workflow for any use case; run it with a JSON support-ticket input."""

from metis import Jev, Step, Workflow


def assess(ctx):
    return Jev().check(ctx.event, {
        "urgent": "Does this support ticket describe an ongoing outage or blocked work?",
        "billing": "Does this support ticket concern payments or invoices?",
    })


def route(ctx):
    answers = ctx.outputs["assess"]
    return {
        "queue": "billing" if answers["billing"] >= 0.8 else (
            "support" if answers["billing"] <= 0.2 else "manual-review"
        ),
        "priority": "high" if answers["urgent"] >= 0.8 else "normal",
    }


# Add your own Step here to write to your helpdesk, database, or another API.
# Every step receives ctx.event, ctx.config, ctx.services, and earlier ctx.outputs.
# Steps that write must honor ctx.dry_run before making an external change.
workflow = Workflow("support-routing", (
    Step("assess", assess),
    Step("route", route),
))
