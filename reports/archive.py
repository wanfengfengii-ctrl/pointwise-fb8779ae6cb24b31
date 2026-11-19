from dataclasses import asdict, dataclass
import json
import sqlite3

from analysis.decision import ReviewDecision
from intake.records import AcceptanceReceipt
from reports.handover import HandoverExcerpt, build_handover_excerpt
from reports.receipts import PublishReceipt, make_publish_receipt


@dataclass(frozen=True)
class ReportRecord:
    report_id: int
    survey_id: str
    layout_digest: str
    parents: tuple[AcceptanceReceipt, ...]
    decision: ReviewDecision
    receipt: PublishReceipt
    handover: HandoverExcerpt


def initialize_report_archive(db: sqlite3.Connection):
    db.execute('''CREATE TABLE IF NOT EXISTS review_reports (
        report_id INTEGER PRIMARY KEY,
        survey_id TEXT NOT NULL,
        layout_digest TEXT NOT NULL,
        parents_json TEXT NOT NULL,
        probe_a TEXT NOT NULL,
        probe_b TEXT NOT NULL,
        threshold INTEGER NOT NULL CHECK (threshold BETWEEN 0 AND 100),
        ceiling INTEGER CHECK (ceiling BETWEEN 0 AND 100),
        passed INTEGER NOT NULL CHECK (passed = COALESCE(ceiling >= threshold, 0))
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS publish_receipts (
        report_id INTEGER PRIMARY KEY REFERENCES review_reports(report_id),
        survey_id TEXT NOT NULL,
        packet_ids_json TEXT NOT NULL
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS handover_excerpts (
        report_id INTEGER PRIMARY KEY REFERENCES review_reports(report_id),
        snapshot TEXT NOT NULL
    )''')


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def commit_report(db: sqlite3.Connection, survey_id: str, layout_digest: str,
                  parents: tuple[AcceptanceReceipt, ...], decision: ReviewDecision) -> ReportRecord:
    parents_json = _json([asdict(parent) for parent in parents])
    db.execute('BEGIN IMMEDIATE')
    with db:
        cursor = db.execute('''INSERT INTO review_reports
                               (survey_id, layout_digest, parents_json, probe_a, probe_b,
                                threshold, ceiling, passed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                            (survey_id, layout_digest, parents_json, decision.probe_a,
                             decision.probe_b, decision.threshold, decision.ceiling, decision.passed))
        report_id = cursor.lastrowid
        receipt = make_publish_receipt(report_id, survey_id, parents)
        excerpt = build_handover_excerpt(decision, receipt)
        db.execute('INSERT INTO publish_receipts VALUES (?, ?, ?)',
                   (receipt.report_id, receipt.survey_id, _json(receipt.packet_ids)))
        db.execute('INSERT INTO handover_excerpts VALUES (?, ?)',
                   (report_id, _json(asdict(excerpt))))
    return ReportRecord(report_id, survey_id, layout_digest, parents, decision, receipt, excerpt)


def load_report(db: sqlite3.Connection, report_id: int) -> ReportRecord | None:
    if type(report_id) is not int or not 0 < report_id <= 2**63 - 1:
        raise ValueError('invalid report identity')
    row = db.execute('''SELECT r.survey_id, r.layout_digest, r.parents_json, r.probe_a, r.probe_b,
                               r.threshold, r.ceiling, r.passed, p.survey_id, p.packet_ids_json,
                               h.snapshot
                        FROM review_reports AS r
                        JOIN publish_receipts AS p USING (report_id)
                        JOIN handover_excerpts AS h USING (report_id)
                        WHERE r.report_id = ?''', (report_id,)).fetchone()
    if row is None:
        return None
    (survey_id, digest, parents_json, a, b, threshold, ceiling, passed,
     receipt_survey, receipt_ids, excerpt_json) = row
    parents = tuple(AcceptanceReceipt(**item) for item in json.loads(parents_json))
    decision = ReviewDecision(a, b, threshold, ceiling, bool(passed))
    receipt = PublishReceipt(report_id, receipt_survey, tuple(json.loads(receipt_ids)))
    excerpt_fields = json.loads(excerpt_json)
    excerpt_fields['packet_ids'] = tuple(excerpt_fields['packet_ids'])
    return ReportRecord(report_id, survey_id, digest, parents, decision, receipt,
                        HandoverExcerpt(**excerpt_fields))
