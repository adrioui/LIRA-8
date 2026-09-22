"""Wire every LIRA-8 OSC bus into the Datamoshing component.

Run from the TouchDesigner Textport (Dialogs menu, Textport and DATs):

    exec(open('/Users/adrifadilah/Fun/Sounds/pd/soma/LIRA-8/LIRA-8_Pd_Standalone/tools/td_build.py').read())

Pd broadcasts every LIRA-8 bus on /lira/<name> to port 9121 and listens on
9122. This makes an OSC In CHOP on 9121 and drives the component from it.

Every bus Pd publishes drives the picture. A bus that only sat in the CHOP
would be a control that does nothing, so the map below covers all of them and
the run reports any that are not. Each destination is a weighted mean of its
group mapped onto a range, and the ranges live on the lira_ui panel so the
look is tuned on screen.

Three TouchDesigner rules shape the expressions. A parameter expression is
only re-evaluated when TouchDesigner can find its dependencies by scanning the
text for `op()['channel']`, so a bus read through a helper such as chans()
freezes at its last value. That plain read of a channel that has never arrived
yields None and arithmetic on it raises, so each read is wrapped in `or 0`. A
destination also has to be a Float parameter, because an Int destination
rounds the mean away.

The component is a recursive loop. Its GLSL Multi samples the Feedback TOP,
which feeds back from that GLSL Multi, and the shader offsets the UV by the
motion vector times motOffset. The loop samples only itself, so Feedback Reset
is the only way the live picture returns. It pulses on a frame interval set on
the panel, so the picture keeps moving whatever the instrument is doing. Tying
that pulse to the hold control was wrong. Hold is the sustain control, and the
video froze whenever a voice was held.

The optical flow has to receive the picture. With nothing wired into it the
flow renders black, every motion vector is zero, and the melt displaces the
image by nothing. Every control then reads correctly while the picture ignores
it. Check that first.

The sound comes from Pd. The project's Audio Device Out CHOP is switched off
so TouchDesigner is picture only.

The destination parameter names are the ones this component ships with. The
OSC node's port and protocol parameters are found on the node instead of
assumed. Re-running is safe.
"""

import re
import traceback

REPORT = []

OSC_NAME = "lira_osc"
UI_NAME = "lira_ui"
ADDRESS_ROOT = "lira"
LISTEN_PORT = 9121
RESET_BELOW = 4.0
SCALE = 127.0
ROOT = "/Users/adrifadilah/Fun/Sounds/pd/soma/LIRA-8/LIRA-8_Pd_Standalone"
BRIDGE = ROOT + "/abs/av.osc.pd"

# name, panel label, slider low, slider high, starting value. These live on
# the panel and the destination ranges read them, so the look is tuned from the
# screen instead of from this file.
UI_CONTROLS = (
    ("Meltlow", "Melt low", 0.0, 1.5, 0.0),
    ("Melthigh", "Melt high", 0.0, 1.5, 0.85),
    ("Forcelow", "Force low", 0.0, 10.0, 1.0),
    ("Forcehigh", "Force high", 0.0, 10.0, 4.0),
    ("Thresholdlow", "Threshold low", 0.0, 0.05, 0.0),
    ("Thresholdhigh", "Threshold high", 0.0, 0.05, 0.005),
    ("Lambdalow", "Lambda low", 0.0, 1.0, 0.1),
    ("Lambdahigh", "Lambda high", 0.0, 2.0, 0.9),
    ("Refreshdiv", "Refresh every N frames", 0.0, 60.0, 8.0),
)

# The preset row and the morph label sit below the sliders, so the panel has to
# be tall enough to hold them. Sized to the sliders alone, a pane opened at the
# panel's own size clipped the Store A, Randomise, Store B and Morph row.
PRESET_ROW_Y = 10 + len(UI_CONTROLS) * 40
PANEL_H = PRESET_ROW_Y + 28 + 20 + 10

# TouchDesigner's uTD2DInfos[i].res is vec4(1/width, 1/height, width, height),
# so res.xy * uOffset is already a step of uOffset pixels and the shipped line
# is correct. Dividing by res instead multiplies by the resolution, which puts
# the two gradient samples a screen apart, clamps them to the same edge texel,
# and leaves the gradient, and therefore the whole flow, at zero.
FLOW_OFFSET_CORRECT = ("vec2 pixelOffset = vec2(uTD2DInfos[0].res.x*uOffset,"
                       "uTD2DInfos[0].res.y*uOffset);")
FLOW_OFFSET_WRONG = ("vec2 pixelOffset = vec2(uOffset/uTD2DInfos[0].res.x,"
                     "uOffset/uTD2DInfos[0].res.y);")
FLOW_OFFSET_PIXELS_VALUE = 3

# The shipped single-tap form. The optical flow already outputs a UV
# displacement, so it is applied straight to the sample coordinate.
#
# A gather-form softmax splat (arXiv 2003.05534) was tried here and reverted.
# It searched a neighbourhood of fixed radius, but this flow's displacement is
# tens to hundreds of texels, so the pixel that should land on a target was
# never inside the search and every weight came out zero. A splat needs a reach
# derived from the displacement, not a constant, before it can replace this.
MOSH_SHADER = """// Single-tap datamosh.
uniform float motOffset;
out vec4 fragColor;
void main()
{
    vec4 mot = texture(sTD2DInputs[1], vUV.st);
    vec4 col = texture(sTD2DInputs[2], vUV.st + mot.rg * motOffset);
    fragColor = TDOutputSwizzle(col);
}
"""

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
        ("vol", 0.15), ("water-lvl", 0.15))),
    ("Force", "Forcelow", "Forcehigh", (
        ("mod-2", 1.0), ("mod-12", 0.5), ("mod-56", 0.5), ("mod-78", 0.5),
        ("cpu", 0.3), ("dsp", 0.3), ("pitch-1234", 0.5), ("pitch-5678", 0.5))),
    ("Threshold", "Thresholdlow", "Thresholdhigh", (
        ("mod-1", 0.3), ("sharp-12", 0.1), ("sharp-34", 0.1),
        ("sharp-56", 0.1), ("sharp-78", 0.1), ("fast-12", 0.1),
        ("fast-34", 0.1), ("fast-56", 0.1), ("fast-78", 0.1),
        ("sensor-1", 0.03), ("sensor-2", 0.03), ("sensor-3", 0.03),
        ("sensor-4", 0.03), ("sensor-5", 0.03), ("sensor-6", 0.03),
        ("sensor-7", 0.03), ("sensor-8", 0.03))),
    ("Lambda", "Lambdalow", "Lambdahigh", (
        ("mod-34", 0.5), ("vibrato", 0.1), ("lfo-wav", 0.1),
        ("time-1", 0.05), ("time-2", 0.05), ("tune-1", 0.1), ("tune-2", 0.1),
        ("tune-3", 0.1), ("tune-4", 0.1), ("tune-5", 0.1), ("tune-6", 0.1),
        ("tune-7", 0.1), ("tune-8", 0.1))),
)

# Destination parameter, the buses that drive it, and the level that flips it.
TOGGLES = (
    ("Inversex", (("switch", 1.0), ("source-12", 0.3), ("source-34", 0.3),
                  ("source-56", 0.3), ("source-78", 0.3), ("led", 0.3)), 0.5),
    ("Inversey", (("andor", 1.0), ("link", 0.3), ("quantize", 0.3)), 0.5),
)

# Destination parameter and the panel control that sets how often the loop is
# re-seeded. The shader samples only the feedback, so without a reset the frame
# melts into a still and stops moving, whatever the hold is doing. One means
# every frame, zero means never.
PULSES = (
    ("Feedbackreset", "Refreshdiv"),
)

# Parameters whose expression is configuration, not picture control, so the
# stray-expression sweep leaves them alone.
KEEP_EXPRESSIONS = ("externaltox",)


def say(line=""):
    REPORT.append(str(line))


def walk(node, depth=0, limit=8):
    if depth > limit:
        return
    for child in node.children:
        yield child
        for grandchild in walk(child, depth + 1, limit):
            yield grandchild


def find_datamosh():
    for node in walk(op("/")):
        if "datamosh" in node.name.lower():
            return node
    return None


def pick_par(node, wanted, avoid=()):
    """Find a parameter by name or label without assuming its exact name."""
    for par in node.pars():
        name = par.name.lower()
        label = str(par.label).lower()
        if any(bad in name for bad in avoid):
            continue
        if wanted in name or wanted in label:
            return par
    return None


def ensure_osc_in(parent):
    chop = parent.op(OSC_NAME)
    if chop is None:
        chop = parent.create(oscinCHOP, OSC_NAME)
        say("created %s" % chop.path)
    else:
        say("reusing %s" % chop.path)

    active = pick_par(chop, "active")
    if active is not None:
        active.val = True

    protocol = pick_par(chop, "protocol")
    if protocol is not None and protocol.menuNames:
        for option in protocol.menuNames:
            if option.lower() == "udp":
                protocol.val = option
                break

    # Never hardcode the port parameter name. TouchDesigner builds differ, and
    # a wrong guess raises instead of failing quietly.
    port = pick_par(chop, "port", avoid=("protocol", "report", "support"))
    if port is None:
        say("  could NOT find a port parameter, set it to %s by hand" % LISTEN_PORT)
    else:
        try:
            port.val = LISTEN_PORT
            say("  %s = %s" % (port.name, port.eval()))
        except Exception as exc:
            say("  setting %s failed: %s" % (port.name, exc))

    address = pick_par(chop, "address")
    if address is not None:
        try:
            address.val = "127.0.0.1"
            say("  %s = %s" % (address.name, address.eval()))
        except Exception:
            pass
    return chop


def covered_buses():
    """Every address the bridge publishes, read from the generated patch."""
    with open(BRIDGE, errors="ignore") as handle:
        return sorted(set(re.findall(r"/lira/([A-Za-z0-9-]+)", handle.read())))


def mapped_buses():
    found = set()
    for _, _, _, terms in CONTINUOUS:
        found.update(bus for bus, _ in terms)
    for _, terms, _ in TOGGLES:
        found.update(bus for bus, _ in terms)
    return found


def report_coverage():
    buses = covered_buses()
    mapped = mapped_buses()
    unmapped = [bus for bus in buses if bus not in mapped]
    stray = sorted(bus for bus in mapped if bus not in buses)
    say("bridge publishes %d buses, the map names %d" % (len(buses), len(mapped)))
    if stray:
        say("MAPPED BUT NOT PUBLISHED: %s" % ", ".join(stray))
    if unmapped:
        say("UNMAPPED BUSES: %s" % ", ".join(unmapped))
    else:
        say("every published bus is mapped to the visual")
    return not unmapped


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


def ensure_visual_only(parent):
    """TouchDesigner draws the picture. The sound comes from Pd alone.

    The project ships an Audio Movie CHOP fed by the movie, wired to an Audio
    Device Out CHOP. Both stay in place so the wiring is visible, but they go
    quiet, so the instrument is the only thing the audience hears.
    """
    changed = []
    for node in parent.children:
        if node.type == "audiodevout":
            try:
                node.par.active = False
                changed.append("%s.active=False" % node.name)
            except Exception as exc:
                say("  could not silence %s: %s" % (node.name, exc))
        elif node.type == "audiomovie":
            try:
                node.par.play = False
                changed.append("%s.play=False" % node.name)
            except Exception as exc:
                say("  could not stop %s: %s" % (node.name, exc))
    return changed


def ensure_flow_input(comp):
    """Feed the optical flow the picture, or every melt is a no-op.

    A black flow means zero motion vectors, and the shader offsets its UV
    sample by those vectors, so with no input the controls change parameters
    and nothing on screen moves.
    """
    flow = None
    for node in comp.children:
        if "opticalflow" in node.name.lower():
            flow = node
            break
    source = comp.op("null1")
    if flow is None or source is None:
        return "no optical flow component or no null1 to feed it"
    if not flow.inputConnectors[0].connections:
        flow.inputConnectors[0].connect(source)
        return "connected %s -> %s" % (source.name, flow.name)
    return "%s already fed by %s" % (
        flow.name, [o.name for o in flow.inputs][0] if flow.inputs else "?")


def ensure_flow_scale(comp):
    """Make the flow's gradient step a pixel count, and give it a usable gain.

    Two things keep the flow empty. The palette multiplies the step by the
    resolution instead of dividing, and the shipped Force of 1 leaves motion
    vectors around 6e-5, which displaces nothing.
    """
    flow = None
    for node in comp.children:
        if "opticalflow" in node.name.lower():
            flow = node
            break
    if flow is None:
        return "no optical flow component"

    notes = []
    dat = flow.op("glsl1_pixel")
    if dat is not None:
        if FLOW_OFFSET_WRONG in dat.text:
            dat.text = dat.text.replace(FLOW_OFFSET_WRONG, FLOW_OFFSET_CORRECT)
            notes.append("restored the shipped offset line, a step of uOffset pixels")
        elif FLOW_OFFSET_CORRECT in dat.text:
            notes.append("offset line already a pixel step")
        else:
            notes.append("could not find the offset line")

    offset = getattr(comp.par, "Offset", None)
    if offset is not None:
        offset.val = FLOW_OFFSET_PIXELS_VALUE
        notes.append("Offset = %s pixels" % FLOW_OFFSET_PIXELS_VALUE)
    return ", ".join(notes)


def ensure_ui(parent):
    """A panel for the destination ranges, so the look is tuned on screen.

    Each range lives on a custom parameter that reads its slider, and the
    destination expressions read those parameters. Re-running keeps whatever
    the sliders are set to.
    """
    ui = parent.op(UI_NAME)
    if ui is None:
        ui = parent.create(containerCOMP, UI_NAME)

    page = None
    for existing in ui.customPages:
        if existing.name == "Lira":
            page = existing
            break
    if page is None:
        page = ui.appendCustomPage("Lira")

    def child(name, node_type):
        # TouchDesigner appends a number when a name is taken, so an earlier
        # run can leave the slider as s_Meltlow1. Reuse whatever is there.
        node = ui.op(name)
        if node is not None:
            return node, False
        for candidate in ui.children:
            if candidate.name.startswith(name):
                return candidate, False
        return ui.create(node_type, name), True

    for index, (name, label, low, high, default) in enumerate(UI_CONTROLS):
        if not hasattr(ui.par, name):
            page.appendFloat(name, label=label)

        slider, made = child("s_" + name, sliderCOMP)
        if made:
            slider.par.value0 = default
        slider.par.x = 8
        slider.par.y = 10 + index * 40
        slider.par.w = 200
        slider.par.h = 24
        slider.par.valuerange0l = low
        slider.par.valuerange0h = high

        text, _ = child("t_" + name, textCOMP)
        text.par.x = 216
        text.par.y = 10 + index * 40
        text.par.w = 190
        text.par.h = 24
        text.par.text = label
        text.par.fontsize = 12

        par = getattr(ui.par, name)
        par.expr = "op(%r).par.value0" % slider.path

    ui.par.w = 420
    ui.par.h = PANEL_H

    # Drop the slider and label of a control that is no longer in UI_CONTROLS,
    # so a renamed or removed control does not leave a dead widget behind.
    reserved = ("s_morph", "t_morph")
    for candidate in list(ui.children):
        name = candidate.name
        if name.startswith(reserved) or not name.startswith(("s_", "t_")):
            continue
        if any(name.startswith(("s_" + control, "t_" + control))
               for control, _, _, _, _ in UI_CONTROLS):
            continue
        candidate.destroy()

    values = ", ".join(
        "%s=%s" % (name, round(float(getattr(ui.par, name).eval()), 3))
        for name, _, _, _, _ in UI_CONTROLS)
    say("  %s panel: %s" % (ui.path, values))
    return ui


# Where a randomise is allowed to look. The slider range is not the useful
# range, because a range that reaches zero melts nothing and a force that
# reaches zero stops the flow.
RANDOM_WINDOWS = {
    "Meltlow": (0.0, 0.4), "Melthigh": (0.4, 1.2),
    "Forcelow": (0.5, 2.0), "Forcehigh": (2.0, 8.0),
    "Thresholdlow": (0.0, 0.005), "Thresholdhigh": (0.005, 0.02),
    "Lambdalow": (0.05, 0.3), "Lambdahigh": (0.3, 1.0),
    "Refreshdiv": (2.0, 30.0),
}

PRESET_DAT = '''"""Presets and the morph, driven from the panel buttons.

Store A and Store B capture the sliders. Morph blends A into B across every
control, which is the cheap version of the point ParamExplorer makes, that the
good settings sit in small parts of a large space (arXiv 2512.16529).
"""

import random

NAMES = %r
WINDOWS = %r


def _slider(ui, name):
    for child in ui.children:
        if child.name.startswith("s_" + name):
            return child
    return None


def _write(ui, values):
    for name, value in zip(NAMES, values):
        slider = _slider(ui, name)
        if slider is not None:
            slider.par.value0 = value


def _store(ui, column):
    table = ui.op("presets")
    for index, name in enumerate(NAMES):
        table[index + 1, column] = getattr(ui.par, name).eval()


def _morph(ui, t):
    table = ui.op("presets")
    # table cells read back as strings
    a = [float(table[i + 1, 1].val) for i in range(len(NAMES))]
    b = [float(table[i + 1, 2].val) for i in range(len(NAMES))]
    _write(ui, [x + (y - x) * t for x, y in zip(a, b)])


def _randomise(ui):
    values = []
    for name in NAMES:
        low, high = WINDOWS.get(name, (0.0, 1.0))
        values.append(low + (high - low) * random.random())
    _write(ui, values)


def onValueChange(panelValue):
    ui = panelValue.owner.parent()
    name = panelValue.owner.name
    if name.startswith("b_storeA"):
        _store(ui, 1)
    elif name.startswith("b_storeB"):
        _store(ui, 2)
    elif name.startswith("b_random"):
        _randomise(ui)
    elif name.startswith("s_morph"):
        # The panel value handed to the callback reads 0 during a touch, so
        # read the slider itself.
        _morph(ui, float(panelValue.owner.par.value0.eval()))
'''


def ensure_presets(ui):
    """A presets table, two store buttons, a randomise button and a morph."""
    names = [name for name, _, _, _, _ in UI_CONTROLS]

    def child(name, node_type):
        # TouchDesigner appends a number when a name is taken, so an earlier
        # run can leave the button as b_storeA1. Reuse whatever is there.
        node = ui.op(name)
        if node is not None:
            return node
        for candidate in ui.children:
            if candidate.name.startswith(name):
                return candidate
        return ui.create(node_type, name)

    table = child("presets", tableDAT)
    if table.numRows == 0:
        table.appendRow(["control", "A", "B"])
    elif table[0, 0].val != "control":
        table.insertRow(0, ["control", "A", "B"])
    present = {table[row, 0].val for row in range(table.numRows)}
    for name in names:
        if name in present:
            continue
        value = getattr(ui.par, name).eval()
        table.appendRow([name, value, value])
    for row in range(table.numRows - 1, 0, -1):
        if table[row, 0].val not in names:
            table.deleteRow(row)

    momentaries = (
        ("b_storeA", "Store A", 8), ("b_storeB", "Store B", 104),
        ("b_random", "Randomise", 200),
    )
    for name, label, x in momentaries:
        button = child(name, buttonCOMP)
        button.par.x = x
        button.par.y = PRESET_ROW_Y
        button.par.w = 90
        button.par.h = 26
        button.par.label = label
        kind = getattr(button.par, "buttontype", None)
        if kind is not None and kind.menuNames:
            for option in kind.menuNames:
                if option.lower().startswith("moment"):
                    kind.val = option
                    break

    morph = child("s_morph", sliderCOMP)
    morph.par.x = 300
    morph.par.y = PRESET_ROW_Y
    morph.par.w = 110
    morph.par.h = 26
    morph.par.valuerange0l = 0.0
    morph.par.valuerange0h = 1.0

    text = child("t_morph", textCOMP)
    text.par.x = 300
    text.par.y = PRESET_ROW_Y + 28
    text.par.w = 110
    text.par.h = 20
    text.par.text = "Morph A to B"
    text.par.fontsize = 11

    execute = child("preset_exec", "panelexecuteDAT")
    execute.text = PRESET_DAT % (names, RANDOM_WINDOWS)
    panels = getattr(execute.par, "panels", None)
    if panels is not None:
        panels.val = ui.path + "/*"
    for switch in ("active", "valuechange"):
        par = getattr(execute.par, switch, None)
        if par is not None:
            par.val = True
    for unused in ("offtoon", "ontooff", "whileon", "whileoff"):
        par = getattr(execute.par, unused, None)
        if par is not None:
            par.val = False
    return "%d controls, presets table and morph" % len(names)


def ensure_mosh(comp):
    """Put the single-tap mosh shader in place."""
    dat = comp.op("glslmulti1_pixel")
    if dat is None:
        return "no mosh pixel shader"
    if "mot.rg * motOffset" in dat.text and "SPLAT_K" not in dat.text:
        notes = ["shader already the single tap"]
    else:
        dat.text = MOSH_SHADER
        notes = ["shader set to the single tap"]
    return ", ".join(notes)


def bind(comp, osc_path, ui_path):
    bindings = bindings_for(osc_path, ui_path)
    done, missing = [], []
    for name, expression in bindings.items():
        par = getattr(comp.par, name, None)
        if par is None:
            missing.append(name)
            continue
        try:
            par.expr = expression
            # A parameter keeps its expression text while it sits in
            # ParMode.CONSTANT, and then it silently stops following the bus.
            # Reporting the mode next to the name makes that visible.
            done.append("%s(%s)" % (name, str(par.mode).split(".")[-1]))
        except Exception as exc:
            say("  binding %s failed: %s" % (name, exc))
    for name in ("Opticalflow", "Glslmulti"):
        par = getattr(comp.par, name, None)
        if par is not None:
            try:
                par.val = 1
                done.append(name)
            except Exception:
                pass
    say("bound %d parameters: %s" % (len(done), ", ".join(done)))
    if missing:
        say("NOT ON THE COMPONENT: %s" % ", ".join(missing))

    # A parameter that is not in the map must stay a plain constant. A
    # leftover expression there fights the map, and one on a flow parameter
    # such as Offset silently zeroes the motion and freezes the picture.
    cleared = []
    for par in comp.pars():
        if par.name in bindings or par.name in KEEP_EXPRESSIONS:
            continue
        try:
            if par.mode == ParMode.EXPRESSION:
                par.expr = ""
                cleared.append(par.name)
        except Exception:
            pass
    if cleared:
        say("cleared stray expressions:")
        for name in cleared:
            par = getattr(comp.par, name)
            say("   %-22s now %s" % (name, par.eval()))


def report_values(osc):
    try:
        names = sorted(c.name for c in osc.chans())
    except Exception as exc:
        say("could not read channels: %s" % exc)
        return
    say()
    say("channels arriving (%d)" % len(names))
    say()
    say("live values")
    for name in ("hold-1234", "hold-5678", "drv", "mod-1", "mod-2", "mod-34",
                 "switch", "andor", "water-lvl"):
        full = "%s/%s" % (ADDRESS_ROOT, name)
        try:
            value = osc[full].eval()
        except Exception:
            say("   %-12s (not arriving yet)" % name)
            continue
        say("   %-12s %s" % (name, round(value, 2)))


def main():
    say("TouchDesigner %s" % app.version)
    report_coverage()
    comp = find_datamosh()
    if comp is None:
        say("no Datamoshing component found anywhere in the project")
        return
    say("component %s" % comp.path)
    osc = ensure_osc_in(comp.parent())
    silenced = ensure_visual_only(comp.parent())
    say("visual only: %s" % (", ".join(silenced) if silenced
                             else "no audio outputs found"))
    say("optical flow: %s" % ensure_flow_input(comp))
    say("flow scale: %s" % ensure_flow_scale(comp))
    ui = ensure_ui(comp.parent())
    say("presets: %s" % ensure_presets(ui))
    say("mosh shader: %s" % ensure_mosh(comp))
    bind(comp, osc.path, ui.path)
    report_values(osc)


try:
    main()
except Exception:
    REPORT.append(traceback.format_exc())

print("\n".join(REPORT))
