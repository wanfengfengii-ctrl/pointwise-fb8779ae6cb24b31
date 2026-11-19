import sqlite3

from evidence.packets import IssuedPacket, load_issued_packet


def read_station_packet(db: sqlite3.Connection, packet_id: str) -> IssuedPacket:
    return load_issued_packet(db, packet_id)
