# Publish the instrument to OSC

Pd sends every bus in the instrument to `127.0.0.1:9121` as `/lira/<name>`, so TouchDesigner can follow the instrument without reading the patch. 59 addresses leave Pd, one per bus.

## Sub-features

- `out-meter` streams `/lira/cpu` and `/lira/water-lvl` continuously, even with the instrument idle.
- `out-all` carries all 59 buses, one address each.
- `out-event` sends the remaining buses when their control moves.

## How to get to it (user POV)

- Launch the instrument with `./run-av.sh`.
- Move any control in the LIRA-8 window.

## Driving it with lira_osc.py

Preconditions:

- `scripts/lira_osc.py doctor` reports `pd_lane_available` true.
- No other process owns 9121. When TouchDesigner's `lira_osc` holds it, read the `lira_osc` CHOP through the MCP instead.

- **Meter.** Observe the always-on bus. Run `python3 .agents/skills/verify-lira-td/scripts/lira_osc.py listen --seconds 6 --expect /lira/cpu`. `/lira/cpu` arrives within a few seconds carrying a value.
- **Full list.** Listen and move controls at the same time, because each bus is published once when it changes. Start `listen --seconds 10 --save artifacts/lira-td/osc-out/moved.txt` in the background, then write ten controls into 9122. The transcript lines read `/lira/<name> <value>`, and the distinct address count grows with the number of controls moved.
- **One event bus.** Move a control from outside the patch and confirm it republishes. Run `roundtrip hold-1234 100 --save artifacts/lira-td/osc-out/hold.txt`. `/lira/hold-1234 100` comes back on 9121.
- **Proof.** Keep the saved transcripts. Each line is one address and its value as it left Pd.

## Gotchas

- 9121 has a single owner. When TouchDesigner's OSC In CHOP holds it, `listen` cannot bind and fails by design. Read the CHOP through the MCP instead.
- Only `/lira/cpu` and `/lira/water-lvl` stream on their own. The rest are events, so a fresh instance shows nothing else until a control moves.
- A bus publishes once per change. Sending a control and then starting `listen` misses it, because the republish already happened. Listen first, then move the control, or use `roundtrip`.
- 19 of the 59 buses are read-only readouts the engine owns, not controls.
