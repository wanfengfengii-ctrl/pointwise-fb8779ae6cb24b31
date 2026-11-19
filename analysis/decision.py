from dataclasses import dataclass

from analysis.compose import connected_at_threshold
from analysis.request import ReviewRequest
from intake.selection import AcceptedSet


@dataclass(frozen=True)
class ReviewDecision:
    probe_a: str
    probe_b: str
    threshold: int
    ceiling: int | None
    passed: bool


def evaluate_review(accepted: AcceptedSet, request: ReviewRequest) -> ReviewDecision:
    low, high = 0, 100
    ceiling = None
    while low <= high:
        threshold = (low + high) // 2
        if connected_at_threshold(accepted, request, threshold):
            ceiling = threshold
            low = threshold + 1
        else:
            high = threshold - 1
    passed = ceiling is not None and request.threshold <= ceiling
    return ReviewDecision(request.probe_a, request.probe_b, request.threshold, ceiling, passed)
