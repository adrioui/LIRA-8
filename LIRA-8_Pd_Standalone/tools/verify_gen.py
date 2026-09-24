#!/usr/bin/env python3
"""Headless check that gen.machine actually plays the LIRA-8 voices.

Runs two throwaway patches that instantiate `gen.machine 999` the same way
`_LIRA-8.pd` does and watch the eight voice buses.

  driven    the probe sends rate and depth, the way a moving slider would
  defaults  the probe sends only gen-on, so rate 64 and depth 48 have to
            arrive from gen.machine's own loadbang, or the pitch collapses
            to a single value

Four things have to hold at once in each run:

  the voice chain moves     at least three of the eight voices gate
  the pitch chain moves     at least three distinct tune values arrive
  gen-on stops it           no voice gates after the probe sends 0
  no prob binding leak      no `embed_gc` teardown error from cyclone/prob

Every assertion reads the same voice buses the real widgets write, so the
check stays valid if the chains are retuned or swapped for other Markov
objects. Pd's `print` goes to stderr in this build, so both streams are read.
"""

import os
import re
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ABS = os.path.join(REPO, "abs")
PREFIX = "999"
SETTLE_MS = 200
DRIVE_RATE = 100
DRIVE_DEPTH = 48
VOICES = range(1, 9)
# label, drive rate/depth from the probe, run seconds, stop after ms
SCENARIOS = [
    ("driven", True, 7, 5000),
    ("defaults", False, 9, 7000),
]

SENSOR = re.compile(r"^s(\d+): 1$")
TUNE = re.compile(r"^t(\d+): (-?[0-9.]+)$")
MARK = "GENSTOP"


def probe(drive, stop_ms):
    objs = []
    conns = []

    def obj(line):
        objs.append(line)
        return len(objs) - 1

    loadbang = obj("#X obj 12 12 loadbang;")
    settle = obj("#X obj 12 40 del %d;" % SETTLE_MS)
    fan = obj("#X obj 12 70 t b b b b;" if drive else "#X obj 12 70 t b b;")
    on = obj("#X msg 12 100 1;")
    on_s = obj("#X obj 12 130 s %s-s-gen-on;" % PREFIX)
    hold = obj("#X obj 12 160 del %d;" % stop_ms)
    stop = obj("#X obj 12 190 t b b;")
    off = obj("#X msg 12 220 0;")
    off_s = obj("#X obj 12 250 s %s-s-gen-on;" % PREFIX)
    mark = obj("#X obj 130 220 print %s;" % MARK)
    obj("#X obj 400 12 gen.machine %s;" % PREFIX)

    conns += [
        (loadbang, 0, settle, 0),
        (settle, 0, fan, 0),
        (fan, 1, on, 0),
        (fan, 0, hold, 0),
        (on, 0, on_s, 0),
        (hold, 0, stop, 0),
        (stop, 1, off, 0),
        (stop, 0, mark, 0),
        (off, 0, off_s, 0),
    ]
    if drive:
        rate = obj("#X msg 130 100 %d;" % DRIVE_RATE)
        rate_s = obj("#X obj 130 130 s %s-s-gen-rate;" % PREFIX)
        depth = obj("#X msg 230 100 %d;" % DRIVE_DEPTH)
        depth_s = obj("#X obj 230 130 s %s-s-gen-depth;" % PREFIX)
        conns += [
            (fan, 3, rate, 0),
            (fan, 2, depth, 0),
            (rate, 0, rate_s, 0),
            (depth, 0, depth_s, 0),
        ]

    for n in VOICES:
        y = 320 + (n - 1) * 30
        recv = obj("#X obj 12 %d r %s-s-sensor-%d;" % (y, PREFIX, n))
        prnt = obj("#X obj 230 %d print s%d;" % (y, n))
        conns.append((recv, 0, prnt, 0))
    for n in VOICES:
        y = 320 + (n - 1) * 30
        recv = obj("#X obj 400 %d r %s-s-tune-%d;" % (y, PREFIX, n))
        prnt = obj("#X obj 620 %d print t%d;" % (y, n))
        conns.append((recv, 0, prnt, 0))

    lines = ["#N canvas 0 0 820 620 10;"] + objs
    lines += ["#X connect %d %d %d %d;" % c for c in conns]
    return "\n".join(lines) + "\n"


def run(path, seconds):
    cmd = ["pd", "-nogui", "-noaudio", "-path", ABS, path]
    try:
        done = subprocess.run(cmd, capture_output=True, timeout=seconds)
        return done.stdout + done.stderr
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or b""
        err = exc.stderr or b""
        return out + err


def check(raw, label):
    lines = raw.decode("utf-8", "replace").splitlines()
    stop_at = next((i for i, line in enumerate(lines)
                    if line.startswith(MARK)), None)
    if stop_at is None:
        before, after = lines, []
    else:
        before, after = lines[:stop_at], lines[stop_at + 1:]

    gated = set()
    tunes = set()
    for line in before:
        hit = SENSOR.match(line)
        if hit:
            gated.add(int(hit.group(1)))
        hit = TUNE.match(line)
        if hit:
            tunes.add(round(float(hit.group(2))))
    late = [line for line in after if SENSOR.match(line)]
    leaks = [line for line in lines if "embed_gc" in line]

    problems = []
    if stop_at is None:
        problems.append("the probe never reached %s" % MARK)
    if len(gated) < 3:
        problems.append("only %d voices gated" % len(gated))
    if len(tunes) < 3:
        problems.append("only %d distinct tune values" % len(tunes))
    if late:
        problems.append("%d voices gated after gen-on 0" % len(late))
    if leaks:
        problems.append("cyclone/prob binding leak: %s" % leaks[0])

    print("[%s] voices gated %d, tune values %d, gates after stop %d"
          % (label, len(gated), len(tunes), len(late)))
    for problem in problems:
        print("[%s] FAIL %s" % (label, problem))
    return problems, len(gated), len(tunes)


def main():
    status = 0
    for label, drive, seconds, stop_ms in SCENARIOS:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gen_probe.pd")
            with open(path, "w") as handle:
                handle.write(probe(drive, stop_ms))
            try:
                raw = run(path, seconds)
            except FileNotFoundError:
                print("FAIL pd not found on PATH")
                return 1
        problems, gated, tunes = check(raw, label)
        if problems:
            status = 1
        else:
            print("[%s] PASS gen.machine gates %d voices across %d pitches "
                  "and stops on gen-on 0" % (label, gated, tunes))
    return status


if __name__ == "__main__":
    sys.exit(main())
