# Build a custom workflow

Install with `python -m pip install .` from this checkout. Create
`workflows/ticket_routing.py`:

```python
from metis_workflow import Step, Workflow
from metis_workflow.integrations import Jev
from metis_workflow.validation import probability


class TicketRouting(Workflow):
    name = "ticket-routing"

    def default_config(self):
        return {"minimum_probability": 0.8}

    def validate_config(self, config):
        threshold = probability(config["minimum_probability"], "minimum_probability")
        if threshold <= 0.5:
            raise ValueError("minimum_probability must exceed 0.5.")

    def build_steps(self):
        return (Step("assess", self.assess), Step("route", self.route))

    def assess(self, ctx):
        jev = ctx.integrations.setdefault("jev", Jev())
        return jev.check(ctx.event, {
            "billing": "Does this ticket concern a payment or invoice?"
        })

    def route(self, ctx):
        value = ctx.outputs["assess"]["billing"]
        threshold = ctx.config["minimum_probability"]
        queue = ("billing" if value >= threshold else
                 "support" if value <= 1 - threshold else "manual-review")
        return {"queue": queue}


workflow = TicketRouting
```

Set `TYPESAFE_API_KEY` in your environment. Save `ticket.json`:

```json
{"message": "I was charged twice for my subscription."}
```

Run it:

```sh
metis-workflow run --workflow-file workflows/ticket_routing.py --event ticket.json
```

To personalize it, change the question, routing rules, or steps. Jev returns
probabilities; your Python code decides what happens.

## Configure and compose

- Override defaults with `--config settings.json` or `.run(config={...})`.
- Add steps in `build_steps()`; read previous results from `ctx.outputs["step-name"]`.
- Keep internal data in `ctx.state`; outputs appear in the JSON run report.
- Add `when=lambda ctx: ...` to a `Step` for conditional execution.
- Call `ctx.skip("reason")` to stop normally; errors stop later steps.
- Override `matches(event, event_name=None)` to filter events during dispatch.

Use an instance directly in your application:

```python
result = TicketRouting(config={"minimum_probability": 0.9}).run(
    event={"message": "I was charged twice"}
)
```

For several workflows, register files in a manifest. Paths are relative to the
manifest. For `.github/metis-workflows.json`:

```json
{
  "version": 1,
  "workflows": [
    {
      "name": "ticket-routing",
      "file": "../workflows/ticket_routing.py",
      "config": {"minimum_probability": 0.9}
    }
  ]
}
```

```sh
metis-workflow run --manifest .github/metis-workflows.json --event ticket.json
```

## Integrations and writes

Use `GitHub(repository, dry_run=ctx.dry_run)` for repository API calls, or supply
your own clients through `integrations={...}`. `Jev.evaluate()` supports batched
Choice, Noul, and Score questions; `Jev.check()` supplies yes/no probabilities.

Write steps must honor `ctx.dry_run` before changing external systems. Dry runs
still make read and Jev requests. The framework runs steps sequentially; your
application or GitHub Actions supplies triggers and scheduling.

Copy the [issue triage](../examples/issue_triage.py) or
[PR screening](../examples/pr_screening.py) Python/JSON pair for a GitHub use case.
See [Action setup](../README.md#github-action) to run your class in GitHub.
