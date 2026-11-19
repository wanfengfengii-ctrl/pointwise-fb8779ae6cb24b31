from dataclasses import dataclass
import sqlite3

from intake.envelope import PacketEnvelope, validate_envelope
from survey.layout import SurveyLayout


@dataclass(frozen=True)
class AcceptanceReceipt:
    acceptance_id: int
    survey_id: str
    tile_id: str
    packet_id: str
    revision_id: str


@dataclass(frozen=True)
class AcceptedPacket:
    envelope: PacketEnvelope
    receipt: AcceptanceReceipt

    @property
    def payload(self):
        return self.envelope.payload


def initialize_intake_store(db: sqlite3.Connection):
    db.execute('''CREATE TABLE IF NOT EXISTS accepted_surveys (
        survey_id TEXT PRIMARY KEY,
        snapshot TEXT NOT NULL
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS accepted_packets (
        acceptance_id INTEGER PRIMARY KEY,
        survey_id TEXT NOT NULL REFERENCES accepted_surveys(survey_id),
        packet_id TEXT NOT NULL UNIQUE,
        payload TEXT NOT NULL
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS acceptance_receipts (
        acceptance_id INTEGER PRIMARY KEY REFERENCES accepted_packets(acceptance_id),
        tile_id TEXT NOT NULL,
        revision_id TEXT NOT NULL
    )''')


def store_acceptance(db: sqlite3.Connection, layout: SurveyLayout,
                     envelope: PacketEnvelope) -> AcceptanceReceipt:
    snapshot = layout.to_json()
    db.execute('BEGIN IMMEDIATE')
    with db:
        db.execute('''INSERT INTO accepted_surveys VALUES (?, ?)
                      ON CONFLICT(survey_id) DO NOTHING''', (layout.survey_id, snapshot))
        registered = db.execute('SELECT snapshot FROM accepted_surveys WHERE survey_id = ?',
                                (layout.survey_id,)).fetchone()
        if registered[0] != snapshot:
            raise ValueError('center already holds a different layout for this survey')
        previous = db.execute('SELECT acceptance_id, payload FROM accepted_packets WHERE packet_id = ?',
                              (envelope.packet_id,)).fetchone()
        if previous is not None:
            if previous[1] != envelope.payload:
                raise ValueError('packet identity already binds a different payload')
            return load_acceptance(db, previous[0]).receipt
        cursor = db.execute('''INSERT INTO accepted_packets(survey_id, packet_id, payload)
                               VALUES (?, ?, ?)''',
                            (envelope.survey_id, envelope.packet_id, envelope.payload))
        receipt = AcceptanceReceipt(cursor.lastrowid, envelope.survey_id, envelope.tile_id,
                                    envelope.packet_id, envelope.revision_id)
        db.execute('INSERT INTO acceptance_receipts VALUES (?, ?, ?)',
                   (receipt.acceptance_id, receipt.tile_id, receipt.revision_id))
    return receipt


def load_accepted_layout(db: sqlite3.Connection, survey_id: str) -> SurveyLayout:
    if not isinstance(survey_id, str):
        raise ValueError('survey identity must be text')
    row = db.execute('SELECT snapshot FROM accepted_surveys WHERE survey_id = ?', (survey_id,)).fetchone()
    if row is None:
        raise KeyError(survey_id)
    return SurveyLayout.from_json(row[0])


def load_acceptance(db: sqlite3.Connection, acceptance_id: int) -> AcceptedPacket:
    if type(acceptance_id) is not int or not 0 < acceptance_id <= 2**63 - 1:
        raise ValueError('invalid acceptance identity')
    row = db.execute('''SELECT p.survey_id, p.packet_id, p.payload, r.tile_id, r.revision_id
                        FROM accepted_packets AS p JOIN acceptance_receipts AS r USING (acceptance_id)
                        WHERE p.acceptance_id = ?''', (acceptance_id,)).fetchone()
    if row is None:
        raise KeyError(acceptance_id)
    survey_id, packet_id, payload, tile_id, revision_id = row
    envelope = validate_envelope(payload)
    if (survey_id, packet_id, tile_id, revision_id) != (
            envelope.survey_id, envelope.packet_id, envelope.tile_id, envelope.revision_id):
        raise ValueError('acceptance receipt differs from stored packet')
    return AcceptedPacket(envelope, AcceptanceReceipt(acceptance_id, survey_id, tile_id,
                                                      packet_id, revision_id))
