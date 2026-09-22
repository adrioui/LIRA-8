# TouchDesigner follows the buses

Every bus Pd publishes drives the `Datamoshing` picture, continuously, so the visual answers the whole instrument rather than waiting on one control. The picture is a feedback loop and the optical flow that steers it is the Palette component `opticalFlow`, whose own defaults are Force 1.0, Offset 3, Lambda 0.1, and Threshold 0.0. The map modulates around those defaults with small weights.

## Sub-features

- `bind-flow-input` feeds the optical flow the picture. Without it every motion vector is zero and every control looks dead.
- `bind-flow-scale` keeps the flow's gradient step the shipped `res.xy * uOffset`, which is already a step of `uOffset` pixels, and keeps its gain small enough that the flow output stays a sane UV displacement.
- `bind-flow-trust` is not implemented. The flow-agreement damping was written for the splat and went out with it.
- `bind-mosh` resamples the feedback at the coordinate the flow displaces to. A gather-form softmax splat was tried here and reverted, because its fixed search radius could not cover this flow's displacement.
- `bind-melt` drives `Offsetbymotionvector` from `hold-1234`, `drv`, `hold-5678`, the feedback and delay family, `vol`, and `water-lvl`.
- `bind-force` adds to `Force` from the `mod` family, `cpu`, `dsp`, and `pitch`.
- `bind-threshold` adds to `Threshold` from `mod-1`, the `sharp` and `fast` families, and `sensor-1..8`.
- `bind-lambda` adds to `Lambda` from `mod-34`, `vibrato`, `lfo-wav`, the two times, and `tune-1..8`.
- `bind-flip` drives `Inversex` from `switch`, the sources, and `led`, and `Inversey` from `andor`, `link`, and `quantize`.
- `bind-reset` pulses `Feedbackreset` on a frame interval from the panel, so the live video keeps returning through the loop whatever the instrument is doing.
- `bind-visual-only` switches the Audio Device Out CHOP off, so the sound is Pd alone.
- `bind-panel` puts the destination ranges and the reset interval on nine sliders under `/project1/lira_ui`, and the expressions read them.
- `bind-audio` drives the melt from the measured level and peak, the flow gain from brightness, the motion gate from spectral flatness, lambda from pitch confidence, and the x inversion from pitch.
- `bind-coverage` requires every published address to appear in one of those expressions.

## How to get to it (user POV)

- Play the instrument and watch the picture melt.
- Leave the hold alone and the clean video keeps coming back.

## Driving it with lira_osc.py

Preconditions:

- TouchDesigner is open with the project that holds `Datamoshing`, and it owns 9121.
- The MCP answers on 9981, so `scripts/lira_osc.py doctor` reports `td_lane_available` true.
- Pd is running, so the buses exist and the picture has a source.

TouchDesigner owns 9121, so `roundtrip` cannot bind and must not be used here. Write with `send` and read through the MCP. The instrument may be live, in which case its own controls overwrite a write immediately, so read the bus back before trusting a result.

- **The flow is fed.** Read the optical flow node's input. It is `null1`. An unfed flow renders black, and a black flow makes every other test below meaningless.
- **The flow is alive.** Sample the optical flow output on a grid. A live run read 0.000000 at every point while the offset line was wrong, then 0.295 once it was fixed. A zero flow means the melt multiplies nothing and every control is a no-op, so check this first.
- **The melt reaches the picture.** With the reset at 1 the melt is one frame deep, so capture the output and the source in the same frame and compare them at two melt settings. A live run matched the source at melt 0, difference 0.00, and differed by 10.00 at melt 1.5.
- **Any bus moves it.** Run `send /lira/mod-1 127` and read `Threshold`, `send /lira/tune-1 127` and read `Lambda`, or `send /lira/mod-2 127` and read `Force`. The melt responds to the whole family, so it is not zero when the hold is idle.
- **The flow window is the default.** Read `Offset`. It is 3, and it is not a performance control.
- **The panel tunes the look.** Move a slider under `/project1/lira_ui` and read the destination it sets. A live run randomised the panel and the destination followed, Melt high 1.125 to 0.736 as `Offsetbymotionvector` went 0.502 to 0.3854. The nine sliders are Melt low and high, Force low and high, Threshold low and high, Lambda low and high, and the refresh interval.
- **TouchDesigner is silent.** Read the Audio Device Out CHOP's `active`. It is off, so the only sound is Pd.
- **Coverage.** Run `scripts/td_binding_check.py` through the MCP. It prints `PASS` only when every bound parameter is in its expected mode and every published address appears in one of the expressions.
- **Proof.** Keep the parameter reads next to the bus values that produced them, plus TOP captures of the clean and melted states.

## Gotchas

- The optical flow must receive the picture. With nothing wired into it the flow is black, the motion vectors are zero, and the shader offsets its UV sample by nothing, so every control appears to do nothing while the parameters change correctly. Check this first when the picture ignores the instrument.
- TouchDesigner's `uTD2DInfos[i].res` is `vec4(1/width, 1/height, width, height)`. So `res.xy * uOffset` is already a step of `uOffset` pixels, and the shipped flow line is correct. A form that divides by `res` multiplies by the resolution instead, puts the two gradient samples a screen apart, clamps both to the same edge texel, and leaves the gradient and the whole flow at exactly zero. A live run read a flow of 0.000000 at every sample until the shipped line was restored, then 0.176.
- A gather-splat mosh must not use `res.zw` as a texel size. `res.zw` is the pixel count, so a reach of `res.zw * radius` spans thousands of UV units, every weight saturates, and the output becomes a broad average that ignores the flow. One texel in UV is `res.xy`.
- The flow's `Threshold` is compared against the magnitude before the force is applied, and that magnitude is small, around 0.005 to 0.07. A threshold of 0.45 zeroed the entire field. Keep the threshold near 0, around 0 to 0.02.
- The flow's `Force` multiplies the output, and the output is used directly as a UV displacement. A gain of 20 to 244 pushes the sample coordinate off the image, so the loop clamps to the edge and the picture flattens to one colour. A gain of about 1 to 8 leaves a visible melt.
- A softmax splat needs a reach that covers the displacement, which here is tens of pixels. A fixed radius of 1 to 40 cannot, so the candidates that should land on a pixel are never inside the search.
- The mosh shader resamples the feedback at `vUV + flow * motOffset`, which is the shipped single-tap form. The flow already outputs a UV displacement, so no scaling is needed.
- The generator deletes a slider and a label whose control is no longer in `UI_CONTROLS`, and drops its presets row, so a removed control leaves nothing dead behind.
- Tune the look from the panel, not from the bus weights. The weights set how much each control counts, and the panel sets the range that lands on each parameter.
- `Offset` sets the flow window. A stray expression on it that evaluates near zero stops the motion and freezes the picture, exactly as an unwired flow does.
- The shader samples only the feedback for colour, so the live video only enters when the Feedback TOP resets. That is why the reset keeps pulsing while the hold is idle.
- A destination must be a Float parameter, or the sum rounds away.
- A parameter keeps its expression text while it sits in `CONSTANT` mode, and then it never moves. Read the mode, because a frozen number is a broken binding and not a small change. Writing `.val` on an expression parameter is what puts it there, so a check that writes values has to set `par.mode = ParMode.EXPRESSION` back or the binding dies quietly.
- TouchDesigner finds an expression's dependencies by scanning its text for `op()['channel']`. A bus read through a helper such as `chans()` is invisible to that scan, and the parameter freezes.
- That plain read of a channel that has never arrived yields `None`, and arithmetic on it raises. Wrap each read in `or 0`, which keeps the address in the text and yields zero until the bus publishes.
- `led` is a readout that only publishes when it changes, so it is the bus most likely to be absent on a fresh session.
- The OSC In CHOP keeps every channel it has ever received, so a probe message leaves a channel behind. A live run carried `lira/shelltest` from an earlier probe and held 59 channels while `lira/led` was still absent, so the channel count alone does not prove the set is right. `td_binding_check.py` prints both deltas as notes.
- `tools/audio_bus_source.py` generates `abs/av.audio.pd` from one descriptor table and appends the analysis stage to `_LIRA-8.pd`. `abs/av.water.pd` throws its DAC feed into the same `av-mix` sum, so the analysis hears both branches of the output. Reload Pd after a regeneration, because the running instance keeps the patch it loaded.
