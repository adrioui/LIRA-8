# The tuning panel

The panel under `/project1/lira_ui` holds the destination ranges and the reset interval, on nine sliders. The destination expressions read those parameters, so the picture is tuned on screen rather than in the build file. The shader enable switches (`Opticalflow`, `Glslmulti`) are separate constants the build sets, not panel numbers.

## Sub-features

- `panel-ranges` nine sliders set the destination ranges and the reset interval.
- `panel-store` Store A and Store B capture the current slider values into the `presets` table.
- `panel-random` Randomise draws every control from its working window.
- `panel-morph` Morph blends A into B across every control.

## How to get to it (user POV)

- Open `/project1/lira_ui`, or float it into its own pane.
- Drag a slider, or press Store A, Randomise, Store B, then Morph.

## Driving it with lira_osc.py

Preconditions:

- TouchDesigner is open on `lira.toe` and cooking.
- The MCP answers on 9981.

- **A slider moves a destination.** Move `Melthigh` and read `Offsetbymotionvector`; the destination follows the slider. The observed example is a Randomise, not a drag: a live run randomised the panel and the destination followed, Melt high 1.125 to 0.736 as `Offsetbymotionvector` went 0.502 to 0.3854.
- **Store and morph.** Store A, Randomise, Store B, then move Morph. A live run morphed to 0.5 and again to 0.75, and both landed on A plus that fraction of B minus A for every control, max error 0.0.
- **The dispatch.** The buttons and the morph slider are routed by name in `preset_exec`. Calling `onValueChange` with a stand-in panel value runs each path, which is how the store, randomise and morph were checked.
- **A button fires on a real click.** `op('/project1/lira_ui/b_storeA1').click()` simulates one and runs the callback, with the panel closed. `b.par.value0` is the Toggle parameter and does not fire it. Verified by storing A, randomising, storing B, then checking column A and column B in `presets`.
- **The morph fires from a real drag.** `op('/project1/lira_ui/s_morph1').interactMouse(0.75, 0.5, leftClick=1)` moves the slider and runs the morph. A run at 0.75 landed on A plus three quarters of B minus A for every control, max error 0.0.
- **Proof.** Keep the slider values before and after, and the resulting destination reads.

## Gotchas

- Randomise draws from a working window per control, not from the slider range. A range that reaches zero melts nothing, and a force that reaches zero stops the flow, so the full range is not useful to explore.
- TouchDesigner appends a number when a node name is taken, so the sliders are `s_Melthigh1` and so on. Address them by prefix.
- The morph writes the sliders, so it overwrites whatever you were dragging. That is the point, but it means a morph after a manual tweak loses the tweak.
- A script sets a parameter value, not a panel event. `par.value0` on a button is the Toggle parameter and does not fire the execute. `buttonCOMP.click()` and `interactMouse` do, and they work with the panel closed.
- Writing `.val` on a parameter that carries an expression drops it to `CONSTANT`, and then it stops following its slider. That is what froze `Meltlow` and `Melthigh` once. Set the mode back with `par.mode = ParMode.EXPRESSION`, or write the slider instead and let the expression read it.
- The morph reads the slider itself. The panel value handed to `onValueChange` reads 0 during a touch, so `preset_exec` calls `float(panelValue.owner.par.value0.eval())`. Replacing that with `panelValue.val` makes every morph land on A.
- `preset_exec` leaves `offtoon` and `ontooff` off. They were on with no `onOffToOn` callback, which printed an error into the node's script errors on every button press.
