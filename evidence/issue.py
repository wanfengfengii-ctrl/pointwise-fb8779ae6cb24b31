import sqlite3

from evidence.packets import IssuedPacket, record_issued_packet
from evidence.terminals import inspect_terminals, terminal_layers
from survey.catalog import load_survey
from survey.layout import layout_digest
from survey.revisions import load_revision


def _positions(groups):
    return [[(port.x, port.y) for port in group] for group in groups]


def _packet_body(layout, revision):
    tile = layout.tile(revision.tile_id)
    base = inspect_terminals(layout, revision, 0)
    scores = []
    for port in sorted(base.active):
        row, col = tile.to_local(port.x, port.y)
        scores.append((port.x, port.y, revision.grid[row][col]))

    # One four-neighbour connectivity partition of the active public ports per
    # integer gate. Layers are nested as the gate rises; interior pixels and
    # pointwise scores never leave the station.
    layers = [_positions(observation.groups) for observation in terminal_layers(layout, revision)]
    return {"ports": scores, "layers": layers}


def issue(db: sqlite3.Connection, revision_id: str) -> IssuedPacket:
    revision = load_revision(db, revision_id)
    layout = load_survey(db, revision.survey_id)
    return record_issued_packet(db, revision, layout_digest(layout), _packet_body(layout, revision))
