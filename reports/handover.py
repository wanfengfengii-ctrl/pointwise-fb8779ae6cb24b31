from dataclasses import dataclass

from analysis.decision import ReviewDecision
from reports.receipts import PublishReceipt


@dataclass(frozen=True)
class HandoverExcerpt:
    report_id: int
    survey_id: str
    probe_a: str
    probe_b: str
    threshold: int
    ceiling: int | None
    passed: bool
    action: str
    packet_ids: tuple[str, ...]


def build_handover_excerpt(decision: ReviewDecision, receipt: PublishReceipt) -> HandoverExcerpt:
    action = '放行' if decision.passed else '补测'
    return HandoverExcerpt(receipt.report_id, receipt.survey_id, decision.probe_a, decision.probe_b,
                           decision.threshold, decision.ceiling, decision.passed, action,
                           receipt.packet_ids)
