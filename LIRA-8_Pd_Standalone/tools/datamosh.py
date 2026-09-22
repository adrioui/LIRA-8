#!/usr/bin/env python3
"""Datamosh a video the way datamosh actually works: drop the I-frames.

A P-frame does not carry a picture. It carries motion plus residual against
whatever the decoder currently holds. Remove the I-frames that refresh the
decoder and every P-frame keeps predicting from a stale reference, so the
motion in the clip drags the old picture around and the image melts.

Video is encoded to a raw MPEG-4 elementary stream, which is a flat sequence
of start-coded units. Dropping the VOP units whose coding type is I leaves the
P-frames referring to whatever came before, and the stream copies straight
back into a container without re-encoding. Re-encoding would recompute the
motion and undo the effect, so the output is always a copy.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

START = b"\x00\x00\x01"
VOP = b"\x00\x00\x01\xb6"
CODING_TYPE = {0b00: "I", 0b01: "P", 0b10: "B", 0b11: "S"}


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr[-2000:])
        raise SystemExit(f"failed: {' '.join(cmd)}")
    return result.stdout


def probe_fps(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v",
               "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0",
               str(path)])
    num, _, den = out.strip().partition("/")
    return float(num) / float(den or 1)


def to_elementary(src, dst, gop):
    run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-an",
         "-c:v", "mpeg4", "-bf", "0", "-g", str(gop), "-q:v", "2",
         "-f", "m4v", str(dst)])


def split_units(data):
    """Cut a start-coded elementary stream into units, headers included."""
    marks = []
    index = data.find(START)
    while index != -1:
        marks.append(index)
        index = data.find(START, index + 4)
    marks.append(len(data))
    return [data[marks[i]:marks[i + 1]] for i in range(len(marks) - 1)]


def vop_type(unit):
    if not unit.startswith(VOP) or len(unit) < 5:
        return None
    return CODING_TYPE.get(unit[4] >> 6)


def mosh_units(units, keep_every):
    """Drop I-frames, keeping 1 in every keep_every so the melt recovers.

    Keeping one every so often matters: without it the picture degrades once
    and never comes back, which reads as a dead decoder rather than a mosh.
    """
    out = []
    seen = 0
    for unit in units:
        if vop_type(unit) == "I":
            seen += 1
            if seen != 1 and (keep_every <= 1 or (seen - 1) % keep_every):
                continue
        out.append(unit)
    return out


def write_container(stream, dst, fps):
    run(["ffmpeg", "-v", "error", "-y", "-framerate", f"{fps:.6f}",
         "-f", "m4v", "-i", str(stream), "-c:v", "copy",
         "-movflags", "+faststart", str(dst)])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=str(ROOT / "av" / "mosh_small.mp4"))
    parser.add_argument("--out", default=str(ROOT / "av" / "mosh_ref.mp4"))
    parser.add_argument("--gop", type=int, default=24,
                        help="frames between I-frames in the source encode")
    parser.add_argument("--keep-every", type=int, default=7,
                        help="keep 1 in N I-frames so the melt recovers")
    args = parser.parse_args()

    work = Path("/tmp/datamosh")
    work.mkdir(exist_ok=True)
    raw = work / "gop.m4v"
    moshed = work / "moshed.m4v"

    fps = probe_fps(args.src)
    to_elementary(args.src, raw, args.gop)
    units = split_units(raw.read_bytes())
    types = [vop_type(u) for u in units if vop_type(u)]
    kept = mosh_units(units, args.keep_every)
    kept_types = [vop_type(u) for u in kept if vop_type(u)]
    moshed.write_bytes(b"".join(kept))
    write_container(moshed, Path(args.out), fps)

    before = {t: types.count(t) for t in ("I", "P", "B") if types.count(t)}
    after = {t: kept_types.count(t) for t in ("I", "P", "B")
             if kept_types.count(t)}
    print(f"frames {len(types)} -> {len(kept_types)}  fps {fps:.3f}")
    print(f"before {before}")
    print(f"after  {after}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
