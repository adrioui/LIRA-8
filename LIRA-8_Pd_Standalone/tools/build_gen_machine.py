#!/usr/bin/env python3
"""Regenerate abs/gen.machine.pd from a name-keyed item and connection list.

Connections resolve by item name, so inserting or deleting an item can never
shift an index into a different object. Hand-edited connection numbers are
what corrupted this file before.

Usage: python3 tools/build_gen_machine.py
"""

from pathlib import Path

CANVAS = "#N canvas 0 0 900 640 10;"

RULES = r"1 2 60 \, 1 1 20 \, 1 5 20 \, 2 3 50 \, 2 1 30 \, 2 6 20 \, 3 4 50 \, 3 2 30 \, 3 8 20 \, 4 5 50 \, 4 3 30 \, 4 1 20 \, 5 6 50 \, 5 4 30 \, 5 2 20 \, 6 7 50 \, 6 5 30 \, 6 3 20 \, 7 8 50 \, 7 6 30 \, 7 4 20 \, 8 1 50 \, 8 7 30 \, 8 5 20"

# (name, kind, x, y, body)
ITEMS = [
    ("on", "obj", 12, 12, r"r \$1-s-gen-on"),
    ("sel", "obj", 12, 40, "sel 1 0"),
    ("off", "msg", 12, 70, "0"),
    ("metro", "obj", 12, 100, "metro 500"),
    ("tick", "obj", 12, 130, "t b b b"),
    ("randi", "obj", 170, 40, "else/rand.i -8 8"),
    ("depin", "obj", 170, 300, r"r \$1-s-gen-depth"),
    ("depscale", "obj", 170, 330, "/ 127"),
    ("depthf", "obj", 170, 360, "f 0"),
    ("mul", "obj", 410, 40, "*"),
    ("offset", "obj", 490, 40, "+ 64"),
    ("clip", "obj", 570, 40, "cyclone/clip 0 127"),
    ("ratein", "obj", 12, 200, r"r \$1-s-gen-rate"),
    ("ratescale", "obj", 12, 230, "/ 127"),
    ("ratemul", "obj", 12, 260, "* -950"),
    ("rateadd", "obj", 12, 290, "+ 1000"),
    ("prob", "obj", 330, 100, "cyclone/prob"),
    ("route", "obj", 330, 140, "route 1 2 3 4 5 6 7 8"),
    ("loadbang", "obj", 12, 350, "loadbang"),
    ("fan", "obj", 12, 380, "t b b b b"),
    ("resetmsg", "msg", 130, 410, "reset 1"),
    ("rulesmsg", "msg", 130, 450, RULES),
    ("ratemsg", "msg", 130, 490, "64"),
    ("depthmsg", "msg", 130, 530, "48"),
    ("ratesend", "obj", 250, 490, r"s \$1-s-gen-rate"),
    ("depthsend", "obj", 250, 530, r"s \$1-s-gen-depth"),
]
for _n in range(1, 9):
    ITEMS.append(("voice%d" % _n, "obj", 720, 40 + (_n - 1) * 50,
                  r"gen.voice \$1 %d 120" % _n))

# (source, outlet, target, inlet)
CONNECTS = [
    ("on", 0, "sel", 0),
    ("sel", 0, "metro", 0),
    ("sel", 1, "off", 0),
    ("off", 0, "metro", 0),
    ("metro", 0, "tick", 0),
    ("tick", 2, "depthf", 0),
    ("tick", 1, "randi", 0),
    ("tick", 0, "prob", 0),
    ("prob", 0, "route", 0),
    ("ratein", 0, "ratescale", 0),
    ("ratescale", 0, "ratemul", 0),
    ("ratemul", 0, "rateadd", 0),
    ("rateadd", 0, "metro", 1),
    ("randi", 0, "mul", 0),
    ("depin", 0, "depscale", 0),
    ("depscale", 0, "depthf", 0),
    ("depthf", 0, "mul", 1),
    ("mul", 0, "offset", 0),
    ("offset", 0, "clip", 0),
    ("loadbang", 0, "fan", 0),
    ("fan", 3, "rulesmsg", 0),
    ("fan", 2, "resetmsg", 0),
    ("fan", 1, "ratemsg", 0),
    ("fan", 0, "depthmsg", 0),
    ("resetmsg", 0, "prob", 0),
    ("rulesmsg", 0, "prob", 0),
    ("ratemsg", 0, "ratesend", 0),
    ("depthmsg", 0, "depthsend", 0),
]
for _n in range(1, 9):
    CONNECTS.append(("route", _n - 1, "voice%d" % _n, 0))
    CONNECTS.append(("clip", 0, "voice%d" % _n, 1))


def render():
    index = {}
    for position, (name, _kind, _x, _y, _body) in enumerate(ITEMS):
        if name in index:
            raise SystemExit("duplicate item name: %s" % name)
        index[name] = position
    lines = [CANVAS]
    for _name, kind, x, y, body in ITEMS:
        lines.append("#X %s %d %d %s;" % (kind, x, y, body))
    for src, outlet, dst, inlet in CONNECTS:
        for endpoint in (src, dst):
            if endpoint not in index:
                raise SystemExit("unknown item in connection: %s" % endpoint)
        lines.append("#X connect %d %d %d %d;"
                     % (index[src], outlet, index[dst], inlet))
    return "\n".join(lines) + "\n"


def main():
    out = Path(__file__).resolve().parent.parent / "abs" / "gen.machine.pd"
    out.write_text(render())
    print("wrote %s (%d items, %d connects)"
          % (out, len(ITEMS), len(CONNECTS)))


if __name__ == "__main__":
    main()
