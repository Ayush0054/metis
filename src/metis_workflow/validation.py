"""Validation helpers for typed workflow judgments and thresholds."""

import math


def probability(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ValueError(f"Invalid probability for {name}.")
    return value
