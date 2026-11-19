from dataclasses import dataclass
import json
import sqlite3
from uuid import uuid4

from survey.catalog import load_survey
from survey.ingest import Grid, GridDraft


@dataclass(frozen=True)
class FrozenRevision:
    revision_id: str
    survey_id: str
    tile_id: str
    grid: Grid


def initialize_revision_store(db: sqlite3.Connection):
    db.execute('''CREATE TABLE IF NOT EXISTS frozen_revisions (
        revision_id TEXT PRIMARY KEY,
        survey_id TEXT NOT NULL REFERENCES station_surveys(survey_id),
        tile_id TEXT NOT NULL,
        grid_json TEXT NOT NULL
    )''')


def append_revision(db: sqlite3.Connection, draft: GridDraft) -> str:
    if not isinstance(draft, GridDraft):
        raise ValueError('a validated draft is required')
    layout = load_survey(db, draft.survey_id)
    if layout.tile(draft.tile.tile_id) != draft.tile:
        raise ValueError('draft bounds differ from registered bounds')
    revision_id = uuid4().hex
    grid_json = json.dumps(draft.grid, separators=(',', ':'))
    db.execute('BEGIN IMMEDIATE')
    with db:
        db.execute('INSERT INTO frozen_revisions VALUES (?, ?, ?, ?)',
                   (revision_id, draft.survey_id, draft.tile.tile_id, grid_json))
    return revision_id


def load_revision(db: sqlite3.Connection, revision_id: str) -> FrozenRevision:
    if not isinstance(revision_id, str):
        raise ValueError('revision identity must be text')
    row = db.execute('SELECT survey_id, tile_id, grid_json FROM frozen_revisions WHERE revision_id = ?',
                     (revision_id,)).fetchone()
    if row is None:
        raise KeyError(revision_id)
    survey_id, tile_id, grid_json = row
    return FrozenRevision(revision_id, survey_id, tile_id,
                          tuple(tuple(scores) for scores in json.loads(grid_json)))
