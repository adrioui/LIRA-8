# The loop keeps moving

The Datamoshing loop samples only its own feedback, so without a reset it melts into a still and stops moving. `Feedbackreset` pulses on an interval set by the panel, which re-seeds the loop from the live source.

## Sub-features

- `reset-off` at 0 leaves the loop alone, so the frame melts into a still.
- `reset-frame` at 1 re-seeds every frame, so the picture is the live video.
- `reset-interval` at N re-seeds every N frames, which leaves a trail that moves.

## How to get to it (user POV)

- Move the `Refresh every N frames` slider under `/project1/lira_ui`.

## Driving it with lira_osc.py

Preconditions:

- TouchDesigner is open on `lira.toe` and cooking, so it owns 9121.
- The MCP answers on 9981, and Pd is running so the picture has a source.

- **Never reset.** Set the `Refreshdiv` slider to 0 and read `Feedbackreset`. It reads 0, and two captures a few seconds apart come back nearly identical.
- **Refresh every frame.** Set it to 1 and read. It reads 1, and the picture is the live video.
- **Refresh on an interval.** Set it to 8 and capture twice a few seconds apart. The difference should be well above the same measurement with the reset at 0, where the loop settles into a still.
- **Proof.** Keep the slider value, the reset reads, and the two TOP captures.

## Gotchas

- HOLD does not control the reset. HOLD is the sustain control on the instrument, and tying the picture's refresh to it froze the video whenever a voice was held.
- The interval counts frames. At 60 fps, 8 is about eight refreshes a second and 60 is one.
- Every read inside one script call returns the same reset value, because a script blocks the frame. Read across separate calls to watch it pulse.
