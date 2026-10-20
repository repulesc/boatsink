# Rowboat: spec

A novelty rowboat for Second Life. It has no oars and goes nowhere: it floats on the flat water, sways softly, can
drift, and can slowly sink with whoever sits in it. Two people can sit in it. One script, `src/rowboat.lsl`, plus
two animation files. This document is the source of truth; `ROADMAP.md` is the order of work.

## 1. What the owner and the guests see

- **Guests:** left-click anywhere on the boat to sit. The first person takes the **driver seat** (rower's bench), the
  second the **passenger seat** (forward, facing the driver). Each seat plays its own seated animation. Standing up
  works as usual. Guests never see a menu.
- **Owner:** right-click > **Touch**, or say **`/9 boat`**, for the boat menu (nobody else gets it).

## 2. Menus (owner only)

Dialogs time out after 60 s. Button labels are 24 characters or fewer. A dialog has at most 12 buttons.

**Main:** `Waterline`, `Driver seat`, `Passenger seat`, `Drift: ON|OFF` (shows the current state, press toggles and
saves), `Sink: ON|OFF` (same), `Close`.

**Waterline:** `Up 5`, `Up 1`, `Down 1`, `Down 5` (centimetres; the boat moves at once), `Align`, `Save`, `Default`,
`Back`. The text shows the current height of the root prim's centre above the water, in cm, and says whether it is
saved.
- `Align`: put the boat on the water level where it is now, level it, make this spot its home (section 5).
- `Save`: write the height to Linkset Data. `Default`: delete the saved value and go back to the computed default.

**Driver seat / Passenger seat (nudge menu):** `Bow`, `Stern`, `Left`, `Right`, `Up`, `Down`, `Turn L`, `Turn R`,
`Step: 5 cm`|`Step: 1 cm` (toggles coarse/fine; coarse = 5 cm and 5 degrees, fine = 1 cm and 1 degree), `Save`,
`Reset`, `Done`. That is exactly 12 buttons.
- Directions are in the **boat's** frame: Bow = toward the front (+X of the root prim), Left = +Y.
- Each press moves the seated avatar **at once** (real time) and updates the seat's sit target for the next sitter.
- `Save` writes the seat offset to Linkset Data. `Reset` restores the saved offset (or the default if none).
  `Done` leaves the menu.
- While a nudge menu is open the boat **holds still** (keyframed motion stopped), because Second Life does not let a
  script move a seated avatar while keyframed motion is running. `Done`, or the dialog timing out, restarts it.
- If nobody sits in that seat the menu still works (the offset applies to the next sitter) but says so in chat.

## 3. Saved settings (Linkset Data)

Stored on the root prim with `llLinksetDataWrite`; survives script resets, copies and re-rezzing. All values are
strings. Missing key (read returns `""`) = use the default.

| Key | Value | Default |
|---|---|---|
| `lift` | metres from the water surface up to the root prim's centre, `"%.3f"` | `DRAFT - hullLow` (computed at start) |
| `drift` | `"1"` or `"0"` | on |
| `sink` | `"1"` or `"0"` | on |
| `seat1` | `"x y z yawDeg"` (sit-target offset in the root prim's frame, yaw in degrees, 4 decimals) | `SEAT1_POS`, `SEAT1_YAW` |
| `seat2` | same | `SEAT2_POS`, `SEAT2_YAW` |

`lift` is stored (not the draft) so the saved height does not depend on how the bounding box happens to measure at
the moment the script starts (a seated avatar can change it). `hullLow` (the hull bottom below the root centre, from
`llGetBoundingBox`) is still measured at start, only to keep the hull off the sea floor and for the default.

Defaults to put at the top of the script (all tunable constants, the owner will nudge them anyway):
`DRAFT = 0.30`, `SEAT1_POS = <-0.25, 0.0, 0.20>`, `SEAT1_YAW = 0.0`, `SEAT2_POS = <0.85, 0.0, 0.20>`,
`SEAT2_YAW = 180.0` (the passenger faces the driver), drift/sink on.

## 4. Seats and animations

- Seat 1 = the root prim (`LINK_ROOT`). Seat 2 = a child prim **named `Seat2`**: a small invisible prim the owner
  links to the boat (found by name among links 2..`llGetObjectPrimCount(llGetKey())`; refreshed on `CHANGED_LINK`). No
  `Seat2` prim: the boat is a one-seater and the owner is told once, in chat, how to add it.
- Sit targets are set with `llLinkSitTarget(link, pos, rot)`. Second Life seats the next person on the lowest-numbered
  free sit target, so "first in = driver, second in = passenger" needs no extra code. Never pass `ZERO_VECTOR` as the
  offset (it removes the sit target).
- Occupants: `llAvatarOnLinkSitTarget(seatLink)`. Compare with the remembered sitter per seat in
  `changed(CHANGED_LINK)`.
- **Animations** are two files in the boat's inventory, named exactly `rowboat_driver` and `rowboat_passenger`
  (section 6). When a new sitter appears: request `PERMISSION_TRIGGER_ANIMATION` (granted without a prompt to a
  sitter), then in `run_time_permissions` `llStopAnimation("sit")` and `llStartAnimation(<that seat's animation>)`.
  Use `llGetPermissionsKey()` to know who was granted.
- **A script holds permission for only one avatar at a time.** Two people sitting close together must be handled
  with a small queue: request for one, handle its `run_time_permissions`, then request for the next. Skip an avatar
  that has left (`llGetAgentSize(k) == ZERO_VECTOR`) or no longer sits where it did. A 1 s timer clears a request
  that never answered after 5 s.
- Missing animation in the inventory: do not start anything (the default sit remains), warn the owner once at start.
- Standing up: the server stops the animations; do not try to stop them without a permission.
- The avatar's own link number (needed to move it live): scan `i` from `llGetObjectPrimCount(llGetKey()) + 1` to
  `llGetNumberOfPrims()` for `llGetLinkKey(i) == avatar`.
- **Live nudge**: read the avatar's current local position/rotation with `llGetLinkPrimitiveParams(i,
  [PRIM_POS_LOCAL, PRIM_ROT_LOCAL])`, apply the *delta* of the button, set it back with
  `llSetLinkPrimitiveParamsFast(i, [PRIM_POS_LOCAL, p, PRIM_ROT_LOCAL, r])`, and apply the same delta to the stored
  seat offset and to `llLinkSitTarget`. Working in deltas avoids the sit-target height quirk (the avatar is not
  placed exactly at the offset you give). Yaw nudges rotate about the boat's Z.

## 5. Motion (carried over from v1, with fixes)

The v1 script in `src/rowboat.lsl` (copied from the cinema lab) already does the keyframed motion; keep its idea:
non-physical `llSetKeyframedMotion`, planned in 6 s batches (ten 0.6 s keyframes) from the boat's real position, the
next batch started on `moving_end` (1 s timer as a backup). A keyframe's move is in region axes, its turn in the
boat's own axes (`r / was`). Soft sway for flat water: bob about 3.5 cm, roll 2 degrees, pitch 0.8 degrees, swells of
6 to 10 s, drift about 5 cm/s on a 700 s loop within `DRIFT_RADIUS` 6 m. Sinking over 90 s to 3 m, bow down and a
list, never closer than `BOTTOM_GAP` to the sea floor; coming back up over 30 s.

Changes from v1:
1. **Sink mode** (menu): when off, the boat never sinks (sitting does nothing to it). When on, it sinks as soon as
   **anyone** sits in either seat and rises when everyone has stood.
2. **Drift mode** (menu): when off, no horizontal wander (the bob and sway stay). Do not jump when toggling: keep a
   `driftAmt` that eases to 0 or 1 at about 1/30 per second and multiply the drift offset by it.
3. **Fix a jump in `Align`.** v1 moves `home` but then adds the wander offset of the absolute clock time, so the boat
   leaps by up to 6 m, and the bow swings by up to 25 degrees, in 0.6 s. Keep a start time `t0` (set at start and at
   `Align`) and feed every wave `t - t0`, with phase 0 in all of them, so the whole motion starts from the neutral pose
   at `t0`.
4. The hull floor check uses `hullLow`: `p.z >= llGround(...) + BOTTOM_GAP - hullLow`.
5. Height is `llWater(ZERO_VECTOR) + lift`, with `lift` from section 3.
6. `Align`: stop the motion, read the yaw, `home = llGetPos()`, set position `<x, y, water + lift>` and the rotation
   to the pure yaw with `llSetLinkPrimitiveParamsFast(LINK_THIS, [PRIM_POSITION, ..., PRIM_ROTATION, ...])`, set
   `t0 = llGetTime()`, restart the batches with zero sinking.
7. While a nudge menu is open (`nudge == TRUE`): no new batches (`moving_end`, the timer and `changed` must check it).
8. `CHANGED_OWNER` resets the script. Other scripts turning physics on: keep the v1 warning.

## 6. Animations (`anims/`)

Generated by `tools/make_anims.py` into Second Life's own `.anim` binary format (the uploader accepts `.anim` and
`.bvh`; `.anim` uses plain avatar-axis rotations, so there are no BVH axis conventions to guess). Format (little
endian): `U16 version=1`, `U16 sub_version=0`, `S32 base_priority`, `F32 duration`, `emote_name` (NUL-terminated),
`F32 loop_in`, `F32 loop_out`, `S32 loop`, `F32 ease_in`, `F32 ease_out`, `U32 hand_pose`, `U32 num_joints`; per
joint: name (NUL-terminated), `S32 priority`, `S32 num_rot_keys`, keys of (`U16 time`, `U16 x`, `U16 y`, `U16 z`) where
0..65535 maps to -1..+1 for the quaternion x, y, z (w is rebuilt and must be >= 0, so negate the quaternion if it is
not), `S32 num_pos_keys` (use 0), then `S32 num_constraints` (use 0). Upload limit 250,000 bytes.

Settings: priority 4 on every joint and as base priority, loop on, `loop_in = 0`, `loop_out = duration`, duration 1.0 s,
ease in/out 0.5 s, `hand_pose = 1` (relaxed). Two identical rotation keys (time 0 and 65535) per joint: a held pose.
No pelvis position keys (the sit target decides the height; the owner nudges).

Joints animated: `mTorso`, `mChest`, `mNeck`, `mHead`, `mShoulderLeft/Right`, `mElbowLeft/Right`,
`mWristLeft/Right`, `mHipLeft/Right`, `mKneeLeft/Right`, `mAnkleLeft/Right`.

Axes (avatar frame: X forward, Y left, Z up; every joint is at rest with identity rotation, legs down, arms out along
Y, which is the Second Life skeleton's rest pose). Derived with the right-hand rule: thigh flexion (leg swings
forward) is a **negative rotation about Y**; knee flexion (shin swings back) is **positive about Y**; spine leaning
forward is **positive about Y**; the arms need a shortest-arc rotation from the rest direction (left arm +Y, right arm
-Y) to the wanted direction. Compute the poses from named angle constants at the top of the generator, and place the
hands by a small search over the elbow angle with forward kinematics (approximate Second Life bone lengths in the
generator), not by hand-tuned magic numbers.

- **`rowboat_driver`** (rower on a small bench; feet relatively high because the seat is small): thighs flexed to about
  110 degrees (knees about 20 degrees above the hips), knees flexed about 110 degrees so the shins hang almost
  straight down, which puts the feet about 17 cm higher than an ordinary sitting pose; torso leaning forward about
  8 degrees, head level; arms relaxed with the hands resting on the knees.
- **`rowboat_passenger`** (sits in the bow, turned to face the driver by the sit rotation, not the animation): relaxed,
  thighs flexed about 90 degrees, knees about 100 degrees, torso leaning back about 8 degrees, head level, hands in the
  lap or on the thighs.

Ship a preview (`anims/preview.png`, side view, drawn with Pillow from the same forward kinematics) so the intended
poses can be looked at before uploading. These files are **untested in Second Life** until the owner uploads them
(Build > Upload > Animation, or File > Upload > Animation; a small fee applies), names them `rowboat_driver` and
`rowboat_passenger`, and drops them into the boat.

## 7. Checks (run in CI, no Second Life needed)

- `tools/lslcheck.sh`: compile check of `src/*.lsl` (LSL-PyOptimizer, which knows `llLinkSitTarget`,
  `llAvatarOnLinkSitTarget` and the `llLinksetData*` functions) plus a memory estimate (must show at least 15 KB free).
- `tools/sim/boat_sim.py`: pure-Python port of the motion maths: no jump at start or at `Align` (first keyframe within
  a few centimetres and 1 degree of rest), drift toggling stays continuous (speed below 0.3 m/s), the sink timeline
  (about 0.8 m after 30 s, 3 m after 90 s, never below the floor), rotation chaining (`r / was` then `* was` gives `r`
  back), and the Linkset Data string round trip for `seat1`/`seat2`/`lift`.
- `tools/sim/anim_test.py`: reads each `.anim` back with an independent parser written from section 6, checks the header,
  the joint list, that every quaternion has w >= 0 and unit length, then runs forward kinematics and checks the pose
  (driver knees above the hips and feet higher than an ordinary sit; passenger torso leaning back; hands near the
  knees or lap).
