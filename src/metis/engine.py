"""Small, synchronous workflows: ordinary Python steps with explicit state."""

from dataclasses import dataclass, field
from typing import Any, Callable

from ._http import APIError


class SkipWorkflow(Exception):
    """Stop this workflow normally; other workflows may still run."""


@dataclass
class Context:
    event: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    services: dict = field(default_factory=dict)
    dry_run: bool = False
    outputs: dict = field(default_factory=dict)

    def skip(self, reason: str):
        raise SkipWorkflow(reason)


@dataclass(frozen=True)
class Step:
    name: str
    run: Callable[[Context], Any]
    when: Callable[[Context], bool] | None = None


@dataclass(frozen=True)
class Workflow:
    name: str
    steps: tuple[Step, ...]

    def __post_init__(self):
        names = [step.name for step in self.steps]
        if not self.name or not names or any(not name for name in names) or len(set(names)) != len(names):
            raise ValueError("Workflows need a name and uniquely named steps.")

    def run(self, *, event=None, config=None, services=None, dry_run=False):
        context = Context(
            event={} if event is None else event,
            config={} if config is None else config,
            services={} if services is None else services,
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
