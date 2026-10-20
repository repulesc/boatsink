# boatsink

A fun, dead-end rowboat for Second Life: no oars, nowhere to go. It floats on the flat water, sways softly, can
drift, can slowly sink with whoever sits in it, and seats two people (a driver on the rower's bench and a passenger
facing them), each with their own seated pose.

- Owner menu: opens by itself and stays open until Finish or Close (right-click > Touch, or `/9 boat`, brings it back).
  The boat holds still while it is open. Calibrate and save the waterline, nudge and save each seat, turn Drift and Sink
  on or off.
- Everything saved lives in the boat itself (Linkset Data), so it survives script resets and copies.

**Status:** under construction, nothing is tested in Second Life yet. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for
the order of work and the in-world test list, and [`docs/SPEC.md`](docs/SPEC.md) for how it works.

## Setting it up in-world
1. **Remove every other script from the boat** (a driving script turns physics on when someone sits, and a physical boat
   cannot be moved this way).
2. The boat's front must point along the root prim's **+X** (the red arrow in Build mode with Local axes).
3. **Second seat:** link a small invisible prim (about 0.1 m cube, 100% transparent, phantom) to the boat and name it
   `Seat2`. Without it the boat is a one-seater and says so in chat.
4. **Animations:** upload `anims/rowboat_driver.anim` and `anims/rowboat_passenger.anim` (Build > Upload > Animation; a
   small fee). Name them exactly `rowboat_driver` and `rowboat_passenger`. They have not been seen on an avatar yet,
   so expect to adjust them (`anims/preview.png` shows the intended poses).
5. Put the boat on open water and drop `rowboat.lsl` and the two animations into the **root prim**. Close the edit
   window: Second Life freezes this kind of motion while the boat is selected.
6. The owner menu opens by itself: set the waterline (Up / Down, Save) and each seat (nudge, Save), then press Finish.

| Path | Contents |
|---|---|
| `src/rowboat.lsl` | The one script (goes in the boat's root prim) |
| `anims/` | The two seated animations (`.anim`) and a preview picture |
| `tools/lslcheck.sh` | Compile check (LSL-PyOptimizer) and a memory estimate |
| `tools/make_anims.py` | Generates the animation files |
| `tools/sim/` | Python checks of the motion maths and the animations, run in CI |

History: the first version (one seat, sinks when sat on) was written in the `cinema` repository's `lab/` folder and
moved here.
