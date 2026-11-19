"""Regressions for the source-off connectivity re-review fix.

The station packet must preserve, for every integer gate 0..100, the active
state of the public ports and their true in-tile four-neighbour connectivity,
while interior pixel coordinates and pointwise scores stay at the station.
"""
import json
from uuid import uuid4

from analysis.compose import connected_at_threshold
from analysis.request import validate_request
from demo import load_sample
from evidence.local_grid import active_components
from intake.accept import accept
from intake.records import load_acceptance
from intake.selection import select_accepted_set
from reports.publish import review_issue
from reports.readback import retrieve
from survey.catalog import register
from survey.layout import PortRef
from tests.support import ProjectCase, REPORT_TABLES, counts, line_layout
from tests.test_oracle import grid_reachable


def expected_layers(layout, tile_id, grid):
    """Independent reference: per-gate active public ports and components."""
    tile = layout.tile(tile_id)
    ports = layout.ports_for(tile_id)
    result = []
    for threshold in range(101):
        labels = active_components(grid, threshold)
        groups = {}
        for port in ports:
            cell = tile.to_local(port.x, port.y)
            if cell in labels:
                groups.setdefault(labels[cell], []).append(port)
        canonical = tuple(sorted(tuple(sorted(members)) for members in groups.values()))
        result.append((frozenset(port for group in canonical for port in group), canonical))
    return result


def body_layers(tile_id, raw_layers):
    layers = []
    for layer in raw_layers:
        groups = tuple(sorted(tuple(sorted(PortRef(tile_id, x, y) for x, y in group))
                               for group in layer))
        layers.append((frozenset(port for group in groups for port in group), groups))
    return layers


class StationLayerTests(ProjectCase):
    def _payload(self, receipt):
        return load_acceptance(self.center, receipt.acceptance_id).payload

    def test_packet_preserves_all_gates_and_revision_relations(self):
        layout, grids, correction, receipts = self.provision_sample()
        for tile_id, grid in grids.items():
            with self.subTest(tile=tile_id):
                payload = self._payload(receipts[tile_id])
                raw = json.loads(payload)['body']
                self.assertEqual(set(raw), {'ports', 'layers'})
                self.assertEqual(len(raw['layers']), 101)
                observed = body_layers(tile_id, raw['layers'])
                expected = expected_layers(layout, tile_id, tuple(tuple(row) for row in grid))
                self.assertEqual(observed, expected)
                # Every active public port occupies a group, singletons included.
                for threshold, (active, groups) in enumerate(observed):
                    self.assertEqual(frozenset().union(*groups) if groups else frozenset(), active)
                    self.assertTrue(all(group for group in groups))
                # Layers only shrink and split as the gate rises.
                for threshold in range(1, 101):
                    lower_active, lower_groups = observed[threshold - 1]
                    active, groups = observed[threshold]
                    self.assertTrue(active <= lower_active)
                    for group in groups:
                        self.assertTrue(any(set(group) <= set(earlier) for earlier in lower_groups))

        east_id = 'east'
        east = receipts[east_id]
        east_layers = body_layers(east_id, json.loads(self._payload(east))['body']['layers'])
        upper, lower = PortRef('east', 3, 0), PortRef('east', 3, 2)

        def joined(threshold):
            return any(upper in group and lower in group for group in east_layers[threshold][1])

        self.assertEqual([joined(t) for t in range(101)], [t <= 5 for t in range(101)])
        # At gate 6 the route through the 5-point interior cell is gone and the
        # surviving seam ports remain present as singleton groups.
        active, groups = east_layers[6]
        self.assertEqual(active, {PortRef('east', 3, 0), PortRef('east', 3, 2)})
        self.assertEqual(groups, ((PortRef('east', 3, 0),), (PortRef('east', 3, 2),)))

        corrected = self.freeze_packet(layout, east_id, correction['rows'])
        corrected_receipt = accept(self.center, layout, corrected.payload)
        new_layers = body_layers(east_id,
                                 json.loads(self._payload(corrected_receipt))['body']['layers'])
        self.assertNotEqual(json.loads(self._payload(east))['body'],
                            json.loads(self._payload(corrected_receipt))['body'])
        new_joined = [any({upper, lower} <= set(group) for group in groups)
                      for _, groups in new_layers]
        self.assertEqual(new_joined, [t <= 3 for t in range(101)])

    def test_interior_choke_cell_sets_ceiling_offline(self):
        layout = line_layout()
        register(self.station, layout)
        cases = (([[9, 4, 9]], 4, True),
                 ([[9, 0, 9]], 0, True),
                 ([[9, None, 9]], None, False))
        packets = [self.freeze_packet(layout, 'one', rows) for rows, _, _ in cases]
        self.station.close()
        self.reopen_center()
        for packet, (_, ceiling, passes_at_zero) in zip(packets, cases):
            receipt = accept(self.center, layout, packet.payload)
            ids = [receipt.acceptance_id]
            selected = select_accepted_set(self.center, layout.survey_id, ids)
            request = validate_request(selected.layout, 'a', 'b', 0)
            observed = [connected_at_threshold(selected, request, t) for t in range(101)]
            if ceiling is None:
                self.assertFalse(any(observed))
            else:
                self.assertEqual([t for t, ok in enumerate(observed) if ok],
                                 list(range(ceiling + 1)))
            report = review_issue(self.center, layout.survey_id, ids, 'a', 'b', 0)
            saved = retrieve(self.center, report.report_id)
            self.assertEqual((saved.decision.ceiling, saved.decision.passed),
                             (ceiling, passes_at_zero))
            self.assertEqual(saved.handover.ceiling, ceiling)
            self.assertEqual(saved.handover.action, '放行' if passes_at_zero else '补测')

    def test_offline_layers_match_global_flood_at_every_gate(self):
        layout, grids, correction, receipts = self.provision_sample()
        changed = dict(grids, east=correction['rows'])
        corrected_receipt = accept(
            self.center, layout,
            self.freeze_packet(layout, correction['tile_id'], correction['rows']).payload)
        self.station.close()
        self.reopen_center()
        a, b = layout.probe('top'), layout.probe('bottom')
        chosen = dict(receipts)
        chosen[correction['tile_id']] = corrected_receipt
        selections = (
            (grids, receipts, list(range(6))),
            (changed, chosen, list(range(4))),
        )
        for scan, chosen_receipts, connected_gates in selections:
            ids = [item.acceptance_id for item in chosen_receipts.values()]
            selected = select_accepted_set(self.center, layout.survey_id, ids)
            request = validate_request(selected.layout, 'top', 'bottom', 6)
            observed = [connected_at_threshold(selected, request, t) for t in range(101)]
            expected = [grid_reachable(layout, scan, a, b, t) for t in range(101)]
            self.assertEqual(observed, expected)
            self.assertEqual([t for t, ok in enumerate(observed) if ok], connected_gates)

    def test_malformed_layers_leave_no_report_or_receipt(self):
        layout = line_layout()
        register(self.station, layout)
        good = self.freeze_packet(layout, 'one', [[7, 4, 7]])
        good_receipt = accept(self.center, layout, good.payload)
        wire = json.loads(good.payload)
        body = wire['body']

        def tamper(new_body):
            edited = dict(wire)
            edited['packet_id'] = uuid4().hex
            edited['body'] = new_body
            return json.dumps(edited)

        broken_nesting = {'ports': body['ports'], 'layers': list(body['layers'])}
        broken_nesting['layers'][4] = [[[0, 0]], [[2, 0]]]
        broken_nesting['layers'][5] = [[[0, 0], [2, 0]]]
        tampered = (
            {'ports': body['ports'], 'groups': body['layers'][0]},
            {'ports': body['ports'], 'layers': body['layers'][:-1]},
            {'ports': body['ports'],
             'layers': [layer[:-1] if layer and threshold == 0 else layer
                        for threshold, layer in enumerate(body['layers'])]},
            broken_nesting,
            {'ports': body['ports'],
             'layers': [[[[0, 0], [9, 9]]] if threshold == 0 else layer
                        for threshold, layer in enumerate(body['layers'])]},
            {'ports': body['ports'],
             'layers': [[[[0, 0], [0, 0]]] if threshold == 0 else layer
                        for threshold, layer in enumerate(body['layers'])]},
        )
        for edited_body in tampered:
            with self.subTest(edited_body=edited_body):
                receipt = accept(self.center, layout, tamper(edited_body))
                with self.assertRaises(ValueError):
                    review_issue(self.center, layout.survey_id,
                                 [receipt.acceptance_id], 'a', 'b', 0)
                self.reopen_center()
                self.assertEqual(counts(self.center, REPORT_TABLES), (0, 0, 0))

        report = review_issue(self.center, layout.survey_id,
                              [good_receipt.acceptance_id], 'a', 'b', 4)
        self.assertEqual((report.decision.ceiling, report.decision.passed), (4, True))
        self.assertEqual(counts(self.center, REPORT_TABLES), (1, 1, 1))
