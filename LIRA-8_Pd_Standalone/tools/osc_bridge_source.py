#!/usr/bin/env python3
"""Emit abs/av.osc.pd: every LIRA-8 bus, as OSC, for TouchDesigner.

TouchDesigner cannot see inside Pd, so the two talk over OSC. Pd vanilla
already ships oscformat, oscparse, netsend and netreceive, so this needs no
externals.

The bus list is read out of _LIRA-8.pd rather than typed in by hand. The
patch names each control twice, $0-s-<base> for the value the engine reads and
$0-r-<base> for the one the widget listens on, so the two collapse to a single
OSC address per control.

  out  an engine readout is read from $0-r-<base>. A control is read from
       $0-s-<base>.
  in   /lira/<base> is sent to $0-s-<base>. That is the name the patch reads.
       The widget listens on $0-r-<base> and does not move.

Because the list is scanned, a bus added to the instrument shows up here on
the next run instead of being silently missing.

The creation argument is the bus prefix, the same $0 that _LIRA-8.pd passes to
its other helpers, written as $1 inside this abstraction.
"""

import re
import sys
from pathlib import Path

from pd_text import connect, item

ROOT = Path(__file__).resolve().parent.parent
PATCH = ROOT / "_LIRA-8.pd"
OUTPUT = ROOT / "abs" / "av.osc.pd"

BUS = "\\$1"
OUT_HOST = "127.0.0.1"
OUT_PORT = 9121
IN_PORT = 9122
ADDRESS_ROOT = "lira"
# Published on a bare global send by abs/av.water.pd, not $0-scoped.
EXTRA_BUSES = ("water-lvl",)

BUS_PATTERN = re.compile(r"\$0-([sr])-([A-Za-z0-9-]+)")
# A bare [s $0-r-<base>] means the engine pushes that value out on its own,
# so the r- name carries the live reading and the s- name is only what a
# number box would emit if someone typed in it.
ENGINE_SEND = re.compile(r"^#X obj [-\d]+ [-\d]+ s \\?\$0-r-([A-Za-z0-9-]+);$")
# The control inputs. The patch listens on the s-name, so only a base with one
# of these can be written from outside.
CONTROL_RECEIVE = re.compile(r"^#X obj [-\d]+ [-\d]+ r \\?\$0-s-([A-Za-z0-9-]+);$")


class Patch:
    """Write a Pd canvas. Objects land six to a row, connects come last."""

    COLUMNS = 6
    COLUMN_PITCH = 260
    ROW_PITCH = 50

    def __init__(self):
        # Pd numbers every item in the file, text boxes included, and a connect
        # refers to those numbers. So the header cannot live in this list.
        self.items = []
        self.connections = []
        self.slots = {}
        self.next_slot = 0
        self.text_y = 20

    def text(self, content):
        self.items.append("#X text 30 %d %s;" % (self.text_y, content))
        self.text_y += 14

    def _declare(self, kind, name, body):
        column = self.next_slot % self.COLUMNS
        row = self.next_slot // self.COLUMNS
        self.next_slot += 1
        self.slots[name] = len(self.items)
        self.items.append(item(
            kind, 40 + column * self.COLUMN_PITCH,
            90 + row * self.ROW_PITCH, body))

    def add(self, name, obj):
        self._declare("obj", name, obj)

    def msg(self, name, content):
        self._declare("msg", name, content)

    def connect(self, source, outlet, sink, inlet):
        self.connections.append(connect(
            self.slots[source], outlet, self.slots[sink], inlet))

    def dump(self):
        return "\n".join(["#N canvas 0 0 1600 1000 12;"]
                         + self.items + self.connections) + "\n"


def scan_buses(patch):
    """base name -> {"s": send bus or None, "r": receive bus or None}."""
    found = {}
    for line in patch.read_text(errors="ignore").splitlines():
        for kind, base in BUS_PATTERN.findall(line):
            entry = found.setdefault(base, {"s": None, "r": None})
            entry[kind] = f"{BUS}-{kind}-{base}"
    return found


def scan_engine_published(patch):
    """Bases the engine pushes out by itself, so they are live readouts."""
    published = set(EXTRA_BUSES)
    for line in patch.read_text(errors="ignore").splitlines():
        match = ENGINE_SEND.match(line)
        if match:
            published.add(match.group(1))
    return published


def scan_control_receivers(patch):
    """Bases the patch will accept a written value on."""
    received = set()
    for line in patch.read_text(errors="ignore").splitlines():
        match = CONTROL_RECEIVE.match(line)
        if match:
            received.add(match.group(1))
    return received


def build():
    buses = scan_buses(PATCH)
    for base in EXTRA_BUSES:
        buses.setdefault(base, {"s": None, "r": None})
        buses[base]["r"] = base
    engine = scan_engine_published(PATCH)

    p = Patch()
    names = sorted(buses)
    # No commas in a Pd text box. Pd stores the comment as a binbuf and a
    # comma splits it into a second message that the canvas then dispatches.
    p.text(f"LIRA-8 to OSC. sends to {OUT_HOST} port {OUT_PORT} "
           f"and listens on port {IN_PORT}.")
    # Written into the patch so the far end can be wired without reading this
    # generator. Wrapped because Pd text boxes do not clip gracefully.
    for start in range(0, len(names), 8):
        p.text("/lira/" + " /lira/".join(names[start:start + 8]))

    p.add("sender", "netsend -u -b")
    p.msg("m_connect", f"connect {OUT_HOST} {OUT_PORT}")
    p.add("send_start", "loadbang")
    p.connect("send_start", 0, "m_connect", 0)
    # netsend takes its connect message on inlet 0 and has no inlet 1.
    p.connect("m_connect", 0, "sender", 0)

    # One sender per bus. A live readout is read from its r- name, because
    # that is the one the engine pushes. A control is read from its s- name,
    # because that is the one the widget pushes. A bus that is both keeps the
    # r- name for the readout and also listens on s-, which is where a write
    # lands. route float then drops the label symbols on r- and passes the
    # number from either side.
    writable = sorted(scan_control_receivers(PATCH))
    writable_set = set(writable)
    led_filt = None
    for i, base in enumerate(sorted(buses)):
        source = (buses[base]["r"] if base in engine
                  else buses[base]["s"] or buses[base]["r"])
        p.add(f"r_{i}", f"r {source}")
        # The widgets also publish label and label_pos on their send bus, and
        # oscformat has no handler for those. [route float] passes numbers and
        # drops everything else silently, which [t f] does not: it filters but
        # prints an error each time.
        p.add(f"filt_{i}", "route float")
        p.add(f"fmt_{i}", f"oscformat /{ADDRESS_ROOT}/{base}")
        p.connect(f"r_{i}", 0, f"filt_{i}", 0)
        p.connect(f"filt_{i}", 0, f"fmt_{i}", 0)
        p.connect(f"fmt_{i}", 0, "sender", 0)
        send = buses[base]["s"]
        if base in writable_set and send and send != source:
            p.add(f"rw_{i}", f"r {send}")
            p.connect(f"rw_{i}", 0, f"filt_{i}", 0)
        if base == "led":
            led_filt = f"filt_{i}"
    # led publishes only when the square LFO changes, so a fresh CHOP has no
    # channel until the first edge. One 0 at load is the initial sample.
    if led_filt is not None:
        p.msg("led_prime", "0")
        p.connect("send_start", 0, "led_prime", 0)
        p.connect("led_prime", 0, led_filt, 0)

    # A live readout is read-only. Writing it would race the engine, which is
    # already pushing a value there every frame.
    p.add("receiver", f"netreceive -u -b {IN_PORT}")
    p.add("parse", "oscparse")
    p.connect("receiver", 0, "parse", 0)
    # oscparse emits a list, so the selector has to come off before route can
    # match the address root.
    p.add("trim", "list trim")
    p.connect("parse", 0, "trim", 0)
    p.add("route_root", f"route {ADDRESS_ROOT}")
    p.connect("trim", 0, "route_root", 0)
    p.add("route_bus", "route " + " ".join(writable))
    p.connect("route_root", 0, "route_bus", 0)
    for i, base in enumerate(writable):
        # The patch listens on $0-s-<base>. Sending to $1-r-<base> reached no
        # receiver, which is why a written control never moved anything.
        target = "%s-s-%s" % (BUS, base)
        p.add(f"s_{i}", f"s {target}")
        p.connect("route_bus", i, f"s_{i}", 0)

    return p.dump(), len(buses), len(writable)


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else OUTPUT
    patch, count, writable = build()
    target.write_text(patch)
    print(f"wrote {target} with {count} buses out, {writable} writable")


if __name__ == "__main__":
    main()
