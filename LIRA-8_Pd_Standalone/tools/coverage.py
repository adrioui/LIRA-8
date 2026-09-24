#!/usr/bin/env python3
"""Prove the bus map is total, with no Pd and no TouchDesigner running.

Three invariants, all pure functions of the generated patch and the binding
tables in tools/picture.py:

  every published bus carries a weight        a control that does nothing
  every weighted bus is published             a weight on a name that never arrives
  every read is a literal op()['...'] read    a dependency the cook scan cannot see

The third one is the freeze. TouchDesigner only re-evaluates a parameter
expression when it can find the dependency by scanning the expression text for
op()['channel']. Route a read through a helper and the parameter silently stops
following its bus while every value still looks correct.
"""

import sys

import picture

OSC_PATH = "/project1/lira_osc"
UI_PATH = "/project1/lira_ui"
ADDRESS_ROOT = picture.ADDRESS_ROOT


def problems(bindings, published, mapped):
    text = " ".join(bindings.values())
    found = []
    for bus in sorted(published - mapped):
        found.append("published with no weight: %s" % bus)
    for bus in sorted(mapped - published):
        found.append("weighted but never published: %s" % bus)
    for bus in sorted(mapped):
        read = "op('%s')['%s/%s']" % (OSC_PATH, ADDRESS_ROOT, bus)
        if read not in text:
            found.append("read the cook scan cannot see: %s" % bus)
    return found


def main():
    bindings = picture.bindings_for(OSC_PATH, UI_PATH)
    published = set(picture.covered_buses())
    mapped = set(picture.mapped_buses())
    found = problems(bindings, published, mapped)

    print("bindings %d, published %d, weighted %d" % (
        len(bindings), len(published), len(mapped)))
    for problem in found:
        print("FAIL " + problem)
    if found:
        return 1
    print("PASS every published bus carries weight and every read is visible")
    return 0


if __name__ == "__main__":
    sys.exit(main())
