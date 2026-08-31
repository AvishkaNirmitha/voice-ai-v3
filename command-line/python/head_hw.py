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


class RobotHeadController(SimHeadController):
    """Sends every resolved pose to the real head, and keeps it for the window.

    Inherits the simulator so .pan/.tilt stay readable: the visualiser draws
    the same numbers that go out on the wire.
    """

    def __init__(self, send_hz=SEND_HZ, settle_s=SETTLE_S, release_idle=True):
        super().__init__()
        self._period = 1.0 / send_hz
        self._settle = settle_s
        self._release_idle = release_idle
        self._last_send = 0.0
        self._quiet_since = None
        self._suspend = 0
        self._lock = threading.Lock()
        self.sent = 0

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
        head_link.jog(pan, tilt)

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


def connect(addr=None, verbose=False):
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
    return RobotHeadController()


def apply_limits(motion, timeout=2.0):
    """Ask the head how far its neck really travels and clamp the mixer to it.

    Returns True if the head answered. When it does not, the conservative
    fallback is used rather than head.py's simulated travel -- driving unknown
    servos to +/-45 is how a neck meets its own stop.
    """
    lim = head_link.limits(timeout=timeout)
    known = lim is not None
    lim = lim or FALLBACK
    motion.set_limits(lim["yaw_min"], lim["yaw_max"],
                      lim["pitch_min"], lim["pitch_max"])
    return known


def directed_look(controller, action):
    """Run a directed look on the head, with jog held off for its duration.

    Returns the sentence the head reports, or None if there is no head.
    """
    if controller is None:
        return None
    with controller.suspended():
        return head_link.look(action)
