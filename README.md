# Jev issue triage

A GitHub Action that automatically triages newly opened issues with TypeSafe AI's
Jev model. Uses Python's standard library, with no packages to install or server to host.

## Setup

1. Add `.github/workflows/jev-triage.yml`, `.github/jev-triage.json`, and
   `scripts/triage_issue.py` to your repository's **default branch**.
2. In **Settings → Secrets and variables → Actions**, add the repository secret
   `TYPESAFE_API_KEY`. GitHub supplies `GITHUB_TOKEN` automatically.
3. Make sure the repository has the `bug`, `enhancement`, `documentation`, and
   `question` labels, or change their names in `.github/jev-triage.json`.
4. Once you are ready to run it, open an issue. Check **Actions → Jev issue triage**
   for the result. Existing issues and comments do not trigger it.

The workflow requests `contents: read` and `issues: write`. Organization policies
must permit those permissions. Issue titles and descriptions are sent to TypeSafe
for classification. Store the API key only in GitHub Secrets or your local ignored
environment file.

## Behavior

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

## Configuration

Edit `.github/jev-triage.json` to change label names, disable missing-detail comments,
or adjust thresholds. Defaults are `0.8` for Choice confidence, `0.85` for the selected
category's probability, and `0.9` for each missing-detail probability. These are initial
policy settings, **not evaluated accuracy guarantees**; tune them on your own issues
when you are ready to test.

Optionally set the Actions repository variable `TYPESAFE_DEFAULT_MODEL` to pin a model.
The default is `jev-latest`. Local `.envrc` and `.env` files are not loaded by the workflow.

An HTTP error during a write can leave a label applied without a reply. Rerun the
failed job after resolving the error; it checks current labels and previous bot comments.
Edits to the issue body do not automatically retrigger triage.

## Implementation references

- [TypeSafe HTTP API](https://docs.typesafe.ai/api)
- [Choice decisions](https://docs.typesafe.ai/primitives/choice)
- [Noul probabilities](https://docs.typesafe.ai/primitives/noul)
- [GitHub issue workflow triggers](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#issues)

This implementation has not been run or tested yet.
