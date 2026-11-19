import sqlite3

from analysis.decision import evaluate_review
from analysis.request import validate_request
from intake.selection import select_accepted_set
from reports.archive import ReportRecord, commit_report
from survey.layout import layout_digest


def review_issue(db: sqlite3.Connection, survey_id: str, acceptance_ids,
                 probe_a: str, probe_b: str, threshold: int) -> ReportRecord:
    accepted = select_accepted_set(db, survey_id, acceptance_ids)
    request = validate_request(accepted.layout, probe_a, probe_b, threshold)
    decision = evaluate_review(accepted, request)
    return commit_report(db, accepted.layout.survey_id, layout_digest(accepted.layout),
                         accepted.parents, decision)
