from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from demo import initialize_center, initialize_station, load_sample
from evidence.issue import issue
from intake.accept import accept
from reports.publish import review_issue
from survey.catalog import register
from survey.freeze import freeze_grid
from survey.layout import PortRef, SurveyLayout, TileBounds


REPORT_TABLES = ('review_reports', 'publish_receipts', 'handover_excerpts')
INTAKE_TABLES = ('accepted_surveys', 'accepted_packets', 'acceptance_receipts')
STATION_TABLES = ('station_surveys', 'frozen_revisions', 'issued_packets')


def counts(db, tables):
    return tuple(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in tables)


def line_layout(survey_id='line', length=3):
    return SurveyLayout(survey_id, (TileBounds('one', 0, 0, length, 1),),
                        (('a', PortRef('one', 0, 0)), ('b', PortRef('one', length - 1, 0))))


class ProjectCase(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.station_file = root / 'station.sqlite'
        self.center_file = root / 'center.sqlite'
        self.station = self.open_store(self.station_file)
        self.center = self.open_store(self.center_file)
        initialize_station(self.station)
        initialize_center(self.center)

    def open_store(self, path):
        db = sqlite3.connect(path)
        self.addCleanup(db.close)
        return db

    def reopen_center(self):
        self.center.close()
        self.center = self.open_store(self.center_file)

    def reopen_station(self):
        self.station.close()
        self.station = self.open_store(self.station_file)

    def freeze_packet(self, layout, tile_id, rows):
        return issue(self.station, freeze_grid(self.station, layout.survey_id, tile_id, rows))

    def provision(self, layout, grids):
        register(self.station, layout)
        packets = {tile: self.freeze_packet(layout, tile, rows) for tile, rows in grids.items()}
        return {tile: accept(self.center, layout, packet.payload) for tile, packet in packets.items()}

    def provision_sample(self):
        layout, grids, correction = load_sample()
        return layout, grids, correction, self.provision(layout, grids)

    def review(self, layout, receipts, threshold, a='top', b='bottom'):
        return review_issue(self.center, layout.survey_id, [item.acceptance_id for item in receipts],
                            a, b, threshold)
