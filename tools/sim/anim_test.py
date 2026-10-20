# The rowboat's two .anim files: read them back with a parser written from SPEC section 6 (not the generator's code),
# check the header, the joint list and the quaternions, then run forward kinematics on the decoded joints and check the
# pose (driver: knees above the hips, feet higher than an ordinary sit, torso forward; passenger: torso back, thighs
# level; both: head level, hands near the knees or in the lap). Also checks the files equal the generator's output.
import math, os, struct, subprocess, sys
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
ok = True
def check(c, msg):
    global ok
    if not c: ok = False; print("FAIL", msg)

JOINTS = ["mTorso", "mChest", "mNeck", "mHead", "mShoulderLeft", "mShoulderRight", "mElbowLeft", "mElbowRight",
          "mWristLeft", "mWristRight", "mHipLeft", "mHipRight", "mKneeLeft", "mKneeRight", "mAnkleLeft", "mAnkleRight"]

# ---- the parser: little endian, section 6 ----
class Reader:
    def __init__(self, b): self.b, self.i = b, 0
    def take(self, fmt):
        n = struct.calcsize(fmt)
        if self.i + n > len(self.b): raise ValueError("file ends too early")
        v = struct.unpack_from(fmt, self.b, self.i); self.i += n
        return v if len(v) > 1 else v[0]
    def cstr(self):
        e = self.b.index(b"\0", self.i); s = self.b[self.i:e].decode("ascii"); self.i = e + 1
        return s

def parse(path):
    r = Reader(open(path, "rb").read())
    a = {}
    a["version"], a["sub"] = r.take("<HH")
    a["base_priority"] = r.take("<i")
    a["duration"] = r.take("<f")
    a["emote"] = r.cstr()
    a["loop_in"], a["loop_out"] = r.take("<f"), r.take("<f")
    a["loop"] = r.take("<i")
    a["ease_in"], a["ease_out"] = r.take("<f"), r.take("<f")
    a["hand"] = r.take("<I")
    n = r.take("<I")
    a["joints"] = []
    for _ in range(n):
        name = r.cstr()
        prio = r.take("<i")
        keys = []
        for _ in range(r.take("<i")):
            t, x, y, z = r.take("<HHHH")
            keys.append((t, x, y, z))
        npos = r.take("<i")
        for _ in range(npos): r.take("<HHHH")                    # a position key is (time, x, y, z) too; none expected
        a["joints"].append((name, prio, keys, npos))
    a["constraints"] = r.take("<i")
    a["rest"] = len(r.b) - r.i
    return a

def dec(u): return -1.0 + 2.0 * u / 65535.0                       # 0..65535 -> -1..+1
def quat(key):
    x, y, z = dec(key[1]), dec(key[2]), dec(key[3])
    s = x * x + y * y + z * z
    return (math.sqrt(max(0.0, 1.0 - s)), x, y, z), s              # w is rebuilt, always >= 0

# ---- forward kinematics with rotation matrices (own copy of the approximate Second Life bone lengths, metres) ----
def mat(q):
    w, x, y, z = q
    return [[1 - 2*(y*y + z*z), 2*(x*y - w*z), 2*(x*z + w*y)],
            [2*(x*y + w*z), 1 - 2*(x*x + z*z), 2*(y*z - w*x)],
            [2*(x*z - w*y), 2*(y*z + w*x), 1 - 2*(x*x + y*y)]]
def mm(a, b): return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
def mv(a, v): return [sum(a[i][k] * v[k] for k in range(3)) for i in range(3)]
def vadd(a, b): return [p + q for p, q in zip(a, b)]
def vsub(a, b): return [p - q for p, q in zip(a, b)]
def norm(a): return math.sqrt(sum(p * p for p in a))
I3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
BONES = {"mTorso": (None, (0, 0, .08)), "mChest": ("mTorso", (0, 0, .21)), "mNeck": ("mChest", (0, 0, .25)),
         "mHead": ("mNeck", (0, 0, .08)),
         "mShoulderLeft": ("mChest", (0, .165, .165)), "mShoulderRight": ("mChest", (0, -.165, .165)),
         "mElbowLeft": ("mShoulderLeft", (0, .25, 0)), "mElbowRight": ("mShoulderRight", (0, -.25, 0)),
         "mWristLeft": ("mElbowLeft", (0, .21, 0)), "mWristRight": ("mElbowRight", (0, -.21, 0)),
         "mHipLeft": (None, (.03, .13, -.04)), "mHipRight": (None, (.03, -.13, -.04)),
         "mKneeLeft": ("mHipLeft", (0, 0, -.49)), "mKneeRight": ("mHipRight", (0, 0, -.49)),
         "mAnkleLeft": ("mKneeLeft", (0, 0, -.47)), "mAnkleRight": ("mKneeRight", (0, 0, -.47))}
def fk(local):
    out = {}
    def go(j):
        if j not in out:
            parent, off = BONES[j]
            pp, pm = ([0, 0, 0], I3) if parent is None else go(parent)
            out[j] = (vadd(pp, mv(pm, off)), mm(pm, mat(local[j])))
        return out[j]
    for j in BONES: go(j)
    return out
def seg_dist(p, a, b):                                            # distance from p to the segment a-b
    ab = vsub(b, a); t = max(0.0, min(1.0, sum(u * v for u, v in zip(vsub(p, a), ab)) / sum(u * u for u in ab)))
    return norm(vsub(p, vadd(a, [t * u for u in ab])))

# ---- are the committed files what the generator makes? ----
run = subprocess.run([sys.executable, "-I", os.path.join(R, "tools", "make_anims.py"), "--check"], capture_output=True, text=True)
check(run.returncode == 0, "anims/*.anim differ from tools/make_anims.py output (run it again): " + run.stdout.strip()[-200:])

ORDINARY_ANKLE_Z = -.04 - .47                                    # an ordinary sit: thighs level, shins straight down
poses = {}
for name in ("rowboat_driver", "rowboat_passenger"):
    path = os.path.join(R, "anims", name + ".anim")
    check(os.path.exists(path), f"{name}: file missing")
    if not os.path.exists(path): continue
    size = os.path.getsize(path)
    check(size < 250000, f"{name}: {size} bytes is over the 250,000 byte upload limit")
    a = parse(path)
    check(a["rest"] == 0, f"{name}: {a['rest']} unread bytes at the end")
    check((a["version"], a["sub"]) == (1, 0), f"{name}: version {a['version']}.{a['sub']}")
    check(a["base_priority"] == 4, f"{name}: base priority {a['base_priority']}")
    check(abs(a["duration"] - 1.0) < 1e-6, f"{name}: duration {a['duration']}")
    check(a["emote"] == "", f"{name}: emote name {a['emote']!r}")
    check(a["loop"] == 1 and a["loop_in"] == 0.0 and abs(a["loop_out"] - a["duration"]) < 1e-6, f"{name}: loop settings")
    check(abs(a["ease_in"] - 0.5) < 1e-6 and abs(a["ease_out"] - 0.5) < 1e-6, f"{name}: ease in/out")
    check(a["hand"] == 1, f"{name}: hand pose {a['hand']}")
    check(a["constraints"] == 0, f"{name}: constraints {a['constraints']}")
    names = [j[0] for j in a["joints"]]
    check(sorted(names) == sorted(JOINTS) and len(names) == len(set(names)), f"{name}: joint list is {names}")
    local = {}
    for jn, prio, keys, npos in a["joints"]:
        check(prio == 4, f"{name}/{jn}: priority {prio}")
        check(npos == 0, f"{name}/{jn}: {npos} position keys")
        check(len(keys) == 2 and keys[0][0] == 0 and keys[1][0] == 65535, f"{name}/{jn}: key times {[k[0] for k in keys]}")
        if len(keys) != 2: continue
        check(keys[0][1:] == keys[1][1:], f"{name}/{jn}: the two keys differ (not a held pose)")
        q, s = quat(keys[0])
        check(s <= 1.0 + 1e-4, f"{name}/{jn}: x,y,z outside the unit ball (|xyz|^2 = {s:.5f}), w cannot be rebuilt")
        check(q[0] >= 0.0 and abs(sum(c * c for c in q) - 1.0) < 1e-3, f"{name}/{jn}: w {q[0]:.4f} or length is wrong")
        local[jn] = q
    if len(local) != len(JOINTS): continue
    poses[name] = (local, fk(local))

# signs by the right-hand rule (SPEC section 6): leg forward = negative about Y, shin back = positive, lean forward = positive
if poses:
    d, dw = poses["rowboat_driver"]; p, pw = poses["rowboat_passenger"]
    for side in ("Left", "Right"):
        for nm, loc in (("driver", d), ("passenger", p)):
            check(loc["mHip" + side][2] < -0.3, f"{nm}: hip {side} is not flexed forward (negative about Y): {loc['mHip' + side]}")
            check(loc["mKnee" + side][2] > 0.3, f"{nm}: knee {side} is not flexed (positive about Y): {loc['mKnee' + side]}")
    check(d["mTorso"][2] > 0.01 and d["mChest"][2] > 0.01, "driver: torso is not leaning forward (positive about Y)")
    check(p["mTorso"][2] < -0.01 and p["mChest"][2] < -0.01, "passenger: torso is not leaning back (negative about Y)")

    def info(w, loc):
        g = {}
        g["knee_rise"] = w["mKneeLeft"][0][2] - w["mHipLeft"][0][2]
        g["ankle_z"] = w["mAnkleLeft"][0][2]
        g["shin_dx"] = abs(w["mAnkleLeft"][0][0] - w["mKneeLeft"][0][0])
        g["lean"] = w["mNeck"][0][0] - 0.0                         # the neck's forward distance from the pelvis
        up = mv(w["mHead"][1], (0, 0, 1))
        g["head_tilt"] = math.degrees(math.acos(max(-1.0, min(1.0, up[2]))))
        g["sym"] = max(abs(w["mKneeLeft"][0][0] - w["mKneeRight"][0][0]), abs(w["mKneeLeft"][0][2] - w["mKneeRight"][0][2]))
        return g
    gd, gp = info(dw, d), info(pw, p)
    # the driver
    check(gd["knee_rise"] > 0.10, f"driver: knees are only {gd['knee_rise']*100:.0f} cm above the hips")
    check(gd["ankle_z"] - ORDINARY_ANKLE_Z > 0.12, f"driver: feet only {(gd['ankle_z'] - ORDINARY_ANKLE_Z)*100:.0f} cm higher than an ordinary sit")
    check(gd["shin_dx"] < 0.06, f"driver: the shin is not nearly vertical (dx {gd['shin_dx']*100:.0f} cm)")
    check(gd["lean"] > 0.02, f"driver: the torso does not lean forward (neck {gd['lean']*100:.0f} cm forward of the pelvis)")
    # the passenger
    check(abs(pw["mKneeLeft"][0][2] - pw["mHipLeft"][0][2]) < 0.05, "passenger: thighs are not about level")
    check(pw["mKneeLeft"][0][0] - pw["mHipLeft"][0][0] > 0.4, "passenger: the knees are not forward of the hips")
    check(gp["lean"] < -0.02, f"passenger: the torso does not lean back (neck {gp['lean']*100:.0f} cm from the pelvis)")
    check(gp["ankle_z"] - ORDINARY_ANKLE_Z < 0.06, "passenger: feet are not at about the ordinary sitting height")
    for nm, g in (("driver", gd), ("passenger", gp)):
        check(g["head_tilt"] < 1.0, f"{nm}: the head is tilted {g['head_tilt']:.1f} degrees")
        check(g["sym"] < 0.01, f"{nm}: left and right legs differ")
    # the hands (the middle of the hand is 9 cm on from the wrist along the forearm)
    for nm, w, near in (("driver", dw, "knee"), ("passenger", pw, "thigh")):
        for side, sgn in (("Left", 1), ("Right", -1)):
            wp, wm = w["mWrist" + side]
            hand = vadd(wp, mv(wm, (0, sgn * 0.09, 0)))
            hip, knee = w["mHip" + side][0], w["mKnee" + side][0]
            dist = norm(vsub(hand, knee)) if near == "knee" else seg_dist(hand, hip, knee)
            lim = 0.12
            check(dist < lim, f"{nm}: {side} hand is {dist*100:.0f} cm from the {near}")
            check(hand[2] > hip[2] - 0.02, f"{nm}: {side} hand is below the thigh")
    print(f"driver: knees {gd['knee_rise']*100:.0f} cm above hips, feet {(gd['ankle_z'] - ORDINARY_ANKLE_Z)*100:.0f} cm above an ordinary sit, "
          f"neck {gd['lean']*100:.0f} cm forward, head tilt {gd['head_tilt']:.1f} deg")
    print(f"passenger: neck {gp['lean']*100:.0f} cm back, thighs level, head tilt {gp['head_tilt']:.1f} deg")
print("anim checks: ALL PASS" if ok else "anim checks: FAILED")
raise SystemExit(0 if ok else 1)
