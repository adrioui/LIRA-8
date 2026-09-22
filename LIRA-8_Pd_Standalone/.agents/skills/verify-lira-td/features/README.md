# LIRA-8 to TouchDesigner verification map

This directory is the maintained source for verifying the LIRA-8 to TouchDesigner bridge. Read this index before driving, then use the matching feature file as the recipe.

## Baseline preconditions

- Launch the instrument with `./run-av.sh` from the repo root and keep its PID.
- TouchDesigner is open on `lira.toe`, whose `lira_osc` OSC In CHOP listens on `127.0.0.1:9121` and whose `Datamoshing` component is bound to it.
- The TouchDesigner MCP answers on `127.0.0.1:9981`, which is what the read side of the TD features needs.
- Run `scripts/lira_osc.py doctor` and require `pd_lane_available`. When TouchDesigner holds 9121, the wire listener cannot bind and every outbound read goes through the MCP instead.
- Never drive a Pd or a TouchDesigner instance this run did not start or health-check.

## Driving conventions

- Start every recipe from the baseline state unless its preconditions say otherwise.
- Run wire commands through `python3 .agents/skills/verify-lira-td/scripts/lira_osc.py`.
- Run TouchDesigner reads through the TouchDesigner MCP tools.
- Treat every command and every bus name as literal. The bus names carry hyphens, and channel names carry the `lira/` root.
- Restore any control the recipe moved. Remove seeded scratch state, but never remove proof artifacts.
- TouchDesigner owns 9121 whenever `lira.toe` is open, which is the normal TD case. Write with `send` there, because `roundtrip` binds 9121 and refuses.

## Proof and skip reporting

- Capture the action and the state it produced. The final screen proves neither on its own.
- Wire proof is the saved address/value transcript from `listen` or `roundtrip`.
- TouchDesigner proof is the `Datamoshing` parameter read and, for the picture, a captured TOP.
- Mutation proof includes a second, independent read of the changed value.
- Record the feature ID and entry point used with every artifact.
- Report an unreachable path with the command attempted and the unmet prerequisite.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior. It then uses exactly four H2 sections in this order.

1. `Sub-features` lists short IDs with one line for each behavior.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with lira_osc.py` starts with `Preconditions:` and pairs each user action with an exact command and an observable result.
4. `Gotchas` lists traps that can waste or invalidate a verification run.

Keep implementation details out of the map. Name only user paths, stable handles, required state, commands, and observable proof.

## Features

- [Publish the instrument to OSC](./osc-out.md) covers the 65 buses Pd sends to 9121, including the six FluCoMa audio descriptors.
- [Write a control from outside the patch](./osc-in.md) covers the 40 writable buses Pd accepts on 9122.
- [TouchDesigner follows the buses](./td-bindings.md) covers the `lira_osc` CHOP driving the `Datamoshing` parameters.
- [The loop recovers when you let go](./td-feedback-reset.md) covers `Feedbackreset` and the return to the clean picture.
- [The tuning panel](./ui-panel.md) covers the ranges, the preset store, the randomise, and the morph.
