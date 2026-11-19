import sqlite3

from demo import initialize_center, initialize_station
from evidence.readback import read_station_packet
from intake.accept import accept
from intake.records import load_acceptance
from reports.readback import retrieve
from survey.revisions import load_revision
from tests.support import INTAKE_TABLES, ProjectCase, REPORT_TABLES, STATION_TABLES, counts


class HandoverTests(ProjectCase):
    def _before_and_after_selection(self):
        layout, _, correction, initial = self.provision_sample()
        self.station.close()
        first = self.review(layout, initial.values(), 6)
        self.reopen_station()
        tile = correction['tile_id']
        packet = self.freeze_packet(layout, tile, correction['rows'])
        self.station.close()
        chosen = dict(initial)
        chosen[tile] = accept(self.center, layout, packet.payload)
        return layout, initial, first, chosen

    def test_amend_and_reopen(self):
        layout, initial, first, chosen = self._before_and_after_selection()
        self.reopen_center()
        second = self.review(layout, chosen.values(), 6)
        at_new_limit = self.review(layout, chosen.values(), 3)
        self.assertEqual((at_new_limit.decision.ceiling, at_new_limit.decision.passed), (3, True))
        self.reopen_center()
        old = retrieve(self.center, first.report_id)
        new = retrieve(self.center, second.report_id)
        self.assertEqual((old, new), (first, second))
        self.assertEqual([(item.decision.ceiling, item.decision.passed) for item in (old, new)],
                         [(5, False), (3, False)])
        for report, expected in ((old, initial), (new, chosen)):
            self.assertEqual({parent.tile_id: parent for parent in report.parents}, expected)
            self.assertEqual(report.receipt.report_id, report.report_id)
            self.assertEqual(report.receipt.packet_ids, tuple(p.packet_id for p in report.parents))
            self.assertEqual(report.handover.packet_ids, report.receipt.packet_ids)
            self.assertEqual((report.handover.probe_a, report.handover.probe_b, report.handover.threshold),
                             ('top', 'bottom', 6))
            self.assertEqual(report.handover.ceiling, report.decision.ceiling)
        self.assertIsNone(retrieve(self.center, second.report_id + 100))
        self.reopen_station()
        for expected, score in ((initial['east'], 5), (chosen['east'], 3)):
            self.assertEqual(load_revision(self.station, expected.revision_id).grid[1][1], score)
            packet = read_station_packet(self.station, expected.packet_id)
            self.assertEqual(packet.revision_id, expected.revision_id)
            self.assertEqual(packet.payload, load_acceptance(self.center, expected.acceptance_id).payload)

    def test_publish_failure(self):
        layout, _, old, chosen = self._before_and_after_selection()
        self.center.execute('''CREATE TRIGGER refuse_receipt BEFORE INSERT ON publish_receipts
            BEGIN SELECT RAISE(ABORT, 'receipt write refused'); END''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'receipt write refused'):
            self.review(layout, chosen.values(), 6)
        self.reopen_center()
        self.assertEqual(counts(self.center, REPORT_TABLES), (1, 1, 1))
        self.assertEqual(retrieve(self.center, old.report_id), old)
        self.center.execute('DROP TRIGGER refuse_receipt')
        fresh = self.review(layout, chosen.values(), 6)
        self.assertEqual(fresh.decision.ceiling, 3)
        self.assertEqual(counts(self.center, REPORT_TABLES), (2, 2, 2))

    def test_failed_commit_rolls_back_all_three_records(self):
        layout, _, old, chosen = self._before_and_after_selection()
        self.center.executescript('''
            PRAGMA foreign_keys = ON;
            CREATE TABLE commit_guard (id INTEGER PRIMARY KEY);
            CREATE TABLE commit_probe (
                key INTEGER REFERENCES commit_guard(id) DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TRIGGER refuse_commit AFTER INSERT ON handover_excerpts
            BEGIN INSERT INTO commit_probe VALUES (1); END;
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
            self.review(layout, chosen.values(), 6)
        self.reopen_center()
        self.assertEqual(counts(self.center, REPORT_TABLES + ('commit_probe',)), (1, 1, 1, 0))
        self.assertEqual(retrieve(self.center, old.report_id), old)
        self.assertIsNone(retrieve(self.center, old.report_id + 1))

    def test_initialize_again(self):
        layout, initial, first, chosen = self._before_and_after_selection()
        second = self.review(layout, chosen.values(), 3)
        self.reopen_station()
        self.reopen_center()
        old_revision = load_revision(self.station, initial['east'].revision_id)
        corrected = load_revision(self.station, chosen['east'].revision_id)
        active_packet = load_acceptance(self.center, chosen['east'].acceptance_id)
        before = (counts(self.station, STATION_TABLES), counts(self.center, INTAKE_TABLES),
                  counts(self.center, REPORT_TABLES))
        self.assertEqual(before, ((1, 3, 3), (1, 3, 3), (2, 2, 2)))
        for _ in range(2):
            initialize_station(self.station)
            initialize_center(self.center)
        self.reopen_station()
        self.reopen_center()
        self.assertEqual((counts(self.station, STATION_TABLES), counts(self.center, INTAKE_TABLES),
                          counts(self.center, REPORT_TABLES)), before)
        self.assertEqual(load_revision(self.station, old_revision.revision_id), old_revision)
        self.assertEqual(load_revision(self.station, corrected.revision_id), corrected)
        self.assertEqual(load_acceptance(self.center, chosen['east'].acceptance_id), active_packet)
        self.assertEqual(retrieve(self.center, first.report_id), first)
        self.assertEqual(retrieve(self.center, second.report_id), second)
