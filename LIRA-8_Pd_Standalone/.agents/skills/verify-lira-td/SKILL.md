---
name: verify-lira-td
description: "Drive and prove the LIRA-8 to TouchDesigner OSC bridge. Launch the Pd instrument, observe or write /lira/* bus traffic on the wire, read the TouchDesigner lira_osc CHOP and Datamoshing parameter bindings, and capture the picture. Use when verifying, debugging, or changing anything that crosses between the LIRA-8 Pd patch and the TouchDesigner project."
---

# Verify the LIRA-8 to TouchDesigner bridge

The LIRA-8 instrument reaches TouchDesigner over OSC. Pd publishes every bus to `127.0.0.1:9121` as `/lira/<name>` and accepts the writable ones on `127.0.0.1:9122`. TouchDesigner's `lira_osc` OSC In CHOP listens on 9121 and drives the parameters of `/project1/Datamoshing`. TouchDesigner is picture only, so its Audio Device Out CHOP stays off and the sound comes from Pd alone. The map in `features/` covers each user-facing behavior. Read `features/README.md` first, then open the matching feature file.

## Launch

Two halves, both on fixed ports, so nothing here is isolatable. Never drive a Pd, a TouchDesigner, or an MCP endpoint this run did not start or health-check.

Pd, the real instrument:

    ./run-av.sh

It starts Pd at 48 kHz with `_LIRA-8.pd`. Ready when `/lira/cpu` arrives, because that meter streams on its own with the instrument idle. Teardown is a signal to the PID this run started.

TouchDesigner:

- The Desktop copy of `lira.toe` is the authoritative project. It holds `lira_osc` on 9121, the `Datamoshing` bindings, and `mcp_webserver_base` on 9981. Opening it and letting it cook is the whole launch.
- If a project lacks those nodes or carries a different shader, run `tools/td_build.py` from the Textport. It finds `Datamoshing` by walking the project, creates the OSC In CHOP, rebinds the parameters, and replaces a shader that is not the single tap. Re-running leaves the presets table alone.
- The MCP webserver powers the read side. It ships inside the project. When 9981 is closed, bring it up from the Textport with `exec(open('/Users/adrifadilah/tdmcp.py').read())` and then `exec(open('/Users/adrifadilah/tdmcp2.py').read())`.
- Opening a project replaces whatever is open. Do not open a project over a running one that may hold unsaved work.

## Doctor

    python3 .agents/skills/verify-lira-td/scripts/lira_osc.py doctor

Read-only. Reports `pd`, whether TouchDesigner is running, whether the MCP answers on 9981, and which process owns 9121 and 9122. `pd_lane_available` is true when Pd is present and no stray `pd` owns 9121. `td_lane_available` is true when the MCP answers. Run it before the first drive, and again after anything looks off.

## Drive

The wire half runs through `scripts/lira_osc.py`. The TouchDesigner half runs through the project webserver on 9981, via `scripts/td_read.py`.

Observe what Pd publishes:

    python3 .agents/skills/verify-lira-td/scripts/lira_osc.py listen --seconds 6 \
        --expect /lira/cpu --save artifacts/lira-td/<feature>/out.txt

This binds 9121. When TouchDesigner's `lira_osc` already owns 9121, which is the normal case while the project is open, the bind fails on purpose and the read goes through the webserver instead.

Watch Pd echo a written control:

    python3 .agents/skills/verify-lira-td/scripts/lira_osc.py roundtrip hold-1234 127 \
        --save artifacts/lira-td/<feature>/roundtrip.txt

`roundtrip` binds 9121 as well, so it suits runs where TouchDesigner is not listening. With TouchDesigner open, write with `send` and read the result through the webserver:

    python3 .agents/skills/verify-lira-td/scripts/lira_osc.py send /lira/hold-1234 127

Read the TouchDesigner side with `scripts/td_read.py`. `td_read.py chans /project1/lira_osc` lists the incoming channels, `td_read.py exec` runs an arbitrary script against the live project (a parameter read, a CHOP sample, a TOP capture), and `td_read.py top /project1/Datamoshing <file>.png` captures the picture. Address channels as `lira/hold-1234`, not `hold-1234`, because TouchDesigner keeps the OSC address root.

## Evidence

Write proofs under `artifacts/lira-td/<feature>/` at the repo root. Proof standards:

- Exercise the real path. `./run-av.sh` for the instrument and the webserver on 9981 for TouchDesigner. The probe patch inside `tools/verify_osc.py` is a narrower harness for the bridge alone, not a substitute for the instrument.
- Capture the action and the resulting state. The OSC transcript that shows a datagram arriving, plus the CHOP channel that shows it landed.
- Verify the side effect, not the send. A control must change the `Datamoshing` parameter its group feeds, and the picture must keep moving while you hold.
- Record the feature ID and entry point used with each artifact.
- Report an unreachable path with the command attempted and the unmet prerequisite. Do not report a skipped entry point as verified through a different one.

## Cleanup

Signal the Pd process this run started, by its PID, never by process name. Leave TouchDesigner alone, because this run does not own it. Leave `artifacts/` in place, because the proof outlives the teardown.

## Helpers

`scripts/lira_osc.py` is the wire harness. Its subcommands:

    python3 .agents/skills/verify-lira-td/scripts/lira_osc.py doctor
    python3 .agents/skills/verify-lira-td/scripts/lira_osc.py listen --seconds 6 --expect /lira/cpu
    python3 .agents/skills/verify-lira-td/scripts/lira_osc.py send /lira/hold-1234 127
    python3 .agents/skills/verify-lira-td/scripts/lira_osc.py roundtrip hold-1234 127

`scripts/td_binding_check.py` runs inside TouchDesigner, through the webserver or the Textport. It reports every bound parameter's mode and value, checks that every address the bridge publishes appears in one of the expressions, and prints `PASS` or `FAIL`:

    exec(open('<repo>/.agents/skills/verify-lira-td/scripts/td_binding_check.py').read())

`scripts/td_read.py` is the read harness for the webserver on 9981. Its subcommands:

    python3 .agents/skills/verify-lira-td/scripts/td_read.py chans /project1/lira_osc
    python3 .agents/skills/verify-lira-td/scripts/td_read.py par /project1/Datamoshing Force
    python3 .agents/skills/verify-lira-td/scripts/td_read.py top /project1/Datamoshing artifacts/lira-td/<feature>/frame.png
    python3 .agents/skills/verify-lira-td/scripts/td_read.py exec --file <script.py>

Two webserver traps shape every script it sends. The serializer sends every non-scalar through `td.op()`, so a nested dict comes back as a node summary; return flat scalars. And a script that never sets `result` gets its last line evaluated again, so a trailing `main()` runs twice; end on a plain expression or set `result` explicitly.
