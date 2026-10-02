# Metis

A small workflow orchestrator powered by TypeSafe AI's Jev model. Compose ordinary
Python steps, pass state between them, and use Jev for focused semantic decisions.
Run workflows from Python, the `metis` CLI, or the reusable GitHub Action.
Python 3.10+, no runtime dependencies.

Two built-in workflows are included:

- **Issue triage** labels new issues and requests missing bug-report details.
- **PR screening** checks external contributions against editable criteria and
  closes clear failures. Passing and uncertain contributions stay open.

## Start with a workflow

```sh
python -m pip install .
metis workflows
metis init pr-screening
```

The last command creates `.github/metis-workflows.json` without overwriting an
existing file. Edit its `criteria`, thresholds, author exemptions, and close
comment. Configuration can override individual top-level settings; the `criteria`
object replaces the complete checklist. Use `metis init issue-triage` for issue
triage, or put both workflow entries into one manifest. Each entry has a unique
`name`, a built-in `uses`, optional `enabled`, and optional `config`.

```json
{
  "version": 1,
  "workflows": [
    {"name": "issue-triage", "uses": "issue-triage"},
    {
      "name": "pr-screening",
      "uses": "pr-screening",
      "config": {
        "repository_context": "We accept bug fixes, useful examples, and documentation improvements.",
        "maximum_fail_probability": 0.05,
        "allow_authors": ["trusted-contributor"]
      }
    }
  ]
}
```

`metis github --config .github/metis-workflows.json` dispatches the GitHub Actions
event to enabled workflows. `--workflow pr-screening` selects one configured name.
Outside Actions, provide a saved GitHub event with
`metis run pr-screening --event event.json --config .github/metis-workflows.json`.
Add `--dry-run` to evaluate and print decisions while suppressing built-in GitHub
writes. A dry run still reads GitHub and calls Jev, so it needs API credentials.

## PR screening setup

For another repository, add this workflow on its default branch:

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
      - uses: Ayush0054/metis@main
        with:
          workflow: pr-screening
          typesafe-api-key: ${{ secrets.TYPESAFE_API_KEY }}
```

Pin a published commit containing these changes for reproducible use. To load a
custom manifest, add `actions/checkout` before Metis with
`ref: ${{ github.event.pull_request.base.sha }}` and `persist-credentials: false`,
then set `config-path: .github/metis-workflows.json`. The repository's own
`.github/workflows/metis-prs.yml` demonstrates this setup. Execute only code from
the trusted base; PR head code and configuration must never be checked out or run
in this privileged workflow. See GitHub's
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

## Create your own workflow

Custom use cases use the same `Workflow`, `Step`, and `Jev` API. Each step is a
Python function; return a value to make it available to later steps by name.

```python
from metis import Jev, Step, Workflow

def assess(ctx):
    return Jev().check(ctx.event, {
        "billing": "Does this ticket concern a payment or invoice?"
    })

def route(ctx):
    value = ctx.outputs["assess"]["billing"]
    return {"queue": "billing" if value >= 0.8 else
            "support" if value <= 0.2 else "manual-review"}

workflow = Workflow("support-routing", (
    Step("assess", assess),
    Step("route", route),
))

result = workflow.run(event={"message": "I was charged twice"})
```

Save the workflow as `support_routing.py` and run
`metis run --workflow-file support_routing.py --event ticket.json`, or adapt
[`examples/support_routing.py`](examples/support_routing.py). Loading a custom
workflow executes trusted local Python. Add steps to call your own database,
helpdesk, or API; no change to the Metis runner is required.

To run a custom workflow in the GitHub Action, check out your trusted repository
code first and set `workflow-file: .github/workflows/my_workflow.py` instead of
`workflow` and `config-path`. The file exports `workflow = Workflow(...)` and
receives the GitHub event as `ctx.event`. With `pull_request_target`, use only the
trusted base checkout described above. Custom files can handle whichever events
your GitHub workflow subscribes to.

The context exposes `event`, `config`, `services`, `dry_run`, and `outputs`.
Inject shared clients using `workflow.run(services={...})`. Add a condition with
`Step("notify", notify, when=lambda ctx: ...)`, or call `ctx.skip("reason")` to stop
the current workflow normally. Errors stop the workflow and prevent later steps
from running. Results include workflow status, step status, and returned outputs;
return only data that belongs in your logs. Custom write steps must check
`ctx.dry_run`; Python plugins are responsible for their own external effects.
Workflows run sequentially in one process; scheduling comes from your caller or
GitHub Actions. This is not a persistent job queue.

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

The package version is in `pyproject.toml`. The current version is `0.2.0`.
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
tag `v0.2.0` to trigger the upload, or manually run **Publish to PyPI** on `main`.
Later releases need a new package version and matching tag. Merely pushing commits
does not run the publishing workflow.

The workflow orchestrator and PR screening changes have not been built, installed,
tested, or run against live APIs. No release has been triggered.

## License

[MIT](https://github.com/Ayush0054/metis/blob/main/LICENSE) © 2026 Ayush Jha.
