# metis-triage (legacy)

This directory preserves the standalone `metis-triage` package at version `0.1.0`.
It contains the original issue classifier and CLI, with no dependency on
`metis-workflow`. New workflow development belongs in the root package and examples.

Install the legacy package from this repository:

```sh
python -m pip install ./legacy/metis-triage
```

Set `TYPESAFE_API_KEY`, then use the original classification API:

```python
from metis_triage import classify_issue

result = classify_issue(
    title="App crashes when exporting",
    body="Clicking Export closes the app. Expected a PDF download.",
    repository="owner/repo",
)
print(result.category)
```

`classify_issue` returns recommendations without making GitHub writes.
`metis-triage classify --title "Export crashes" --body-file issue.md` prints JSON.
The legacy `github` command retains its original GitHub Actions environment-based
behavior. The repository's active Action and examples use `metis-workflow`.

The legacy source is archived separately; the new package does not import it,
register it as an adapter, or provide aliases for it.
