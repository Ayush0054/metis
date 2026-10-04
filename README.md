# Metis Workflow

`metis-workflow` is a small Python framework for workflows powered by TypeSafe AI's
Jev model. Define a workflow class, use integrations where needed, and compose
named steps. Python 3.10+, no runtime dependencies.

| Package | Location | Purpose |
| --- | --- | --- |
| `metis-workflow` | Repository root | Framework, CLI, GitHub Action, and integrations |
| `metis-triage` | `legacy/metis-triage/` | Archived standalone issue-triage package |

The framework imports as `metis_workflow`. Both issue triage and PR screening are
examples built entirely with this framework. They do not import the legacy package.
The current framework version is **0.1.1**.

## Install

From this checkout:

```sh
python -m pip install .
```

After publication, the distribution can be installed with `pip install metis-workflow`.

## Define a workflow class

```python
from metis_workflow import Step, Workflow
from metis_workflow.integrations import Jev

class SupportRouting(Workflow):
    name = "support-routing"

    def build_steps(self):
        return (
            Step("assess", self.assess),
            Step("route", self.route),
        )

    def assess(self, ctx):
        jev = ctx.integrations.setdefault("jev", Jev())
        return jev.check(ctx.event, {
            "billing": "Does this ticket concern a payment or invoice?"
        })

    def route(self, ctx):
        value = ctx.outputs["assess"]["billing"]
        return {"queue": "billing" if value >= 0.8 else
                "support" if value <= 0.2 else "manual-review"}

workflow = SupportRouting
```

Export the class as `workflow` to run it from the CLI. In application code, use
`SupportRouting().run(event={"message": "I was charged twice"})`.

`Workflow` owns execution, skips, error handling, and the run report. Define the
order in `build_steps()` and change behavior by overriding individual methods.
Each step's return value is available by name in `ctx.outputs`.

| Context field | Purpose |
| --- | --- |
| `event` | Input for this run |
| `config` | Workflow defaults merged with supplied settings |
| `integrations` | API clients shared by the steps |
| `state` | Internal run data, omitted from the run report |
| `outputs` | Named step results included in the run report |
| `dry_run` | Whether write steps should suppress external changes |

Override `default_config()` and `validate_config(config)` to define and check
settings. Pass overrides to the constructor or `.run(config={...})`. Each run gets
fresh state and outputs and a copy of its configuration. Supply clients with
`SupportRouting(integrations={"jev": Jev(...)})` or `.run(integrations={...})`.

Use `Step("notify", self.notify, when=lambda ctx: ...)` for conditional steps.
Call `ctx.skip("reason")` to stop the workflow normally. Errors stop subsequent
steps. Write steps must honor `ctx.dry_run`; return only data suitable for the run
report. Override `matches(event, event_name=None)` to control event dispatch.
Workflows run sequentially in one process; scheduling comes from the caller or
GitHub Actions.

## Integrations

`src/metis_workflow/integrations/` contains the shared clients:

- `GitHub(repository, token=None, dry_run=False)` reads repository API endpoints,
  follows paginated lists, and supports explicit writes.
- `Jev(api_key=None, model=None)` supplies typed judgments. `check(state, criteria)`
  returns yes/no probabilities for a checklist. `evaluate(state, questions)` runs
  Choice, Noul, and Score questions together and validates the returned answers.
  Question and answer shapes follow the [TypeSafe API](https://docs.typesafe.ai/api).

GitHub credentials default to `GITHUB_TOKEN`. Jev credentials default to
`TYPESAFE_API_KEY`, and the model defaults to `TYPESAFE_DEFAULT_MODEL` or `jev-latest`.
The workflow owns thresholds, policies, and actions; integrations own API calls.

## Examples

```text
src/metis_workflow/
  workflow.py             Workflow, Step, and Context
  runner.py               Event dispatch
  integrations/
    github.py             GitHub API client
    jev.py                Typed Jev judgments
examples/
  issue_triage.py         IssueTriage(Workflow)
  issue_triage.json       Label names and triage thresholds
  pr_screening.py         PRScreening(Workflow)
  pr_screening.json       PR criteria and screening policy
  support_routing.py      SupportRouting(Workflow)
legacy/metis-triage/       Independent archived package
```

Copy an example and its companion JSON to customize it. Both GitHub examples
read defaults from the JSON next to their Python file. They use the same public
framework and integrations available to any user workflow.

| Example | Steps | Result |
| --- | --- | --- |
| Issue triage | load → classify → label → reply | Labels issues and requests missing bug details |
| PR screening | load → evidence → judge → apply | Screens external contributions and closes clear failures |
| Support routing | assess → route | Chooses a support queue and priority |

Issue triage classifies new issues as bug, feature, documentation, question, or
other. It applies existing labels only after configured confidence and probability
thresholds pass. For clear bugs, it posts a fixed template listing missing
reproduction, behavior, or environment details. It skips uncertain results,
bot-authored or oversized issues, changed text, conflicting category labels,
previous Metis replies, and conversations a person has already joined. It does not
create labels or close issues. Default label names are `bug`, `enhancement`,
`documentation`, and `question`; configure names that exist in your repository.

PR screening exempts the repository owner and owning organization's members,
bots, drafts, and configured author exemptions. It reads the title, body, patches,
repository description, and README at the trusted base commit. The default checks
are relevance, a concrete useful change, and absence of promotional spam. No
linked issue is required; small fixes and documentation improvements count.

Passing and uncertain PRs stay open. A criterion probability at or below `0.05`
allows closure; all probabilities at least `0.8` count as passing. Missing,
binary, or incomplete patches and oversized PRs need manual review. These are
initial policy thresholds, not evaluated accuracy guarantees. The workflow
rechecks PR state before writing, posts a configured explanation, and closes
clear failures. There remains a small race between the final read and GitHub's
close request. Reopened PRs are screened again; use an author exemption to
exclude a contributor from future screening.

## Run workflows

```sh
metis-workflow run --workflow-file examples/support_routing.py --event ticket.json
metis-workflow run --workflow-file examples/issue_triage.py --event issue-event.json --dry-run
metis-workflow run --workflow-file examples/pr_screening.py --event pr-event.json --dry-run
```

`--event` supplies a JSON input object. For a single class file, `--config path.json`
overrides its defaults. A dry run still reads GitHub and calls Jev; the examples
suppress writes when `dry_run` is true. Loading a workflow file executes trusted
local Python.

For several workflows, create a manifest such as `.github/metis-workflows.json`:

```json
{
  "version": 1,
  "workflows": [
    {"name": "issue-triage", "file": "../examples/issue_triage.py"},
    {
      "name": "pr-screening",
      "file": "../examples/pr_screening.py",
      "config": {"repository_context": "We accept bug fixes, examples, and docs improvements."}
    }
  ]
}
```

Entries contain a unique `name`, a `file` relative to the manifest, and optional
`enabled` and `config` fields. Settings override top-level defaults; a `criteria`
object replaces the complete checklist. All workflows use this same file-based
registration; the framework has no built-in use cases or legacy adapters.

```sh
metis-workflow list --manifest .github/metis-workflows.json
metis-workflow run --manifest .github/metis-workflows.json --workflow issue-triage --event issue-event.json
```

The dispatcher calls each class's `matches()` method. `python -m metis_workflow`
uses the same CLI.

## GitHub Action

Copy the examples, companion JSON files, and manifest into your repository. Add
the following workflow on the default branch and configure `TYPESAFE_API_KEY` as a
repository secret. Pin a published commit containing this framework for reproducible
use; `main` is the development reference.

```yaml
name: Metis workflows
on:
  issues:
    types: [opened]
  pull_request_target:
    types: [opened, reopened, synchronize, edited, ready_for_review]

permissions:
  contents: read
  issues: write
  pull-requests: write

concurrency:
  group: metis-${{ github.repository }}-${{ github.event.issue.number || github.event.pull_request.number }}
  cancel-in-progress: false

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with:
          ref: ${{ github.event.pull_request.base.sha || github.sha }}
          persist-credentials: false
      - uses: Ayush0054/metis@main
        with:
          manifest-path: .github/metis-workflows.json
          typesafe-api-key: ${{ secrets.TYPESAFE_API_KEY }}
```

Use `workflow` to select a name from the manifest. To run one class directly, set
`workflow-file: examples/issue_triage.py` and optional `config-path` instead of
`manifest-path`. `dry-run: 'true'` asks the workflow to evaluate without writes.
The optional `github-token` and `model` inputs replace the default GitHub token
and Jev model. A write error can leave a partial action; inspect or rerun the job.

Only trusted base code and configuration should execute in `pull_request_target`.
PR head code must never be checked out or run in this privileged job. See
[GitHub's trigger documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request_target).
Issue text, PR text, and patches are sent to TypeSafe for evaluation.

## Legacy package

[`legacy/metis-triage`](legacy/metis-triage/README.md) retains the original package
at version `0.1.0`, with its own metadata, source, README, and license. It can be
installed independently. It has no dependency on the new framework, and the new
framework and examples have no dependency on it. New work belongs in
`metis-workflow` and the examples.

## Publishing

`.github/workflows/publish.yml` builds only the root `metis-workflow` distribution
and publishes through PyPI Trusted Publishing. Configure the publisher for project
`metis-workflow`, owner `Ayush0054`, repository `metis`, workflow `publish.yml`, and
environment `pypi-workflow`. A release tag must match the root package version,
currently `v0.1.1`. The legacy package has no automated publication in this workflow.

## Design references

The class API draws on [Temporal workflow classes](https://docs.temporal.io/develop/python/workflows/basics),
step composition on [Agno workflows](https://docs.agno.com/workflows/overview), and
explicit execution state on [Prefect flows](https://docs.prefect.io/v3/concepts/flows).

## License

[MIT](LICENSE) © 2026 Ayush Jha.
