"""head_hw.py - drives the real robot head from the simulation's pose stream.

The simulation and the hardware are the same motion: head.py resolves one pose
per frame, and RobotHeadController forwards it over head_link as an absolute
jog. Whatever the window draws is what the neck is being told to do, so the two
cannot drift apart.

WHY jog AND NOT speak. head_link also offers speak()/stop(), which hand the
sentence and its [head_*] tags to the head's own gesture engine. That path is
not used here, for two reasons. It would replay Gemini's raw tags, and those
are unreliable enough that head.plan_sentence deliberately overrules them --
the model tags questions as shakes and refusals as calm. And it would put a
second gesture engine on the same neck, so the window would stop being a
picture of what the head is doing. One engine, one pose stream.

look() IS used, from the look_around tool: it blocks until the neck has
finished sweeping and returns the sentence the head wants said, which is a
better answer than anything this side could invent. Jog packets have to stop
while it runs -- one arriving mid-look abandons the look -- which is what
suspended() is for.

WHICH WAY IS UP. The simulation and the neck have to agree on the sign of each
axis or the window becomes actively misleading -- it lifts its chin while the
real head drops it. INVERT_PAN/INVERT_TILT below reconcile the two frames, and
they do it at the wire and only at the wire: see the note on them.

HANDING THE HEAD BACK. While jog packets arrive the head stops tracking faces
and stops gesturing on its own, and it takes itself back about two seconds
after the last one. So this controller goes quiet when head.py reports that
nothing is being expressed, rather than idling at 25 Hz forever: an idle robot
gets its own face tracking back. Set release_idle=False to keep the neck under
this program's control for as long as it runs.
"""

import contextlib
import threading
import time

import head_link
from head import SimHeadController

# The neck cannot follow faster than this, so anything above it is wasted
# bandwidth rather than smoother motion. head.py resolves at 50 Hz, so roughly
# every second frame goes out.
SEND_HZ = 25

# Keep sending a settled pose for this long after the head stops expressing
# anything, then go quiet. Long enough to cover a dropped packet, far short of
# the head's ~2 s hand-back.
SETTLE_S = 0.3

# Used only when the head does not answer limits(). Deliberately smaller than
# head.py's simulated travel: a neck that turns further than we ask loses only
# reach, one that turns less would be driven into its stop.
FALLBACK = {"yaw_min": -30.0, "yaw_max": 30.0,
            "pitch_min": -20.0, "pitch_max": 20.0}

# COMMANDED ANGLE IS NOT ACHIEVED ANGLE. The simulation has no inertia, so it
# swings the full amplitude the mixer asks for. A real neck has mass and a
# servo with its own speed ceiling, so it low-passes the gesture and arrives at
# a fraction of it -- the faster the gesture, the smaller the fraction. The
# wire therefore carries a pre-compensated command: the window keeps showing
# the intended pose, and this scales it up so the neck actually gets there.
#
# This is calibration, not licence. The result is still clamped to the travel
# the head itself reported, so gain can never drive a servo into its stop; too
# much of it just flattens the tops of a gesture, which `clipped` counts.
GAIN_PAN = 2.2
GAIN_TILT = 2.2

# WHICH WAY IS UP ON THE REAL NECK. head.py and the head_link protocol agree on
# paper -- pan/yaw + is the robot's right, tilt/pitch + is up -- but a servo
# that is mounted or geared the other way round makes the hardware read that
# convention backwards, and then the window and the neck disagree: the
# simulation lifts its chin while the real head drops it.
#
# The correction belongs HERE and nowhere else. Flipping a sign in head.py
# would flip the window too, so the two would agree by both being wrong;
# flipping it inside a gesture would fix that gesture and leave the state poses
# and the RMS accent inverted. This is the single place where the simulation's
# pose becomes a wire command, so this is where the frames are reconciled --
# the window keeps showing the intended pose and only the datagram is flipped.
#
# Both axes are mirrored on this build of the neck: confirmed on the bench,
# the window turning left while the head turned right and lifting its chin
# while the head dropped it. Set from main_with_head.py's --invert.
INVERT_PAN = True
INVERT_TILT = True


def _orient(lo, hi, invert):
    """Re-express one axis's travel from the head's frame in the simulation's.

    Inverting an axis does not merely negate its bounds, it SWAPS them: a neck
    that pitches -24.9..+33.7 accepts simulated tilts of -33.7..+24.9. Negating
    without swapping yields min > max, and every clamp after it collapses the
    axis onto a single angle -- the head would simply stop moving on it.
    """
    return (-hi, -lo) if invert else (lo, hi)


class RobotHeadController(SimHeadController):
    """Sends every resolved pose to the real head, and keeps it for the window.

    Inherits the simulator so .pan/.tilt stay readable: the visualiser draws
    the same numbers that go out on the wire.
    """

    def __init__(self, send_hz=SEND_HZ, settle_s=SETTLE_S, release_idle=True,
                 gain_pan=GAIN_PAN, gain_tilt=GAIN_TILT,
                 invert_pan=None, invert_tilt=None):
        super().__init__()
        self._period = 1.0 / send_hz
        self._settle = settle_s
        self._release_idle = release_idle
        self._last_send = 0.0
        self._quiet_since = None
        self._suspend = 0
        self._lock = threading.Lock()
        self.gain_pan = float(gain_pan)
        self.gain_tilt = float(gain_tilt)
        # Read at construction, not at send time, so a controller built for a
        # test can differ from the module default.
        self.invert_pan = INVERT_PAN if invert_pan is None else bool(invert_pan)
        self.invert_tilt = INVERT_TILT if invert_tilt is None else bool(invert_tilt)
        # The neck's own travel, which bounds whatever the gain produces, held
        # in the SIMULATION's frame so the clamp and the pose it clamps are
        # measured the same way round. Replaced by apply_limits() when the head
        # answers.
        self.pan_min, self.pan_max = _orient(
            FALLBACK["yaw_min"], FALLBACK["yaw_max"], self.invert_pan)
        self.tilt_min, self.tilt_max = _orient(
            FALLBACK["pitch_min"], FALLBACK["pitch_max"], self.invert_tilt)
        self.sent = 0
        self.clipped = 0        # frames the gain pushed past the neck's travel

    def set_limits(self, pan_min, pan_max, tilt_min, tilt_max):
        """Adopt the neck's travel. Takes SIMULATION-frame bounds -- see
        apply_limits(), which is what converts the head's own numbers."""
        with self._lock:
            self.pan_min, self.pan_max = float(pan_min), float(pan_max)
            self.tilt_min, self.tilt_max = float(tilt_min), float(tilt_max)

    def write(self, pan, tilt, active=True):
        super().write(pan, tilt)        # the window reads these
        now = time.monotonic()
        if now - self._last_send < self._period:
            return                      # 50 Hz in, 25 Hz out
        with self._lock:
            if self._suspend:
                return                  # a directed look owns the neck
        if active or not self._release_idle:
            self._quiet_since = None
        elif self._quiet_since is None:
            self._quiet_since = now     # keep sending through the settle window
        elif now - self._quiet_since > self._settle:
            return                      # silence: the head takes itself back
        self._last_send = now
        self.sent += 1
        # Amplify, then bound by the real neck. In that order: the clamp is the
        # safety net and has to be the last thing that CONSTRAINS the number.
        out_pan = max(self.pan_min, min(self.pan_max, pan * self.gain_pan))
        out_tilt = max(self.tilt_min, min(self.tilt_max, tilt * self.gain_tilt))
        if out_pan != pan * self.gain_pan or out_tilt != tilt * self.gain_tilt:
            self.clipped += 1
        # Into the head's frame last of all. The sign flip is a change of
        # coordinates, not of magnitude, so it cannot undo the clamp above --
        # the bounds it was clamped to were converted the same way round.
        if self.invert_pan:
            out_pan = -out_pan
        if self.invert_tilt:
            out_tilt = -out_tilt
        head_link.jog(out_pan, out_tilt)

    @contextlib.contextmanager
    def suspended(self):
        """Hold jog packets off the wire while something else owns the neck."""
        with self._lock:
            self._suspend += 1
        try:
            yield
        finally:
            with self._lock:
                self._suspend = max(0, self._suspend - 1)
            # Resume from wherever the head left the neck rather than snapping
            # from a stale pose.
            self._last_send = 0.0


def parse_invert(spec):
    """Read an --invert argument into (invert_pan, invert_tilt).

        "pan,tilt"  the shipped default: this neck runs mirrored on both
        "tilt"      pitch only
        "none"/""   trust the protocol's convention as documented

    Returns the module defaults when spec is None, so not passing the flag
    leaves the constants above in charge.
    """
    if spec is None:
        return INVERT_PAN, INVERT_TILT
    axes = {a.strip().lower() for a in str(spec).split(",") if a.strip()}
    axes.discard("none")
    unknown = axes - {"pan", "tilt", "yaw", "pitch"}
    if unknown:
        raise ValueError(f"--invert: unknown axis {sorted(unknown)}; "
                         "expected pan, tilt, none, or pan,tilt")
    return bool(axes & {"pan", "yaw"}), bool(axes & {"tilt", "pitch"})


def connect(addr=None, verbose=False, gain=None, invert=None):
    """Point head_link at the head. Returns a controller, or None if disabled.

    Never raises and never blocks on the head being present: UDP sendto to a
    machine that is not listening simply succeeds, which is why limits() below
    is the only real test of whether anything is there.
    """
    # head_link ships VERBOSE on, which at 25 packets a second would bury the
    # transcript this program exists to show.
    head_link.VERBOSE = verbose
    if addr:
        host, _, port = str(addr).partition(":")
        head_link.set_target(host or "127.0.0.1", int(port or 8770))
    inv_pan, inv_tilt = parse_invert(invert)
    kw = {"invert_pan": inv_pan, "invert_tilt": inv_tilt}
    if gain is not None:
        kw["gain_pan"] = kw["gain_tilt"] = float(gain)
    ctl = RobotHeadController(**kw)
    mirrored = ", ".join(n for n, on in (("pan", inv_pan), ("tilt", inv_tilt)) if on)
    print(f"[head] axes mirrored on the wire: {mirrored or 'none'}")
    return ctl


def apply_limits(motion, controller=None, timeout=2.0):
    """Ask the head how far its neck really travels and clamp the mixer to it.

    Returns True if the head answered. When it does not, the conservative
    fallback is used rather than head.py's simulated travel -- driving unknown
    servos to +/-45 is how a neck meets its own stop.
    """
    lim = head_link.limits(timeout=timeout)
    known = lim is not None
    lim = lim or FALLBACK
    # The head reports its travel in its OWN frame; the mixer and the
    # controller both clamp poses expressed in the simulation's. On a mirrored
    # axis those are not the same interval -- an asymmetric neck reporting
    # pitch -24.9..+33.7 can be driven to a simulated tilt of -33.7..+24.9 --
    # so the bounds are converted before either of them sees a number.
    inv_pan = getattr(controller, "invert_pan", INVERT_PAN)
    inv_tilt = getattr(controller, "invert_tilt", INVERT_TILT)
    pan_min, pan_max = _orient(lim["yaw_min"], lim["yaw_max"], inv_pan)
    tilt_min, tilt_max = _orient(lim["pitch_min"], lim["pitch_max"], inv_tilt)
    motion.set_limits(pan_min, pan_max, tilt_min, tilt_max)
    if controller is not None:
        # The controller needs them as well: it applies the gain *after* the
        # mixer has already clamped, so it owns the last word on travel.
        controller.set_limits(pan_min, pan_max, tilt_min, tilt_max)
    return known


def directed_look(controller, action):
    """Run a directed look on the head, with jog held off for its duration.

    Returns the sentence the head reports, or None if there is no head.
    """
    if controller is None:
        return None
    with controller.suspended():
        return head_link.look(action)
