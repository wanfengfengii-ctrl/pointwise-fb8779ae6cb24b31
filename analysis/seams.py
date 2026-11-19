from dataclasses import dataclass

from survey.layout import PortRef, SurveyLayout


@dataclass(frozen=True)
class SeamLink:
    a: PortRef
    b: PortRef


def enumerate_seam_links(layout: SurveyLayout) -> tuple[SeamLink, ...]:
    return tuple(SeamLink(a, b) for a, b in layout.seams
                 if a.tile_id != b.tile_id and abs(a.x - b.x) + abs(a.y - b.y) == 1)
