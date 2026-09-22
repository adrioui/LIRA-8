# Write a control from outside the patch

Pd accepts 22 writable addresses on `127.0.0.1:9122`. Writing one moves the matching control in the running instrument and republishes the new value on 9121, so the instrument can be driven without its GUI.

## Sub-features

- `in-accept` accepts the 22 buses that have a `r $0-s-<name>` receiver.
- `in-move` moves the matching control to the written value.
- `in-echo` republishes the new value on 9121.

## How to get to it (user POV)

- Send an OSC message to `127.0.0.1:9122` while the instrument runs.
- Use `tools/verify_osc.py` for the bridge alone, with no instrument.

## Driving it with lira_osc.py

Preconditions:

- `scripts/lira_osc.py doctor` reports `pd_lane_available` true.
- The instrument is running and has finished loading.

- **Round trip.** Write a control and require the echo. Run `roundtrip hold-1234 127 --save artifacts/lira-td/osc-in/hold.txt`. Pd reports `/lira/hold-1234 127` back on 9121 and the command prints `PASS`.
- **Second bus.** Move a different control. Run `roundtrip mod-2 90`. `/lira/mod-2 90` comes back.
- **Third bus.** Repeat the round trip on another control. Run `roundtrip drv 80 --save artifacts/lira-td/osc-in/drv.txt`. `/lira/drv 80` comes back.
- **Proof.** Keep the `roundtrip` transcripts. Each shows the value sent to 9122 and the same value echoed on 9121.

## Gotchas

- The 19 read-only buses are not in the accepted list. Writing one has no effect, because the engine overwrites it every frame. A live run showed this plainly. Writing `andor`, a read-only bus, produced no echo, while the eleven writable buses written alongside it all came back.
- `netreceive` coalesces datagrams that land in the same poll, so space consecutive sends by a few hundred milliseconds.
- Only some writable buses hold a written value. A live run wrote `hold-1234`, `hold-5678` and `switch` and read them back at 0 a second later, because those are momentary controls the patch releases. It wrote `mod-2`, `vol` and `tune-1` and read back the engine's own values, because the engine pushes those every frame. Pick a bus and read it back before trusting a write.
- A control is a widget bus. Only the `$0-s-<name>` side of a control is writable, and the bridge selects that side for you from the bus name alone.
