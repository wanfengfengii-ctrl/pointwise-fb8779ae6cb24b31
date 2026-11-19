from dataclasses import dataclass

from survey.layout import SurveyLayout, TileBounds

Grid = tuple[tuple[int | None, ...], ...]


@dataclass(frozen=True)
class GridDraft:
    survey_id: str
    tile: TileBounds
    grid: Grid

    def __post_init__(self):
        if not isinstance(self.tile, TileBounds):
            raise ValueError('draft requires tile bounds')
        rows = self.grid
        if not isinstance(rows, (list, tuple)) or len(rows) != self.tile.height:
            raise ValueError('wrong grid height')
        snapshot = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) != self.tile.width:
                raise ValueError('wrong grid width')
            for score in row:
                if score is not None and (type(score) is not int or not 0 <= score <= 100):
                    raise ValueError('pixel score must be an integer from 0 to 100 or None')
            snapshot.append(tuple(row))
        object.__setattr__(self, 'grid', tuple(snapshot))


def validate_scan(layout: SurveyLayout, tile_id: str, rows) -> GridDraft:
    return GridDraft(layout.survey_id, layout.tile(tile_id), rows)
