from dataclasses import dataclass

from intake.records import AcceptanceReceipt


@dataclass(frozen=True)
class PublishReceipt:
    report_id: int
    survey_id: str
    packet_ids: tuple[str, ...]


def make_publish_receipt(report_id: int, survey_id: str,
                         parents: tuple[AcceptanceReceipt, ...]) -> PublishReceipt:
    return PublishReceipt(report_id, survey_id, tuple(parent.packet_id for parent in parents))
