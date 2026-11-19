import sqlite3

from reports.archive import ReportRecord, load_report


def retrieve(db: sqlite3.Connection, report_id: int) -> ReportRecord | None:
    return load_report(db, report_id)
