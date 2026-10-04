# Metis

A small workflow orchestrator powered by TypeSafe AI's Jev model. Define a workflow
class, connect API integrations, and run named steps with shared context.
Python 3.10+, no runtime dependencies.

## Define a workflow class

```python
from metis import Step, Workflow
from metis.integrations import Jev

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

# Export the class so the CLI can instantiate it.
workflow = SupportRouting

# In application code:
# result = SupportRouting().run(event={"message": "I was charged twice"})
```

`Workflow` owns execution, skips, error handling, and the run report. Override
`build_steps()` to define the order and change behavior by overriding individual
methods. Each step returns a value that later steps read by name from `ctx.outputs`.
For short workflows, `Workflow(name, steps)` remains available.

The context exposes:

| Field | Purpose |
| --- | --- |
| `event` | Input for this run |
| `config` | Workflow defaults merged with supplied settings |
| `integrations` | Shared API clients such as GitHub and Jev |
| `state` | Internal data for this run, omitted from the run report |
| `outputs` | Named step results included in the run report |
| `dry_run` | Whether write steps should suppress external changes |

Override `default_config()` and `validate_config(config)` to define and check your
settings. Pass overrides to `SupportRouting(config={...})` or `.run(config={...})`.
Each run gets fresh state, outputs, and a copy of its configuration. Integrations
can be supplied to the constructor or `.run(integrations={"jev": Jev(...)})`.

Use `Step("notify", self.notify, when=lambda ctx: ...)` for conditional execution,
or `ctx.skip("reason")` to stop the current workflow normally. Errors stop later
steps from running. Return only data that belongs in the run report. Write steps
must check `ctx.dry_run` before changing an external system. Override
`matches(event, event_name=None)` to decide which events the dispatcher accepts.
Workflows run sequentially in one process; scheduling comes from your caller or
GitHub Actions.

## Integrations and examples

The framework and use cases have separate locations:

```text
src/metis/
  workflow.py             Workflow, Step, and Context
  runner.py               Event dispatch
  integrations/
    github.py             GitHub API integration
    jev.py                Jev judgments
examples/
  pr_screening.py         PRScreening(Workflow)
  pr_screening.json       Editable PR criteria and policy
  support_routing.py      SupportRouting(Workflow)
```

Import clients with `from metis.integrations import GitHub, Jev`. Jev returns
probabilities; the workflow class owns policy and actions. PR screening is an
example users can copy, modify, or subclass. It is not imported by the framework.
The existing issue-triage behavior remains available through the packaged
`IssueTriage` class in `metis_triage.workflow` and the original library API.

## Run a workflow

```sh
python -m pip install .
metis workflows
metis run --workflow-file examples/support_routing.py --event ticket.json
metis run --workflow-file examples/pr_screening.py --event event.json --dry-run
```

A custom file exports `workflow = YourWorkflowClass`; existing Workflow instances
are also accepted. Loading it executes trusted local Python. With `--workflow-file`,
`--config path.json` supplies a plain JSON settings object. PR screening reads its
defaults from the companion `pr_screening.json`; copy both files together.
A PR dry run still reads GitHub and calls Jev, so it needs API credentials.

For several workflows, use a manifest like `.github/metis-workflows.json`:

```json
{
  "version": 1,
  "workflows": [
    {"name": "issue-triage", "uses": "issue-triage"},
    {
      "name": "pr-screening",
      "file": "../examples/pr_screening.py",
      "config": {
        "repository_context": "We accept bug fixes, examples, and documentation improvements.",
        "maximum_fail_probability": 0.05,
        "allow_authors": ["trusted-contributor"]
      }
    }
  ]
}
```

Every entry has a unique `name`, exactly one installed `uses` adapter or custom
`file`, and optional `enabled` and `config`. File paths are relative to the
manifest. Configuration overrides individual top-level settings; `criteria`
replaces the whole checklist. Add another class through a `file` entry without
changing Metis. `metis init issue-triage` scaffolds the packaged issue adapter.

`metis github --config .github/metis-workflows.json` dispatches the GitHub Actions
event to matching classes. Select one configured name with `--workflow pr-screening`,
or use `metis run pr-screening --event event.json --config .github/metis-workflows.json`
outside Actions. The dispatcher calls each workflow's `matches()` method.

## PR screening setup

Copy `examples/pr_screening.py` and its companion JSON into your repository,
then add this workflow on the default branch:

```yaml
name: Metis PR screening
on:
  pull_request_target:
    types: [opened, reopened, synchronize, edited, ready_for_review]

permissions:
  contents: read
  issues: write
  pull-requests: write

concurrency:
  group: metis-pr-${{ github.repository }}-${{ github.event.pull_request.number }}
  cancel-in-progress: false

jobs:
  screen:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with:
          ref: ${{ github.event.pull_request.base.sha }}
          persist-credentials: false
      - uses: Ayush0054/metis@main
        with:
          workflow-file: examples/pr_screening.py
          typesafe-api-key: ${{ secrets.TYPESAFE_API_KEY }}
```

Pin a published commit containing these changes for reproducible use. With
`workflow-file`, an optional `config-path` points to plain JSON settings. For a
manifest, use `config-path: .github/metis-workflows.json` and optionally
`workflow: pr-screening` instead of `workflow-file`. The repository's own
`.github/workflows/metis-prs.yml` demonstrates manifest dispatch.

Custom classes can handle any event your GitHub workflow subscribes to. Execute
only trusted code and configuration in `pull_request_target`; PR head code must
never be checked out or run in this privileged workflow. See GitHub's
[pull_request_target documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request_target).

Screening runs as **load → evidence → judge → apply**:

- Uses GitHub's [`author_association`](https://docs.github.com/en/graphql/reference/issues#commentauthorassociation) to skip `OWNER` and `MEMBER`: the owning
  organization's members are exempt. On a personal repository the owner is exempt.
  External collaborators and previous contributors are screened unless listed in
  `allow_authors`; bots and drafts are skipped.
- Reads the title, body, all changed-file patches, repository description, and
  README from the trusted base commit. `repository_context` adds your own scope
  and contribution expectations. It does not execute PR code or perform a full
  correctness review of the repository.
- Asks Jev one yes/no question per criterion in a single request. The default
  checklist is relevance, a concrete useful change, and absence of promotional spam.
  Small improvements are welcome; no linked issue is required. This follows the
  [TypeSafe Noul pattern](https://docs.typesafe.ai/primitives/noul).
- Keeps the PR open when every criterion's probability is at least `0.8`. A
  probability at or below `0.05` on any criterion allows closure. Other cases stay
  open for manual review. These thresholds are initial policy settings, not
  evaluated accuracy guarantees.
- Leaves oversized PRs, missing/binary patches, incomplete patches, and unknown
  author associations for manual review. API failures fail the job without making
  a closure decision. Default budgets are 100 changed files and 60,000 characters
  of serialized evidence.
- Rechecks title, body, head/base commits, state, author association, draft status,
  and labels before writing. Closure is still subject to a small race between the
  final read and GitHub's close request; GitHub does not provide a conditional
  close by head SHA.
- Posts a configured comment listing failed criteria, then closes the PR. Jev
  supplies probabilities; workflow code owns the comment and action. Comment
  markers avoid duplicate bot replies for the same head and policy on reruns.
  A partial write can leave a comment without closing; inspect or rerun the job.
  Reopened PRs are screened again; add an author exemption to override screening.

## Design references

The class API takes inspiration from
[Temporal's workflow classes](https://docs.temporal.io/develop/python/workflows/basics).
Named function steps and prior outputs follow the useful composition pattern in
[Agno workflows](https://docs.agno.com/workflows/overview). Keeping workflow
configuration and execution status explicit is also informed by
[Prefect flows](https://docs.prefect.io/v3/concepts/flows).

## Python package

Distribution name: **metis-triage**. Workflow import: **metis**. The existing
**metis_triage** API and CLI remain available for issue triage.
The initial PyPI release is pending; installation from this checkout is available with
`python -m pip install .`. After publication:

```sh
pip install metis-triage
```

Set `TYPESAFE_API_KEY` in your environment, then use the library:

```python
from metis_triage import classify_issue

result = classify_issue(
    title="App crashes when exporting a report",
    body="Clicking Export closes the app. Expected a PDF download.",
    repository="owner/repo",
)

print(result.category)
print(result.suggested_label)
print(result.needs_review)
print(result.missing_details)
```

`classify_issue` calls TypeSafe and returns a `TriageResult`. It makes no GitHub
requests and never posts comments or applies labels. You can also pass `api_key`,
`model`, and a complete `config` dictionary from `load_config()` or
`load_config("path/to/config.json")`. With the library API, suggested labels are
recommendations; the caller checks whether they exist before applying them.

The CLI prints the result as JSON:

```sh
metis-triage classify --title "Export crashes" --body-file issue.md
```

`python -m metis_triage` supports the same commands. `metis-triage github` runs
the GitHub integration using `GITHUB_EVENT_PATH`, `GITHUB_EVENT_NAME`,
`GITHUB_REPOSITORY`, `GITHUB_TOKEN`, and `TYPESAFE_API_KEY` from the environment.
That command may apply labels and post a comment, using the same rules as the Action.

## GitHub Action setup

1. Add the workflow below as `.github/workflows/metis.yml` on your repository's
   **default branch**. No script copying or checkout is needed for the default setup.
2. In **Settings → Secrets and variables → Actions**, add the repository secret
   `TYPESAFE_API_KEY`. GitHub supplies `GITHUB_TOKEN` automatically.
3. Make sure the repository has the `bug`, `enhancement`, `documentation`, and
   `question` labels, or provide a custom configuration as described below.
4. Once you are ready to run it, open an issue. Check **Actions → Metis issue triage**
   for the result. Existing issues and comments do not trigger it.

```yaml
name: Metis issue triage
on:
  issues:
    types: [opened]

permissions:
  issues: write

concurrency:
  group: metis-${{ github.repository }}-${{ github.event.issue.number }}
  cancel-in-progress: false

jobs:
  triage:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: Ayush0054/metis@main
        with:
          typesafe-api-key: ${{ secrets.TYPESAFE_API_KEY }}
```

`main` is the initial development version; pin a commit SHA for reproducible use.
The action requires Bash and Python 3.10+, available on GitHub-hosted Ubuntu runners.

The workflow requests `issues: write`. Organization policies
must permit those permissions. Issue titles and descriptions are sent to TypeSafe
for classification. Store the API key only in GitHub Secrets or your local ignored
environment file.

## Issue triage behavior

- Classifies the primary issue purpose as bug, feature, documentation, question, or other.
- Applies the corresponding existing label when both confidence thresholds pass.
- Leaves unrelated labels intact and defers to conflicting existing category labels.
- For clear bug reports, checks reproduction steps, expected/actual behavior, and
  relevant environment details in the same TypeSafe request.
- Posts a fixed template listing only details judged missing. Jev selects typed
  decisions; it does not generate the reply text.
- Skips uncertain classifications, bot-authored issues, closed issues, and oversized
  reports. Skips writes if the issue title or body changed during classification.
- Avoids duplicate bot replies on reruns and avoids asking for information once a
  person has already commented. Reapplying the same label is unnecessary and skipped.
- Fails the workflow on API errors or invalid responses. It never executes issue text,
  creates labels, assigns people, closes issues, or changes code.

## Legacy issue configuration

Copy [the default configuration](https://github.com/Ayush0054/metis/blob/main/src/metis_triage/default_config.json) to your repository to change
label names, disable missing-detail comments, or adjust thresholds. Add a checkout
step before Metis, grant `contents: read` alongside `issues: write`, and pass
`config-path: .github/metis.json`. The entire configuration file is required.

Defaults are `0.8` for Choice confidence, `0.85` for the selected
category's probability, and `0.9` for each missing-detail probability. These are initial
policy settings, **not evaluated accuracy guarantees**; tune them on your own issues
when you are ready to test.

Set the action's `model` input to pin a model. The default is `jev-latest`.
The optional `github-token` input defaults to GitHub's automatic token.
Local `.envrc` and `.env` files are not loaded by the workflow.

An HTTP error during a write can leave a label applied without a reply. Rerun the
failed job after resolving the error; it checks current labels and previous bot comments.
Edits to the issue body do not automatically retrigger triage.

## Implementation references

- [TypeSafe HTTP API](https://docs.typesafe.ai/api)
- [Choice decisions](https://docs.typesafe.ai/primitives/choice)
- [Noul probabilities](https://docs.typesafe.ai/primitives/noul)
- [GitHub issue workflow triggers](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#issues)

## Publishing to PyPI

The package version is in `pyproject.toml`. The current version is `0.1.1`.
The `.github/workflows/publish.yml` workflow builds the wheel and source distribution,
then publishes them using PyPI Trusted Publishing. No PyPI API token is needed.

Create a pending publisher in PyPI with these exact values:

| Field | Value |
| --- | --- |
| PyPI Project Name | `metis-triage` |
| Owner | `Ayush0054` |
| Repository name | `metis` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

Use a GitHub environment named `pypi` in the repository settings. After configuring
the publisher and completing your desired validation, publish a GitHub release with
tag `v0.1.1` to trigger the upload, or manually run **Publish to PyPI** on `main`.
Later releases need a new package version and matching tag. Merely pushing commits
does not run the publishing workflow.

The workflow orchestrator and PR screening changes have not been built, installed,
tested, or run against live APIs. No release has been triggered.

## License

[MIT](https://github.com/Ayush0054/metis/blob/main/LICENSE) © 2026 Ayush Jha.
