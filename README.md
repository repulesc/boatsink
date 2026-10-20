# boatsink

A fun, dead-end rowboat for Second Life: no oars, nowhere to go. It floats on the flat water, sways softly, can
drift, can slowly sink with whoever sits in it, and seats two people (a driver on the rower's bench and a passenger
facing them), each with their own seated pose.

- Owner menu (right-click > Touch, or `/9 boat`): calibrate and save the waterline, nudge and save each seat,
  turn Drift and Sink on or off.
- Everything saved lives in the boat itself (Linkset Data), so it survives script resets and copies.

**Status:** under construction, nothing is tested in Second Life yet. See [`docs/ROADMAP.md`](docs/ROADMAP.md) for
the order of work and the in-world test list, and [`docs/SPEC.md`](docs/SPEC.md) for how it works.

| Path | Contents |
|---|---|
| `src/rowboat.lsl` | The one script (goes in the boat's root prim) |
| `anims/` | The two seated animations (`.anim`) and a preview picture |
| `tools/lslcheck.sh` | Compile check (LSL-PyOptimizer) and a memory estimate |
| `tools/make_anims.py` | Generates the animation files |
| `tools/sim/` | Python checks of the motion maths and the animations, run in CI |

History: the first version (one seat, sinks when sat on) was written in the `cinema` repository's `lab/` folder and
moved here.
