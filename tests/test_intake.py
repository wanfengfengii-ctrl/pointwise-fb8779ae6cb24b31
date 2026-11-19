from dataclasses import replace
import json

from intake.accept import accept
from intake.records import load_acceptance, load_accepted_layout
from survey.catalog import register
from tests.support import INTAKE_TABLES, ProjectCase, counts, line_layout


class IntakeTests(ProjectCase):
    def test_mixed_survey(self):
        own = line_layout('own')
        other = line_layout('other')
        register(self.station, own)
        register(self.station, other)
        packet = self.freeze_packet(other, 'one', [[7, 7, 7]])
        with self.assertRaises(ValueError):
            accept(self.center, own, packet.payload)
        self.reopen_center()
        self.assertEqual(counts(self.center, INTAKE_TABLES), (0, 0, 0))

    def test_changed_layout_with_same_name(self):
        layout = line_layout()
        register(self.station, layout)
        packet = self.freeze_packet(layout, 'one', [[7, 7, 7]])
        edited = replace(layout, probes=layout.probes[:-1])
        with self.assertRaises(ValueError):
            accept(self.center, edited, packet.payload)
        self.assertEqual(counts(self.center, INTAKE_TABLES), (0, 0, 0))

    def test_invalid_envelope(self):
        layout = line_layout()
        register(self.station, layout)
        packet = self.freeze_packet(layout, 'one', [[7, 7, 7]])
        wire = json.loads(packet.payload)
        invalid = ['{', '{}', json.dumps(dict(wire, version=True)), json.dumps(dict(wire, version=2)),
                   json.dumps(dict(wire, body=[])), json.dumps(dict(wire, packet_id='')),
                   json.dumps(dict(wire, tile_id='outside')),
                   packet.payload[:-1] + ',"version":1}']
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                accept(self.center, layout, payload)
        self.assertEqual(counts(self.center, INTAKE_TABLES), (0, 0, 0))

    def test_exact_acceptance_after_reopen(self):
        layout = line_layout()
        register(self.station, layout)
        packet = self.freeze_packet(layout, 'one', [[7, 2, 7]])
        payload = '\n ' + packet.payload + '\n'
        receipt = accept(self.center, layout, payload)
        self.station.close()
        self.reopen_center()
        saved = load_acceptance(self.center, receipt.acceptance_id)
        self.assertEqual(saved.payload, payload)
        self.assertEqual(saved.receipt, receipt)
        self.assertEqual(receipt.revision_id, packet.revision_id)
        self.assertEqual(load_accepted_layout(self.center, layout.survey_id), layout)
        self.assertEqual(accept(self.center, layout, payload), receipt)
        with self.assertRaises(ValueError):
            accept(self.center, layout, packet.payload)
        self.assertEqual(counts(self.center, INTAKE_TABLES), (1, 1, 1))
