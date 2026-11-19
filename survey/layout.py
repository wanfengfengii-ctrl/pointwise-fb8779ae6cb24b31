from dataclasses import asdict, dataclass
from hashlib import sha256
import json


def _name(value):
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True, order=True)
class PortRef:
    tile_id: str
    x: int
    y: int


@dataclass(frozen=True)
class TileBounds:
    tile_id: str
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    def to_local(self, x, y):
        if type(x) is not int or type(y) is not int:
            raise ValueError('coordinates must be integers')
        if not (self.x <= x < self.right and self.y <= y < self.bottom):
            raise ValueError('position outside tile')
        return y - self.y, x - self.x

    def on_boundary(self, x, y):
        row, col = self.to_local(x, y)
        return row in (0, self.height - 1) or col in (0, self.width - 1)


@dataclass(frozen=True)
class SurveyLayout:
    survey_id: str
    tiles: tuple[TileBounds, ...]
    probes: tuple[tuple[str, PortRef], ...]
    seams: tuple[tuple[PortRef, PortRef], ...] = ()

    def tile(self, tile_id):
        for tile in self.tiles:
            if tile.tile_id == tile_id:
                return tile
        raise KeyError(tile_id)

    def probe(self, name):
        for probe_name, port in self.probes:
            if probe_name == name:
                return port
        raise KeyError(name)

    def ports_for(self, tile_id):
        self.tile(tile_id)
        ports = {port for _, port in self.probes if port.tile_id == tile_id}
        ports.update(port for seam in self.seams for port in seam if port.tile_id == tile_id)
        return tuple(sorted(ports))

    def to_json(self):
        return json.dumps(asdict(validate_layout(self)), sort_keys=True, separators=(',', ':'))

    @classmethod
    def from_json(cls, text):
        try:
            data = json.loads(text)
            if not isinstance(data, dict) or set(data) != {'survey_id', 'tiles', 'probes', 'seams'}:
                raise ValueError('invalid survey fields')
            tiles = tuple(TileBounds(**tile) for tile in data['tiles'])
            probes = tuple((name, PortRef(**port)) for name, port in data['probes'])
            seams = tuple((PortRef(**a), PortRef(**b)) for a, b in data['seams'])
        except (TypeError, ValueError) as error:
            raise ValueError('invalid survey snapshot') from error
        return validate_layout(cls(data['survey_id'], tiles, probes, seams))


def _pairs(entries):
    for pair in entries:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError('expected a pair')
        yield pair


def _port_tile(port, tiles):
    if not isinstance(port, PortRef) or not _name(port.tile_id) or port.tile_id not in tiles:
        raise ValueError('port must reference a survey tile')
    tile = tiles[port.tile_id]
    tile.to_local(port.x, port.y)
    return tile


def validate_layout(layout):
    if not isinstance(layout, SurveyLayout) or not _name(layout.survey_id):
        raise ValueError('survey identity required')
    if not all(isinstance(v, (list, tuple)) for v in (layout.tiles, layout.probes, layout.seams)):
        raise ValueError('tiles, probes and seams must be sequences')
    if not layout.tiles:
        raise ValueError('at least one tile required')

    tiles = {}
    for tile in layout.tiles:
        if not isinstance(tile, TileBounds) or not _name(tile.tile_id) or tile.tile_id in tiles:
            raise ValueError('tile identities must be unique')
        if any(type(v) is not int for v in (tile.x, tile.y, tile.width, tile.height)):
            raise ValueError('tile bounds must be integers')
        if tile.width <= 0 or tile.height <= 0:
            raise ValueError('tile dimensions must be positive')
        for other in tiles.values():
            if (max(tile.x, other.x) < min(tile.right, other.right)
                    and max(tile.y, other.y) < min(tile.bottom, other.bottom)):
                raise ValueError('tile bounds overlap')
        tiles[tile.tile_id] = tile

    probes = {}
    for name, port in _pairs(layout.probes):
        if not _name(name) or name in probes:
            raise ValueError('probe identities must be unique')
        _port_tile(port, tiles)
        probes[name] = port

    seams = set()
    for a, b in _pairs(layout.seams):
        tile_a, tile_b = _port_tile(a, tiles), _port_tile(b, tiles)
        if tile_a == tile_b or not (tile_a.on_boundary(a.x, a.y) and tile_b.on_boundary(b.x, b.y)):
            raise ValueError('seam must reference boundaries of distinct tiles')
        seams.add(tuple(sorted((a, b))))
    return SurveyLayout(layout.survey_id, tuple(tiles[key] for key in sorted(tiles)),
                        tuple(sorted(probes.items())), tuple(sorted(seams)))


def layout_digest(layout):
    return sha256(layout.to_json().encode('utf-8')).hexdigest()
