from intake.records import AcceptedPacket
from survey.layout import SurveyLayout, layout_digest


def validate_coverage(layout: SurveyLayout, packets: tuple[AcceptedPacket, ...]):
    expected_tiles = {tile.tile_id for tile in layout.tiles}
    digest = layout_digest(layout)
    seen = set()
    for packet in packets:
        envelope = packet.envelope
        if envelope.survey_id != layout.survey_id or envelope.layout_digest != digest:
            raise ValueError('selected packet belongs to another survey layout')
        tile = envelope.tile_id
        if tile not in expected_tiles or tile in seen:
            raise ValueError(f'foreign or repeated tile {tile!r}')
        seen.add(tile)
    missing = expected_tiles - seen
    if missing:
        raise ValueError(f'missing survey tiles: {sorted(missing)}')
