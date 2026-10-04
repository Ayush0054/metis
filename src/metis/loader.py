"""Load workflow classes from installed adapters or trusted local examples."""

import hashlib
import importlib
import importlib.util
import sys
from copy import copy, deepcopy
from pathlib import Path

from .workflow import Workflow

BUILTINS = {"issue-triage": ("metis_triage.workflow", "IssueTriage")}


def instantiate(export, *, name=None, config=None):
    if isinstance(export, type) and issubclass(export, Workflow):
        return export(name=name, config=config)
    if isinstance(export, Workflow):
        workflow = copy(export)
        workflow.name = name or export.name
        workflow.config = deepcopy(export.config)
        workflow.config.update(deepcopy(config or {}))
        if type(export) is not Workflow:
            workflow.steps = tuple(workflow.build_steps())
        return workflow
    raise ValueError("Custom file must export a Workflow subclass or instance as workflow.")


def load_builtin(uses, *, name=None, config=None):
    module_name, class_name = BUILTINS[uses]
    export = getattr(importlib.import_module(module_name), class_name)
    return instantiate(export, name=name, config=config)


def load_workflow(path, *, name=None, config=None):
    path = Path(path).resolve()
    module_name = "metis_workflow_" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load workflow file.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return instantiate(getattr(module, "workflow", None), name=name, config=config)
