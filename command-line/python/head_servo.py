"""head_servo.py - drives the neck's servos straight off the serial bus.

The alternative to head_hw.py. Both are the same idea -- take the pose the
mixer resolves and put it on a wire -- and they differ only in which wire:

    head_hw     pose -> UDP jog -> the head's own firmware -> servos
    head_servo  pose -> serial sync-write -> servos

That firmware is what head_hw exists to talk to. When it is not running, or
the servos are wired straight to this machine, there is nothing to talk to and
the pose has nowhere to go. --direct-servo is that case.

WHAT CHANGES, AND WHAT DOES NOT. Nothing above HeadController.write() knows the
difference: the same mixer resolves the same gestures at the same 50 Hz. Three
things are genuinely different down here, and all three follow from there being
no firmware in the path:

  no gain          head_hw multiplies by 2.2 because the head's own gesture
                   engine low-passes what it is sent. A servo commanded to an
                   absolute count with a speed and an acceleration runs its own
                   trajectory to get there, so there is nothing to pre-empt --
                   amplifying here would only drive the neck into its limits.

  no hand-back     head_hw goes quiet when the head is expressing nothing, so
                   the firmware can resume face tracking. Nothing here tracks
                   faces, so going quiet would only let the neck sag under its
                   own weight. Torque stays on and the last pose is held.

  travel is ours   there is no limits() to ask. PAN_LIMIT/TILT_LIMIT below are
                   the conservative defaults; widen them once the neck has been
                   walked to its stops with the sliders.

WHERE ZERO IS. The mixer works in degrees either side of a neutral pose; the
servos work in absolute counts. The neck's resting position at startup is
adopted as that neutral, which is why attach() is called from the scan rather
than from connect(): the scan is where the resting counts are read. Nothing
jumps when the window opens, and a neck that has been re-homed needs no edit.
"""

import threading
import time

from feetech_sts import COUNTS_PER_REV, DEG_PER_COUNT, STSError
from head import MOTION_HZ, HeadController, HeadWindow

# Read off the bench with `feetech_sts.py scan`: this neck answers on 9 and 11,
# not the 1 and 2 a fresh pair of servos ships with. Which of the two is pan is
# a guess -- override with --pan-id / --tilt-id if the axes come out swapped.
PAN_ID = 9
TILT_ID = 11

# Degrees either side of the pose the neck was resting in at startup. The same
# conservative figures head_hw falls back to when no head answers: a neck that
# turns less than we ask loses only reach, one that turns more meets its stop.
PAN_LIMIT = 30.0
TILT_LIMIT = 20.0

# Fallbacks for the servo's motion profile, used until the window's sliders
# have published theirs. These match direct_servo_call.py's own defaults.
DEFAULT_SPEED = 3400            # counts/s, the STS3215 ceiling
DEFAULT_ACCEL = 150             # units of 100 counts/s^2

SEND_HZ = 50                    # the mixer's own rate; no network to spare

# A frame arrives every 1/MOTION_HZ, so testing `elapsed < period` against a
# period that IS 1/MOTION_HZ rejects half the frames on rounding alone -- the
# stream silently runs at half the rate asked for. Allowing a frame that is
# within half a period of due fixes that without letting the rate drift up.
_SEND_SLOP = 0.5 / MOTION_HZ


class ServoHeadController(HeadController):
    """Turns each resolved pose into one broadcast packet on the servo bus.

    Writes are handed to direct_servo_call.Bridge rather than to a bus this
    class opens itself. One thread owns the port, which is the whole reason
    that class exists -- the window's sliders and this stream would otherwise
    be two threads interleaving half-duplex traffic on the same wire.
    """

    def __init__(self, pan_id=PAN_ID, tilt_id=TILT_ID,
                 pan_limit=PAN_LIMIT, tilt_limit=TILT_LIMIT,
                 invert_pan=False, invert_tilt=False):
        self.pan_id = int(pan_id)
        self.tilt_id = int(tilt_id)
        self.pan_limit = float(pan_limit)
        self.tilt_limit = float(tilt_limit)
        self.sign_pan = -1.0 if invert_pan else 1.0
        self.sign_tilt = -1.0 if invert_tilt else 1.0

        self._lock = threading.Lock()
        self._app = None            # the window, once it has scanned
        self._home = {}             # servo id -> counts at startup
        self._enabled = True
        self._period = 1.0 / SEND_HZ
        self._last_send = 0.0

        # Mirrors head_hw's counters, so the same shutdown line reads the same
        # way whichever transport was in use.
        self.sent = 0
        self.clipped = 0
        # The visualiser reads these; kept for parity with SimHeadController.
        self.pan = 0.0
        self.tilt = 0.0

    # -- identity ----------------------------------------------------------

    @property
    def servo_ids(self):
        return (self.pan_id, self.tilt_id)

    @property
    def ready(self):
        return self._app is not None and bool(self._home)

    # -- wiring ------------------------------------------------------------

    def attach(self, app, found):
        """Adopt the window's bus and the neck's resting pose as zero.

        `found` maps every servo id the scan answered to the counts it was
        sitting at. Missing ids are reported rather than guessed: commanding a
        servo that is not there is silent on a broadcast write, so the neck
        would simply half-move with no error anywhere.
        """
        missing = [s for s in self.servo_ids if s not in found]
        with self._lock:
            self._app = app
            self._home = {s: int(found[s]) for s in self.servo_ids if s in found}
        if missing:
            print(f"[servo] servo id {missing} did not answer the scan - "
                  f"that axis will not move. Check wiring, power and IDs; "
                  f"the scan found {sorted(found)}.")
        else:
            self._check_headroom()
            print(f"[servo] neck adopted: pan id {self.pan_id} @ "
                  f"{self._home[self.pan_id]} counts, tilt id {self.tilt_id} @ "
                  f"{self._home[self.tilt_id]} counts (this pose is now zero)")
            print(f"[servo] travel +/-{self.pan_limit:.0f} pan, "
                  f"+/-{self.tilt_limit:.0f} tilt")

    def _check_headroom(self):
        """Warn when the pose adopted as zero leaves an axis nowhere to go.

        Zero is wherever the neck was resting at startup, which is only a
        sensible zero if the neck was resting somewhere near its middle. Left
        at an extreme by the previous run, the adopted zero sits against the
        end of the servo's single turn and _counts() clamps every command that
        would move that way -- the axis simply stops in one direction, with
        nothing in the log to say why. Hence this, loudly, at startup.
        """
        for name, servo_id, limit in (("pan", self.pan_id, self.pan_limit),
                                      ("tilt", self.tilt_id, self.tilt_limit)):
            home = self._home[servo_id]
            span = limit / DEG_PER_COUNT
            low, high = home - span, home + span
            if low >= 0 and high <= COUNTS_PER_REV - 1:
                continue
            lost = ("below" if low < 0 else "above")
            print(f"[servo] WARNING: {name} (id {servo_id}) is resting at "
                  f"{home} counts = {home * DEG_PER_COUNT:.1f} deg, which is "
                  f"{abs(low if low < 0 else high - (COUNTS_PER_REV - 1)):.0f} "
                  f"counts short of the +/-{limit:.0f} deg it needs {lost} it.")
            print(f"[servo]          That axis will hit the clamp and stop "
                  f"moving that way. Centre the neck by hand (or with the "
                  f"sliders) and restart.")

    def set_enabled(self, on):
        with self._lock:
            self._enabled = bool(on)

    # -- the pose stream ---------------------------------------------------

    def _counts(self, servo_id, degrees, sign):
        """Absolute counts for an angle measured from the startup pose."""
        counts = self._home[servo_id] + sign * degrees / DEG_PER_COUNT
        # A hard stop on top of the degree clamp. The degree limits are a
        # guess at the mechanism; this one is arithmetic, and catches a home
        # position near either end of the servo's single turn.
        return int(round(max(0, min(COUNTS_PER_REV - 1, counts))))

    def write(self, pan, tilt, active=True):
        # `active` is ignored on purpose -- see the module docstring.
        self.pan, self.tilt = pan, tilt
        now = time.monotonic()
        if now - self._last_send < self._period - _SEND_SLOP:
            return
        with self._lock:
            app, home, enabled = self._app, self._home, self._enabled
        if app is None or not enabled or len(home) < 2:
            return
        self._last_send = now

        # A guard, not the working limit: HeadMotion has already clamped this
        # pose to the same travel, so in normal running this never fires and
        # `clipped` stays at 0. A non-zero count means a pose reached the bus
        # without passing the mixer's clamp, which is worth knowing about.
        clamped_pan = max(-self.pan_limit, min(self.pan_limit, pan))
        clamped_tilt = max(-self.tilt_limit, min(self.tilt_limit, tilt))
        if clamped_pan != pan or clamped_tilt != tilt:
            self.clipped += 1

        targets = {}
        for servo_id, degrees, sign in (
                (self.pan_id, clamped_pan, self.sign_pan),
                (self.tilt_id, clamped_tilt, self.sign_tilt)):
            speed, accel = app.profile(servo_id, (DEFAULT_SPEED, DEFAULT_ACCEL))
            targets[servo_id] = (self._counts(servo_id, degrees, sign),
                                 speed or DEFAULT_SPEED, accel)
        try:
            app.bridge.set_pose(targets)
            self.sent += 1
        except (STSError, OSError) as exc:
            print(f"[servo] pose dropped: {exc}")

    def close(self):
        """Release torque, so the neck is not left straining after exit."""
        with self._lock:
            app = self._app
        if app is None:
            return
        for servo_id in self.servo_ids:
            app.bridge.submit(
                lambda bus, s=servo_id: bus.set_torque(s, False))


def parse_invert(spec):
    """Read --servo-invert into (invert_pan, invert_tilt). See head_hw."""
    if spec is None:
        return False, False
    axes = {a.strip().lower() for a in str(spec).split(",") if a.strip()}
    axes.discard("none")
    unknown = axes - {"pan", "tilt"}
    if unknown:
        raise ValueError(f"--servo-invert: unknown axis {sorted(unknown)}; "
                         "expected pan, tilt, none, or pan,tilt")
    return "pan" in axes, "tilt" in axes


def start(motion, controller, port=None, baud=1_000_000, simulation=True):
    """Open the servo panel -- and the head simulation beside it -- on one
    thread, and connect the bus.

    ONE ROOT, ONE THREAD, ONE MAINLOOP. Both windows live under the same Tk
    root: the servo panel is the root itself, and the simulation is a Toplevel
    of it. A second Tk() on a second thread would be the obvious way to get two
    windows and a reliable way to hang the interpreter instead.

    The panel is the root rather than the simulation because it owns the
    serial port -- closing it runs App._on_close, which releases torque. The
    simulation is a borrowed window and closing it only hides itself.

    None of this can be the main thread: mainloop() never returns and the
    conversation needs that thread. The panel is also where the bus is opened
    and scanned, which is what eventually calls controller.attach().
    """
    import direct_servo_call as gui

    def run():
        import tkinter as tk
        from tkinter import ttk
        root = tk.Tk()
        root.title("Spera neck - direct servo control")
        root.minsize(660, 420)
        try:
            ttk.Style().theme_use("clam")
        except tk.TclError:
            pass
        app = gui.App(root, port or gui.DEFAULT_PORT, baud, driver=controller)
        if simulation:
            try:
                HeadWindow(motion).build(root)
            except Exception as exc:
                print(f"[head] no simulation window ({exc}); servo panel only")
        # Connect straight away: standalone the user clicks Connect, but here
        # the neck is meant to be live from the moment the robot starts.
        root.after(200, app._toggle_connect)
        root.mainloop()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread
