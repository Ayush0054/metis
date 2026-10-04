"""Load a workflow class from a trusted Python file."""

import hashlib
import importlib.util
import sys
from pathlib import Path

from .workflow import Workflow


def load_workflow(path, *, name=None, config=None):
    path = Path(path).resolve()
    module_name = "metis_workflow_" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load workflow file.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    export = getattr(module, "workflow", None)
    if not isinstance(export, type) or not issubclass(export, Workflow):
        raise ValueError("Workflow files must export workflow = YourWorkflowClass.")
    return export(name=name, config=config)
