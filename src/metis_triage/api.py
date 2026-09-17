"""Python API for classification without GitHub writes."""

from dataclasses import dataclass
from typing import Literal

from ._triage import MISSING_DETAILS, classify, load_config, validate_config


@dataclass(frozen=True)
class TriageResult:
    """Model judgment and the recommendations allowed by the configured thresholds."""

    category: Literal["bug", "feature", "documentation", "question", "other"]
    confidence: float
    probability: float
    needs_review: bool
    suggested_label: str | None
    missing_details: tuple[str, ...]


def classify_issue(
    title: str,
    body: str = "",
    *,
    repository: str = "",
    api_key: str | None = None,
    model: str | None = None,
    config: dict | None = None,
) -> TriageResult:
    """Call TypeSafe to classify an issue; never read from or write to GitHub.

    Credentials and model default to TYPESAFE_API_KEY and TYPESAFE_DEFAULT_MODEL.
    ``config`` must contain the complete configuration returned by ``load_config``.
    Labels are recommendations; the caller decides whether to apply them.
    """
    if not isinstance(title, str) or not isinstance(body, str):
        raise ValueError("Issue title and body must be strings.")
    if len(title) + len(body) > 40000:
        raise ValueError("Issue exceeds the 40,000-character input budget.")
    if api_key is not None and not api_key.strip():
        raise ValueError("The API key must not be empty.")
    config = load_config() if config is None else validate_config(config)
    answers = classify(
        {"title": title, "body": body}, repository, config["labels"], config,
        api_key=api_key, model=model,
    )
    answer = answers["category"]
    category = answer["choice"]
    selected_probability = answer["probabilities"][category]
    needs_review = (
        category == "other"
        or answer["confidence"] < config["minimum_choice_confidence"]
        or selected_probability < config["minimum_choice_probability"]
    )
    missing = ()
    if not needs_review and category == "bug" and config["request_missing_details"]:
        missing = tuple(
            text for name, (text, _) in MISSING_DETAILS.items()
            if answers[name]["noul"] >= config["minimum_missing_probability"]
        )
    return TriageResult(
        category=category,
        confidence=answer["confidence"],
        probability=selected_probability,
        needs_review=needs_review,
        suggested_label=None if needs_review else config["labels"][category],
        missing_details=missing,
    )
