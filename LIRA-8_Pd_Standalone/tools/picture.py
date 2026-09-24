"""The picture map. A list of weights. No TouchDesigner process required."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRIDGE = ROOT / "abs" / "av.osc.pd"
ADDRESS_ROOT = "lira"
SCALE = 127.0

# Destination parameter, low, high, and the buses that drive it with a weight.
# The value is a weighted mean of the group, mapped onto low..high, so a group
# that adds up past the top cannot pin the destination and swallow every
# later change. A plain sum saturates and then stops responding.
#
# The optical flow is the Palette component, and its own defaults are Force
# 1.0, Offset 3, Lambda 0.1, Threshold 0.0. Offset is left alone, because it
# sets the flow window and a wrong value there stops the motion entirely.
CONTINUOUS = (
    ("Offsetbymotionvector", "Meltlow", "Melthigh", (
        ("hold-1234", 0.50), ("hold-5678", 0.30), ("drv", 0.30),
        ("feedback", 0.15), ("total-fb", 0.15), ("dst-mix", 0.15),
        ("del-mix", 0.15), ("del-mod", 0.15), ("f-a", 0.15), ("f-b", 0.15),
        ("vol", 0.15), ("water-lvl", 0.15),
        # From the audio analysis. The melt is the main event, so level drives
        # it hardest and the peak adds the transient on top.
        ("a-loud", 0.60), ("a-peak", 0.25))),
    ("Force", "Forcelow", "Forcehigh", (
        ("mod-2", 1.0), ("mod-12", 0.5), ("mod-56", 0.5), ("mod-78", 0.5),
        ("cpu", 0.3), ("dsp", 0.3), ("pitch-1234", 0.5), ("pitch-5678", 0.5),
        # Brightness pushes the flow harder.
        ("a-cent", 0.40))),
    ("Threshold", "Thresholdlow", "Thresholdhigh", (
        ("mod-1", 0.3), ("sharp-12", 0.1), ("sharp-34", 0.1),
        ("sharp-56", 0.1), ("sharp-78", 0.1), ("fast-12", 0.1),
        ("fast-34", 0.1), ("fast-56", 0.1), ("fast-78", 0.1),
        ("sensor-1", 0.03), ("sensor-2", 0.03), ("sensor-3", 0.03),
        ("sensor-4", 0.03), ("sensor-5", 0.03), ("sensor-6", 0.03),
        ("sensor-7", 0.03), ("sensor-8", 0.03),
        # A noisy spectrum raises the motion gate.
        ("a-flat", 0.30))),
    ("Lambda", "Lambdalow", "Lambdahigh", (
        ("mod-34", 0.5), ("vibrato", 0.1), ("lfo-wav", 0.1),
        ("time-1", 0.05), ("time-2", 0.05), ("tune-1", 0.1), ("tune-2", 0.1),
        ("tune-3", 0.1), ("tune-4", 0.1), ("tune-5", 0.1), ("tune-6", 0.1),
        ("tune-7", 0.1), ("tune-8", 0.1),
        # A confident pitch reading steadies the flow weighting.
        ("a-conf", 0.20))),
)

# Destination parameter, the buses that drive it, and the level that flips it.
TOGGLES = (
    ("Inversex", (("switch", 1.0), ("source-12", 0.3), ("source-34", 0.3),
                  ("source-56", 0.3), ("source-78", 0.3), ("led", 0.3),
                  # A high note flips the melt direction.
                  ("a-pitch", 0.40)), 0.5),
    ("Inversey", (("andor", 1.0), ("link", 0.3), ("quantize", 0.3)), 0.5),
)

# Destination parameter and the panel control that sets how often the loop is
# re-seeded. The shader samples only the feedback, so without a reset the frame
# melts into a still and stops moving, whatever the hold is doing. One means
# every frame, zero means never.
PULSES = (
    ("Feedbackreset", "Refreshdiv"),
)


def covered_buses():
    """Every address the bridge publishes, read from the generated patch."""
    return sorted(set(re.findall(
        r"/lira/([A-Za-z0-9-]+)", BRIDGE.read_text(errors="ignore"))))


def mapped_buses():
    found = set()
    for _, _, _, terms in CONTINUOUS:
        found.update(bus for bus, _ in terms)
    for _, terms, _ in TOGGLES:
        found.update(bus for bus, _ in terms)
    return found


def read_bus(bus, osc_path):
    """Tracked for dependency scanning, and zero until the bus publishes."""
    return "(op(%r)[%r] or 0)" % (osc_path, ADDRESS_ROOT + "/" + bus)


def bindings_for(osc_path, ui_path):
    bindings = {}
    for name, low_par, high_par, terms in CONTINUOUS:
        total_weight = sum(weight for _, weight in terms)
        body = " + ".join(
            "%s * %s" % (weight, read_bus(bus, osc_path))
            for bus, weight in terms)
        low = "op(%r).par.%s.eval()" % (ui_path, low_par)
        high = "op(%r).par.%s.eval()" % (ui_path, high_par)
        bindings[name] = "%s + (%s - %s) * (%s) / %s" % (
            low, high, low, body, total_weight * SCALE)
    for name, terms, threshold in TOGGLES:
        body = " + ".join(
            "%s * %s / %s" % (weight, read_bus(bus, osc_path), SCALE)
            for bus, weight in terms)
        bindings[name] = "1 if (%s) > %s else 0" % (body, threshold)
    for name, rate_par in PULSES:
        rate = "op(%r).par.%s.eval()" % (ui_path, rate_par)
        bindings[name] = ("1 if {r} >= 1 and absTime.frame % int({r}) == 0 "
                          "else 0").format(r=rate)
    return bindings
