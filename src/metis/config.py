"""Versioned workflow manifests with partial overrides of built-in defaults."""

import copy
import json
from importlib.resources import files
from pathlib import Path

from metis_triage._triage import load_config as issue_defaults, validate_config as validate_issue

from .pr_screening import validate_config as validate_pr

BUILTINS = ("issue-triage", "pr-screening")


def template(name):
    if name not in BUILTINS:
        raise ValueError("Unknown workflow template.")
    return json.loads(files("metis").joinpath("templates", name + ".json").read_text(encoding="utf-8"))


def load_manifest(path=None):
    if path is None:
        manifest = {"version": 1, "workflows": [template(name)["workflows"][0] for name in BUILTINS]}
    else:
        manifest = json.loads(Path(path).read_text(encoding="utf-8"))
        # Existing issue configuration and Action setups keep working.
        if isinstance(manifest, dict) and "workflows" not in manifest and "labels" in manifest:
            manifest = {"version": 1, "workflows": [
                {"name": "issue-triage", "uses": "issue-triage", "config": manifest}
            ]}
    if not isinstance(manifest, dict) or type(manifest.get("version")) is not int or manifest["version"] != 1:
        raise ValueError("Workflow manifest requires version 1.")
    if set(manifest) - {"version", "workflows"}:
        raise ValueError("Unknown manifest field.")
    entries = manifest.get("workflows")
    if not isinstance(entries, list) or not entries:
        raise ValueError("A manifest needs at least one workflow.")
    names = set()
    resolved = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - {"name", "uses", "enabled", "config"}:
            raise ValueError("Invalid workflow entry.")
        name, uses = entry.get("name"), entry.get("uses")
        if not isinstance(name, str) or not name.strip() or name in names or uses not in BUILTINS:
            raise ValueError("Workflow names must be unique and uses must name a built-in.")
        names.add(name)
        if type(entry.get("enabled", True)) is not bool:
            raise ValueError("Workflow enabled must be a boolean.")
        overrides = entry.get("config", {})
        if not isinstance(overrides, dict):
            raise ValueError("Workflow config must be an object.")
        defaults = issue_defaults() if uses == "issue-triage" else template(uses)["workflows"][0]["config"]
        if set(overrides) - set(defaults):
            raise ValueError("Unknown workflow configuration field.")
        config = copy.deepcopy(defaults)
        config.update(overrides)
        (validate_issue if uses == "issue-triage" else validate_pr)(config)
        resolved.append({"name": name, "uses": uses, "enabled": entry.get("enabled", True), "config": config})
    return resolved
