import json

from analysis.compose import connected_at_threshold
from analysis.request import validate_request
from intake.accept import accept
from intake.selection import select_accepted_set
from reports.publish import review_issue
from reports.readback import retrieve
from survey.catalog import register
from survey.layout import PortRef, SurveyLayout, TileBounds
from tests.support import ProjectCase, REPORT_TABLES, counts, line_layout


class ReviewTests(ProjectCase):
    def test_reentry(self):
        layout, grids, _, receipts = self.provision_sample()
        self.station.close()
        self.reopen_center()
        above = self.review(layout, receipts.values(), 6)
        self.assertEqual((above.decision.ceiling, above.decision.passed), (5, False),
                         'REENTRY_CEILING_AND_GATE')
        exact = self.review(layout, receipts.values(), 5)
        self.assertEqual((exact.decision.ceiling, exact.decision.passed), (5, True))
        self.reopen_center()
        held = retrieve(self.center, above.report_id)
        cleared = retrieve(self.center, exact.report_id)
        self.assertEqual(held, above)
        self.assertEqual(cleared, exact)
        actions = [held.handover.action, cleared.handover.action]
        self.assertEqual(actions, ['补测', '放行'])
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'reentry', 'input': {'grids': grids, 'thresholds': [6, 5]},
            'expected': [[5, False], [5, True]],
            'actual': [[held.decision.ceiling, held.decision.passed],
                       [cleared.decision.ceiling, cleared.decision.passed]],
            'downstream_expected': ['补测', '放行'], 'downstream_actual': actions,
            'code_paths': ['evidence/issue.py', 'analysis/compose.py', 'reports/publish.py',
                           'reports/readback.py'],
            'oracle': '上、下排以两条正对接缝连入右幅，中间一行最大为 5。'
        }, ensure_ascii=False))

    def test_consumer_layers_and_input_order(self):
        layout, _, _, receipts = self.provision_sample()
        self.station.close()
        self.reopen_center()
        ids = [receipt.acceptance_id for receipt in receipts.values()]
        accepted = select_accepted_set(self.center, layout.survey_id, ids)
        request = validate_request(accepted.layout, 'top', 'bottom', 6)
        self.assertEqual([connected_at_threshold(accepted, request, t) for t in (0, 4, 5, 6, 7, 100)],
                         [True, True, True, False, False, False])
        first = review_issue(self.center, layout.survey_id, ids, 'top', 'bottom', 6)
        other = review_issue(self.center, layout.survey_id, ids[::-1], 'top', 'bottom', 6)
        self.assertEqual(first.parents, other.parents)
        self.assertEqual(first.decision, other.decision)
        self.assertEqual(tuple(p.tile_id for p in first.parents), ('east', 'west'))

    def test_corner_and_missing(self):
        a, b = PortRef('a', 0, 0), PortRef('b', 1, 1)
        corner = SurveyLayout('corner', (TileBounds('a', 0, 0, 1, 1), TileBounds('b', 1, 1, 1, 1)),
                              (('a', a), ('b', b)), ((a, b),))
        receipts = self.provision(corner, {'a': [[100]], 'b': [[100]]})
        result = self.review(corner, receipts.values(), 0, 'a', 'b')
        self.assertEqual((result.decision.ceiling, result.decision.passed), (None, False))
        layout = line_layout()
        register(self.station, layout)
        for middle, expected in ((0, (0, True)), (None, (None, False))):
            packet = self.freeze_packet(layout, 'one', [[7, middle, 7]])
            receipt = accept(self.center, layout, packet.payload)
            result = self.review(layout, [receipt], 0, 'a', 'b')
            saved = retrieve(self.center, result.report_id)
            self.assertEqual((saved.decision.ceiling, saved.decision.passed), expected)
            self.assertEqual(saved.handover.ceiling, expected[0])

    def test_seam_diagonal_and_positive_control(self):
        left_top, left_bottom = PortRef('left', 0, 0), PortRef('left', 0, 1)
        right_top, right_bottom = PortRef('right', 1, 0), PortRef('right', 1, 1)
        layout = SurveyLayout('seam-offset', (TileBounds('left', 0, 0, 1, 2),
                                               TileBounds('right', 1, 0, 1, 2)),
                              (('a', left_top), ('b', right_bottom)),
                              ((left_top, right_top), (left_bottom, right_bottom), (left_top, right_bottom)))
        receipts = self.provision(layout, {'left': [[100], [None]], 'right': [[None], [100]]})
        report = self.review(layout, receipts.values(), 0, 'a', 'b')
        self.assertIsNone(report.decision.ceiling)
        self.assertFalse(report.decision.passed)
        packet = self.freeze_packet(layout, 'right', [[84], [100]])
        receipts['right'] = accept(self.center, layout, packet.payload)
        report = self.review(layout, receipts.values(), 84, 'a', 'b')
        self.assertEqual((report.decision.ceiling, report.decision.passed), (84, True))

    def test_colocated_probes_use_activity(self):
        layout = line_layout(length=1)
        register(self.station, layout)
        for score, expected in ((100, (100, True)), (None, (None, False))):
            packet = self.freeze_packet(layout, 'one', [[score]])
            receipt = accept(self.center, layout, packet.payload)
            report = self.review(layout, [receipt], 100, 'a', 'b')
            self.assertEqual((report.decision.ceiling, report.decision.passed), expected)

    def test_invalid_requests(self):
        layout, _, correction, receipts = self.provision_sample()
        corrected = self.freeze_packet(layout, correction['tile_id'], correction['rows'])
        new_east = accept(self.center, layout, corrected.payload)
        full = list(receipts.values())
        other = line_layout('other')
        other_receipt = self.provision(other, {'one': [[100, 100, 100]]})['one']
        cases = (([], 0, 'top'), ([receipts['west']], 0, 'top'),
                 (full + [new_east], 0, 'top'), (full + [other_receipt], 0, 'top'),
                 (full, 0, 'unregistered'), (full, -1, 'top'), (full, 101, 'top'),
                 (full, True, 'top'), (full, 0.0, 'top'))
        for selected, threshold, a in cases:
            with self.subTest(selected=selected, threshold=threshold, a=a), self.assertRaises(ValueError):
                self.review(layout, selected, threshold, a=a)
        with self.assertRaises(ValueError):
            review_issue(self.center, layout.survey_id, [999], 'top', 'bottom', 0)
        self.reopen_center()
        self.assertEqual(counts(self.center, REPORT_TABLES), (0, 0, 0))

    def test_body_failure_precedes_publication(self):
        layout = line_layout()
        register(self.station, layout)
        issued = self.freeze_packet(layout, 'one', [[7, 7, 7]])
        envelope = json.loads(issued.payload)
        envelope['body'] = {}
        receipt = accept(self.center, layout, json.dumps(envelope))
        with self.assertRaises(ValueError):
            self.review(layout, [receipt], 0, 'a', 'b')
        self.assertEqual(counts(self.center, REPORT_TABLES), (0, 0, 0))
