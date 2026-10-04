"""Versioned manifests containing only user-defined workflow classes."""

import json
from pathlib import Path


def load_manifest(path):
    path = Path(path).resolve()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or type(manifest.get("version")) is not int or manifest["version"] != 1:
        raise ValueError("Workflow manifest requires version 1.")
    if set(manifest) - {"version", "workflows"}:
        raise ValueError("Unknown manifest field.")
    entries = manifest.get("workflows")
    if not isinstance(entries, list) or not entries:
        raise ValueError("A manifest needs at least one workflow.")
    names = set()
    resolved = []
    base = path.parent
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - {"name", "file", "enabled", "config"}:
            raise ValueError("Invalid workflow entry.")
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("Workflow names must be unique and nonempty.")
        names.add(name)
        if not isinstance(entry.get("file"), str) or not entry["file"].strip():
            raise ValueError("Workflow file must be a nonempty path.")
        if type(entry.get("enabled", True)) is not bool:
            raise ValueError("Workflow enabled must be a boolean.")
        overrides = entry.get("config", {})
        if not isinstance(overrides, dict):
            raise ValueError("Workflow config must be an object.")
        resolved.append({"name": name, "file": base / entry["file"],
                         "enabled": entry.get("enabled", True), "config": overrides})
    return resolved
