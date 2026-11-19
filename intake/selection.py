from dataclasses import dataclass
import sqlite3

from intake.coverage import validate_coverage
from intake.records import AcceptedPacket, AcceptanceReceipt, load_acceptance, load_accepted_layout
from survey.layout import SurveyLayout


@dataclass(frozen=True)
class AcceptedSet:
    layout: SurveyLayout
    packets: tuple[AcceptedPacket, ...]

    @property
    def parents(self) -> tuple[AcceptanceReceipt, ...]:
        return tuple(packet.receipt for packet in self.packets)


def select_accepted_set(db: sqlite3.Connection, survey_id: str, acceptance_ids) -> AcceptedSet:
    if not isinstance(acceptance_ids, (list, tuple)):
        raise ValueError('provide a list or tuple of acceptance identities')
    try:
        layout = load_accepted_layout(db, survey_id)
        packets = tuple(load_acceptance(db, item) for item in acceptance_ids)
    except KeyError as error:
        raise ValueError('survey or packet has not been accepted') from error
    validate_coverage(layout, packets)
    return AcceptedSet(layout, tuple(sorted(packets, key=lambda packet: packet.envelope.tile_id)))
