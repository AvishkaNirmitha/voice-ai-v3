#!/usr/bin/env python3
"""Drive two Feetech STS3215 servos over the motor control board.

Reads a target angle from stdin, sends it, waits until the servo reports it
has stopped moving, and prints how long the move took.

Usage:
    source .venv/bin/activate
    python feetech_servo.py                       # /dev/ttyACM2, ids 9 and 11
    python feetech_servo.py --port /dev/ttyACM0 --ids 1 2 3

At the prompt:
    90            -> move every servo to 90 deg
    9 90          -> move servo 9 to 90 deg
    9 90 11 180   -> move servo 9 to 90 and servo 11 to 180 together
    r             -> read and print the current position of every servo
    t             -> torque off (servos go limp), 'T' turns it back on
    q             -> quit

Other modes:
    python feetech_servo.py --stream        50 Hz streaming demo + tracking report
    python feetech_servo.py --tune-pgain    sweep the position P gain, then restore

WHY STREAMING EXISTS. A point-to-point move pays a fixed ~83 ms of internal
servo startup latency and then decelerates to a standstill, so stepping to a
pose costs 400-900 ms. That latency is not a stall, it is a lag: if goal
positions keep arriving the servo stays mid-profile and absorbs them
continuously. Measured on this hardware, streaming 50 Hz position writes
tracks a 30 deg/s ramp to within 2.7 deg and a 60 deg/s ramp to within 7.4
deg, and saturates at ~130 deg/s. So the neck is driven by streaming a pose,
never by stepping to one.
"""

import argparse
import math
import statistics
import sys
import time

from scservo_sdk import COMM_SUCCESS, GroupSyncWrite, PacketHandler, PortHandler

# STS3215 control table (SCS/STS series, little-endian words).
ADDR_TORQUE_ENABLE = 40
ADDR_GOAL_ACC = 41
ADDR_GOAL_POSITION = 42
ADDR_GOAL_SPEED = 46
ADDR_PRESENT_POSITION = 56
ADDR_MOVING = 66

# The STS3215 is a 0..4095 step encoder over a 0..360 deg range.
STEPS_PER_REV = 4096
DEG_PER_STEP = 360.0 / STEPS_PER_REV

ADDR_P_GAIN = 21
ADDR_D_GAIN = 22
ADDR_I_GAIN = 23
ADDR_LOCK = 55

PROTOCOL_END = 0        # STS/SMS servos are little-endian; SCS servos use 1.
BAUDRATE = 1000000

# Measured ceiling on these units: ~130 deg/s sustained, so ~2.6 deg per 20 ms
# frame. Commanding past it does not go faster, it just opens a tracking error
# that has to be paid back later -- which reads as the neck overshooting and
# then catching up. The slew limiter below exists to keep that from happening.
MAX_VEL_DEG_S = 130.0
STREAM_HZ = 50


def deg_to_steps(deg):
    """Absolute degrees to encoder steps, CLAMPED rather than wrapped.

    Wrapping here is not a harmless modulo. The STS3215 has hard angle limits
    at 0 and 4095 and does not take the short way round, so letting -30 deg
    become 330 deg does not nudge the joint back a little -- it drives it 330
    degrees forward, through everything in the way. Clamping turns that into a
    joint that simply stops at its limit.
    """
    steps = int(round(deg / DEG_PER_STEP))
    return max(0, min(STEPS_PER_REV - 1, steps))


def steps_to_deg(steps):
    return steps * DEG_PER_STEP


class ServoBus:
    def __init__(self, port, ids, baudrate=BAUDRATE, speed=2400, accel=50):
        self.ids = list(ids)
        self.speed = speed
        self.accel = accel
        self.port = PortHandler(port)
        self.packet = PacketHandler(PROTOCOL_END)

        if not self.port.openPort():
            raise RuntimeError("failed to open %s" % port)
        if not self.port.setBaudRate(baudrate):
            raise RuntimeError("failed to set baudrate %d on %s" % (baudrate, port))

        for sid in self.ids:
            model, comm, err = self.packet.ping(self.port, sid)
            if comm != COMM_SUCCESS:
                raise RuntimeError(
                    "no response from servo id %d on %s: %s"
                    % (sid, port, self.packet.getTxRxResult(comm))
                )
            print("servo %d found (model %d)" % (sid, model))

        self.set_torque(True)

    def set_torque(self, on):
        for sid in self.ids:
            self.packet.write1ByteTxRx(self.port, sid, ADDR_TORQUE_ENABLE, 1 if on else 0)

    def read_position(self, sid):
        """Present position in degrees, or None if the read failed.

        The SDK indexes its payload before checking the result code, so a
        truncated reply surfaces as IndexError rather than a comm status --
        which under a hard-driving servo is a glitch to skip, not a crash.
        """
        try:
            steps, comm, err = self.packet.read2ByteTxRx(
                self.port, sid, ADDR_PRESENT_POSITION)
        except (IndexError, TypeError):
            return None
        if comm != COMM_SUCCESS or err != 0:
            return None
        return steps_to_deg(steps)

    def is_moving(self, sid):
        try:
            flag, comm, err = self.packet.read1ByteTxRx(self.port, sid, ADDR_MOVING)
        except (IndexError, TypeError):
            return False
        if comm != COMM_SUCCESS:
            return False
        return bool(flag)

    def write_goals(self, targets):
        """targets: {servo_id: degrees}. All servos start moving in one packet."""
        group = GroupSyncWrite(self.port, self.packet, ADDR_GOAL_ACC, 7)
        for sid, deg in targets.items():
            steps = deg_to_steps(deg)
            # acc, pos_lo, pos_hi, time_lo, time_hi, speed_lo, speed_hi
            param = [
                self.accel & 0xFF,
                steps & 0xFF, (steps >> 8) & 0xFF,
                0, 0,
                self.speed & 0xFF, (self.speed >> 8) & 0xFF,
            ]
            if not group.addParam(sid, param):
                raise RuntimeError("syncwrite addParam failed for id %d" % sid)
        comm = group.txPacket()
        if comm != COMM_SUCCESS:
            raise RuntimeError("syncwrite failed: %s" % self.packet.getTxRxResult(comm))
        group.clearParam()

    def move_and_time(self, targets, tolerance=1.5, settle=0.05, timeout=10.0):
        """Send the goals and block until every servo stops.

        Returns (total_seconds, dead_seconds). dead_seconds is the gap between
        the goal packet going out and the first servo actually breaking away
        from its start pose -- on an STS3215 that is a fixed ~83 ms of internal
        startup latency, and it is worth seeing separately from travel time.
        """
        start = time.perf_counter()
        origin = {sid: self.read_position(sid) for sid in targets}
        self.write_goals(targets)

        stable_since = {sid: None for sid in targets}
        done = set()
        dead = None
        while len(done) < len(targets):
            if time.perf_counter() - start > timeout:
                print("  timeout: %s never reported arrival"
                      % sorted(set(targets) - done))
                break
            now = time.perf_counter()
            for sid, goal in targets.items():
                if sid in done:
                    continue
                pos = self.read_position(sid)
                if pos is None:
                    continue
                if dead is None and origin[sid] is not None:
                    if abs((pos - origin[sid] + 180.0) % 360.0 - 180.0) > 0.5:
                        dead = now - start
                error = abs((pos - goal + 180.0) % 360.0 - 180.0)
                if error <= tolerance and not self.is_moving(sid):
                    # Require the servo to hold still briefly so we do not
                    # latch on a position sampled while it coasts through.
                    if stable_since[sid] is None:
                        stable_since[sid] = now
                    elif now - stable_since[sid] >= settle:
                        done.add(sid)
                else:
                    stable_since[sid] = None

        elapsed = time.perf_counter() - start - settle
        return max(elapsed, 0.0), dead

    # -- streaming -----------------------------------------------------
    #
    # The point-to-point path above is a bench tool. Everything that has to
    # look like motion goes through here instead: configure the profile once,
    # then push nothing but goal position, one small increment per frame.

    def configure_stream(self, speed=0, accel=None):
        """Set the profile once so streaming writes carry position only.

        speed=0 means uncapped -- the slew limiter, not the servo, decides how
        far a frame may travel, because the servo's own limiter would ramp
        down near each target and reintroduce the stop-start we are avoiding.
        """
        for sid in self.ids:
            self.packet.write1ByteTxRx(self.port, sid, ADDR_GOAL_ACC,
                                       self.accel if accel is None else accel)
            self.packet.write2ByteTxRx(self.port, sid, ADDR_GOAL_SPEED, speed)

    def stream_write(self, targets):
        """Push goal positions for this frame. No status read, so ~0.2 ms."""
        group = GroupSyncWrite(self.port, self.packet, ADDR_GOAL_POSITION, 2)
        for sid, deg in targets.items():
            steps = deg_to_steps(deg)
            group.addParam(sid, [steps & 0xFF, (steps >> 8) & 0xFF])
        group.txPacket()
        group.clearParam()

    def _read_byte(self, sid, addr, retries=8):
        """One byte, read until two consecutive attempts agree.

        THE FIRST READ AFTER A WRITE IS A LIE. On these servos the read
        immediately following any write comes back 242 -- reproducibly, at
        every inter-command delay from 20 ms to 100 ms, and with a clean
        COMM_SUCCESS, so neither a longer sleep nor a status check catches it.
        The second read is correct. Requiring agreement is what makes a gain
        readback trustworthy; taking the first value is how a verified restore
        reports a failure that did not happen.
        """
        last = None
        for _ in range(retries):
            try:
                v, comm, err = self.packet.read1ByteTxRx(self.port, sid, addr)
            except (IndexError, TypeError):
                v, comm, err = None, -1, -1
            if comm == COMM_SUCCESS and err == 0:
                if v == last:
                    return v
                last = v
            else:
                last = None
            time.sleep(0.005)
        return last

    def read_gains(self, sid):
        return tuple(self._read_byte(sid, a)
                     for a in (ADDR_P_GAIN, ADDR_D_GAIN, ADDR_I_GAIN))

    def write_p_gain(self, sid, value, verify=True):
        """Set the position P coefficient, and confirm it landed.

        P/D/I live in the EEPROM block, so the lock at ADDR_LOCK has to come
        off around the write. The sleeps are not decoration: the servo needs a
        moment to commit, and writing the lock back too early is how a gain
        ends up half-written.
        """
        value = int(value)
        self.packet.write1ByteTxRx(self.port, sid, ADDR_LOCK, 0)
        time.sleep(0.02)
        self.packet.write1ByteTxRx(self.port, sid, ADDR_P_GAIN, value)
        time.sleep(0.02)
        self.packet.write1ByteTxRx(self.port, sid, ADDR_LOCK, 1)
        time.sleep(0.02)
        if not verify:
            return True
        got = self._read_byte(sid, ADDR_P_GAIN)
        if got != value:
            print("  WARNING: servo %d P gain read back as %s, wanted %d"
                  % (sid, got, value))
            return False
        return True

    def close(self, release=False):
        # Torque stays on by default: a loaded joint would drop if we cut it.
        if release:
            self.set_torque(False)
        self.port.closePort()


# --- head integration -----------------------------------------------------
#
# head.py resolves one pose per frame and hands it to a HeadController. This is
# that controller, talking to the servos directly rather than over head_link,
# so the drop-in at head.py's FeetechController stub is:
#
#     from feetech_servo import ServoBus, FeetechController
#     bus = ServoBus("/dev/ttyACM2", [9, 11])
#     controller = FeetechController(bus, pan=Joint(9, 226.0, 196.0, 256.0),
#                                         tilt=Joint(11, 20.0, 0.0, 45.0))
#
# and nothing else in head.py changes.


class Joint:
    """One servo's mapping from head.py's signed degrees to absolute steps.

    head.py thinks in degrees either side of centre; the servo thinks in a
    0..360 absolute encoder. `lo`/`hi` are that servo's real mechanical travel
    and are the last thing applied, so no gain or overshoot upstream can drive
    the joint into its own stop.
    """

    def __init__(self, sid, center, lo, hi, sign=1.0):
        self.sid = sid
        self.center = float(center)
        self.lo = float(lo)
        self.hi = float(hi)
        self.sign = float(sign)

    def to_absolute(self, deg):
        raw = self.center + self.sign * float(deg)
        clamped = max(self.lo, min(self.hi, raw))
        return clamped, clamped != raw


class FeetechController:
    """Streams head.py's pose to the servos at a fixed rate.

    Exposes .pan/.tilt like SimHeadController so the visualiser keeps reading
    the same numbers that go on the wire.
    """

    def __init__(self, bus, pan, tilt, send_hz=STREAM_HZ,
                 max_vel=MAX_VEL_DEG_S):
        self.bus = bus
        self.joints = {"pan": pan, "tilt": tilt}
        self._period = 1.0 / send_hz
        self._max_step = max_vel * self._period
        self._last_send = 0.0
        self.pan = 0.0
        self.tilt = 0.0
        self.sent = 0
        self.clipped = 0        # frames the travel limit had to bite
        self.slewed = 0         # frames asked for more than the servo can do
        bus.configure_stream(speed=0)
        # Start the ramp from where the servos actually are, so the first
        # frame is an increment rather than a jump across the whole range.
        self._out = {}
        for name, j in self.joints.items():
            here = bus.read_position(j.sid)
            self._out[name] = here if here is not None else j.center

    def write(self, pan, tilt, active=True):
        self.pan, self.tilt = pan, tilt
        now = time.monotonic()
        if now - self._last_send < self._period:
            return
        self._last_send = now
        targets = {}
        for name, value in (("pan", pan), ("tilt", tilt)):
            j = self.joints[name]
            want, clipped = j.to_absolute(value)
            if clipped:
                self.clipped += 1
            # Slew limit. The servo cannot exceed ~130 deg/s, so commanding
            # past it does not move faster -- it only builds a tracking error
            # the servo pays back as an overshoot once the command slows.
            # Clamping here keeps commanded and achieved pose in step.
            delta = want - self._out[name]
            if abs(delta) > self._max_step:
                want = self._out[name] + math.copysign(self._max_step, delta)
                self.slewed += 1
            self._out[name] = want
            targets[j.sid] = want
        self.bus.stream_write(targets)
        self.sent += 1

    def close(self):
        # Torque stays on: releasing drops a loaded neck.
        self.bus.close()


def parse_command(line, ids):
    """Return {id: degrees} for a command line, or None if it is not a move."""
    parts = line.split()
    values = []
    for p in parts:
        try:
            values.append(float(p))
        except ValueError:
            return None

    if len(values) == 1:
        return {sid: values[0] for sid in ids}
    if len(values) % 2 == 0:
        targets = {}
        for i in range(0, len(values), 2):
            sid = int(values[i])
            if sid not in ids:
                print("servo %d is not on the bus (have %s)" % (sid, ids))
                return None
            targets[sid] = values[i + 1]
        return targets
    print("expected one angle, or id/angle pairs")
    return None


def _check_range(home, amp, label):
    """Refuse to run a demo whose excursion would hit the 0/360 wall.

    The servo's usable range is 0..360 absolute with no wraparound, so a
    centre too close to either end cannot swing symmetrically. Better to say
    so than to clamp silently and report a flattened result as data.
    """
    lo, hi = home - amp, home + amp
    if lo < 0.0 or hi > 359.9:
        print("\n  REFUSING %s: centre %.1f deg +/- %.1f deg spans %.1f..%.1f,"
              % (label, home, amp, lo, hi))
        print("  which leaves the servo's 0..360 range. Park it nearer the")
        print("  middle first -- e.g. --center %.0f -- or lower --span."
              % max(amp, min(360.0 - amp, 180.0)))
        return False
    return True


def _track(bus, sid, profile, duration, hz=STREAM_HZ):
    """Stream profile(t) to one servo and record commanded vs achieved."""
    period = 1.0 / hz
    rows = []
    t0 = time.perf_counter()
    frame = 0
    while True:
        now = time.perf_counter() - t0
        if now > duration:
            break
        cmd = profile(now)
        bus.stream_write({sid: cmd})
        actual = bus.read_position(sid)
        if actual is not None:
            rows.append((now, cmd, actual))
        frame += 1
        target = t0 + frame * period
        while time.perf_counter() < target:
            pass
    return rows


def _report(rows, label, settle=0.15):
    """Lag and error over the steady part of the ramp.

    Trimmed at both ends: the first `settle` seconds are the servo picking the
    ramp up, and everything from the moment the command stops rising is the
    servo catching up to a target that is no longer moving. Averaging either
    into the lag is what makes a saturated run look like a slow one.
    """
    rising = [r for r in rows if r[0] > settle]
    if rising:
        top = max(c for _, c, _ in rows)
        # Drop the tail once the commanded ramp has flattened against its span.
        rising = [r for r in rising if r[1] < top - 1e-6]
    body = rising
    if len(body) < 6:
        print("  %-22s ramp too short to measure (raise --span)" % label)
        return
    errs = [c - a for _, c, a in body]
    mean_err = sum(errs) / len(errs)
    rms = (sum(e * e for e in errs) / len(errs)) ** 0.5
    peak = max(abs(e) for e in errs)
    vel = (body[-1][1] - body[0][1]) / (body[-1][0] - body[0][0])
    lag = (mean_err / vel) if abs(vel) > 1.0 else float("nan")
    achieved = (body[-1][2] - body[0][2]) / (body[-1][0] - body[0][0])
    print("  %-22s rms %5.2f deg  peak %5.2f deg  lag %6.1f ms  "
          "cmd %6.1f -> got %6.1f deg/s"
          % (label, rms, peak, lag * 1000.0, vel, achieved))


def mode_stream(bus, args):
    """Show that 50 Hz streaming is continuous, and how well it tracks."""
    sid = args.ids[0]
    if args.center is not None:
        print("parking servo %d at %.1f deg" % (sid, args.center))
        bus.move_and_time({sid: args.center})
    home = bus.read_position(sid)
    print("streaming on servo %d at %d Hz, centred on %.1f deg" % (sid, args.hz, home))
    print("a %d Hz frame is %.1f ms, and at the measured %.0f deg/s ceiling the"
          % (args.hz, 1000.0 / args.hz, MAX_VEL_DEG_S))
    print("servo can advance %.2f deg per frame -- that, not a whole move, is"
          % (MAX_VEL_DEG_S / args.hz))
    print("what has to fit in one frame.\n")
    bus.configure_stream(speed=0)

    if not _check_range(home + args.span / 2.0, args.span / 2.0, "ramps"):
        return
    print("ramps (constant velocity):")
    for vel in (30, 60, 120, 200):
        span = args.span
        # Ramp for exactly as long as the span allows, plus a little tail so
        # the trim in _report has something to cut against.
        dur = span / float(vel) + 0.25
        bus.stream_write({sid: home})
        time.sleep(1.0)
        rows = _track(bus, sid, lambda t, v=vel, s=span: home + min(v * t, s),
                      dur, args.hz)
        _report(rows, "%d deg/s" % vel)
        bus.stream_write({sid: home})
        time.sleep(0.8)

    print("\nsine sweep (what a gesture actually looks like):")
    if not _check_range(home, args.span / 2.0, "sine sweep"):
        return
    for freq in (0.25, 0.5, 1.0, 2.0):
        amp = args.span / 2.0
        bus.stream_write({sid: home})
        time.sleep(1.0)
        rows = _track(bus, sid,
                      lambda t, f=freq, a=amp: home + a * math.sin(2 * math.pi * f * t),
                      max(2.0, 2.0 / freq), args.hz)
        body = [r for r in rows if r[0] > 0.3]
        cmd_amp = (max(c for _, c, _ in body) - min(c for _, c, _ in body)) / 2
        got_amp = (max(a for _, _, a in body) - min(a for _, _, a in body)) / 2
        peak_v = 2 * math.pi * freq * amp
        print("  %4.2f Hz +/-%4.1f deg   peak %5.1f deg/s   amplitude reached "
              "%5.1f / %5.1f deg (%3.0f%%)"
              % (freq, amp, peak_v, got_amp, cmd_amp, 100 * got_amp / cmd_amp))
        bus.stream_write({sid: home})
        time.sleep(0.8)
    bus.stream_write({sid: home})
    time.sleep(0.8)


def mode_bandwidth(bus, args):
    """Amplitude vs frequency: how big a gesture survives at what speed.

    A sine of amplitude A at frequency f needs a peak velocity of 2*pi*f*A.
    Since the servo has a fixed velocity ceiling, the biggest gesture it can
    reproduce shrinks as the gesture gets faster -- so "maximum frequency" is
    only meaningful paired with an amplitude. This sweeps both and reports,
    per amplitude, where the reproduced motion falls to 90% and to 70% of what
    was asked for.
    """
    sid = args.ids[0]
    if args.center is not None:
        bus.move_and_time({sid: args.center})
    home = bus.read_position(sid)
    amps = args.amps
    freqs = args.freqs
    if not _check_range(home, max(amps), "bandwidth sweep"):
        return
    bus.configure_stream(speed=0)
    print("bandwidth sweep on servo %d, centred %.1f deg, streaming at %d Hz"
          % (sid, home, args.hz))
    print("cells are achieved amplitude as percent of commanded\n")
    print("  amp \\ Hz  " + "".join("%7.2f" % f for f in freqs))
    table = {}
    for amp in amps:
        row = []
        for f in freqs:
            bus.stream_write({sid: home})
            time.sleep(0.6)
            dur = max(1.6, 3.0 / f)
            rows = _track(bus, sid,
                          lambda t, a=amp, ff=f: home + a * math.sin(2 * math.pi * ff * t),
                          dur, args.hz)
            body = [r for r in rows if r[0] > 0.5 / f]
            if len(body) < 8:
                row.append(float("nan"))
                continue
            cmd_a = (max(c for _, c, _ in body) - min(c for _, c, _ in body)) / 2
            got_a = (max(a for _, _, a in body) - min(a for _, _, a in body)) / 2
            row.append(100.0 * got_a / cmd_a if cmd_a else float("nan"))
        table[amp] = row
        print("  %5.1f deg " % amp + "".join("%6.0f%%" % v for v in row))
    bus.stream_write({sid: home})
    time.sleep(0.8)

    def cross(row, level):
        """Frequency where the response falls through `level` percent."""
        for i in range(1, len(row)):
            a, b = row[i - 1], row[i]
            if a >= level > b:
                t = (a - level) / (a - b)
                return freqs[i - 1] + t * (freqs[i] - freqs[i - 1])
        return None

    print("\n  amplitude | full-size up to | half-size by | peak vel at 90%")
    for amp in amps:
        f90, f70 = cross(table[amp], 90.0), cross(table[amp], 70.0)
        pv = 2 * math.pi * f90 * amp if f90 else float("nan")
        print("  %5.1f deg  |   %s   |  %s  |  %s"
              % (amp,
                 "%5.2f Hz" % f90 if f90 else "  >max ",
                 "%5.2f Hz" % f70 if f70 else " >max ",
                 "%5.0f deg/s" % pv if f90 else "    -"))


def mode_tune_pgain(bus, args):
    """Sweep the position P coefficient, measuring lag. Always restores it.

    P is the servo's proportional term: raising it makes the servo chase its
    goal harder, which is exactly the ~90 ms of streaming lag we want back.
    Too much of it oscillates, so the sweep reports the ringing alongside the
    lag rather than just picking the lowest number.
    """
    sid = args.ids[0]
    original = {s: bus.read_gains(s) for s in bus.ids}
    for s, (gp, gd, gi) in original.items():
        print("servo %d gains before: P=%d D=%d I=%d" % (s, gp, gd, gi))
    if args.center is not None:
        bus.move_and_time({sid: args.center})
    home = bus.read_position(sid)
    if not _check_range(home + args.span / 2.0, args.span / 2.0, "P sweep"):
        return
    bus.configure_stream(speed=0)
    print("\nsweeping P on servo %d, 60 deg/s ramp, %.0f deg span" % (sid, args.span))
    print("  P  |  lag     rms err  | settle ring (deg pk-pk after stop)")
    try:
        dur = args.span / 60.0 + 0.25
        for pval in args.pgains:
            if not bus.write_p_gain(sid, pval):
                continue
            lags, rmss, rings = [], [], []
            # Repeat: a single ramp scatters by enough to invert neighbouring
            # P values, which would make the sweep worse than no data.
            for _ in range(args.repeats):
                bus.stream_write({sid: home})
                time.sleep(1.0)
                rows = _track(bus, sid,
                              lambda t: home + min(60.0 * t, args.span),
                              dur, args.hz)
                top = max(c for _, c, _ in rows)
                body = [r for r in rows if r[0] > 0.15 and r[1] < top - 1e-6]
                if len(body) < 6:
                    continue
                errs = [c - a for _, c, a in body]
                rmss.append((sum(e * e for e in errs) / len(errs)) ** 0.5)
                lags.append((sum(errs) / len(errs)) / 60.0)
                # Hold the final pose and watch for ringing: the cost of high P.
                tail = []
                t0 = time.perf_counter()
                while time.perf_counter() - t0 < 0.6:
                    a = bus.read_position(sid)
                    if a is not None:
                        tail.append(a)
                rings.append(max(tail) - min(tail) if tail else 0.0)
                bus.stream_write({sid: home})
                time.sleep(0.8)
            if not lags:
                print("  %3d |  no usable samples" % pval)
                continue
            ring = max(rings)
            print("  %3d |  %5.1f ms  %5.2f deg  | %5.2f%s"
                  % (pval, statistics.median(lags) * 1000,
                     statistics.median(rmss), ring,
                     "   <-- ringing" if ring > 1.0 else ""))
    finally:
        # This must not be skipped and must not be believed without checking:
        # leaving a servo on a swept gain is a change to the user's hardware
        # that would outlive the process.
        ok = True
        for s, gains in original.items():
            want = gains[0]
            if want is None:
                print("  WARNING: never read servo %d's original P gain" % s)
                ok = False
                continue
            if not bus.write_p_gain(s, want):
                ok = False
        readback = {s: bus.read_gains(s)[0] for s in bus.ids}
        print("\nrestored: %s%s"
              % (", ".join("servo %d P=%s" % (s, v) for s, v in readback.items()),
                 "" if ok else "   <-- RESTORE FAILED, re-run or set P by hand"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=BAUDRATE)
    ap.add_argument("--ids", type=int, nargs="+", default=[9, 11])
    ap.add_argument("--speed", type=int, default=2400,
                    help="0..4095 steps/s, 0 means full speed")
    ap.add_argument("--accel", type=int, default=50, help="0..255")
    ap.add_argument("--tolerance", type=float, default=1.5,
                    help="degrees of error that count as arrived")
    ap.add_argument("--release-on-exit", action="store_true",
                    help="cut torque when quitting (servos go limp)")
    ap.add_argument("--stream", action="store_true",
                    help="50 Hz streaming demo with a tracking report")
    ap.add_argument("--tune-pgain", action="store_true",
                    help="sweep position P gain, then restore the original")
    ap.add_argument("--hz", type=int, default=STREAM_HZ)
    ap.add_argument("--span", type=float, default=40.0,
                    help="degrees of travel the demos are allowed to use")
    ap.add_argument("--pgains", type=int, nargs="+",
                    default=[32, 64, 96, 128, 160, 192],
                    help="P values to try with --tune-pgain")
    ap.add_argument("--bandwidth", action="store_true",
                    help="sweep amplitude x frequency and report usable range")
    ap.add_argument("--amps", type=float, nargs="+", default=[5, 10, 20, 30],
                    help="gesture amplitudes to test, degrees either side")
    ap.add_argument("--freqs", type=float, nargs="+",
                    default=[0.5, 1.0, 1.5, 2.0, 3.0, 4.0],
                    help="gesture frequencies to test, Hz")
    ap.add_argument("--center", type=float, default=None,
                    help="park the servo here before a demo runs")
    ap.add_argument("--repeats", type=int, default=3,
                    help="measurements per P value; the median is reported")
    args = ap.parse_args()

    bus = ServoBus(args.port, args.ids, args.baud, args.speed, args.accel)
    print("connected on %s at %d baud" % (args.port, args.baud))

    if args.stream or args.tune_pgain or args.bandwidth:
        try:
            if args.stream:
                mode_stream(bus, args)
            elif args.bandwidth:
                mode_bandwidth(bus, args)
            else:
                mode_tune_pgain(bus, args)
        except KeyboardInterrupt:
            print()
        finally:
            bus.close(release=args.release_on_exit)
        return
    for sid in bus.ids:
        print("  servo %d at %.1f deg" % (sid, bus.read_position(sid) or 0.0))
    print("enter an angle, or 'id angle' pairs. 'r' read, 't'/'T' torque, 'q' quit.")

    try:
        while True:
            try:
                line = input("> ").strip()
            except EOFError:
                break
            if not line:
                continue
            if line in ("q", "quit", "exit"):
                break
            if line == "r":
                for sid in bus.ids:
                    print("  servo %d at %.1f deg" % (sid, bus.read_position(sid) or 0.0))
                continue
            if line == "t":
                bus.set_torque(False)
                print("  torque off")
                continue
            if line == "T":
                bus.set_torque(True)
                print("  torque on")
                continue

            targets = parse_command(line, bus.ids)
            if targets is None:
                continue

            elapsed, dead = bus.move_and_time(targets, tolerance=args.tolerance)
            moved = ", ".join("servo %d -> %.1f deg (now %.1f)"
                              % (sid, goal, bus.read_position(sid) or float("nan"))
                              for sid, goal in sorted(targets.items()))
            print("  %s" % moved)
            if dead is None:
                print("  took %.3f s (%.1f ms)" % (elapsed, elapsed * 1000.0))
            else:
                print("  took %.3f s (%.1f ms)  =  %.0f ms startup + %.0f ms travel"
                      % (elapsed, elapsed * 1000.0, dead * 1000.0,
                         (elapsed - dead) * 1000.0))
    except KeyboardInterrupt:
        print()
    finally:
        bus.close(release=args.release_on_exit)
        print("closed")


if __name__ == "__main__":
    sys.exit(main())
