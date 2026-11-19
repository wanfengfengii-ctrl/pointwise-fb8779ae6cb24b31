from dataclasses import replace
import json

from demo import load_sample
from evidence.issue import issue
from evidence.readback import read_station_packet
from evidence.terminals import inspect_terminals, list_terminals
from survey.catalog import load_survey, register
from survey.freeze import freeze_grid
from survey.ingest import GridDraft
from survey.layout import PortRef, SurveyLayout, TileBounds, validate_layout
from survey.revisions import append_revision, load_revision
from tests.support import ProjectCase, STATION_TABLES, counts, line_layout


class StationTests(ProjectCase):
    def test_layout(self):
        layout, _, _ = load_sample()
        self.assertEqual(register(self.station, layout), layout.survey_id)
        reordered = replace(layout, tiles=layout.tiles[::-1], seams=tuple((b, a) for a, b in layout.seams))
        self.assertEqual(register(self.station, reordered), layout.survey_id)
        self.assertEqual(load_survey(self.station, layout.survey_id), validate_layout(layout))
        self.assertEqual(layout.tile('east').to_local(5, 2), (2, 2))
        with self.assertRaises(ValueError):
            layout.tile('east').to_local(6, 2)
        invalid = (
            replace(layout, tiles=layout.tiles + (TileBounds('overlap', 2, 2, 2, 2),)),
            replace(layout, tiles=layout.tiles + (layout.tiles[0],)),
            replace(layout, tiles=layout.tiles + (TileBounds('empty', 9, 0, 0, 1),)),
            replace(layout, probes=layout.probes + (('stray', PortRef('west', 0, 9)),)),
            replace(layout, probes=layout.probes + (layout.probes[0],)),
            replace(layout, seams=((PortRef('missing', 0, 0), PortRef('east', 3, 0)),)),
            replace(layout, seams=((PortRef('west', 1, 1), PortRef('east', 3, 0)),)),
            replace(layout, probes=layout.probes[:-1]),
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                register(self.station, candidate)
        self.assertEqual(counts(self.station, STATION_TABLES), (1, 0, 0))
        self.assertEqual(load_survey(self.station, layout.survey_id), layout)
        self.assertEqual(SurveyLayout.from_json(layout.to_json()), layout)

    def test_freeze_and_issue(self):
        layout = line_layout()
        register(self.station, layout)
        packet = self.freeze_packet(layout, 'one', [[100, 6, 9]])
        revision = load_revision(self.station, packet.revision_id)
        body = json.loads(packet.payload)
        self.assertEqual((body['version'], body['survey_id'], body['tile_id'], body['revision_id'], body['packet_id']),
                         (1, layout.survey_id, 'one', revision.revision_id, packet.packet_id))
        a, b = (layout.probe(name) for name in ('a', 'b'))
        self.assertEqual(list_terminals(layout, 'one'), (a, b))
        self.assertEqual(inspect_terminals(layout, revision, 6).groups, ((a, b),))
        self.assertEqual(inspect_terminals(layout, revision, 7).groups, ((a,), (b,)))
        self.assertEqual(read_station_packet(self.station, packet.packet_id), packet)

    def test_freeze_snapshot(self):
        layout = line_layout()
        register(self.station, layout)
        rows = [[100, 0, None]]
        old = freeze_grid(self.station, layout.survey_id, 'one', rows)
        rows[0][1] = 3
        new = freeze_grid(self.station, layout.survey_id, 'one', rows)
        self.reopen_station()
        self.assertNotEqual(old, new)
        self.assertEqual(load_revision(self.station, old).grid, ((100, 0, None),))
        self.assertEqual(load_revision(self.station, new).grid, ((100, 3, None),))

    def test_invalid_score(self):
        layout = line_layout()
        register(self.station, layout)
        old = freeze_grid(self.station, layout.survey_id, 'one', [[100, 8, 100]])
        with self.assertRaises(ValueError):
            freeze_grid(self.station, layout.survey_id, 'one', [[100, 101, 100]])
        self.reopen_station()
        self.assertEqual(counts(self.station, STATION_TABLES), (1, 1, 0))
        self.assertEqual(load_revision(self.station, old).grid, ((100, 8, 100),))

    def test_invalid_shape_and_non_integer(self):
        layout = line_layout()
        register(self.station, layout)
        for rows in ([], [[7]], [[7, 0, 7], [7]], [[7, True, 7]], [[7, 1.0, 7]],
                     [[7, '1', 7]], [[7, -1, 7]]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                freeze_grid(self.station, layout.survey_id, 'one', rows)
        with self.assertRaises(KeyError):
            freeze_grid(self.station, layout.survey_id, 'absent', [[7, 7, 7]])
        mismatched = GridDraft(layout.survey_id, TileBounds('one', 0, 0, 1, 1), ((7,),))
        with self.assertRaises(ValueError):
            append_revision(self.station, mismatched)
        self.assertEqual(counts(self.station, STATION_TABLES), (1, 0, 0))

    def test_active_singleton(self):
        layout = line_layout(length=1)
        register(self.station, layout)
        present = self.freeze_packet(layout, 'one', [[0]])
        absent = self.freeze_packet(layout, 'one', [[None]])
        a = layout.probe('a')
        revision = load_revision(self.station, present.revision_id)
        self.assertEqual(inspect_terminals(layout, revision, 0).groups, ((a,),))
        self.assertEqual(inspect_terminals(layout, revision, 1).active, frozenset())
        self.assertEqual(inspect_terminals(layout, load_revision(self.station, absent.revision_id), 0).groups, ())

    def test_revision_sensitive_evidence(self):
        layout, grids, correction = load_sample()
        register(self.station, layout)
        first = self.freeze_packet(layout, 'east', grids['east'])
        second = self.freeze_packet(layout, 'east', correction['rows'])
        upper, lower = PortRef('east', 3, 0), PortRef('east', 3, 2)
        for revision_id, expected in ((first.revision_id, (True, True, False)),
                                      (second.revision_id, (False, False, False))):
            revision = load_revision(self.station, revision_id)
            actual = []
            for t in (4, 5, 6):
                groups = inspect_terminals(layout, revision, t).groups
                actual.append(any(upper in group and lower in group for group in groups))
            self.assertEqual(tuple(actual), expected)
        old_body = json.loads(read_station_packet(self.station, first.packet_id).payload)['body']
        new_body = json.loads(read_station_packet(self.station, second.packet_id).payload)['body']
        self.assertNotEqual(old_body, new_body, 'distinct frozen scans must retain their different port relations')

    def test_packet_readback_and_unknown_revision(self):
        layout = line_layout()
        register(self.station, layout)
        packet = self.freeze_packet(layout, 'one', [[7, 2, 7]])
        self.freeze_packet(layout, 'one', [[7, 4, 7]])
        self.reopen_station()
        self.assertEqual(read_station_packet(self.station, packet.packet_id), packet)
        with self.assertRaises(KeyError):
            issue(self.station, '0' * 32)
        with self.assertRaises(KeyError):
            read_station_packet(self.station, '0' * 32)
        self.assertEqual(counts(self.station, STATION_TABLES), (1, 2, 2))
