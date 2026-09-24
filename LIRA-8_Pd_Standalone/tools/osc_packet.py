"""The integer OSC datagram both probes send on the LIRA buses."""

import struct


def encode_int(address, value):
    def pad(raw):
        # OSC pads a string to a 4-byte boundary, and a string that already
        # ends on that boundary still takes one extra null word.
        return raw + b"\x00" * (4 - len(raw) % 4)

    return pad(address.encode()) + pad(b",i") + struct.pack(">i", value)


def decode(data):
    def read_string(buf, start):
        end = buf.index(b"\x00", start)
        return buf[start:end].decode(), (end + 4) & ~3

    address, offset = read_string(data, 0)
    if offset >= len(data):
        return address, []
    tags, offset = read_string(data, offset)
    values = []
    for tag in tags[1:]:
        if tag == "i":
            values.append(struct.unpack_from(">i", data, offset)[0])
            offset += 4
        elif tag == "f":
            values.append(struct.unpack_from(">f", data, offset)[0])
            offset += 4
    return address, values
