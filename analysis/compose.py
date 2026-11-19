from collections import deque
import json

from analysis.request import ReviewRequest
from analysis.seams import enumerate_seam_links
from intake.selection import AcceptedSet
from survey.layout import PortRef


def _read_port(tile_id, position):
    if (not isinstance(position, list) or len(position) != 2
            or any(type(coord) is not int for coord in position)):
        raise ValueError('invalid coordinate in station evidence')
    return PortRef(tile_id, *position)


def _read_groups(tile_id, raw):
    if not isinstance(raw, list):
        raise ValueError('invalid station groups')
    groups, membership = [], {}
    for group in raw:
        if not isinstance(group, list) or not group:
            raise ValueError('station group must contain an active port')
        ports = tuple(_read_port(tile_id, position) for position in group)
        for port in ports:
            if port in membership:
                raise ValueError('port occurs twice at a station threshold')
            membership[port] = len(groups)
        groups.append(frozenset(ports))
    return tuple(groups), membership


def _station_evidence(envelope, allowed_ports):
    """Parse and validate the fixed station evidence for one tile.

    Returns the measured public port scores and, for each integer gate 0..100,
    the partition of the active public ports into true in-tile components.
    """
    raw = json.loads(envelope.body)
    if not isinstance(raw, dict) or set(raw) != {"ports", "layers"}:
        raise ValueError("unrecognized station evidence")
    if not isinstance(raw["ports"], list):
        raise ValueError("invalid scored station ports")
    allowed = set(allowed_ports)
    scores = {}
    for entry in raw["ports"]:
        if not isinstance(entry, list) or len(entry) != 3:
            raise ValueError("invalid scored station port")
        port = _read_port(envelope.tile_id, entry[:2])
        score = entry[2]
        if (port in scores or port not in allowed
                or type(score) is not int or not 0 <= score <= 100):
            raise ValueError("invalid station port or score")
        scores[port] = score

    layers_raw = raw["layers"]
    if not isinstance(layers_raw, list) or len(layers_raw) != 101:
        raise ValueError("station evidence must carry one layer for every gate 0..100")

    layers = []
    previous_groups = None
    for threshold, layer_raw in enumerate(layers_raw):
        groups, membership = _read_groups(envelope.tile_id, layer_raw)
        active = set(membership)
        # The active public ports must agree exactly with the frozen scores,
        # which is the only per-port numeric fact retained for offline review.
        if active != {port for port, score in scores.items() if score >= threshold}:
            raise ValueError("station layer activity disagrees with scored ports")
        # Raising a gate can only remove ports and split components, so each
        # surviving component must stay inside one component of the prior gate.
        if previous_groups is not None:
            for group in groups:
                if not any(group <= earlier for earlier in previous_groups):
                    raise ValueError("station layers break threshold nesting")
        previous_groups = groups
        layers.append(groups)
    return scores, layers


def _groups_at(envelope, allowed_ports, threshold):
    if type(threshold) is not int or not 0 <= threshold <= 100:
        raise ValueError('threshold must be an integer from 0 to 100')
    _, layers = _station_evidence(envelope, allowed_ports)
    return layers[threshold]


def connected_at_threshold(accepted: AcceptedSet, request: ReviewRequest, threshold: int) -> bool:
    if type(threshold) is not int or not 0 <= threshold <= 100:
        raise ValueError('threshold must be an integer from 0 to 100')
    graph = {}
    for packet in accepted.packets:
        envelope = packet.envelope
        allowed_ports = set(accepted.layout.ports_for(envelope.tile_id))
        for group in _groups_at(envelope, allowed_ports, threshold):
            head, *rest = group
            graph.setdefault(head, set()).update(rest)
            for port in rest:
                graph.setdefault(port, set()).add(head)
    for link in enumerate_seam_links(accepted.layout):
        if link.a in graph and link.b in graph:
            graph[link.a].add(link.b)
            graph[link.b].add(link.a)

    if request.start not in graph or request.finish not in graph:
        return False
    frontier = deque([request.start])
    seen = {request.start}
    while frontier:
        port = frontier.popleft()
        if port == request.finish:
            return True
        for neighbor in graph[port] - seen:
            seen.add(neighbor)
            frontier.append(neighbor)
    return False
