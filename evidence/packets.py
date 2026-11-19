from dataclasses import dataclass
import json
import sqlite3
from uuid import uuid4

from survey.revisions import FrozenRevision


@dataclass(frozen=True)
class IssuedPacket:
    packet_id: str
    survey_id: str
    layout_digest: str
    tile_id: str
    revision_id: str
    payload: str


def initialize_packet_store(db: sqlite3.Connection):
    db.execute('''CREATE TABLE IF NOT EXISTS issued_packets (
        packet_id TEXT PRIMARY KEY,
        survey_id TEXT NOT NULL REFERENCES station_surveys(survey_id),
        layout_digest TEXT NOT NULL,
        tile_id TEXT NOT NULL,
        revision_id TEXT NOT NULL REFERENCES frozen_revisions(revision_id),
        payload TEXT NOT NULL
    )''')


def record_issued_packet(db: sqlite3.Connection, revision: FrozenRevision,
                         layout_digest: str, body: dict) -> IssuedPacket:
    packet_id = uuid4().hex
    payload = json.dumps({'version': 1, 'packet_id': packet_id,
                          'survey_id': revision.survey_id, 'layout_digest': layout_digest,
                          'tile_id': revision.tile_id, 'revision_id': revision.revision_id,
                          'body': body}, sort_keys=True, separators=(',', ':'), allow_nan=False)
    fields = (packet_id, revision.survey_id, layout_digest, revision.tile_id,
              revision.revision_id, payload)
    db.execute('BEGIN IMMEDIATE')
    with db:
        db.execute('INSERT INTO issued_packets VALUES (?, ?, ?, ?, ?, ?)', fields)
    return IssuedPacket(*fields)


def load_issued_packet(db: sqlite3.Connection, packet_id: str) -> IssuedPacket:
    if not isinstance(packet_id, str):
        raise ValueError('packet identity must be text')
    row = db.execute('''SELECT packet_id, survey_id, layout_digest, tile_id, revision_id, payload
                        FROM issued_packets WHERE packet_id = ?''', (packet_id,)).fetchone()
    if row is None:
        raise KeyError(packet_id)
    return IssuedPacket(*row)
