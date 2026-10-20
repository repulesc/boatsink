// Rowboat 2 - a gag rowboat that sways and drifts on open water, seats two people and slowly sinks with them.
// Drop into the ROOT prim of the boat, put the boat on the water and CLOSE THE EDIT WINDOW: Second Life freezes this
// kind of motion while the boat is selected. Where the boat is when the script starts is home.
// SEATS: the root prim is the driver seat; a child prim named Seat2 (small, invisible, linked to the boat) is the
// passenger seat. Without it the boat has one seat. Animations "rowboat_driver" and "rowboat_passenger" go in the root.
// OWNER MENU: right-click the boat > Touch (or say /9 boat). Only the owner gets it. Guests just left-click to sit.
// What the menu saves lives in the boat itself (Linkset Data), so it survives script resets and copies.
// The boat is moved with keyframed motion (non-physical, smooth, run by the simulator), so it cannot be pushed away,
// cannot wander off the parcel, and always rides at the water level of the region.

// ---- Floating ----
float DRAFT         = 0.30;   // m, how deep the bottom of the hull sits in the water at first (the boat's size is measured)
float HEAVE         = 0.035;  // m, up-and-down bob (Second Life water is flat: keep it very small)
float ROLL_DEG      = 2.0;    // side-to-side rock
float PITCH_DEG     = 0.8;    // bow-to-stern rock
float YAW_SWING_DEG = 25.0;   // how far the bow slowly swings round
// ---- Drift ----
float DRIFT_RADIUS  = 6.0;    // m, the boat wanders within this distance of home (keep it over deep water)
float DRIFT_PERIOD  = 700.0;  // s, a wander loop takes about this long (bigger = slower; 700 s is ~5 cm/s)
float DRIFT_EASE    = 30.0;   // s to switch the wandering fully on or off
// ---- Sinking ----
float SINK_TIME     = 90.0;   // s from sitting down to fully under
float SINK_DEPTH    = 3.0;    // m the boat goes down when fully sunk
float SINK_PITCH    = 12.0;   // degrees bow down when sunk (the bow is the root prim's +X; use a minus value for -X)
float SINK_ROLL     = 6.0;    // degrees list to one side when sunk
float RISE_TIME     = 30.0;   // s to come back up after the last sitter stands
float BOTTOM_GAP    = 0.5;    // m, the hull never goes closer than this to the sea floor
// ---- Seats (sit-target offsets in the root prim's frame; the owner nudges and saves them from the menu) ----
vector SEAT1_POS    = <-0.25, 0.0, 0.20>;   // driver, on the rower's bench
float  SEAT1_YAW    = 0.0;                  // degrees about the boat's Z
vector SEAT2_POS    = <0.85, 0.0, 0.20>;    // passenger, forward
float  SEAT2_YAW    = 180.0;                // faces the driver
string SEAT2_NAME   = "Seat2";              // name of the child prim that carries the second sit target
string ANIM_DRIVER    = "rowboat_driver";
string ANIM_PASSENGER = "rowboat_passenger";

float   FRAME  = 0.6;         // s per keyframe (27/45 s: keyframe times should be whole multiples of 1/45 s)
integer FRAMES = 10;          // keyframes per batch: a new 6 s batch is sent each time the last one ends

vector  home;
float   homeYaw;
float   hullLow;              // m the hull bottom is below the root prim's centre (a minus number)
float   lift;                 // m from the water surface up to the root prim's centre (saved as "lift")
float   t0;                   // the motion starts from the neutral pose at this time (start, Align, end of a nudge)
integer seated;               // anyone sits in either seat
integer driftOn;
integer sinkOn;
float   driftAmt;             // 0..1, how much of the wander is shown; eases to 0 or 1
float   driftT;               // when driftAmt was last brought up to date
float   batchStart;           // when the batch now playing started, and how far sunk (0 afloat, 1 under) it was then
float   batchSunk;
integer batchSeated;          // that batch was sinking (someone sat and Sink is on)
// seats: index 0 = driver (root prim), 1 = passenger (Seat2)
list    seatPos = [ZERO_VECTOR, ZERO_VECTOR];   // current sit-target offsets, root prim's frame
list    seatYaw = [0.0, 0.0];                   // degrees
list    seatWho = [NULL_KEY, NULL_KEY];         // who sits there now
integer seat2Link;            // link number of the prim named Seat2, 0 = none
integer warned;               // the owner has been told that Seat2 is missing
list    queue;                // [avatar, seat, ...] waiting for animation permission
key     permFor;              // the avatar the open permission request is for, NULL_KEY = none
integer permSeat;
float   permAt;
// menus: 0 none, 1 main, 2 waterline, 3 driver nudge, 4 passenger nudge
integer menu;
integer menuChan;             // dialog channel; 0 until the script is set up
integer menuListen;
float   menuUntil;
integer nudge;                // TRUE while a nudge menu is open: the boat holds still
float   heldAt;
integer fine;                 // nudge step: FALSE = 5 cm / 5 degrees, TRUE = 1 cm / 1 degree

// a number as text with exactly d (3 or 4) decimals, for Linkset Data
string fix(float x, integer d)
{
    float m = 1000.0;
    if (d == 4) m = 10000.0;
    string s = (string)((float)llRound(x * m) / m);
    return llGetSubString(s, 0, llSubStringIndex(s, ".") + d);
}

float wave(float t, float period)
{
    return llSin(TWO_PI * t / period);
}

float clamp01(float x)
{
    if (x < 0.0) return 0.0;
    if (x > 1.0) return 1.0;
    return x;
}

// how far sunk the boat is dt seconds after the batch started
float sunkAfter(float dt)
{
    if (batchSeated) return clamp01(batchSunk + dt / SINK_TIME);
    return clamp01(batchSunk - dt / RISE_TIME);
}

// how much of the wander is shown dt seconds after driftAmt was last brought up to date
float driftAfter(float dt)
{
    float goal = (float)driftOn;
    float step = dt / DRIFT_EASE;
    float a = driftAmt - step;
    if (driftAmt < goal)
    {
        a = driftAmt + step;
        if (a > goal) a = goal;
    }
    else if (a < goal) a = goal;
    return a;
}

// where the boat should be, and how it should be turned, t seconds after t0 (every wave starts at phase 0, so the whole
// motion starts from the neutral pose); s = how far sunk, da = how much wander, start = where the boat is now
list pose(float t, float s, float da, vector start)
{
    float e = s * s * (3.0 - 2.0 * s);            // eased sinking: slow start, slow finish
    float calm = 1.0 - 0.8 * e;                   // waves move a sunken boat much less

    vector p = home + da * <DRIFT_RADIUS * wave(t, DRIFT_PERIOD),
                            DRIFT_RADIUS * wave(t, DRIFT_PERIOD * 1.37), 0.0>;
    // slow swells of unrelated periods, so the rocking is soft and never visibly repeats
    float heave = HEAVE * (0.6 * wave(t, 9.7) + 0.4 * wave(t, 6.3));
    p.z = llWater(ZERO_VECTOR) + lift - e * SINK_DEPTH + calm * heave;
    float floor = llGround(p - start) + BOTTOM_GAP - hullLow;
    if (p.z < floor) p.z = floor;

    float roll  = calm * ROLL_DEG  * (0.7 * wave(t, 8.9) + 0.3 * wave(t, 5.7)) + e * SINK_ROLL;
    float pitch = calm * PITCH_DEG * (0.6 * wave(t, 7.9) + 0.4 * wave(t, 5.1)) + e * SINK_PITCH;
    float yaw   = homeYaw + YAW_SWING_DEG * DEG_TO_RAD * (0.8 * wave(t, 97.0) + 0.2 * wave(t, 41.0));
    rotation r = llEuler2Rot(<roll, pitch, 0.0> * DEG_TO_RAD) * llEuler2Rot(<0.0, 0.0, yaw>);
    return [p, r];
}

// bring the sinking and the wander up to date as of now (call before changing driftOn or the sitting state)
settle()
{
    float t = llGetTime();
    batchSunk = sunkAfter(t - batchStart);    // how far the last batch got, even if it was cut short
    driftAmt = driftAfter(t - driftT);
    batchStart = t;
    driftT = t;
}

// plan the next 6 s of motion from where the boat really is, and play it (not while a nudge menu holds it still)
nextBatch()
{
    if (nudge) return;
    settle();
    batchSeated = seated && sinkOn;
    vector start = llGetPos();
    vector at = start;
    rotation was = llGetRot();
    float t = batchStart - t0;
    list frames = [];
    integer k;
    for (k = 1; k <= FRAMES; ++k)
    {
        list p = pose(t + k * FRAME, sunkAfter(k * FRAME), driftAfter(k * FRAME), start);
        vector to = llList2Vector(p, 0);
        rotation r = llList2Rot(p, 1);
        // a keyframe's move is in region axes, its turn in the boat's own axes: r = turn * was
        frames += [to - at, r / was, FRAME];
        at = to;
        was = r;
    }
    llSetKeyframedMotion(frames, []);
}

// stop the motion and plan again now (after a change of height, sinking or wander)
replan()
{
    if (nudge) return;
    llSetKeyframedMotion([], []);
    nextBatch();
}

// a nudge menu opens: the boat holds still, and the clock of the motion stops with it
holdStill()
{
    if (nudge) return;
    settle();
    heldAt = batchStart;
    nudge = TRUE;
    llSetKeyframedMotion([], []);
    llOwnerSay("The boat holds still while the nudge menu is open. Done (or 60 s without a button) lets it move again.");
}

// the nudge menu is over: carry on from the pose where the boat stopped, without a jump
endNudge()
{
    float t = llGetTime();
    t0 += t - heldAt;
    batchStart = t;
    driftT = t;
    nudge = FALSE;
    nextBatch();
}

// put the boat on the water level where it is, level it, and make this its home
align()
{
    llSetKeyframedMotion([], []);
    vector e = llRot2Euler(llGetRot());
    homeYaw = e.z;
    home = llGetPos();
    home.z = llWater(ZERO_VECTOR) + lift;
    llSetLinkPrimitiveParamsFast(LINK_THIS, [PRIM_POSITION, home, PRIM_ROTATION, llEuler2Rot(<0.0, 0.0, homeYaw>)]);
    t0 = llGetTime();                         // the motion starts from the neutral pose here: no leap, no swing
    batchStart = t0;
    driftT = t0;
    batchSunk = 0.0;
    nextBatch();
}

// ---- Seats ----

string seatName(integer s)
{
    if (s == 0) return "driver seat";
    return "passenger seat";
}

// the saved offset of a seat, or its default: [vector, yaw in degrees]
list savedSeat(integer s)
{
    list p = llParseString2List(llLinksetDataRead("seat" + (string)(s + 1)), [" "], []);
    if (llGetListLength(p) == 4)
        return [<(float)llList2String(p, 0), (float)llList2String(p, 1), (float)llList2String(p, 2)>,
                (float)llList2String(p, 3)];
    if (s == 0) return [SEAT1_POS, SEAT1_YAW];
    return [SEAT2_POS, SEAT2_YAW];
}

setSeat(integer s, vector pos, float yaw)
{
    if (yaw > 180.0) yaw -= 360.0;
    if (yaw <= -180.0) yaw += 360.0;
    seatPos = llListReplaceList(seatPos, [pos], s, s);
    seatYaw = llListReplaceList(seatYaw, [yaw], s, s);
}

// the sit target of a seat from its offset (given in the root prim's frame; Seat2's own frame is worked out here)
applySeat(integer s)
{
    integer link = LINK_ROOT;
    if (s == 1) link = seat2Link;
    if (link == 0) return;
    vector p = llList2Vector(seatPos, s);
    rotation r = llEuler2Rot(<0.0, 0.0, llList2Float(seatYaw, s) * DEG_TO_RAD>);
    if (s == 1)
    {
        list d = llGetLinkPrimitiveParams(link, [PRIM_POS_LOCAL, PRIM_ROT_LOCAL]);
        rotation cr = llList2Rot(d, 1);
        p = (p - llList2Vector(d, 0)) / cr;
        r = r / cr;
    }
    if (p == ZERO_VECTOR) p = <0.0, 0.0, 0.001>;    // ZERO_VECTOR would remove the sit target
    llLinkSitTarget(link, p, r);
}

// the link number of the avatar, 0 if it is not on the boat
integer avatarLink(key a)
{
    integer i;
    integer n = llGetNumberOfPrims();
    for (i = llGetObjectPrimCount(llGetKey()) + 1; i <= n; ++i)
        if (llGetLinkKey(i) == a) return i;
    return 0;
}

// ---- Animations: one permission request at a time ----

// ask the next waiting avatar still sitting where it sat for permission to animate it
nextPerm()
{
    while (permFor == NULL_KEY && llGetListLength(queue) > 0)
    {
        key a = llList2Key(queue, 0);
        integer s = llList2Integer(queue, 1);
        queue = llDeleteSubList(queue, 0, 1);
        if (llGetAgentSize(a) != ZERO_VECTOR && llList2Key(seatWho, s) == a)
        {
            permFor = a;
            permSeat = s;
            permAt = llGetTime();
            llRequestPermissions(a, PERMISSION_TRIGGER_ANIMATION);
        }
    }
}

string animOf(integer s)
{
    if (s == 0) return ANIM_DRIVER;
    return ANIM_PASSENGER;
}

// find Seat2, set the sit targets, see who sits where; an empty seat (or force) gets its sit target set again
refreshSeats(integer force)
{
    seat2Link = 0;
    integer i;
    integer n = llGetObjectPrimCount(llGetKey());
    for (i = 2; i <= n; ++i)
        if (llGetLinkName(i) == SEAT2_NAME) seat2Link = i;
    if (seat2Link == 0 && !warned)
    {
        warned = TRUE;
        llOwnerSay("There is no prim named " + SEAT2_NAME + ", so the boat has one seat. For a second seat, link a small "
            + "invisible prim to the boat, name it " + SEAT2_NAME + " (Edit > select it > General > Name), and put it where "
            + "the passenger sits.");
    }
    integer any = FALSE;
    integer s;
    for (s = 0; s < 2; ++s)
    {
        key who = NULL_KEY;
        if (s == 0) who = llAvatarOnLinkSitTarget(LINK_ROOT);
        else if (seat2Link) who = llAvatarOnLinkSitTarget(seat2Link);
        if (who == NULL_KEY || force) applySeat(s);
        if (who != llList2Key(seatWho, s))
        {
            seatWho = llListReplaceList(seatWho, [who], s, s);
            if (who != NULL_KEY && llGetInventoryType(animOf(s)) == INVENTORY_ANIMATION)
            {
                queue += [who, s];
                nextPerm();
            }
        }
        if (who != NULL_KEY) any = TRUE;
    }
    seated = any;
}

// ---- Nudging a seat ----

// move a seat by dp (boat's frame, metres) and dyaw (degrees about the boat's Z): the sit target for the next sitter and,
// at once, whoever sits there now (by the same step from where they are, so the sit-target height quirk does not matter)
nudgeSeat(integer s, vector dp, float dyaw)
{
    setSeat(s, llList2Vector(seatPos, s) + dp, llList2Float(seatYaw, s) + dyaw);
    applySeat(s);
    key a = llList2Key(seatWho, s);
    integer i = 0;
    if (a != NULL_KEY) i = avatarLink(a);
    if (i == 0)
    {
        llOwnerSay("Nobody sits in the " + seatName(s) + ": the change applies to the next sitter.");
        return;
    }
    list d = llGetLinkPrimitiveParams(i, [PRIM_POS_LOCAL, PRIM_ROT_LOCAL]);
    llSetLinkPrimitiveParamsFast(i, [PRIM_POS_LOCAL, llList2Vector(d, 0) + dp,
        PRIM_ROT_LOCAL, llList2Rot(d, 1) * llEuler2Rot(<0.0, 0.0, dyaw * DEG_TO_RAD>)]);
}

// ---- Menus ----

closeMenu()
{
    llListenRemove(menuListen);
    menuListen = 0;
    menu = 0;
    if (nudge) endNudge();
}

// the state of the saved waterline, for the Waterline menu
string liftState()
{
    string v = llLinksetDataRead("lift");
    if (v == "") return "not saved, this is the computed default";
    if (v == fix(lift, 3)) return "saved";
    return "changed, not saved";
}

// Dialogs fill from the bottom row up, so each list below is written bottom row first.
showMenu()
{
    llListenRemove(menuListen);
    menuListen = llListen(menuChan, "", llGetOwner(), "");
    menuUntil = llGetTime() + 60.0;
    if (menu == 1)
    {
        string d = "OFF";
        if (driftOn) d = "ON";
        string k = "OFF";
        if (sinkOn) k = "ON";
        llDialog(llGetOwner(), "Rowboat\n\nWaterline: how high the boat floats.\nDriver seat / Passenger seat: move where "
            + "the sitter sits.\nDrift: the slow wandering. Sink: sinks when anyone sits. Both are saved.",
            ["Drift: " + d, "Sink: " + k, "Close", "Waterline", "Driver seat", "Passenger seat"], menuChan);
    }
    else if (menu == 2)
    {
        llDialog(llGetOwner(), "Waterline\n\nThe centre of the boat is " + (string)llRound(lift * 100.0)
            + " cm above the water (" + liftState() + ").\nUp / Down move the boat at once. Align: put the boat on the "
            + "water level where it is now, level it, and make this its home. Save keeps the height, Default goes back "
            + "to the computed one.", ["Save", "Default", "Back", "Down 5", "Down 1", "Align", "Up 5", "Up 1"], menuChan);
    }
    else
    {
        string st = "5 cm";
        if (fine) st = "1 cm";
        string n = seatName(menu - 3);
        llDialog(llGetOwner(), llToUpper(llGetSubString(n, 0, 0)) + llGetSubString(n, 1, -1)
            + "\n\nMove the seat in the boat's directions (Bow = front, Left = the boat's left); the sitter moves at once. "
            + "Step now " + st + " (and the same number of degrees). Save keeps the place, Reset goes back to the saved "
            + "one, Done lets the boat move again.",
            ["Save", "Reset", "Done", "Turn L", "Turn R", "Step: " + st, "Left", "Right", "Down", "Bow", "Stern", "Up"],
            menuChan);
    }
}

// one button of the main menu
mainMenu(string msg)
{
    if (msg == "Waterline") menu = 2;
    else if (msg == "Driver seat" || msg == "Passenger seat")
    {
        menu = 3;
        if (msg == "Passenger seat") menu = 4;
        holdStill();
    }
    else if (msg == "Close")
    {
        closeMenu();
        return;
    }
    else if (llGetSubString(msg, 0, 4) == "Drift")
    {
        settle();                                 // the wander so far, with the old setting
        driftOn = !driftOn;
        llLinksetDataWrite("drift", (string)driftOn);
        replan();
    }
    else if (llGetSubString(msg, 0, 3) == "Sink")
    {
        settle();
        sinkOn = !sinkOn;
        llLinksetDataWrite("sink", (string)sinkOn);
        replan();
    }
    showMenu();
}

// one button of the Waterline menu
waterMenu(string msg)
{
    integer k = llListFindList(["Up 5", "Up 1", "Down 1", "Down 5"], [msg]);
    if (msg == "Back") menu = 1;
    else if (msg == "Align")
    {
        align();
        llOwnerSay("Aligned to the water level here. The centre of the boat is " + (string)llRound(lift * 100.0)
            + " cm above the water. Save keeps this height.");
    }
    else if (msg == "Save")
    {
        llLinksetDataWrite("lift", fix(lift, 3));
        llOwnerSay("Waterline saved: " + (string)llRound(lift * 100.0) + " cm.");
    }
    else if (msg == "Default")
    {
        llLinksetDataDelete("lift");
        lift = DRAFT - hullLow;
        replan();
        llOwnerSay("Back to the computed waterline: " + (string)llRound(lift * 100.0) + " cm.");
    }
    else if (k >= 0)
    {
        float d = 0.05;
        if (k == 1 || k == 2) d = 0.01;
        if (k >= 2) d = -d;
        lift += d;
        replan();
    }
    showMenu();
}

// one button of a nudge menu
nudgeMenu(string msg)
{
    integer s = menu - 3;
    if (msg == "Done")
    {
        closeMenu();
        return;
    }
    if (msg == "Save")
    {
        vector p = llList2Vector(seatPos, s);
        llLinksetDataWrite("seat" + (string)(s + 1), fix(p.x, 4) + " " + fix(p.y, 4) + " " + fix(p.z, 4) + " "
            + fix(llList2Float(seatYaw, s), 4));
        llOwnerSay("The " + seatName(s) + " place is saved.");
    }
    else if (msg == "Reset")
    {
        list v = savedSeat(s);
        nudgeSeat(s, llList2Vector(v, 0) - llList2Vector(seatPos, s), llList2Float(v, 1) - llList2Float(seatYaw, s));
    }
    else if (llGetSubString(msg, 0, 3) == "Step") fine = !fine;
    else
    {
        float st = 5.0;
        if (fine) st = 1.0;
        integer k = llListFindList(["Bow", "Stern", "Left", "Right", "Up", "Down", "Turn L", "Turn R"], [msg]);
        float yaw = 0.0;
        if (k == 6) yaw = st;
        if (k == 7) yaw = -st;
        if (k >= 0)
            nudgeSeat(s, llList2Vector([<1.0, 0.0, 0.0>, <-1.0, 0.0, 0.0>, <0.0, 1.0, 0.0>, <0.0, -1.0, 0.0>,
                <0.0, 0.0, 1.0>, <0.0, 0.0, -1.0>, ZERO_VECTOR, ZERO_VECTOR], k) * st * 0.01, yaw);
    }
    showMenu();
}

default
{
    state_entry()
    {
        llSetKeyframedMotion([], []);
        if (llGetLinkNumber() > 1)
        {
            llOwnerSay("Put this script in the ROOT prim of the boat (the one that highlights yellow when you edit it).");
            return;
        }
        if (llGetInventoryNumber(INVENTORY_SCRIPT) > 1)
            llOwnerSay("There are other scripts in this prim. If one of them is the boat's own driving script, remove it: "
                + "it turns physics on, and a physical boat cannot be moved this way.");
        llSetStatus(STATUS_PHYSICS, FALSE);
        // keyframed motion needs the new land impact accounting: a convex hull root prim switches the linkset to it
        llSetLinkPrimitiveParamsFast(LINK_THIS, [PRIM_PHYSICS_SHAPE_TYPE, PRIM_PHYSICS_SHAPE_CONVEX]);
        llSetLinkPrimitiveParamsFast(LINK_SET, [PRIM_CLICK_ACTION, CLICK_ACTION_SIT]);    // a click anywhere on the boat sits
        llSetSitText("Sit");

        home = llGetPos();
        vector e = llRot2Euler(llGetRot());
        homeYaw = e.z;
        vector low = llList2Vector(llGetBoundingBox(llGetKey()), 0);
        hullLow = low.z;                          // how far the hull bottom is below the root prim (a minus number)
        // saved settings; a missing key means the default
        lift = DRAFT - hullLow;
        string v = llLinksetDataRead("lift");
        if (v != "") lift = (float)v;
        driftOn = llLinksetDataRead("drift") != "0";
        sinkOn = llLinksetDataRead("sink") != "0";
        driftAmt = (float)driftOn;
        integer s;
        for (s = 0; s < 2; ++s)
        {
            list d = savedSeat(s);
            setSeat(s, llList2Vector(d, 0), llList2Float(d, 1));
            if (llGetInventoryType(animOf(s)) != INVENTORY_ANIMATION)
                llOwnerSay("The animation " + animOf(s) + " is not in the boat: that seat keeps the ordinary sit.");
        }
        seatWho = [NULL_KEY, NULL_KEY];
        queue = [];
        permFor = NULL_KEY;
        warned = FALSE;
        nudge = FALSE;
        menu = 0;
        refreshSeats(TRUE);

        float water = llWater(ZERO_VECTOR);
        llOwnerSay("Afloat on the water at " + (string)llRound(water) + " m. If you are editing the boat, "
            + "close the edit window: it stands still while selected.");
        if (llGround(ZERO_VECTOR) > water - SINK_DEPTH - 1.0)
            llOwnerSay("The water here is shallow: the boat will touch bottom before it is fully under.");
        menuChan = -1 - (integer)llFrand(2000000000.0);
        llListen(9, "", llGetOwner(), "boat");
        llResetTime();
        t0 = 0.0;
        batchStart = 0.0;
        driftT = 0.0;
        batchSunk = 0.0;
        batchSeated = seated && sinkOn;
        nextBatch();
        llSetTimerEvent(1.0);
    }

    on_rez(integer n)
    {
        llResetScript();
    }

    changed(integer c)
    {
        if (c & CHANGED_OWNER) llResetScript();
        if (c & CHANGED_LINK)
        {
            integer was = seated;
            refreshSeats(FALSE);
            if (seated == was) return;
            if (sinkOn)
            {
                if (seated) llOwnerSay("Someone sat down: the boat starts taking on water (" + (string)llRound(SINK_TIME) + " s to go under).");
                else        llOwnerSay("Everyone stood up: the boat comes back up.");
            }
            if (llGetStatus(STATUS_PHYSICS))
            {
                llOwnerSay("Another script turned physics on. Remove the boat's other scripts.");
                llSetStatus(STATUS_PHYSICS, FALSE);
            }
            // start the new batch now, so sitting or standing shows at once (not while a nudge menu holds the boat)
            replan();
        }
    }

    run_time_permissions(integer perm)
    {
        key a = llGetPermissionsKey();
        if (a == permFor && (perm & PERMISSION_TRIGGER_ANIMATION) && llList2Key(seatWho, permSeat) == a
            && llGetInventoryType(animOf(permSeat)) == INVENTORY_ANIMATION)
        {
            llStopAnimation("sit");
            llStartAnimation(animOf(permSeat));
        }
        permFor = NULL_KEY;
        nextPerm();
    }

    moving_end()
    {
        nextBatch();
    }

    touch_start(integer n)
    {
        if (menuChan && llDetectedKey(0) == llGetOwner())
        {
            if (menu == 0) menu = 1;
            showMenu();
        }
    }

    listen(integer channel, string name, key id, string msg)
    {
        if (channel == 9)
        {
            if (menu == 0) menu = 1;
            showMenu();
        }
        else if (menu == 1) mainMenu(msg);
        else if (menu == 2) waterMenu(msg);
        else if (menu >= 3) nudgeMenu(msg);
    }

    // backup in case a batch ends without a moving_end; also the menu and permission time-outs
    timer()
    {
        float t = llGetTime();
        if (menu && t > menuUntil) closeMenu();
        if (permFor != NULL_KEY && t > permAt + 5.0)
        {
            permFor = NULL_KEY;
            nextPerm();
        }
        if (!nudge && t > batchStart + FRAMES * FRAME + 1.0) nextBatch();
    }
}
