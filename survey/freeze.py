import sqlite3

from survey.catalog import load_survey
from survey.ingest import validate_scan
from survey.revisions import append_revision


def freeze_grid(db: sqlite3.Connection, survey_id: str, tile_id: str, rows) -> str:
    layout = load_survey(db, survey_id)
    draft = validate_scan(layout, tile_id, rows)
    return append_revision(db, draft)
