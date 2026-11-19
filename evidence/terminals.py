from collections import defaultdict
from dataclasses import dataclass

from evidence.local_grid import active_components
from survey.layout import PortRef, SurveyLayout
from survey.revisions import FrozenRevision


@dataclass(frozen=True)
class TerminalObservation:
    threshold: int
    groups: tuple[tuple[PortRef, ...], ...]

    @property
    def active(self):
        return frozenset(port for group in self.groups for port in group)


def list_terminals(layout: SurveyLayout, tile_id: str) -> tuple[PortRef, ...]:
    return layout.ports_for(tile_id)


def inspect_terminals(layout: SurveyLayout, revision: FrozenRevision,
                      threshold: int) -> TerminalObservation:
    if revision.survey_id != layout.survey_id:
        raise ValueError('revision belongs to another survey')
    tile = layout.tile(revision.tile_id)
    labels = active_components(revision.grid, threshold)
    groups = defaultdict(list)
    for port in list_terminals(layout, revision.tile_id):
        cell = tile.to_local(port.x, port.y)
        if cell in labels:
            groups[labels[cell]].append(port)
    return TerminalObservation(threshold, tuple(sorted(tuple(group) for group in groups.values())))


def terminal_layers(layout: SurveyLayout, revision: FrozenRevision) -> tuple[TerminalObservation, ...]:
    """Public port activity and true in-tile connectivity for every gate 0..100.

    Interior pixel coordinates and pointwise scores remain at the station; only
    the public ports' grouping at each integer threshold leaves in the packet.
    """
    if revision.survey_id != layout.survey_id:
        raise ValueError('revision belongs to another survey')
    return tuple(inspect_terminals(layout, revision, threshold) for threshold in range(101))
