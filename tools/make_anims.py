#!/usr/bin/env python3
"""Generate the rowboat's two seated animations (Second Life .anim files) and a side-view preview picture.

    python3 tools/make_anims.py            write anims/rowboat_driver.anim, anims/rowboat_passenger.anim, anims/preview.png
    python3 tools/make_anims.py --check    write nothing; exit 1 if the committed .anim files differ from the output

The poses come from the named angle constants below. Rotations are plain avatar-axis rotations (X forward, Y left,
Z up, every joint at rest with identity rotation: legs down, arms out along Y). Right-hand rule: leg swinging forward =
negative about Y, knee bending (shin swings back) = positive about Y, leaning forward = positive about Y. The hands are
placed by a small search over the elbow angle with forward kinematics. Nothing here has been tried in Second Life yet.
Needs Pillow for the preview only (not for --check).
"""
import math, os, struct, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "anims")

# ---- the poses: named angles in degrees (positive lean = forward, negative = back) ----
DRIVER = dict(
    name="rowboat_driver",
    hip_flex=110.0,        # thigh swung forward from hanging down: 110 = knees 20 degrees above the hips
    knee_flex=110.0,       # shin swung back relative to the thigh: 110 here leaves the shin hanging straight down
    hip_splay=6.0,         # knees a little apart
    lean=8.0,              # torso leaning forward (shared by mTorso and mChest); the neck and head cancel it
    arm_down=50.0,         # upper arm: degrees below the horizontal, out to the side ...
    arm_fwd=60.0,          # ... and swung this far forward
    hand_along=0.85,        # the hand rests this fraction of the way from the hip to the knee along the thigh ...
    hand_lift=0.05,        # ... and this far above it (m)
    wrist=10.0,            # slight wrist bend
)
PASSENGER = dict(
    name="rowboat_passenger",
    hip_flex=90.0,
    knee_flex=100.0,
    hip_splay=4.0,
    lean=-8.0,
    arm_down=88.0,
    arm_fwd=10.0,
    hand_along=0.45,       # on the thighs, nearer the lap
    hand_lift=0.07,
    wrist=5.0,
)
HEAD_SHARE = (0.4, 0.6)    # how the neck and the head cancel the torso lean (they add up to 1: head stays level)

# ---- the file ----
DURATION = 1.0
PRIORITY = 4
EASE = 0.5
HAND_POSE = 1              # relaxed
JOINTS = ["mTorso", "mChest", "mNeck", "mHead",
          "mShoulderLeft", "mShoulderRight", "mElbowLeft", "mElbowRight", "mWristLeft", "mWristRight",
          "mHipLeft", "mHipRight", "mKneeLeft", "mKneeRight", "mAnkleLeft", "mAnkleRight"]

# ---- approximate Second Life skeleton (m): joint -> (parent, offset in the parent's frame at rest) ----
# mPelvis is the origin and is not animated; mCollar is not animated, its offset is folded into the shoulder.
THIGH, SHIN, UPPER_ARM, FOREARM, HAND = 0.49, 0.47, 0.25, 0.21, 0.09
SKEL = {
    "mTorso": (None, (0.0, 0.0, 0.08)), "mChest": ("mTorso", (0.0, 0.0, 0.21)),
    "mNeck": ("mChest", (0.0, 0.0, 0.25)), "mHead": ("mNeck", (0.0, 0.0, 0.08)),
    "mShoulderLeft": ("mChest", (0.0, 0.165, 0.165)), "mShoulderRight": ("mChest", (0.0, -0.165, 0.165)),
    "mElbowLeft": ("mShoulderLeft", (0.0, UPPER_ARM, 0.0)), "mElbowRight": ("mShoulderRight", (0.0, -UPPER_ARM, 0.0)),
    "mWristLeft": ("mElbowLeft", (0.0, FOREARM, 0.0)), "mWristRight": ("mElbowRight", (0.0, -FOREARM, 0.0)),
    "mHipLeft": (None, (0.03, 0.13, -0.04)), "mHipRight": (None, (0.03, -0.13, -0.04)),
    "mKneeLeft": ("mHipLeft", (0.0, 0.0, -THIGH)), "mKneeRight": ("mHipRight", (0.0, 0.0, -THIGH)),
    "mAnkleLeft": ("mKneeLeft", (0.0, 0.0, -SHIN)), "mAnkleRight": ("mKneeRight", (0.0, 0.0, -SHIN)),
}
HEAD_TOP = 0.13            # m above mHead (for the drawing)
TOE = (0.11, 0.0, -0.06)   # ankle to toe in the ankle's frame (for the drawing)


# ---- small quaternion kit, (w, x, y, z), v' = q v q^-1, child world = parent world * local ----
def qmul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw*bw - ax*bx - ay*by - az*bz, aw*bx + ax*bw + ay*bz - az*by,
            aw*by - ax*bz + ay*bw + az*bx, aw*bz + ax*by - ay*bx + az*bw)

def qaxis(axis, deg):
    h = math.radians(deg) / 2
    s = math.sin(h)
    return (math.cos(h), axis[0]*s, axis[1]*s, axis[2]*s)

def qrot(q, v):
    w, x, y, z = q
    t = qmul(qmul(q, (0.0,) + tuple(v)), (w, -x, -y, -z))
    return t[1:]

def arc(u, v):
    """shortest-arc rotation taking unit vector u to unit vector v"""
    d = sum(a*b for a, b in zip(u, v))
    if d < -0.999999:
        return (0.0, 1.0, 0.0, 0.0) if abs(u[0]) < 0.9 else (0.0, 0.0, 1.0, 0.0)
    c = (u[1]*v[2] - u[2]*v[1], u[2]*v[0] - u[0]*v[2], u[0]*v[1] - u[1]*v[0])
    n = math.sqrt(2 * (1 + d))
    return (n / 2, c[0] / n, c[1] / n, c[2] / n)

X, Y, Z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)

def add(a, b): return tuple(p + q for p, q in zip(a, b))
def sub(a, b): return tuple(p - q for p, q in zip(a, b))
def dist(a, b): return math.sqrt(sum((p - q) ** 2 for p, q in zip(a, b)))


def fk(rots):
    """world (position, rotation) of every joint, pelvis at the origin; rots = joint -> local quaternion"""
    ident = (1.0, 0.0, 0.0, 0.0)
    out = {}
    def go(j):
        if j in out:
            return out[j]
        parent, off = SKEL[j]
        pp, pr = ((0.0, 0.0, 0.0), ident) if parent is None else go(parent)
        out[j] = (add(pp, qrot(pr, off)), qmul(pr, rots.get(j, ident)))
        return out[j]
    for j in SKEL:
        go(j)
    return out


def hand_point(w, side):
    """the middle of the hand: HAND metres on from the wrist along the forearm (side +1 left, -1 right)"""
    pos, rot = w["mWrist" + ("Left" if side > 0 else "Right")]
    return add(pos, qrot(rot, (0.0, side * HAND, 0.0)))


def build(p):
    """local rotations for every animated joint of a pose, hands placed by the elbow search; returns (rots, report)"""
    r = {}
    lean = p["lean"]
    r["mTorso"] = qaxis(Y, lean / 2)
    r["mChest"] = qaxis(Y, lean / 2)
    r["mNeck"] = qaxis(Y, -lean * HEAD_SHARE[0])
    r["mHead"] = qaxis(Y, -lean * HEAD_SHARE[1])
    for side, nm in ((1, "Left"), (-1, "Right")):
        r["mHip" + nm] = qmul(qaxis(Z, side * p["hip_splay"]), qaxis(Y, -p["hip_flex"]))
        r["mKnee" + nm] = qaxis(Y, p["knee_flex"])
        r["mAnkle" + nm] = qaxis(Y, p["hip_flex"] - p["knee_flex"])      # foot flat: the Y rotations add up to zero
        a, d = math.radians(p["arm_down"]), math.radians(p["arm_fwd"])
        want = (math.cos(a) * math.sin(d), side * math.cos(a) * math.cos(d), -math.sin(a))
        r["mShoulder" + nm] = arc((0.0, float(side), 0.0), want)
        r["mWrist" + nm] = qaxis(Z, -side * p["wrist"])
    report = {}
    for side, nm in ((1, "Left"), (-1, "Right")):
        w = fk(r)
        hip, knee = w["mHip" + nm][0], w["mKnee" + nm][0]
        target = add(add(hip, tuple(p["hand_along"] * c for c in sub(knee, hip))), (0.0, 0.0, p["hand_lift"]))
        best = None
        for i in range(-40, 301):                       # elbow flexion -20 .. 150 degrees in half-degree steps
            flex = i / 2.0
            r["mElbow" + nm] = qaxis(Z, -side * flex)   # forearm swings forward for a positive flexion
            err = dist(hand_point(fk(r), side), target)
            if best is None or err < best[0]:
                best = (err, flex)
        r["mElbow" + nm] = qaxis(Z, -side * best[1])
        report[nm] = best
    return r, report


# ---- the .anim file ----
def u16(v):
    return max(0, min(65535, int(round((v + 1.0) * 32767.5))))

def anim_bytes(rots):
    # version, sub_version, base priority, duration, then the (empty) emote name
    b = struct.pack("<HHif", 1, 0, PRIORITY, DURATION) + b"\0"
    # loop_in, loop_out, loop, ease_in, ease_out, hand_pose, number of joints
    b += struct.pack("<ffiffII", 0.0, DURATION, 1, EASE, EASE, HAND_POSE, len(JOINTS))
    for j in JOINTS:
        w, x, y, z = rots[j]
        n = math.sqrt(w*w + x*x + y*y + z*z)
        w, x, y, z = w / n, x / n, y / n, z / n
        if w < 0:
            w, x, y, z = -w, -x, -y, -z                                     # the file stores w >= 0 (it rebuilds w)
        key = (u16(x), u16(y), u16(z))
        b += j.encode() + b"\0" + struct.pack("<ii", PRIORITY, 2)           # name, priority, number of rotation keys
        b += struct.pack("<HHHH", 0, *key) + struct.pack("<HHHH", 65535, *key)   # a held pose: the same key twice
        b += struct.pack("<i", 0)                                           # no position keys
    return b + struct.pack("<i", 0)                                         # no constraints (once, after the joints)


# ---- the preview picture ----
def draw_pose(d, ox, oy, scale, w, ghost, font):
    def pt(p):
        return (ox + p[0] * scale, oy - p[2] * scale)
    pelvis = (0.0, 0.0, 0.0)
    ank = w["mAnkleLeft"][0]
    d.line([pt((-0.30, 0, -0.10)), pt((0.30, 0, -0.10))], fill=(120, 90, 60), width=5)             # the bench
    d.line([pt((-0.55, 0, ghost)), pt((0.75, 0, ghost))], fill=(150, 150, 150), width=1)           # ordinary sit: ankle height
    d.text(pt((-0.55, 0, ghost + 0.07)), "ankle height of an ordinary sit", fill=(120, 120, 120), font=font)
    def chain(names, colour, width=4):
        pts = [pt(pelvis)] + [pt(w[n][0]) for n in names]
        d.line(pts, fill=colour, width=width)
    chain(["mTorso", "mChest", "mNeck", "mHead"], (30, 30, 30), 5)
    head = w["mHead"][0]
    top = add(head, qrot(w["mHead"][1], (0.0, 0.0, HEAD_TOP)))
    d.line([pt(head), pt(top)], fill=(30, 30, 30), width=5)
    hc = pt(add(head, qrot(w["mHead"][1], (0.0, 0.0, HEAD_TOP / 2))))
    d.ellipse([hc[0] - 0.085 * scale, hc[1] - 0.085 * scale, hc[0] + 0.085 * scale, hc[1] + 0.085 * scale],
              outline=(30, 30, 30), width=3)
    for nm, colour in (("Left", (200, 60, 40)), ("Right", (40, 90, 200))):
        side = 1 if nm == "Left" else -1
        hip = w["mHip" + nm][0]
        d.line([pt(pelvis), pt(hip), pt(w["mKnee" + nm][0]), pt(w["mAnkle" + nm][0])], fill=colour, width=4)
        apos, arot = w["mAnkle" + nm]
        d.line([pt(apos), pt(add(apos, qrot(arot, TOE)))], fill=colour, width=4)
        sh = w["mShoulder" + nm][0]
        d.line([pt(w["mChest"][0]), pt(sh), pt(w["mElbow" + nm][0]), pt(w["mWrist" + nm][0]), pt(hand_point(w, side))],
               fill=colour, width=4)
    for n in ("mTorso", "mHipLeft", "mKneeLeft", "mShoulderLeft", "mElbowLeft"):
        c = pt(w[n][0])
        d.ellipse([c[0] - 3, c[1] - 3, c[0] + 3, c[1] + 3], fill=(30, 30, 30))


def preview(path, poses):
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.load_default(size=14)
    except TypeError:
        font = ImageFont.load_default()
    scale = 300.0
    img = Image.new("RGB", (1000, 640), (250, 250, 246))
    d = ImageDraw.Draw(img)
    for i, (p, rots) in enumerate(poses):
        w = fk(rots)
        ox, oy = 250 + 500 * i, 330
        ordinary = SKEL["mHipLeft"][1][2] - SHIN              # ankle height of an ordinary sit: thigh level, shin down
        draw_pose(d, ox, oy, scale, w, ordinary, font)
        d.text((ox - 200, 20), p["name"], fill=(20, 20, 20), font=font)
        d.text((ox - 200, 44), "facing right; left and right sides overlap in this view", fill=(90, 90, 90), font=font)
    d.text((20, 610), "Side view drawn from the same forward kinematics as the .anim files. Not seen in Second Life yet.",
           fill=(90, 90, 90), font=font)
    img.save(path)


def main():
    check = "--check" in sys.argv
    poses = []
    bad = False
    for p in (DRIVER, PASSENGER):
        rots, report = build(p)
        poses.append((p, rots))
        data = anim_bytes(rots)
        path = os.path.join(OUT, p["name"] + ".anim")
        print(f"{p['name']}: {len(data)} bytes, hand errors "
              + ", ".join(f"{k} {e * 100:.1f} cm at elbow {f:.1f} deg" for k, (e, f) in report.items()))
        if check:
            if not os.path.exists(path) or open(path, "rb").read() != data:
                bad = True
                print("DIFFERS:", path)
        else:
            os.makedirs(OUT, exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
    if check:
        print("anim files differ from the generator output" if bad else "anim files match the generator output")
        raise SystemExit(1 if bad else 0)
    preview(os.path.join(OUT, "preview.png"), poses)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
