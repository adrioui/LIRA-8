#!/usr/bin/env python3
"""Codec-level datamosh: drop MPEG-4 Part 2 I-frames so P-frames predict from a stale reference.

Datamoshing is not an image effect. It happens in the compressed bitstream: P-frames
only carry motion and residual, so if you delete an I-frame the following P-frames
keep predicting from the last decoded picture and the image melts.

This operates on a raw MPEG-4 Part 2 elementary stream (.m4v). Encode one first:

    ffmpeg -i in.mp4 -c:v mpeg4 -bf 0 -g 100000 -q:v 3 -an -f avi step1.avi
    ffmpeg -i step1.avi -c:v copy -f m4v step1.m4v

Then patch and remux:

    python3 datamosh.py step1.m4v step2.m4v --keep-first
    ffmpeg -i step2.m4v -c:v copy out.avi

Frame markers: a VOP starts with 00 00 01 B6. The two high bits of the next byte
are the coding type, 00 = I, 01 = P, 10 = B, 11 = S.
"""

import argparse
import sys

VOP_START = b"\x00\x00\x01\xb6"
CODING = {0: "I", 1: "P", 2: "B", 3: "S"}


def find_vops(data):
    """Return [(start, coding_type)] for every VOP in the elementary stream."""
    vops = []
    i = data.find(VOP_START)
    while i != -1:
        if i + 4 < len(data):
            vops.append((i, (data[i + 4] >> 6) & 0x03))
        i = data.find(VOP_START, i + 4)
    return vops


def patch(data, mode, keep_first):
    """Remove I-VOPs. `bloom` keeps only the very first, `weld` drops every one."""
    vops = find_vops(data)
    if not vops:
        raise SystemExit("no VOP start codes found; is this an MPEG-4 Part 2 stream?")

    counts = {}
    for _, ct in vops:
        counts[CODING[ct]] = counts.get(CODING[ct], 0) + 1

    drops = []
    seen_i = 0
    for idx, (pos, ct) in enumerate(vops):
        if ct != 0:
            continue
        seen_i += 1
        if keep_first and seen_i == 1:
            continue
        if mode == "weld" or seen_i > 1:
            end = vops[idx + 1][0] if idx + 1 < len(vops) else len(data)
            drops.append((pos, end))

    out = bytearray()
    cursor = 0
    for start, end in drops:
        out += data[cursor:start]
        cursor = end
    out += data[cursor:]

    return bytes(out), counts, len(drops)


def main():
    ap = argparse.ArgumentParser(description="Drop I-frames for a datamosh.")
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument(
        "--keep-first",
        action="store_true",
        help="keep the first I-frame so the clip has a reference (bloom); "
        "otherwise drop them all (weld)",
    )
    args = ap.parse_args()

    data = open(args.src, "rb").read()
    out, counts, dropped = patch(data, "bloom" if args.keep_first else "weld", args.keep_first)
    open(args.dst, "wb").write(out)

    total = sum(counts.values())
    print(f"frames: {total}  ({', '.join(f'{k}={v}' for k, v in sorted(counts.items()))})")
    print(f"dropped I-frames: {dropped}")
    print(f"wrote {args.dst}  {len(data)} -> {len(out)} bytes")
    if dropped == 0:
        print("warning: nothing dropped, the stream has no droppable I-frames", file=sys.stderr)


if __name__ == "__main__":
    main()