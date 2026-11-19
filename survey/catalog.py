import sqlite3

from survey.layout import SurveyLayout


def initialize_catalog(db: sqlite3.Connection):
    db.execute('''CREATE TABLE IF NOT EXISTS station_surveys (
        survey_id TEXT PRIMARY KEY,
        snapshot TEXT NOT NULL
    )''')


def register(db: sqlite3.Connection, layout: SurveyLayout) -> str:
    snapshot = layout.to_json() if isinstance(layout, SurveyLayout) else None
    if snapshot is None:
        raise ValueError('expected a survey layout')
    db.execute('BEGIN IMMEDIATE')
    with db:
        db.execute('''INSERT INTO station_surveys VALUES (?, ?)
                      ON CONFLICT(survey_id) DO NOTHING''', (layout.survey_id, snapshot))
        row = db.execute('SELECT snapshot FROM station_surveys WHERE survey_id = ?',
                         (layout.survey_id,)).fetchone()
        if row[0] != snapshot:
            raise ValueError('survey identity already binds a different layout')
    return layout.survey_id


def load_survey(db: sqlite3.Connection, survey_id: str) -> SurveyLayout:
    if not isinstance(survey_id, str):
        raise ValueError('survey identity must be text')
    row = db.execute('SELECT snapshot FROM station_surveys WHERE survey_id = ?',
                     (survey_id,)).fetchone()
    if row is None:
        raise KeyError(survey_id)
    return SurveyLayout.from_json(row[0])
