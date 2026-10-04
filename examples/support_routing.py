"""Subclass Workflow to route a support ticket with Jev judgments."""

from metis import Step, Workflow
from metis.integrations import Jev


class SupportRouting(Workflow):
    name = "support-routing"

    def build_steps(self):
        return (Step("assess", self.assess), Step("route", self.route))

    def assess(self, ctx):
        jev = ctx.integrations.setdefault("jev", Jev())
        return jev.check(ctx.event, {
            "urgent": "Does this support ticket describe an ongoing outage or blocked work?",
            "billing": "Does this support ticket concern payments or invoices?",
        })

    def route(self, ctx):
        answers = ctx.outputs["assess"]
        return {
            "queue": "billing" if answers["billing"] >= 0.8 else (
                "support" if answers["billing"] <= 0.2 else "manual-review"
            ),
            "priority": "high" if answers["urgent"] >= 0.8 else "normal",
        }


# Export the class; the CLI creates an instance with the supplied configuration.
# Add write steps that check ctx.dry_run before changing any external system.
workflow = SupportRouting
