from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from evidence.issue import issue
from evidence.packets import initialize_packet_store
from intake.accept import accept
from intake.records import initialize_intake_store
from reports.archive import initialize_report_archive
from reports.publish import review_issue
from reports.readback import retrieve
from survey.catalog import initialize_catalog, register
from survey.freeze import freeze_grid
from survey.layout import SurveyLayout
from survey.revisions import initialize_revision_store


def load_sample():
    sample_path = Path(__file__).resolve().parent / 'examples' / 'scan.json'
    data = json.loads(sample_path.read_text(encoding='utf-8'))
    return SurveyLayout.from_json(json.dumps(data['layout'])), data['grids'], data['correction']


def initialize_station(db):
    initialize_catalog(db)
    initialize_revision_store(db)
    initialize_packet_store(db)


def initialize_center(db):
    initialize_intake_store(db)
    initialize_report_archive(db)


def main():
    layout, grids, correction = load_sample()
    with TemporaryDirectory() as workspace:
        station_file = Path(workspace) / 'station.sqlite'
        center_file = Path(workspace) / 'center.sqlite'
        with closing(sqlite3.connect(station_file)) as station:
            initialize_station(station)
            register(station, layout)
            initial = {tile: issue(station, freeze_grid(station, layout.survey_id, tile, rows))
                       for tile, rows in grids.items()}
        with closing(sqlite3.connect(center_file)) as center:
            initialize_center(center)
            selected = {tile: accept(center, layout, packet.payload).acceptance_id
                        for tile, packet in initial.items()}
            old_report = review_issue(center, layout.survey_id, list(selected.values()), 'top', 'bottom', 6)
        with closing(sqlite3.connect(station_file)) as station:
            tile = correction['tile_id']
            corrected = issue(station, freeze_grid(station, layout.survey_id, tile, correction['rows']))
        with closing(sqlite3.connect(center_file)) as center:
            selected[tile] = accept(center, layout, corrected.payload).acceptance_id
            new_report = review_issue(center, layout.survey_id, list(selected.values()), 'top', 'bottom', 6)
        with closing(sqlite3.connect(center_file)) as center:
            old_copy = retrieve(center, old_report.report_id)
            new_copy = retrieve(center, new_report.report_id)
            assert old_copy == old_report and new_copy == new_report
            actual = [old_report.decision.ceiling, new_report.decision.ceiling]
            downstream = [old_copy.handover.action, new_copy.handover.action]
            assert actual == [5, 3] and downstream == ['补测', '补测']
            assert next(parent.packet_id for parent in old_copy.parents if parent.tile_id == tile) == initial[tile].packet_id
            assert next(parent.packet_id for parent in new_copy.parents if parent.tile_id == tile) == corrected.packet_id
            for record in (old_copy, new_copy):
                print(f'报告 {record.report_id}  上限 {record.decision.ceiling}  '
                      f'请求门槛 {record.decision.threshold}  {record.handover.action}')
            print('POINTWISE_SCENARIO ' + json.dumps({
                'case_id': 'historical',
                'input': {'grids': grids, 'correction': correction, 'requested_threshold': 6},
                'expected': [5, 3], 'actual': actual,
                'downstream_expected': ['补测', '补测'], 'downstream_actual': downstream,
                'code_paths': ['evidence/issue.py', 'analysis/compose.py', 'reports/archive.py',
                               'reports/readback.py'],
                'oracle': '东西幅上、下排均为 7 分，连接两排的右幅中间行最大值先为 5 后为 3。'
            }, ensure_ascii=False))


if __name__ == '__main__':
    main()
