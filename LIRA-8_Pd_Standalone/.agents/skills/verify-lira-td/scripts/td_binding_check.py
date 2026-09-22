"""Check that every published bus reaches the picture. Runs in TouchDesigner.

Run it through the TouchDesigner MCP with execute_python_script, or from the
Textport with:

    exec(open('/Users/adrifadilah/Fun/Sounds/pd/soma/LIRA-8/LIRA-8_Pd_Standalone/.agents/skills/verify-lira-td/scripts/td_binding_check.py').read())

It answers two questions. Is every bound parameter in the mode it needs, since
a parameter keeps its expression text while sitting in ParMode.CONSTANT and
then silently stops following its bus. And does every address the LIRA-8
bridge publishes appear in at least one of those expressions, so no control
arrives and then does nothing.

It also checks that the optical flow receives the picture. A flow with no input
renders black, the motion vectors are zero, and the melt displaces the image by
nothing, so every control appears dead while every parameter reads correctly.
"""

import re

BRIDGE = ("/Users/adrifadilah/Fun/Sounds/pd/soma/LIRA-8/LIRA-8_Pd_Standalone"
          "/abs/av.osc.pd")

EXPECTED = {
    "Offsetbymotionvector": "EXPRESSION",
    "Force": "EXPRESSION",
    "Threshold": "EXPRESSION",
    "Lambda": "EXPRESSION",
    "Inversex": "EXPRESSION",
    "Inversey": "EXPRESSION",
    "Feedbackreset": "EXPRESSION",
    "Opticalflow": "CONSTANT",
    "Glslmulti": "CONSTANT",
}


def main():
    comp = op("/project1/Datamoshing")
    if comp is None:
        print("FAIL: no /project1/Datamoshing component")
        return

    problems = []
    expressions = []
    flow = None
    for node in comp.children:
        if "opticalflow" in node.name.lower():
            flow = node
            break
    if flow is None:
        problems.append("no optical flow component")
    elif not flow.inputConnectors[0].connections:
        print("%-22s NO INPUT" % flow.name)
        problems.append("%s has no input, so every motion vector is zero" % flow.name)
    else:
        print("%-22s fed by %s" % (flow.name, [o.name for o in flow.inputs][0]))

    for name, want in EXPECTED.items():
        par = getattr(comp.par, name, None)
        if par is None:
            print("%-22s MISSING" % name)
            problems.append("%s is missing" % name)
            continue
        got = str(par.mode).split(".")[-1]
        expressions.append(par.expr or "")
        print("%-22s mode=%-11s want=%-11s value=%s" % (
            name, got, want, round(float(par.eval()), 4)))
        if got != want:
            problems.append("%s is %s, want %s" % (name, got, want))

    if expressions:
        text = " ".join(expressions)
        with open(BRIDGE, errors="ignore") as handle:
            published = sorted(set(re.findall(r"/lira/([A-Za-z0-9-]+)",
                                              handle.read())))
        unmapped = [bus for bus in published if ("lira/%s'" % bus) not in text]
        print("bridge publishes %d buses, %d reach a parameter" % (
            len(published), len(published) - len(unmapped)))
        if unmapped:
            problems.append("unmapped: %s" % ", ".join(unmapped))

        # The list above comes from the generated patch file, so it cannot see
        # a stale bridge. The live CHOP can, so print the two deltas. They are
        # notes and not failures, because a bus that publishes only on change
        # is legitimately absent until it moves, and the OSC In CHOP keeps
        # whatever an earlier probe left behind.
        osc = op("/project1/lira_osc")
        if osc is None:
            problems.append("no /project1/lira_osc to compare against")
        else:
            live = sorted({name.split("/", 1)[-1] for name in
                           (channel.name for channel in osc.chans())
                           if name.startswith("lira/")})
            print("lira_osc carries %d channels" % len(live))
            missing = [bus for bus in published if bus not in live]
            extra = [bus for bus in live if bus not in published]
            if missing:
                print("note: published, not seen in the CHOP yet: %s" %
                      ", ".join(missing))
            if extra:
                print("note: in the CHOP with no publisher: %s" %
                      ", ".join(extra))

    print("FAIL: " + "; ".join(problems) if problems else
          "PASS: every binding is live and every published bus is mapped")


main()
