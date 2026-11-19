from dataclasses import dataclass
import json


@dataclass(frozen=True)
class PacketEnvelope:
    version: int
    survey_id: str
    layout_digest: str
    tile_id: str
    revision_id: str
    packet_id: str
    body: str
    payload: str


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON field')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f'invalid JSON constant {value}')


def _hex(value, size):
    return isinstance(value, str) and len(value) == size and all(c in '0123456789abcdef' for c in value)


def validate_envelope(payload: str) -> PacketEnvelope:
    if not isinstance(payload, str):
        raise ValueError('station packet must be JSON text')
    try:
        data = json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as error:
        raise ValueError('invalid station packet JSON') from error
    fields = {'version', 'survey_id', 'layout_digest', 'tile_id', 'revision_id', 'packet_id', 'body'}
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError('invalid station packet fields')
    if type(data['version']) is not int or data['version'] != 1:
        raise ValueError('unsupported station packet version')
    for key in ('survey_id', 'tile_id'):
        if not isinstance(data[key], str) or not data[key].strip():
            raise ValueError('missing station packet identity')
    if not (_hex(data['layout_digest'], 64) and _hex(data['packet_id'], 32)
            and _hex(data['revision_id'], 32)):
        raise ValueError('invalid station packet identity')
    if not isinstance(data['body'], dict):
        raise ValueError('station packet body must be a JSON object')
    data['body'] = json.dumps(data['body'], sort_keys=True, separators=(',', ':'))
    return PacketEnvelope(**data, payload=payload)
