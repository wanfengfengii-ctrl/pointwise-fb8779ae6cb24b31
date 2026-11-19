import sqlite3

from intake.envelope import validate_envelope
from intake.records import AcceptanceReceipt, store_acceptance
from survey.layout import SurveyLayout, layout_digest, validate_layout


def accept(db: sqlite3.Connection, layout: SurveyLayout, payload: str) -> AcceptanceReceipt:
    snapshot = validate_layout(layout)
    envelope = validate_envelope(payload)
    if envelope.survey_id != snapshot.survey_id or envelope.layout_digest != layout_digest(snapshot):
        raise ValueError('station packet belongs to another survey layout')
    if envelope.tile_id not in {tile.tile_id for tile in snapshot.tiles}:
        raise ValueError('station packet tile is outside the survey')
    return store_acceptance(db, snapshot, envelope)
