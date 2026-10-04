# Migrate to Metis Workflow

`metis-workflow` 0.1.1 is the new framework. `metis-triage` 0.1.0 remains
independent under [`legacy/metis-triage/`](../legacy/metis-triage/).

## Move issue triage

1. Install the root package with `python -m pip install .` from this checkout.
2. Copy [`issue_triage.py`](../examples/issue_triage.py) and
   [`issue_triage.json`](../examples/issue_triage.json) into your repository's
   `workflows/` directory. Keep both files together. Existing `.github/metis.json`
   settings can become `workflows/issue_triage.json`; the triage fields are unchanged.
3. Add `.github/metis-workflows.json`:

```json
{
  "version": 1,
  "workflows": [
    {"name": "issue-triage", "file": "../workflows/issue_triage.py"}
  ]
}
```

In your issue Action, add a checkout before Metis, grant `contents: read` and
`issues: write`, and replace the old `config-path` input with:

```yaml
- uses: Ayush0054/metis@main # Pin a commit containing the new framework.
  with:
    manifest-path: .github/metis-workflows.json
    workflow: issue-triage
    typesafe-api-key: ${{ secrets.TYPESAFE_API_KEY }}
```

Keep the `issues: opened` trigger. Token and model inputs are unchanged.
For PR screening, copy its Python/JSON pair and add another manifest entry.
Use the [PR Action setup](../README.md#github-action), which checks out trusted base code.

## Update custom code

| Previous API | New API |
| --- | --- |
| `from metis import Workflow, Step` | `from metis_workflow import Workflow, Step` |
| `from metis.integrations import GitHub, Jev` | `from metis_workflow.integrations import GitHub, Jev` |
| `Workflow(name, steps)` or an exported instance | Subclass `Workflow`, implement `build_steps()`, export the class |
| Manifest `uses: issue-triage` | Manifest `file: ../workflows/issue_triage.py` |
| `metis workflows` | `metis-workflow list --manifest path.json` |
| `metis run ...` | `metis-workflow run --workflow-file workflow.py --event event.json` |
| Action `config-path` for a manifest | Action `manifest-path` |

`config-path` still supplies plain settings when using `workflow-file`.
Manifest `config` overrides defaults at the top level; supplying `labels` or
`criteria` replaces that whole mapping. There are no aliases or legacy adapters.
See [custom workflows](custom-workflows.md) for the class API.

## Keep the legacy classifier

Code using `metis_triage.classify_issue()` can keep the legacy package:

```sh
python -m pip install ./legacy/metis-triage
```

The new package does not provide `classify_issue()` or its result type.
The new issue example processes GitHub events; use Jev directly for custom
classification without GitHub writes.
