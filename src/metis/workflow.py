"""Small, synchronous workflows: ordinary Python steps with explicit state."""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

from ._http import APIError


class SkipWorkflow(Exception):
    """Stop this workflow normally; other workflows may still run."""


@dataclass
class Context:
    event: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    integrations: dict = field(default_factory=dict)
    dry_run: bool = False
    outputs: dict = field(default_factory=dict)
    state: dict = field(default_factory=dict)

    def skip(self, reason: str):
        raise SkipWorkflow(reason)


@dataclass(frozen=True)
class Step:
    name: str
    run: Callable[[Context], Any]
    when: Callable[[Context], bool] | None = None


class Workflow:
    """Subclass and define build_steps(); the runner owns execution and reporting."""

    name = ""

    def __init__(self, name=None, steps=None, *, config=None, integrations=None):
        self.name = name or self.name or type(self).__name__
        self.config = deepcopy(self.default_config())
        if config is not None:
            self.config.update(deepcopy(config))
        self.integrations = dict(integrations or {})
        self.steps = tuple(self.build_steps() if steps is None else steps)
        names = [step.name for step in self.steps]
        if not self.name or not names or any(not name for name in names) or len(set(names)) != len(names):
            raise ValueError("Workflows need a name and uniquely named steps.")

    def build_steps(self):
        """Return ordered Step objects, usually wrapping this class's methods."""
        raise NotImplementedError("Define build_steps() or pass steps to Workflow.")

    def default_config(self):
        return {}

    def validate_config(self, config):
        """Override to reject invalid policy before any steps run."""

    def matches(self, event, event_name=None):
        """Override to restrict event dispatch; custom workflows accept all by default."""
        return True

    def run(self, *, event=None, config=None, integrations=None, dry_run=False):
        run_config = deepcopy(self.config)
        if config is not None:
            run_config.update(deepcopy(config))
        self.validate_config(run_config)
        context = Context(
            event={} if event is None else event,
            config=run_config,
            integrations=self.integrations | (integrations or {}),
            dry_run=dry_run,
        )
        steps = []
        for step in self.steps:
            try:
                if step.when is not None and not step.when(context):
                    steps.append({"name": step.name, "status": "skipped"})
                    continue
                context.outputs[step.name] = step.run(context)
                steps.append({"name": step.name, "status": "completed"})
            except SkipWorkflow as error:
                steps.append({"name": step.name, "status": "skipped"})
                return {"workflow": self.name, "status": "skipped", "reason": str(error),
                        "dry_run": dry_run, "steps": steps, "outputs": context.outputs}
            except Exception as error:
                # Do not echo credentials or application state from arbitrary exceptions.
                detail = str(error) if isinstance(error, APIError) else type(error).__name__
                raise RuntimeError(f"Workflow {self.name}: step {step.name} failed ({detail}).") from None
        return {"workflow": self.name, "status": "completed", "dry_run": dry_run,
                "steps": steps, "outputs": context.outputs}
