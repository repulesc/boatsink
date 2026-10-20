# The rowboat's motion maths and saved-settings format (src/rowboat.lsl), ported to Python and run against a small
# model of keyframed motion. Constants are read from the script itself. Checks: where the hull sits against the water (the
# physical meaning of the saved height and of Up / Down), no jump at start, at Align or after a menu; a boat moved by hand
# stays where it is; the menu holds the boat still; drift on/off stays continuous; the sink timeline (and the sea-floor limit); rotation chaining; the Linkset
# Data text for lift / seat1 / seat2 and the sit-target maths for the Seat2 prim; the menu lists fit a dialog.
# This checks the maths, not Second Life: how the simulator really plays keyframes is assumed (linear moves, turns
# spread evenly), and the script has not been run in-world.
import math, os, random, re, struct
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
SRC = open(os.path.join(R, "src", "rowboat.lsl")).read()
ok = True
def check(c, msg):
    global ok
    if not c: ok = False; print("FAIL", msg)

# ---- constants from the script ----
def const(name):
    m = re.search(r"^(?:float|integer|string|vector)\s+" + name + r"\s*=\s*([^;]+);", SRC, re.M)
    if not m: raise SystemExit(f"constant {name} not found in rowboat.lsl")
    v = m.group(1).split("//")[0].strip()
    if v.startswith("<"): return tuple(float(x) for x in v.strip("<>").split(","))
    if v.startswith('"'): return v.strip('"')
    return float(v)
C = {n: const(n) for n in ("DRAFT", "HEAVE", "ROLL_DEG", "PITCH_DEG", "YAW_SWING_DEG", "DRIFT_RADIUS", "DRIFT_PERIOD",
                           "DRIFT_EASE", "SINK_TIME", "SINK_DEPTH", "SINK_PITCH", "SINK_ROLL", "RISE_TIME", "BOTTOM_GAP",
                           "SEAT1_POS", "SEAT1_YAW", "SEAT2_POS", "SEAT2_YAW", "FRAME", "FRAMES", "MENU_AGAIN", "MOVED")}
FRAME, FRAMES = C["FRAME"], int(C["FRAMES"])
TWO_PI, D2R = 2 * math.pi, math.pi / 180

# ---- LSL vectors and rotations: (w, x, y, z); LSL's a * b turns by a first, then b (so it is the Hamilton product b.a) ----
def ham(a, b):
    aw, ax, ay, az = a; bw, bx, by, bz = b
    return (aw*bw - ax*bx - ay*by - az*bz, aw*bx + ax*bw + ay*bz - az*by,
            aw*by - ax*bz + ay*bw + az*bx, aw*bz + ax*by - ay*bx + az*bw)
def rmul(a, b): return ham(b, a)
def rinv(a): return (a[0], -a[1], -a[2], -a[3])
def rdiv(a, b): return rmul(a, rinv(b))
def vrot(v, q):                                                   # LSL: v * q
    t = ham(ham(q, (0.0,) + tuple(v)), rinv(q))
    return t[1:]
def axis_rot(axis, ang): s = math.sin(ang / 2); return (math.cos(ang / 2), axis[0]*s, axis[1]*s, axis[2]*s)
def euler2rot(x, y, z): return rmul(rmul(axis_rot((1, 0, 0), x), axis_rot((0, 1, 0), y)), axis_rot((0, 0, 1), z))
def yaw_of(q):
    w, x, y, z = q
    return math.atan2(2 * (w*z + x*y), 1 - 2 * (y*y + z*z))
def angle(a, b):                                                  # degrees between two rotations
    d = rmul(a, rinv(b))
    return 2 * math.degrees(math.atan2(math.sqrt(d[1]**2 + d[2]**2 + d[3]**2), abs(d[0])))
def vadd(a, b): return tuple(p + q for p, q in zip(a, b))
def vsub(a, b): return tuple(p - q for p, q in zip(a, b))
def vlen(a): return math.sqrt(sum(p * p for p in a))
def vscale(a, k): return tuple(p * k for p in a)
def part(q, f):                                                   # the rotation f of the way from none to q
    w = max(-1.0, min(1.0, q[0])); a = 2 * math.acos(w); s = math.sqrt(max(0.0, 1 - w * w))
    if s < 1e-9: return (1.0, 0.0, 0.0, 0.0)
    return axis_rot((q[1] / s, q[2] / s, q[3] / s), a * f)

def wave(t, period): return math.sin(TWO_PI * t / period)
def clamp01(x): return max(0.0, min(1.0, x))
IDENT = (1.0, 0.0, 0.0, 0.0)

# ---- the boat: the script's functions, and a model of what the simulator does with the keyframes ----
class Boat:
    def __init__(s, water=20.0, ground=lambda p: 0.0, hull_low=-0.45, pos=(128.0, 128.0, None), yaw=0.5):
        s.water, s.ground, s.hullLow = water, ground, hull_low
        s.lift = -C["DRAFT"] - hull_low                           # the hull bottom is DRAFT under the water
        z = water + s.lift if pos[2] is None else pos[2]
        s.pos, s.rot = (pos[0], pos[1], z), euler2rot(0, 0, yaw)
        s.now = 0.0
        s.frames, s.fi, s.ft, s.base_pos, s.base_rot, s.ended = [], 0, 0.0, s.pos, s.rot, False
        s.seated = s.held = False
        s.driftOn = s.sinkOn = True
        s.driftAmt, s.driftT, s.batchStart, s.batchSunk, s.batchSeated, s.t0, s.heldAt = 1.0, 0.0, 0.0, 0.0, False, 0.0, 0.0
        s.home, s.homeYaw = s.pos, yaw
        s.moved = False                                           # the last nextBatch found the boat moved by hand
        s.first = None                                            # (move, turn angle) of the first keyframe of the last batch

    # -- the simulator --
    def set_keyframed(s, frames):
        s.frames, s.fi, s.ft, s.base_pos, s.base_rot, s.ended = frames, 0, 0.0, s.pos, s.rot, False
    def step(s, dt):
        s.now += dt
        while dt > 1e-12 and s.fi < len(s.frames):
            mv, turn, fdur = s.frames[s.fi]
            use = min(dt, fdur - s.ft)
            s.ft += use; dt -= use
            f = s.ft / fdur
            s.pos = vadd(s.base_pos, vscale(mv, f)); s.rot = rmul(part(turn, f), s.base_rot)
            if fdur - s.ft < 1e-9:
                s.base_pos, s.base_rot, s.fi, s.ft = s.pos, s.rot, s.fi + 1, 0.0
                if s.fi == len(s.frames): s.ended = True

    # -- the script --
    def sunkAfter(s, dt):
        if s.batchSeated: return clamp01(s.batchSunk + dt / C["SINK_TIME"])
        return clamp01(s.batchSunk - dt / C["RISE_TIME"])
    def driftAfter(s, dt):
        goal = float(s.driftOn); a = s.driftAmt - dt / C["DRIFT_EASE"]
        if s.driftAmt < goal: a = min(goal, s.driftAmt + dt / C["DRIFT_EASE"])
        elif a < goal: a = goal
        return a
    def pose(s, t, sk, da, start):
        e = sk * sk * (3 - 2 * sk); calm = 1 - 0.8 * e
        p = list(vadd(s.home, vscale((C["DRIFT_RADIUS"] * wave(t, C["DRIFT_PERIOD"]),
                                      C["DRIFT_RADIUS"] * wave(t, C["DRIFT_PERIOD"] * 1.37), 0.0), da)))
        heave = C["HEAVE"] * (0.6 * wave(t, 9.7) + 0.4 * wave(t, 6.3))
        p[2] = s.water + s.lift - e * C["SINK_DEPTH"] + calm * heave
        floor = s.ground(vadd(start, vsub(p, start))) + C["BOTTOM_GAP"] - s.hullLow
        if p[2] < floor: p[2] = floor
        roll = calm * C["ROLL_DEG"] * (0.7 * wave(t, 8.9) + 0.3 * wave(t, 5.7)) + e * C["SINK_ROLL"]
        pitch = calm * C["PITCH_DEG"] * (0.6 * wave(t, 7.9) + 0.4 * wave(t, 5.1)) + e * C["SINK_PITCH"]
        yaw = s.homeYaw + C["YAW_SWING_DEG"] * D2R * (0.8 * wave(t, 97.0) + 0.2 * wave(t, 41.0))
        return tuple(p), rmul(euler2rot(roll * D2R, pitch * D2R, 0.0), euler2rot(0, 0, yaw))
    def settle(s):
        t = s.now
        s.batchSunk = s.sunkAfter(t - s.batchStart)
        s.driftAmt = s.driftAfter(t - s.driftT)
        s.batchStart = s.driftT = t
    def adoptMove(s):
        t = s.now; pos = s.pos
        sk = s.sunkAfter(t - s.batchStart)
        want = s.pose(t - s.t0, sk, s.driftAfter(t - s.driftT), pos)[0]
        off = vsub(pos, want)
        if math.hypot(off[0], off[1]) < C["MOVED"] and abs(off[2]) < C["MOVED"]: return
        s.moved = True
        s.homeYaw, s.home, s.t0 = yaw_of(s.rot), pos, t
        if sk < 0.001:
            if abs(off[2]) >= C["MOVED"]: s.lift += off[2]
        else:                                                     # sinking: its depth says how far down it really is
            e = max(0.0, min(1.0, (s.water + s.lift - pos[2]) / C["SINK_DEPTH"]))
            s.batchSunk = 0.5 - math.sin(math.asin(1.0 - 2.0 * e) / 3.0)
            s.batchStart = t
    def nextBatch(s):
        if s.held: return
        s.adoptMove()
        s.settle()
        s.batchSeated = s.seated and s.sinkOn
        start = s.pos; at = start; was = s.rot
        t = s.batchStart - s.t0
        frames = []
        for k in range(1, FRAMES + 1):
            p, r = s.pose(t + k * FRAME, s.sunkAfter(k * FRAME), s.driftAfter(k * FRAME), start)
            frames.append((vsub(p, at), rdiv(r, was), FRAME))
            at, was = p, r
        s.first = (vlen(frames[0][0]), angle(frames[0][1], IDENT))
        s.planned = (at, was)
        s.set_keyframed(frames)
    def replan(s):
        if s.held: return
        s.set_keyframed([]); s.nextBatch()
    def holdStill(s):
        if s.held: return
        s.settle(); s.heldAt = s.batchStart; s.held = True; s.set_keyframed([])
    def endHold(s):
        t = s.now
        s.t0 += t - s.heldAt; s.batchStart = s.driftT = t; s.held = False; s.nextBatch()
    def raise_(s, d):                                             # Up / Down while held: moved by hand, lift changes with it
        s.lift += d; s.pos = vadd(s.pos, (0.0, 0.0, d))
    def place(s):
        s.homeYaw = yaw_of(s.rot)
        s.home = (s.pos[0], s.pos[1], s.water + s.lift)
        s.pos, s.rot = s.home, euler2rot(0, 0, s.homeYaw)
    def align(s):
        s.set_keyframed([])
        s.place()
        s.t0 = s.batchStart = s.driftT = s.now
        s.batchSunk = 0.0
        if s.held: s.heldAt = s.t0
        s.nextBatch()
    def start(s):                                                 # state_entry
        s.place()
        s.t0 = s.batchStart = s.driftT = s.now = 0.0
        s.driftAmt = float(s.driftOn); s.batchSunk = 0.0
        s.batchSeated = s.seated and s.sinkOn
        s.nextBatch()

def run(b, until, events=(), dt=0.05):
    """the script's events: moving_end and the 1 s timer backup call nextBatch; events = [(time, fn(boat))]"""
    ev = sorted(events, key=lambda e: e[0]); rec = [(b.now, b.pos, b.rot)]
    while b.now < until - 1e-9:
        while ev and ev[0][0] <= b.now + 1e-9: ev.pop(0)[1](b)
        b.step(dt)
        if b.ended: b.ended = False; b.nextBatch()
        elif not b.held and b.now > b.batchStart + FRAMES * FRAME + 1.0: b.nextBatch()
        rec.append((b.now, b.pos, b.rot))
    return rec

def speeds(rec):
    v = w = 0.0
    for (t1, p1, r1), (t2, p2, r2) in zip(rec, rec[1:]):
        v = max(v, vlen(vsub(p2, p1)) / (t2 - t1)); w = max(w, angle(r1, r2) / (t2 - t1))
    return v, w

# ---- 0. the script still has the lines this port stands for ----
for needle in ("float t = batchStart - t0;", "t0 = llGetTime();", "t0 += t - heldAt;", "frames += [to - at, r / was, FRAME];",
               "batchSeated = seated && sinkOn;", "float floor = llGround(p - start) + BOTTOM_GAP - hullLow;",
               "p.z = llWater(ZERO_VECTOR) + lift - e * SINK_DEPTH + calm * heave;",
               "pose(t + k * FRAME, sunkAfter(k * FRAME), driftAfter(k * FRAME), start)",
               "home.z = llWater(ZERO_VECTOR) + lift;", "lift = -DRAFT - hullLow;", "raise(-DRAFT - hullLow - lift);", "llLinkSitTarget(link, p, r);",
               'llLinksetDataWrite("lift", fix(lift, 3))', 'llLinksetDataWrite("drift"', 'llLinksetDataWrite("sink"',
               'llLinksetDataRead("seat" + (string)(s + 1))', 'llLinksetDataWrite("seat" + (string)(s + 1)'):
    check(needle in SRC, f"script: missing {needle!r}")
check(re.search(r"nextBatch\(\)\s*\{\s*if \(held\) return;\s*adoptMove\(\);\s*settle\(\);", SRC) is not None, "script: nextBatch does not stop while held, or does not adopt a move first")
check(re.search(r"replan\(\)\s*\{\s*if \(held\) return;", SRC) is not None, "script: replan does not stop while a menu holds the boat")
check(re.search(r"wave\([^()]*,[^()]*,[^()]*\)", SRC) is None, "script: a wave still has a phase")
check(re.search(r"llSitTarget\(", SRC) is None, "script: llSitTarget (one seat only) is still used")
check("DRAFT - hullLow" not in SRC.replace("-DRAFT - hullLow", ""), "script: the old height formula (hull bottom ABOVE the water) is back")

# ---- 1. no jump at start: the first keyframe is within a few centimetres and about a degree of rest ----
b = Boat(); b.start()
mv, ang = b.first
print(f"start: first keyframe moves {mv*100:.1f} cm and turns {ang:.2f} deg")
check(mv < 0.05, f"start: first keyframe moves {mv*100:.1f} cm")
check(ang < 2.0, f"start: first keyframe turns {ang:.2f} deg")
rec = run(b, 120)
v, w = speeds(rec)
check(v < 0.3 and w < 5.0, f"start: speed {v:.2f} m/s, turn {w:.1f} deg/s")
check(abs(b.planned[0][2] - (b.water + b.lift)) < 0.05, "start: the boat does not ride at water level plus lift")

# ---- 2. Align after the boat has been moved by hand (and the v1 behaviour it replaces) ----
b = Boat(); b.start(); run(b, 300)
b.pos, b.rot = (140.0, 96.0, 24.7), euler2rot(0.3, -0.2, 1.9)       # dragged and turned by hand, mid-run
b.set_keyframed([]); yaw = yaw_of(b.rot); before = b.pos
b.align()
mv, ang = b.first
print(f"align: first keyframe moves {mv*100:.1f} cm and turns {ang:.2f} deg")
check(abs(b.pos[0] - before[0]) < 1e-9 and abs(b.pos[2] - (b.water + b.lift)) < 1e-9, "align: not on the water level at the same x, y")
check(angle(b.rot, euler2rot(0, 0, yaw)) < 1e-6, "align: not levelled to the same yaw")
check(mv < 0.05 and ang < 2.0, f"align: first keyframe moves {mv*100:.1f} cm, turns {ang:.2f} deg")
rec = run(b, b.now + 120)
v, w = speeds(rec)
check(v < 0.3 and w < 5.0, f"align: speed {v:.2f} m/s, turn {w:.1f} deg/s after the jump fix")
# v1 for comparison: absolute clock and phases, home moved at Align: it must jump, or this test proves nothing
def v1_first(tnow):
    t = tnow + FRAME                                                  # v1: the absolute clock, and phases in the waves
    off = (C["DRIFT_RADIUS"] * wave(t, C["DRIFT_PERIOD"]), C["DRIFT_RADIUS"] * wave(t, C["DRIFT_PERIOD"] * 1.37))
    swing = C["YAW_SWING_DEG"] * (0.8 * wave(t, 97.0) + 0.2 * math.sin(TWO_PI * t / 41.0 + 1.0))
    return vlen(off), abs(swing)
jump, swing = v1_first(300.0)
check(jump > 1.0 and swing > 5.0, f"v1 comparison: expected a leap of over 1 m and a swing of over 5 deg, got {jump:.2f} m, {swing:.1f} deg")
print(f"align: v1 would have leapt {jump:.1f} m and swung {swing:.0f} deg in 0.6 s; now {mv*100:.1f} cm")

# ---- 3. drift toggling stays continuous, and off really holds the spot ----
b = Boat(); b.start()
def setdrift(on):
    def f(bt): bt.settle(); bt.driftOn = on; bt.replan()
    return f
rec = run(b, 700, [(100.0, setdrift(False)), (160.3, setdrift(True)), (161.7, setdrift(False)), (250.0, setdrift(True)),
                   (251.0, setdrift(False)), (251.4, setdrift(True))])
v, w = speeds(rec)
print(f"drift: top speed {v:.3f} m/s over 700 s with six toggles")
check(v < 0.3, f"drift toggling: speed {v:.2f} m/s")
b = Boat(); b.start()
rec = run(b, 400, [(50.0, setdrift(False))])
late = [p for t, p, r in rec if t > 50 + C["DRIFT_EASE"] + 12]
spread = max(vlen(vsub((p[0], p[1], 0), (b.home[0], b.home[1], 0))) for p in late)
check(spread < 0.01, f"drift off: the boat is still {spread:.2f} m from home after the ease-out")
b = Boat(); b.driftOn = False; b.start()
rec = run(b, 400, [(100.0, setdrift(True))])
reach = max(vlen(vsub((p[0], p[1], 0), (b.home[0], b.home[1], 0))) for t, p, r in rec)
check(reach > 1.5, f"drift on: the boat only got {reach:.2f} m from home")

# ---- 4. the sink timeline ----
def drop(b, rec, t): return b.water + b.lift - min(rec, key=lambda r: abs(r[0] - t))[1][2]
b = Boat(); b.seated = True; b.start(); rec = run(b, 130)
d30, d90, d120 = drop(b, rec, 30), drop(b, rec, 90), drop(b, rec, 120)
print(f"sink: down {d30:.2f} m after 30 s, {d90:.2f} m after 90 s")
check(abs(d30 - 0.8) < 0.1, f"sink: {d30:.2f} m after 30 s (about 0.8)")
check(abs(d90 - C["SINK_DEPTH"]) < 0.05 and abs(d120 - C["SINK_DEPTH"]) < 0.05, f"sink: {d90:.2f} / {d120:.2f} m at 90 / 120 s (3.0)")
check(angle(b.rot, euler2rot(0, 0, yaw_of(b.rot))) > 5.0, "sink: no bow-down / list at the bottom")
# stands after 100 s: back up over 30 s
b = Boat(); b.seated = True; b.start()
def stand(bt): bt.seated = False; bt.replan()
rec = run(b, 160, [(100.0, stand)])
check(abs(drop(b, rec, 100 + C["RISE_TIME"] + 1)) < 0.05, f"rise: still {drop(b, rec, 131):.2f} m down 31 s after standing")
check(abs(drop(b, rec, 115) - C["SINK_DEPTH"] / 2) < 0.2, f"rise: {drop(b, rec, 115):.2f} m down halfway up")
# stands at 50 s (partly sunk), then sits again at 60 s: continuous
b = Boat(); b.seated = True; b.start()
def sit(bt): bt.seated = True; bt.replan()
rec = run(b, 200, [(50.0, stand), (60.0, sit)])
v, w = speeds(rec)
check(v < 0.5, f"sit/stand/sit: speed {v:.2f} m/s")
# Sink off: sitting does nothing; switched off while going down: comes back up
b = Boat(); b.sinkOn = False; b.seated = True; b.start(); rec = run(b, 120)
check(max(abs(drop(b, rec, t)) for t in range(0, 120, 5)) < 0.1, "sink off: the boat moved down")
b = Boat(); b.seated = True; b.start()
def sinkoff(bt): bt.settle(); bt.sinkOn = False; bt.replan()
rec = run(b, 200, [(45.0, sinkoff)])
check(abs(drop(b, rec, 45 + 31)) < 0.05 and max(drop(b, rec, t) for t in range(0, 200, 2)) < 2.0, "sink switched off midway: did not rise")
# the sea floor: shallow water, and a sloping bottom
for name, g in (("flat", lambda p: 20.0 - 2.0), ("slope", lambda p: 20.0 - 1.0 - 0.15 * (p[0] - 128.0))):
    b = Boat(ground=g); b.seated = True; b.start(); rec = run(b, 200)
    low = min(p[2] - (g(p) + C["BOTTOM_GAP"] - b.hullLow) for t, p, r in rec)
    check(low > -0.02, f"floor ({name}): the hull went {-low:.2f} m under the limit")
    check(min(p[2] for t, p, r in rec) > 20.0 - 3.0 - 1e-6, f"floor ({name}): below the sink depth")

# ---- 5. rotation chaining: r / was, then * was, gives r back; the engine ends where the plan ends ----
rng = random.Random(3)
for _ in range(200):
    q = [rng.uniform(-1, 1) for _ in range(4)]; n = math.sqrt(sum(c * c for c in q)); r = tuple(c / n for c in q)
    q = [rng.uniform(-1, 1) for _ in range(4)]; n = math.sqrt(sum(c * c for c in q)); was = tuple(c / n for c in q)
    back = rmul(rdiv(r, was), was)
    check(angle(back, r) < 1e-6, "rotation chaining: (r / was) * was is not r")
b = Boat(); b.seated = True; b.start()
for _ in range(120): b.step(0.05)                                   # one whole batch, no new one planned
check(vlen(vsub(b.pos, b.planned[0])) < 1e-6 and angle(b.rot, b.planned[1]) < 1e-4, "a batch does not end where it was planned to end")

# ---- 6. a menu holds the boat still, then it carries on from where it stopped, without a jump ----
b = Boat(); b.seated = True; b.start(); run(b, 50.0)
b.holdStill(); sunk_at_hold = b.batchSunk
held = run(b, 170.0)
check(max(vlen(vsub(p, held[0][1])) for t, p, r in held) < 1e-9, "hold: the boat moved while held")
b.endHold(); mv, ang = b.first
print(f"nudge: after a 120 s hold the first keyframe moves {mv*100:.1f} cm and turns {ang:.2f} deg")
check(mv < 0.12 and ang < 3.0, f"nudge: first keyframe after the hold moves {mv*100:.1f} cm, turns {ang:.2f} deg")
check(abs(b.batchSunk - sunk_at_hold) < 1e-9, "nudge: the hold counted as sinking time")
v, w = speeds(run(b, 230.0))
check(v < 0.3 and w < 5.0, f"nudge: speed {v:.2f} m/s, {w:.1f} deg/s after the hold")
b = Boat(); b.start(); run(b, 30); b.holdStill(); run(b, 90); b.endHold()
check(b.first[0] < 0.1, "nudge: the wander jumped after the hold")

# ---- 7. Linkset Data text ----
def f32(x): return struct.unpack("<f", struct.pack("<f", x))[0]
def lsl_round(x): return int(math.floor(x + 0.5))
def fix(x, d):                                                          # the script's fix(): whole numbers, no float text
    m = 10000 if d == 4 else 1000
    n = lsl_round(f32(x * m)); sign = ""
    if n < 0: sign, n = "-", -n
    return sign + str(n // m) + "." + str(n % m).rjust(d, "0")
def seat_text(pos, yaw): return " ".join([fix(pos[0], 4), fix(pos[1], 4), fix(pos[2], 4), fix(yaw, 4)])
def seat_read(txt, default):
    p = txt.split()
    return (tuple(f32(float(x)) for x in p[:3]), f32(float(p[3]))) if len(p) == 4 else default
for nm, pos, yaw in (("seat1", C["SEAT1_POS"], C["SEAT1_YAW"]), ("seat2", C["SEAT2_POS"], C["SEAT2_YAW"])):
    t = seat_text(pos, yaw)
    check(t == "%.4f %.4f %.4f %.4f" % (*pos, yaw), f"{nm}: default text {t!r}")
    back = seat_read(t, None)
    check(back is not None and max(abs(a - b2) for a, b2 in zip(back[0] + (back[1],), pos + (yaw,))) < 1e-5, f"{nm}: round trip {t!r}")
check(seat_read("", ("d", 1)) == ("d", 1) and seat_read("1 2 3", ("d", 1)) == ("d", 1), "seat: a missing or bad value must give the default")
for _ in range(500):
    pos = tuple(round(rng.uniform(-3, 3), rng.choice([2, 3, 5])) for _ in range(3)); yaw = rng.uniform(-180, 180)
    t = seat_text(pos, yaw); back = seat_read(t, None)
    check(re.fullmatch(r"-?\d+\.\d{4} -?\d+\.\d{4} -?\d+\.\d{4} -?\d+\.\d{4}", t) is not None, f"seat text format {t!r}")
    check(max(abs(a - b2) for a, b2 in zip(back[0] + (back[1],), pos + (yaw,))) < 6e-5, f"seat round trip {pos} {yaw} -> {t!r}")
    lift = rng.uniform(-0.5, 1.5); lt = fix(lift, 3)
    check(re.fullmatch(r"-?\d+\.\d{3}", lt) is not None and abs(float(lt) - lift) < 6e-4, f"lift text {lt!r} for {lift}")
check(fix(0.75, 3) == "0.750" and fix(0.3, 3) == "0.300" and fix(-0.05, 3) == "-0.050", "lift text for plain values")
lift0 = 0.6
for step in (0.05, 0.01, -0.01, -0.05, 0.05):                          # Up/Down presses, then Save and read back
    lift0 += step
check(abs(float(fix(lift0, 3)) - round(lift0, 3)) < 1e-9, "lift after Up/Down presses")
def wrap(y): return y - 360.0 if y > 180.0 else (y + 360.0 if y <= -180.0 else y)
check(wrap(190.0) == -170.0 and wrap(180.0) == 180.0 and wrap(-180.0) == 180.0 and wrap(-190.0) == 170.0, "seat yaw wrap")

# ---- 8. the nudge buttons and the Seat2 sit-target maths ----
names = re.search(r'llListFindList\(\[("Bow".*?)\], \[msg\]\)', SRC).group(1)
names = [x.strip().strip('"') for x in names.split(",")]
vecs = re.search(r"llList2Vector\(\[(<1\.0, 0\.0, 0\.0>.*?)\], k\)", SRC, re.S).group(1)
vecs = [tuple(float(c) for c in m.split(",")) for m in re.findall(r"<([^>]+)>", vecs)]
want = {"Bow": (1, 0, 0), "Stern": (-1, 0, 0), "Left": (0, 1, 0), "Right": (0, -1, 0), "Up": (0, 0, 1), "Down": (0, 0, -1)}
check(re.search(r"<0\.0, 0\.0, -1\.0>, ZERO_VECTOR, ZERO_VECTOR\], k\)", SRC) is not None and len(vecs) == 6, "nudge: vector list")
vecs += [(0.0, 0.0, 0.0)] * 2
check(names == ["Bow", "Stern", "Left", "Right", "Up", "Down", "Turn L", "Turn R"], f"nudge button order {names}")
for n, v in want.items(): check(vecs[names.index(n)] == tuple(map(float, v)), f"nudge: {n} is not {v} in the boat's frame")
check(re.search(r"if \(k == 6\) yaw = st;\s*if \(k == 7\) yaw = -st;", SRC) is not None, "nudge: Turn L / Turn R signs")
pos, yaw = C["SEAT1_POS"], C["SEAT1_YAW"]
for n, fine in (("Bow", False), ("Left", True), ("Up", False), ("Turn L", False), ("Turn R", True), ("Down", True), ("Stern", False)):
    st = 1.0 if fine else 5.0
    k = names.index(n); dp = vscale(vecs[k], st * 0.01)
    pos = vadd(pos, dp); yaw = wrap(yaw + (st if k == 6 else -st if k == 7 else 0.0))
saved = seat_read(seat_text(pos, yaw), None)
check(abs(saved[0][0] - (C["SEAT1_POS"][0] + 0.05 - 0.05)) < 1e-4 and abs(saved[0][1] - 0.01) < 1e-4 and abs(saved[0][2] - (C["SEAT1_POS"][2] + 0.05 - 0.01)) < 1e-4
      and abs(saved[1] - (5.0 - 1.0)) < 1e-4, f"nudge sequence saved as {saved}")
# Seat2's own frame: the offset is given in the root prim's frame, the sit target in the child's: undo the child's place
for _ in range(100):
    cp = tuple(rng.uniform(-1, 1) for _ in range(3))
    cr = euler2rot(rng.uniform(-3, 3), rng.uniform(-3, 3), rng.uniform(-3, 3))
    v = tuple(rng.uniform(-1, 1) for _ in range(3)); rr = euler2rot(0, 0, rng.uniform(-3, 3))
    vc = vrot(vsub(v, cp), rinv(cr)); rc = rdiv(rr, cr)                  # (p - cp) / cr and r / cr, as in applySeat
    check(vlen(vsub(vadd(vrot(vc, cr), cp), v)) < 1e-9, "Seat2: the sit-target offset does not map back to the root frame")
    check(angle(rmul(rc, cr), rr) < 1e-6, "Seat2: the sit-target rotation does not map back to the root frame")
check("(p - llList2Vector(d, 0)) / cr" in SRC and "r = r / cr;" in SRC, "script: applySeat no longer does the Seat2 conversion")

# ---- 9. the dialogs fit: at most 12 buttons, labels of 24 characters or fewer, text under 512 characters ----
dialogs = []
for m in re.finditer(r"llDialog\(", SRC):
    i = m.end(); depth = 1; j = i
    while depth:
        ch = SRC[j]
        if ch == '"':
            j += 1
            while SRC[j] != '"': j += 2 if SRC[j] == "\\" else 1
        elif ch in "([": depth += 1
        elif ch in ")]": depth -= 1
        j += 1
    call = SRC[i:j - 1]
    lm = re.search(r"\[((?:[^\[\]])*)\],\s*menuChan\s*$", call.strip(), re.S)
    items = [x.strip() for x in lm.group(1).split(",")]
    check(1 <= len(items) <= 12, f"dialog at line {SRC[:m.start()].count(chr(10)) + 1}: {len(items)} buttons")
    dialogs.append(items)
    for it in items:
        lit = re.findall(r'"((?:[^"\\]|\\.)*)"', it)
        check(len(lit[0]) + (3 if "+" in it else 0) <= 24, f"button label too long: {it}")
    lits = re.findall(r'"((?:[^"\\]|\\.)*)"', call[:lm.start()])
    total = sum(len(x) for x in lits) + 60                              # plus the numbers and the saved state
    check(total < 512, f"dialog text may reach {total} characters")

# ---- 10. the saved height means what it says: the hull bottom is DRAFT under the water, and Up raises the boat ----
for hl in (-0.45, -0.2, -0.8):
    b = Boat(hull_low=hl, pos=(128.0, 128.0, 20.0 + 3.0)); b.start()          # placed 3 m too high: start puts it on the waterline
    check(abs((b.pos[2] + hl) - (b.water - C["DRAFT"])) < 1e-9, f"waterline: hull bottom {b.pos[2] + hl - b.water:+.3f} m from the water, not -{C['DRAFT']}")
    check(abs(b.pos[2] - (b.water + b.lift)) < 1e-9 and angle(b.rot, euler2rot(0, 0, yaw_of(b.rot))) < 1e-6, "waterline: start did not put the boat on the water level, level")
def menu_delta(label):                                                  # the script's Up / Down buttons
    k = ["Up 5", "Up 1", "Down 1", "Down 5"].index(label)
    d = 0.05
    if k in (1, 2): d = 0.01
    if k >= 2: d = -d
    return d
check(re.search(r'llListFindList\(\["Up 5", "Up 1", "Down 1", "Down 5"\], \[msg\]\)', SRC) is not None, "script: the Up / Down button list changed")
check(re.search(r"float d = 0\.05;\s*if \(k == 1 \|\| k == 2\) d = 0\.01;\s*if \(k >= 2\) d = -d;\s*raise\(d\);", SRC) is not None, "script: Up / Down steps changed")
for label, want in (("Up 5", 0.05), ("Up 1", 0.01), ("Down 1", -0.01), ("Down 5", -0.05)):
    b = Boat(); b.start(); b.holdStill(); z0, l0 = b.pos[2], b.lift
    b.raise_(menu_delta(label))
    check(abs((b.pos[2] - z0) - want) < 1e-12 and abs((b.lift - l0) - want) < 1e-12, f"waterline: {label} moved the boat {b.pos[2] - z0:+.3f} m, wanted {want:+.2f}")
    b.endHold(); run(b, b.now + 30)
    check(abs(b.pos[2] - (b.water + b.lift)) < 0.05, f"waterline: after {label} and Finish the boat is not at water + lift")
# Default: back to the computed height by moving the boat the difference
b = Boat(); b.start(); b.holdStill(); b.raise_(0.2); b.raise_(-C["DRAFT"] - b.hullLow - b.lift)
check(abs(b.lift - (-C["DRAFT"] - b.hullLow)) < 1e-12, "waterline: Default does not go back to the computed height")

# ---- 11. a boat moved by hand stays where it is (it used to glide back to its old home) ----
def far(a, c): return math.hypot(a[0] - c[0], a[1] - c[1])
b = Boat(); b.start(); run(b, 100)
old_home = b.home; new = vadd(b.pos, (20.0, -15.0, 0.0))
b.pos = new; b.set_keyframed([])                                          # dragged away; the editor holds the motion paused
rec = run(b, 135)
check(b.moved, "moved by hand: the script did not notice the boat had been moved")
check(b.first[0] < 0.12, f"moved by hand: the first keyframe after the move is {b.first[0]*100:.1f} cm (it must not glide back)")
check(max(far(p, new) for t, p, r in rec if t > 101) < C["DRIFT_RADIUS"] * 2 + 1.0 and min(far(p, old_home) for t, p, r in rec if t > 101) > 15.0,
      "moved by hand: the boat went back towards its old home")
check(abs(b.home[0] - new[0]) < 1e-9 and abs(b.home[1] - new[1]) < 1e-9, "moved by hand: the new spot is not home")
v, w = speeds(run(b, 200)); check(v < 0.3 and w < 5.0, f"moved by hand: speed {v:.2f} m/s, {w:.1f} deg/s afterwards")
# held in the editor for a long while without being moved: no leap either
b = Boat(); b.start(); run(b, 100); b.pos = b.pos; b.set_keyframed([]); run(b, 160)
check(b.first[0] < 0.12, f"paused 60 s: the first keyframe afterwards moves {b.first[0]*100:.1f} cm")
# moved up by hand while afloat: the new height is the waterline
b = Boat(); b.start(); run(b, 100); lift0 = b.lift
b.pos = vadd(b.pos, (0.0, 0.0, 1.0)); b.set_keyframed([]); rec = run(b, 170)
check(abs(b.lift - (lift0 + 1.0)) < 0.06, f"raised by hand: lift {b.lift - lift0:+.2f} m, wanted +1.00")
check(all(abs(p[2] - (b.water + b.lift)) < 0.06 for t, p, r in rec if t > 108), "raised by hand: the boat went back down")
# a small difference is not a move (nothing to adopt in normal running)
b = Boat(); b.start(); rec = run(b, 400); check(not b.moved, "normal running was taken for a move by hand")
for seated in (False, True):
    b = Boat(); b.seated = seated; b.start()
    def toggles(bt): bt.settle(); bt.driftOn = not bt.driftOn; bt.replan()
    run(b, 600, [(100.0, toggles), (160.0, toggles), (200.0, lambda bt: (setattr(bt, "seated", not bt.seated), bt.replan())),
                 (330.0, lambda bt: (setattr(bt, "seated", not bt.seated), bt.replan()))])
    check(not b.moved, f"normal running with toggles and sitting (seated={seated}) was taken for a move by hand")
# sinking, paused while selected for 20 s: the depth it really has becomes its depth; the height setting is not touched
b = Boat(); b.seated = True; b.start(); run(b, 60); lift0, z0 = b.lift, b.pos[2]
b.set_keyframed([]); rec = run(b, 82)
check(abs(b.lift - lift0) < 1e-12, "sinking, paused: the height setting was changed")
check(b.first[0] < 0.15, f"sinking, paused 20 s: the first keyframe afterwards moves {b.first[0]*100:.1f} cm")
rec = run(b, 200); check(min(p[2] for t, p, r in rec) > b.water - C["SINK_DEPTH"] - 0.2 and abs(rec[-1][1][2] - (b.water + b.lift - C["SINK_DEPTH"])) < 0.2,
                         "sinking, paused: it did not carry on down to the full depth")

# ---- 12. the menu holds the boat; moving it meanwhile, then Finish, leaves it where it was put ----
b = Boat(); b.seated = True; b.start(); run(b, 40)
b.holdStill(); frozen = b.pos; sunk_then = b.batchSunk
rec = run(b, 100)
check(all(p == frozen for t, p, r in rec), "menu: the boat moved while the menu was open")
b.pos = vadd(b.pos, (7.0, 3.0, 0.0)); new = b.pos                         # dragged while the menu is open
b.raise_(0.05); b.raise_(0.05)
rec = run(b, 400)
check(b.batchSunk == sunk_then, "menu: the hold counted as sinking time")
b.endHold(); mv = b.first[0]
check(mv < 0.15, f"menu Finish: the first keyframe moves {mv*100:.1f} cm")
rec = run(b, b.now + 120)
check(max(far(p, new) for t, p, r in rec) < C["DRIFT_RADIUS"] * 2 + 1.0, "menu Finish: the boat did not stay where it was put")
v, w = speeds(rec); check(v < 0.5 and w < 5.0, f"menu Finish: speed {v:.2f} m/s, {w:.1f} deg/s")
# Drift and Sink switched in the menu (held): they take effect at Finish, without a jump
b = Boat(); b.start(); run(b, 50); b.holdStill(); b.driftOn = False; b.sinkOn = False; run(b, 80); b.endHold()
check(b.first[0] < 0.12, "menu: switching Drift off in the menu made the boat jump at Finish")
rec = run(b, b.now + 120); check(max(far(p, b.home) for t, p, r in rec if t > b.now - 60) < 0.05, "menu: Drift off, but the boat kept wandering")

# ---- 13. the menu in the script: opens by itself, stays open until Finish or Close, holds the boat ----
check(re.search(r"llSetTimerEvent\(1\.0\);\s*if \(llGetAgentSize\(llGetOwner\(\)\) != ZERO_VECTOR\) openMenu\(\);", SRC) is not None, "script: the menu does not open by itself at start")
check(re.search(r"openMenu\(\)\s*\{\s*if \(menu == 0\) menu = 1;\s*holdStill\(\);\s*showMenu\(\);\s*\}", SRC) is not None, "script: openMenu does not hold the boat")
check(SRC.count("openMenu();") >= 3, "script: touch and /9 boat do not open the menu")
check("menuUntil" not in SRC and "t > menuNext) showMenu();" in SRC and "== ZERO_VECTOR) closeMenu();" in SRC, "script: the menu still times out (or is not sent again, or not closed when the owner leaves)")
check(len(re.findall(r'"Finish"', SRC)) >= 3 and '"Done"' not in SRC, "script: Finish is missing from the Waterline or seat menus")
check('"Close"' in SRC and re.search(r'msg == "Close"\)\s*\{\s*closeMenu\(\);\s*return;', SRC) is not None, "script: Close does not end the menu")
check(len(re.findall(r'msg == "Finish"\)\s*\{\s*closeMenu\(\);\s*return;', SRC)) == 2, "script: Finish does not end the menu in both submenus")
check(re.search(r"closeMenu\(\)\s*\{[^}]*if \(held\) endHold\(\);", SRC, re.S) is not None, "script: closing the menu does not let the boat go")
check(C["MENU_AGAIN"] >= 60.0, "script: the dialog is sent again too often")
# after every button the dialog comes back (nothing in the three menu handlers returns without it, except Finish / Close)
for fn in ("mainMenu", "waterMenu", "nudgeMenu"):
    body = re.search(fn + r"\(string msg\)\s*\{(.*?)\n\}\n", SRC, re.S).group(1)
    check(body.rstrip().endswith("showMenu();"), f"script: {fn} does not show the menu again after a button")
    check(body.count("return;") == body.count("closeMenu();\n        return;"), f"script: {fn} returns without the menu being closed")

check(len(dialogs) == 3, f"expected 3 dialogs (main, Waterline, seat), found {len(dialogs)}")
if len(dialogs) == 3:
    check(any(i == '"Close"' for i in dialogs[0]), "main menu has no Close button")
    check(any(i == '"Finish"' for i in dialogs[1]), "Waterline menu has no Finish button")
    check(any(i == '"Finish"' for i in dialogs[2]), "seat menu has no Finish button")
    check(all(len(set(d)) == len(d) for d in dialogs), "a dialog has two buttons with the same label")

print("boat checks: ALL PASS" if ok else "boat checks: FAILED")
raise SystemExit(0 if ok else 1)
