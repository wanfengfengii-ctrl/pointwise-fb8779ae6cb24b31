from itertools import product

from analysis.compose import connected_at_threshold
from analysis.request import validate_request
from intake.selection import select_accepted_set
from reports.readback import retrieve
from survey.layout import PortRef, SurveyLayout, TileBounds
from tests.support import ProjectCase


def grid_reachable(layout, grids, a, b, threshold):
    active = {}
    for tile in layout.tiles:
        for row, scores in enumerate(grids[tile.tile_id]):
            for col, score in enumerate(scores):
                if score is not None and score >= threshold:
                    active[tile.x + col, tile.y + row] = tile.tile_id
    seams = {frozenset(((p.x, p.y), (q.x, q.y))) for p, q in layout.seams}
    start, goal = (a.x, a.y), (b.x, b.y)
    if start not in active or goal not in active:
        return False
    reached = {start}
    while True:
        more = set()
        for target in active.keys() - reached:
            for source in reached:
                if abs(source[0] - target[0]) + abs(source[1] - target[1]) != 1:
                    continue
                if active[source] == active[target] or frozenset((source, target)) in seams:
                    more.add(target)
                    break
        if not more:
            return goal in reached
        reached |= more


class OracleTests(ProjectCase):
    def test_fragmented_scan_matches_direct_grid_at_every_threshold(self):
        left, right = TileBounds('left', -2, -1, 2, 2), TileBounds('right', 0, -1, 2, 2)
        a, b = PortRef('left', -2, -1), PortRef('left', -2, 0)
        seams = tuple((PortRef('left', -1, y), PortRef('right', 0, y)) for y in (-1, 0))
        layout = SurveyLayout('oracle', (left, right), (('a', a), ('b', b)), seams)
        samples = []
        for p, q, r in product((None, 0, 9), repeat=3):
            grids = {'left': [[7, p], [7, 7]], 'right': [[q, 9], [r, 9]]}
            receipts = self.provision(layout, grids)
            samples.append((grids, receipts))
        self.station.close()
        self.reopen_center()
        for grids, receipts in samples:
            with self.subTest(grids=grids):
                ids = [receipt.acceptance_id for receipt in receipts.values()]
                selected = select_accepted_set(self.center, layout.survey_id, ids)
                request = validate_request(selected.layout, 'a', 'b', 6)
                expected = [grid_reachable(layout, grids, a, b, t) for t in range(101)]
                observed = [connected_at_threshold(selected, request, t) for t in range(101)]
                self.assertEqual(observed, expected)
                ceiling = max((t for t, connected in enumerate(expected) if connected), default=None)
                report = self.review(layout, receipts.values(), 6, 'a', 'b')
                saved = retrieve(self.center, report.report_id)
                self.assertEqual((saved.decision.ceiling, saved.decision.passed), (ceiling, expected[6]))

    def test_sample_reentry_and_amendment_match_direct_grid(self):
        layout, grids, correction, receipts = self.provision_sample()
        changed = dict(grids, east=correction['rows'])
        a, b = layout.probe('top'), layout.probe('bottom')
        initial_layers = [grid_reachable(layout, grids, a, b, t) for t in range(101)]
        changed_layers = [grid_reachable(layout, changed, a, b, t) for t in range(101)]
        self.assertEqual([i for i, connected in enumerate(initial_layers) if connected], list(range(6)))
        self.assertEqual([i for i, connected in enumerate(changed_layers) if connected], list(range(4)))
        self.station.close()
        ids = [receipt.acceptance_id for receipt in receipts.values()]
        selected = select_accepted_set(self.center, layout.survey_id, ids)
        request = validate_request(selected.layout, 'top', 'bottom', 6)
        self.assertEqual([connected_at_threshold(selected, request, t) for t in range(101)], initial_layers)
