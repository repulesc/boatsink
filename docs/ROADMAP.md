# Roadmap

Order of work for the rowboat. `SPEC.md` has the details of each step.

## Done
- [x] Boat moved out of the `cinema` repository (it never belonged there). v1 (one seat, sinks when sat on, Align
      menu) is the starting point in `src/rowboat.lsl`.
- [x] Decisions: two seats found by name (`Seat2` child prim), animations generated as `.anim`, settings in Linkset
      Data, sink when anyone sits.

## 1. Script v2 (`src/rowboat.lsl`)
- [ ] Settings layer: read/write `lift`, `drift`, `sink`, `seat1`, `seat2` (Linkset Data), with defaults.
- [ ] Waterline menu: Up/Down 5 and 1 cm, Align, Save, Default. Fix the Align jump (`t0`).
- [ ] Two seats: `Seat2` lookup, `llLinkSitTarget`, sitter tracking, animation permission queue.
- [ ] Nudge menu per seat: live move, step toggle, Save, Reset, Done; boat holds still meanwhile.
- [ ] Drift and Sink toggles (drift eases in and out).
- [ ] Compiles with `tools/lslcheck.sh`, at least 15 KB free.

## 2. Animations (`tools/make_anims.py`, `anims/`)
- [ ] `.anim` writer, driver and passenger poses from named angles, forward-kinematics hand placement.
- [ ] `anims/rowboat_driver.anim`, `anims/rowboat_passenger.anim`, `anims/preview.png`.

## 3. Checks
- [ ] `tools/sim/boat_sim.py`, `tools/sim/anim_test.py`, CI workflow runs them with `tools/lslcheck.sh`.

## 4. In-world test (the owner; nothing above is tested in Second Life yet)
Set-up: remove the boat's other scripts; link a small invisible prim named `Seat2` (about 0.1 m cube, 100% transparent,
phantom) to the boat; upload the two `.anim` files, name them `rowboat_driver` and `rowboat_passenger`; drop them and
`rowboat.lsl` into the root prim; close the edit window.
- [ ] Waterline: Down/Up until the hull sits right, Save, reset the script (Edit > Scripts > Reset): same height.
- [ ] Driver seat: sit, nudge until it looks right, Save, stand up, sit again: same place. Feet look high.
- [ ] Passenger: a second person sits: they take the front seat, face the driver, nudge and Save work independently.
- [ ] Drift off: the boat holds its spot; on: it wanders slowly, no jump when toggled.
- [ ] Sink off: sitting does nothing; on: slow sink over about 90 s, comes back up after everyone stands.
- [ ] Align after moving the boat by hand: no leap or spin.
- [ ] Say what is off (pose, heights, anything that errors in chat) and it gets fixed.

## Later (not now)
- Pitch/roll nudge for the seats, a third seat, a stand-up animation, splash particles and creaking sounds, a "sink
  and spill the riders" ending, a save of the home position across resets.
