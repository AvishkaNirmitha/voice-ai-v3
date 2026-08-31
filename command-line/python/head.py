"""Head motion: pose mixing, gesture planning, and a simulator.

The robot has a two-axis (pan/tilt) neck. Nothing above HeadController knows
that it is simulated -- drop in a serial/PWM implementation of write() and the
rest of this file, and all of main_with_head.py, is unchanged.

Angle convention, in degrees, from the robot's point of view:

    pan    + right   - left    (yaw)
    tilt   + up      - down    (pitch)

Three sources want the head at the same time and must not fight over it:

    base pose    where the head *is*: the conversational state
                 (listening / thinking / ...) plus any gesture playing
  + rms accent   a decaying dip driven by the loudness of the audio Piper is
                 playing right now -- rides on top, never overwrites
  + breath       a slow idle oscillation, so a quiet robot is not a dead one
  ------------
  = final        clamped, slew-limited, written to the controller

That sum is resolved once per frame on a dedicated thread. It deliberately does
not happen in the audio path: stream.write() in speak_worker blocks for the
duration of the chunk it is handed, so a servo write inside that loop would eat
into the audio budget and risk an underrun.

Run this file directly to exercise the motion system without Gemini or a mic:

    python head.py                  # scripted conversation, Piper audio if present
    python head.py --no-window      # terminal log only
    python head.py --silent         # no audio, synthetic loudness envelope
"""

import math
import re
import sys
import threading
import time
from dataclasses import dataclass

import numpy as np

# --- tuning ---------------------------------------------------------------

MOTION_HZ = 50                  # resolve + write rate of the motion thread
PAN_LIMIT = 45.0                # mechanical travel, degrees either side
TILT_LIMIT = 30.0
MAX_SLEW = 420.0                # deg/s ceiling; keeps a real servo from jerking

RMS_ACCENT_DEG = 9.0            # loudest syllable dips the head this far
RMS_ATTACK = 0.55               # per-frame envelope coefficients: fast attack,
RMS_DECAY = 0.12                # slow release, so accents punch then relax

BREATH_HZ = 0.18                # idle oscillation
BREATH_DEG = 1.5
BREATH_DEG_BUSY = 0.4           # damped while listening or speaking

POSE_EASE = 0.10                # per-frame approach rate toward the STATE pose
CHARS_PER_SEC = 13.5            # rough speech rate, used to size a gesture

# Scales every gesture's cycles-per-second. Below 1.0 the gestures slow down,
# which matters on hardware and not at all in simulation: a neck with mass
# achieves far more of the commanded amplitude at 1 Hz than at 2.2 Hz, so
# slowing a gesture can make the real head move MORE, not less. Set from
# main_with_head.py's --gesture-rate.
GESTURE_RATE_SCALE = 1.0

THINK_AFTER = 0.25              # silence before the "considering" pose engages
YIELD_HOLD = 0.8                # how long the turn-yield lift is held
GESTURE_RELEASE = 0.30          # fade-out when speech ends mid-gesture


# --- loudness -------------------------------------------------------------

def rms_level(pcm_bytes):
    """Normalised RMS (0..1) of a chunk of 16-bit mono PCM."""
    if not pcm_bytes:
        return 0.0
    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)) / 32768.0)


class _AutoGain:
    """Scales raw RMS against a decaying running maximum.

    Speech RMS lands around 0.05-0.15 depending on the voice, the model and the
    volume, so a fixed threshold is either always on or never on. Tracking the
    loudest thing heard recently makes the accent depth independent of all of
    that.
    """

    def __init__(self, floor=0.02, decay=0.9995):
        self.floor = floor
        self.decay = decay
        self.peak = floor

    def __call__(self, raw):
        self.peak = max(raw, self.peak * self.decay, self.floor)
        return min(raw / self.peak, 1.0)


# --- poses and gestures ---------------------------------------------------

@dataclass(frozen=True)
class Pose:
    pan: float = 0.0
    tilt: float = 0.0

    def __add__(self, other):
        return Pose(self.pan + other.pan, self.tilt + other.tilt)

    def __mul__(self, k):
        return Pose(self.pan * k, self.tilt * k)


# Where the head rests in each conversational state. A gesture, when one is
# playing, adds to whichever of these is current.
STATE_POSE = {
    "idle":      Pose(0.0, 0.0),
    "listening": Pose(0.0, 4.0),    # lifted and still: attentive
    "thinking":  Pose(-6.0, 7.0),   # up and away: considering
    "speaking":  Pose(0.0, 0.0),
    "yield":     Pose(0.0, 3.5),    # small lift: "your turn"
}


def _bell(u):
    """0 at both ends, 1 in the middle."""
    return math.sin(math.pi * max(0.0, min(1.0, u)))


def _win(u, edge=0.18):
    """Soft ramp in and out, so a gesture neither starts nor ends abruptly.

    Unlike _bell this holds full amplitude across the middle, which is what
    lets a repeating gesture stay visible for the length of a long sentence.
    """
    u = max(0.0, min(1.0, u))
    return min(1.0, u / edge, (1.0 - u) / edge)


# Gestures repeat for as long as the sentence lasts. Stretching a single arc
# over a whole sentence -- which is what these used to do -- turns a nod into a
# 0.3 Hz drift of a few degrees, and the eye does not read that as motion at
# all. Cycle counts come from the per-gesture rate below times the duration.

def _g_shake(u, amp, cycles):
    return Pose(pan=amp * math.sin(2 * math.pi * cycles * u) * _win(u))


def _g_nod(u, amp, cycles):
    # Dips and recovers, repeatedly: a nod lives below the neutral line.
    swing = 0.5 - 0.5 * math.cos(2 * math.pi * cycles * u)
    return Pose(tilt=-amp * swing * _win(u))


def _g_nod_hard(u, amp, cycles):
    swing = 0.5 - 0.5 * math.cos(2 * math.pi * cycles * u)
    return Pose(tilt=-amp * (swing ** 0.7) * _win(u))


def _g_query(u, amp, cycles):
    # Held lean rather than a repeat: a question is one sustained posture.
    lean = _win(u, 0.30)
    return Pose(pan=amp * 0.45 * lean, tilt=amp * 0.55 * lean)


def _g_calm(u, amp, cycles):
    return Pose(tilt=amp * math.sin(2 * math.pi * cycles * u) * _win(u))


def _g_scan(u, amp, cycles):
    return Pose(pan=amp * math.sin(2 * math.pi * cycles * u))


# name -> (function, amplitude in degrees, cycles per second)
GESTURES = {
    "shake":     (_g_shake, 16.0, 2.2),
    "nod":       (_g_nod, 9.0, 1.5),
    "nod_hard":  (_g_nod_hard, 13.0, 1.7),
    "query":     (_g_query, 9.0, 0.0),
    "calm":      (_g_calm, 3.5, 0.7),
    "scan":      (_g_scan, 26.0, 0.45),
}

# The [head_*] tags the system prompt asks Gemini to emit, mapped onto the
# gesture library. Anything the model invents that is not here falls back to
# the text heuristics in plan_sentence().
TAG_GESTURE = {
    "head_calm": "calm",
    "head_up_to_down_hard": "nod_hard",
    "head_up_to_down_medium": "nod",
    "head_left_to_right_hard": "shake",
    "head_left_to_right_medium": "shake",
}

TAG_RE = re.compile(r"\[\s*(head_[a-z_]+)\s*\]", re.I)


def strip_tags(text):
    """Pull [head_*] tags out of a transcript fragment.

    Returns (clean_text, gesture_names). The tags have to come out before the
    text reaches Piper, or the robot reads them aloud.
    """
    tags = [m.group(1).lower() for m in TAG_RE.finditer(text)]
    clean = re.sub(r"\s{2,}", " ", TAG_RE.sub(" ", text)).strip()
    return clean, [TAG_GESTURE[t] for t in tags if t in TAG_GESTURE]


# Words that flip a sentence negative when they open it.
NEGATIONS = ("no", "not", "negative", "never", "nothing", "none",
             "denied", "unauthorized", "unable", "cannot", "sorry")

# Negations of the main clause, which a sentence-initial check misses entirely:
# "I am not able to fly" and "I cannot access that floor" are both refusals and
# should shake, even though they open with "I".
NEGATION_PHRASES = ("do not", "does not", "did not", "cannot", "can not",
                    "am not", "is not", "are not", "was not", "will not",
                    "unable", "not able", "not within", "not permitted",
                    "no longer", "never")


@dataclass
class Plan:
    """A gesture chosen for one sentence, before it is spoken."""
    gesture: str
    duration: float
    text: str
    reason: str


def plan_sentence(text, tag_gestures=()):
    """Choose a gesture for a sentence. Called when the text is known, which
    is up to a few hundred ms before Piper starts playing it -- that lead is
    what lets a gesture wind up *with* the first word instead of after it.

    A [head_*] tag the model placed in this sentence wins; the heuristics below
    are the fallback for when it ignores the instruction, which it will.
    """
    stripped = text.strip()
    duration = max(0.5, min(len(stripped) / CHARS_PER_SEC, 9.0))

    lowered = stripped.lower()
    first = lowered.lstrip("\"'([").split(" ")[0].strip(".,!?;:")

    # What the sentence plainly *is* outranks whatever the model tagged it.
    # Gemini places these tags to satisfy the prompt rather than to mean
    # anything -- observed tagging questions as shakes and refusals as calm --
    # so an unambiguous syntactic signal wins and the tag is only consulted
    # when the text itself gives nothing to go on.
    if stripped.endswith("?"):
        return Plan("query", duration, stripped, "question")
    if stripped.endswith("!"):
        return Plan("nod_hard", duration, stripped, "exclamation")
    if first in NEGATIONS:
        return Plan("shake", duration, stripped, f"opens '{first}'")
    if any(ph in lowered for ph in NEGATION_PHRASES):
        return Plan("shake", duration, stripped, "negated clause")

    # A shake means "no". The text was checked for negation just above and had
    # none, so a shake tag here contradicts the sentence it sits in -- drop it
    # rather than have the robot deny its own statement.
    usable = [g for g in tag_gestures if g != "shake"]
    if usable:
        return Plan(usable[0], duration, stripped, "model tag")

    if len(stripped) < 18:
        return Plan("calm", duration, stripped, "short phrase")
    return Plan("nod", duration, stripped, "declarative")


# --- controllers ----------------------------------------------------------

class HeadController:
    """Where the abstraction ends and the hardware begins."""

    def write(self, pan, tilt, active=True):
        """Command a pose. `active` is False when the head has nothing to
        express, which a hardware link may use to go quiet."""
        raise NotImplementedError

    def close(self):
        pass


class SimHeadController(HeadController):
    """Records the commanded pose. The visualiser, if running, reads it."""

    def __init__(self):
        self.pan = 0.0
        self.tilt = 0.0

    def write(self, pan, tilt, active=True):
        self.pan = pan
        self.tilt = tilt


# A real one, for later, looks like this and nothing else changes:
#
# class FeetechController(HeadController):
#     def __init__(self, port="/dev/ttyUSB0"):
#         self.bus = ...
#     def write(self, pan, tilt):
#         self.bus.set_position(PAN_ID, deg_to_ticks(pan))
#         self.bus.set_position(TILT_ID, deg_to_ticks(tilt))


# --- motion ---------------------------------------------------------------

DIM = "\033[2m"
RESET = "\033[0m"


class HeadMotion:
    """Owns the head. Everything else calls the small API at the bottom."""

    def __init__(self, controller=None, log=True):
        self.controller = controller or SimHeadController()
        self.log_enabled = log

        # Travel, per axis. The module constants are only a default: a real
        # neck reports its own calibration through head_link.limits(), which is
        # asymmetric on real hardware, so min and max are tracked separately.
        # set_limits() replaces these at startup when a head answers.
        self.pan_min, self.pan_max = -PAN_LIMIT, PAN_LIMIT
        self.tilt_min, self.tilt_max = -TILT_LIMIT, TILT_LIMIT

        self._lock = threading.Lock()
        self._stop = threading.Event()

        self.state = "idle"
        self._state_since = time.monotonic()
        self._last_input = 0.0
        self._speaking = False

        self._gesture = None            # (name, fn, amp, started, duration, cycles)
        self._release = None            # when the current gesture began fading
        self._gain = _AutoGain()
        self._rms_raw = 0.0
        self._rms_env = 0.0

        # The pose actually being approached and written, so state changes and
        # gestures ease rather than snap.
        self._cur = Pose()
        self._prev_written = Pose()
        self._t0 = time.monotonic()
        self._log_pending = None    # printed after the lock is released

        # Manual override: the sliders take the head off the mixer entirely,
        # which is how you check travel and find the mechanical limits without
        # having to hold a conversation with it.
        self._manual = False
        self._manual_pose = Pose()

        self.thread = threading.Thread(target=self._run, daemon=True)

    # -- lifecycle --

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self._stop.set()
        self.thread.join(timeout=1.0)
        self.controller.close()

    # -- called from receive_audio (event loop) and speak_worker (thread) --

    def set_state(self, state):
        with self._lock:
            if self.state == state:
                return
            self.state = state
            self._state_since = time.monotonic()
            if state == "listening":
                self._last_input = time.monotonic()
        self._log(f"STATE {state:<9} base(pan {STATE_POSE[state].pan:+6.1f}, "
                  f"tilt {STATE_POSE[state].tilt:+6.1f})")

    def set_limits(self, pan_min, pan_max, tilt_min, tilt_max):
        """Adopt the neck's real travel. Anything the mixer produces is
        clamped to this, so a gesture can never demand an angle the servos do
        not have."""
        with self._lock:
            self.pan_min, self.pan_max = float(pan_min), float(pan_max)
            self.tilt_min, self.tilt_max = float(tilt_min), float(tilt_max)
        self._log(f"LIMITS pan {pan_min:+.1f}..{pan_max:+.1f}  "
                  f"tilt {tilt_min:+.1f}..{tilt_max:+.1f}")

    def set_manual(self, on):
        with self._lock:
            if self._manual == on:
                return
            self._manual = on
            if on:
                self._gesture = None
                self._rms_raw = 0.0
        self._log("MANUAL on -- mixer bypassed" if on else "MANUAL off")

    def set_manual_pose(self, pan, tilt):
        with self._lock:
            self._manual_pose = Pose(float(pan), float(tilt))

    def saw_input(self):
        """User speech is arriving."""
        with self._lock:
            self._last_input = time.monotonic()
        self.set_state("listening")

    def begin_gesture(self, plan):
        """Start a planned gesture. Called just before Piper synthesises, so
        the wind-up happens during synthesis and lands on the first word."""
        if plan is None:
            return
        fn, amp, rate = GESTURES.get(plan.gesture, GESTURES["nod"])
        cycles = (max(1.0, rate * GESTURE_RATE_SCALE * plan.duration)
                  if rate else 1.0)
        with self._lock:
            self._speaking = True
            self._release = None
            self._gesture = (plan.gesture, fn, amp, time.monotonic(),
                             plan.duration, cycles)
            self.state = "speaking"
            self._state_since = time.monotonic()
        self._log(f"PLAN  {plan.gesture:<9} {plan.duration:4.2f}s  "
                  f"({plan.reason})  {plan.text[:44]!r}")

    def push_rms(self, level):
        """Loudness of the audio slice about to reach the speaker."""
        with self._lock:
            self._rms_raw = level

    def end_speech(self):
        """One sentence finished playing."""
        with self._lock:
            self._speaking = False
            self._rms_raw = 0.0
            if self._gesture is not None and self._release is None:
                self._release = time.monotonic()
        self._log("SETTLE")

    def interrupt(self):
        """Barge-in: drop everything and snap to attention."""
        with self._lock:
            self._speaking = False
            self._gesture = None
            self._release = None
            self._rms_raw = 0.0
            self._rms_env = 0.0
            self.state = "listening"
            self._state_since = time.monotonic()
            self._last_input = time.monotonic()
        self._log("INTERRUPT -> listening")

    def turn_complete(self):
        if not self._speaking:
            self.set_state("yield")

    # -- introspection for the visualiser --

    def snapshot(self):
        with self._lock:
            return {
                "state": self.state,
                "gesture": self._gesture[0] if self._gesture else None,
                "pan": self.controller.pan if hasattr(self.controller, "pan") else 0.0,
                "tilt": self.controller.tilt if hasattr(self.controller, "tilt") else 0.0,
                "rms": self._rms_env,
                "raw": self._rms_raw,
                "manual": self._manual,
            }

    # -- the frame loop --

    def _run(self):
        period = 1.0 / MOTION_HZ
        next_t = time.monotonic()
        while not self._stop.is_set():
            self._frame()
            next_t += period
            delay = next_t - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:                       # fell behind; resync rather than spiral
                next_t = time.monotonic()

    def _frame(self):
        now = time.monotonic()
        with self._lock:
            state = self.state
            gesture = self._gesture
            raw = self._rms_raw
            manual = self._manual
            manual_pose = self._manual_pose
            release = self._release

            # Idle transitions the motion thread owns, so callers do not have
            # to run timers of their own.
            if state == "listening" and not self._speaking:
                if now - self._last_input > THINK_AFTER:
                    self.state = state = "thinking"
                    self._state_since = now
                    self._log_pending = "STATE thinking  base(pan   -6.0, tilt   +7.0)"
            elif state == "yield" and now - self._state_since > YIELD_HOLD:
                self.state = state = "idle"
                self._state_since = now

            # Loudness envelope: jump on attack, ease off on release, so an
            # accent reads as a punch rather than a tremor.
            level = self._gain(raw)
            k = RMS_ATTACK if level > self._rms_env else RMS_DECAY
            self._rms_env += (level - self._rms_env) * k
            env = self._rms_env

            # Retire a gesture that has run its course, or finish fading one
            # that speech ended under.
            gesture_gain = 1.0
            if gesture and now - gesture[3] > gesture[4]:
                self._gesture = gesture = None
                self._release = release = None
            elif release is not None:
                gesture_gain = 1.0 - (now - release) / GESTURE_RELEASE
                if gesture_gain <= 0.0:
                    self._gesture = gesture = None
                    self._release = release = None
                    gesture_gain = 0.0

        # Only the state pose is eased. Those are deliberate changes of posture
        # and should glide into place.
        target = manual_pose if manual else STATE_POSE[state]
        self._cur = Pose(
            self._cur.pan + (target.pan - self._cur.pan) * POSE_EASE,
            self._cur.tilt + (target.tilt - self._cur.tilt) * POSE_EASE,
        )

        # Gesture, accent and breath are added *after* that filter, never
        # through it. Running a gesture through the ease was the bug: a 0.1
        # per-frame lag at 50 Hz corners at roughly 0.8 Hz, so it attenuated
        # exactly the 1.5-2.5 Hz motion that reads to the eye as a nod.
        # Under manual control they are silenced, so the sliders read as
        # commanded.
        final = self._cur
        if not manual:
            if gesture:
                _, fn, amp, started, duration, cycles = gesture
                final = final + fn((now - started) / duration, amp,
                                   cycles) * gesture_gain
            final = final + Pose(tilt=-RMS_ACCENT_DEG * env)
            breath_amp = (BREATH_DEG_BUSY if state in ("listening", "speaking")
                          else BREATH_DEG)
            final = final + Pose(
                tilt=breath_amp * math.sin(2 * math.pi * BREATH_HZ
                                           * (now - self._t0)))

        # Clamp to the mechanism, then limit how fast it may get there. Both
        # are pointless in simulation and essential the moment this drives a
        # real servo, which is exactly why they live here and not in main.
        pan = max(self.pan_min, min(self.pan_max, final.pan))
        tilt = max(self.tilt_min, min(self.tilt_max, final.tilt))
        step = MAX_SLEW / MOTION_HZ
        pan = self._prev_written.pan + max(-step, min(step, pan - self._prev_written.pan))
        tilt = self._prev_written.tilt + max(-step, min(step, tilt - self._prev_written.tilt))
        self._prev_written = Pose(pan, tilt)

        # `active` says whether the head is expressing anything right now.
        # A hardware controller uses it to fall silent when it is not, which
        # is what lets the real head hand itself back to face tracking; the
        # simulator ignores it.
        active = (manual or state != "idle" or gesture is not None
                  or env > 0.02)
        self.controller.write(pan, tilt, active)

        pending = getattr(self, "_log_pending", None)
        if pending:
            self._log_pending = None
            self._log(pending)

    def _log(self, msg):
        if self.log_enabled:
            print(f"{DIM}[head] {msg}{RESET}", flush=True)


# --- visualiser -----------------------------------------------------------

class HeadWindow:
    """A Tk window drawing the commanded pose, with manual controls.

    The drawing is traced off the real frame -- tapered shell, sensor bar with
    the stereo pair either side of the colour lens, slatted grille, and the
    open handle cut-out -- so that a pose on screen is recognisable as the same
    pose on the bench.

    Runs its own root and mainloop on a dedicated thread; every Tk call stays
    on that thread. Optional -- the motion system is fully functional without
    it, and on a headless Jetson it simply is not started.
    """

    # Head geometry in local coordinates, origin at the pan/tilt centre.
    SHELL = [(-96, -140), (-40, -145), (40, -145), (96, -140),
             (104, -112), (104, -30), (96, 50), (76, 112),
             (44, 138), (0, 145), (-44, 138), (-76, 112),
             (-96, 50), (-104, -30), (-104, -112)]
    HANDLE = [(-56, 26), (0, 22), (56, 26), (60, 68), (48, 112),
              (0, 132), (-48, 112), (-60, 68)]

    BG = "#111318"
    SHELL_FILL = "#c9ced6"
    SHELL_EDGE = "#8f97a3"
    RECESS = "#15181e"
    SLAT = "#b9bfc7"
    METAL = "#3d4450"

    STATE_COLOUR = {"idle": "#5c6676", "listening": "#4ea3ff",
                    "thinking": "#c08cff", "speaking": "#3ddc84",
                    "yield": "#ffc45c"}

    W, H = 500, 430
    CX, CY = 250, 152

    def __init__(self, motion):
        self.motion = motion
        self.thread = threading.Thread(target=self._run, daemon=True)
        self._syncing = False       # guards slider.set() against its callback

    def start(self):
        self.thread.start()
        return self

    def _run(self):
        import tkinter as tk

        root = tk.Tk()
        root.title("Spera head - simulation")
        root.configure(bg=self.BG)
        root.resizable(False, False)

        c = tk.Canvas(root, width=self.W, height=self.H, bg=self.BG,
                      highlightthickness=0)
        c.pack()

        # -- controls ------------------------------------------------------
        ctrl = tk.Frame(root, bg=self.BG)
        ctrl.pack(fill="x", padx=16, pady=(0, 14))

        manual_var = tk.BooleanVar(value=False)

        def btn(parent, text, cmd, width=9):
            return tk.Button(parent, text=text, command=cmd, width=width,
                             bg="#232833", fg="#c9ced6", relief="flat",
                             activebackground="#2e3542", activeforeground="#fff",
                             font=("monospace", 9), bd=0, highlightthickness=0,
                             padx=4, pady=3)

        def slider(parent, label, lo, hi):
            tk.Label(parent, text=label, bg=self.BG, fg="#8b93a1",
                     font=("monospace", 9)).pack(anchor="w")
            s = tk.Scale(parent, from_=lo, to=hi, resolution=0.5,
                         orient="horizontal",
                         bg=self.BG, fg="#c9ced6", troughcolor="#1b1f26",
                         highlightthickness=0, bd=0, sliderrelief="flat",
                         activebackground="#4ea3ff", length=self.W - 32,
                         font=("monospace", 8))
            s.set(0.0)
            s.pack(fill="x")
            # The callback is attached only after the widget exists and has
            # its starting value. A tk.Scale fires its command once while it
            # is being constructed, and wiring it up front meant simply
            # opening the window engaged manual mode and bypassed the mixer.
            s.config(command=on_slider)
            # Taking manual control is a deliberate click, never a programmatic
            # .set() -- draw() calls set() on every frame to keep the sliders
            # tracking the live pose.
            s.bind("<ButtonPress-1>", lambda _e: engage())
            return s

        def engage():
            manual_var.set(True)
            self.motion.set_manual(True)
            self.motion.set_manual_pose(pan_s.get(), tilt_s.get())

        def on_slider(_=None):
            if self._syncing or not manual_var.get():
                return
            self.motion.set_manual_pose(pan_s.get(), tilt_s.get())

        def on_manual_toggle():
            self.motion.set_manual(manual_var.get())
            if manual_var.get():
                self.motion.set_manual_pose(pan_s.get(), tilt_s.get())

        def centre():
            self._syncing = True
            pan_s.set(0.0)
            tilt_s.set(0.0)
            self._syncing = False
            manual_var.set(True)
            self.motion.set_manual(True)
            self.motion.set_manual_pose(0.0, 0.0)

        def fire(name):
            # A gesture is a mixer product, so previewing one has to hand the
            # head back to the mixer first.
            manual_var.set(False)
            self.motion.set_manual(False)
            dur = 1.8
            self.motion.begin_gesture(Plan(name, dur, "", "manual preview"))
            root.after(int(dur * 1000) + 150, self.motion.end_speech)

        row1 = tk.Frame(ctrl, bg=self.BG)
        row1.pack(fill="x", pady=(2, 6))
        tk.Checkbutton(row1, text="manual", variable=manual_var,
                       command=on_manual_toggle, bg=self.BG, fg="#c9ced6",
                       selectcolor="#1b1f26", activebackground=self.BG,
                       activeforeground="#fff", font=("monospace", 9),
                       highlightthickness=0, bd=0).pack(side="left")
        btn(row1, "centre", centre, 8).pack(side="left", padx=6)
        btn(row1, "release", lambda: (manual_var.set(False),
                                      self.motion.set_manual(False)), 8
            ).pack(side="left")

        pan_s = slider(ctrl, "pan   - left / + right",
                       self.motion.pan_min, self.motion.pan_max)
        tilt_s = slider(ctrl, "tilt  - down / + up",
                        self.motion.tilt_min, self.motion.tilt_max)

        row2 = tk.Frame(ctrl, bg=self.BG)
        row2.pack(fill="x", pady=(8, 0))
        tk.Label(row2, text="gesture", bg=self.BG, fg="#8b93a1",
                 font=("monospace", 9)).pack(anchor="w")
        row3 = tk.Frame(ctrl, bg=self.BG)
        row3.pack(fill="x", pady=(3, 0))
        for name in GESTURES:
            btn(row3, name, lambda n=name: fire(n), 8).pack(side="left", padx=2)

        # -- drawing -------------------------------------------------------
        def draw():
            s = self.motion.snapshot()
            pan, tilt = s["pan"], s["tilt"]
            c.delete("all")

            yaw, pitch = math.radians(pan), math.radians(tilt)
            # Pan swings the head across and foreshortens it; tilt lifts it and
            # squashes it. Cheap, but it reads as the right rotation.
            sx = max(0.30, math.cos(yaw))
            sy = max(0.55, math.cos(pitch))
            ox = self.CX + math.sin(yaw) * 66
            oy = self.CY - math.sin(pitch) * 62

            def P(lx, ly):
                return ox + lx * sx, oy + ly * sy

            def poly(pts, **kw):
                flat = []
                for lx, ly in pts:
                    flat.extend(P(lx, ly))
                return c.create_polygon(*flat, **kw)

            def rect(x0, y0, x1, y1, **kw):
                ax, ay = P(x0, y0)
                bx, by = P(x1, y1)
                return c.create_rectangle(ax, ay, bx, by, **kw)

            def circ(lx, ly, r, **kw):
                ax, ay = P(lx - r, ly - r)
                bx, by = P(lx + r, ly + r)
                return c.create_oval(ax, ay, bx, by, **kw)

            # Rail and mount: fixed, so the head is seen to move against them.
            c.create_rectangle(70, 392, self.W - 70, 414,
                               fill="#2a2f38", outline="#3d4450")
            c.create_rectangle(90, 396, self.W - 90, 402, fill="#454c58",
                               outline="")
            c.create_rectangle(196, 352, 304, 394, fill="#d5d9de",
                               outline="#9aa1ab")

            # Pan bracket and servo: yaw with the head, but do not tilt.
            bx = self.CX + math.sin(yaw) * 22
            c.create_polygon(bx - 34, 300, bx + 34, 300, bx + 28, 356,
                             bx - 28, 356, fill="#39414f", outline="#4d5666",
                             width=1)
            c.create_rectangle(bx - 24, 306, bx + 24, 350, fill="#22262e",
                               outline="#39404c")
            c.create_line(bx, 300, bx, 276, fill="#4d5666", width=6)

            # Shell.
            poly(self.SHELL, fill=self.SHELL_FILL, outline=self.SHELL_EDGE,
                 width=2, smooth=True, splinesteps=24)

            # The two dark recesses either side of the brow.
            for sgn in (-1, 1):
                rect(sgn * 74 - 23, -128, sgn * 74 + 23, -92,
                     fill=self.RECESS, outline="#a8afb9")

            # Sensor bar: stereo pair either side of the colour lens.
            rect(-66, -86, 66, -48, fill=self.RECESS, outline="#a8afb9")
            for lx, r, glass in ((-37, 11, "#151a22"), (0, 13, "#1f8f74"),
                                 (37, 11, "#151a22")):
                circ(lx, -67, r, fill="#2a2f38", outline="#454c58")
                circ(lx, -67, r - 4, fill=glass, outline="")
            circ(-37, -70, 3, fill="#5b6470", outline="")
            circ(37, -70, 3, fill="#5b6470", outline="")
            circ(0, -71, 4, fill="#7fd8bf", outline="")

            # Slatted grille.
            rect(-58, -36, 58, 8, fill=self.RECESS, outline="#a8afb9")
            for i in range(11):
                lx = -52 + i * 10.4
                rect(lx, -32, lx + 5.2, 4, fill=self.SLAT, outline="")

            # Handle cut-out: the background showing through the frame.
            poly(self.HANDLE, fill=self.BG, outline="#a8afb9", width=2,
                 smooth=True, splinesteps=20)

            # -- HUD --
            state = s["state"]
            colour = "#ff8a5c" if s["manual"] else self.STATE_COLOUR.get(state, "#888")
            label = "MANUAL" if s["manual"] else state.upper()
            c.create_text(18, 20, anchor="w", fill=colour,
                          font=("monospace", 15, "bold"), text=label)
            c.create_text(18, 44, anchor="w", fill="#8b93a1",
                          font=("monospace", 10),
                          text=f"gesture: {s['gesture'] or '-'}")
            c.create_text(self.W - 18, 20, anchor="e", fill="#c9ced6",
                          font=("monospace", 12), text=f"pan  {pan:+6.1f}°")
            c.create_text(self.W - 18, 40, anchor="e", fill="#c9ced6",
                          font=("monospace", 12), text=f"tilt {tilt:+6.1f}°")

            c.create_rectangle(18, 352, self.W - 18, 368, outline="#22262e")
            c.create_rectangle(18, 352, 18 + (self.W - 36) * s["rms"], 368,
                               fill="#3ddc84", outline="")
            c.create_text(18, 340, anchor="w", fill="#8b93a1",
                          font=("monospace", 9),
                          text=f"rms raw {s['raw']:.3f}   env {s['rms']:.2f}")

            # While the mixer has the head, the sliders follow it rather than
            # fight it, so they always show where it actually is.
            if not s["manual"]:
                self._syncing = True
                pan_s.set(round(pan, 1))
                tilt_s.set(round(tilt, 1))
                self._syncing = False

            root.after(int(1000 / MOTION_HZ), draw)

        draw()
        root.mainloop()


# --- demo -----------------------------------------------------------------

def _demo():
    """A scripted exchange, so the motion system can be judged on its own."""
    no_window = "--no-window" in sys.argv
    silent = "--silent" in sys.argv

    motion = HeadMotion().start()
    if not no_window:
        HeadWindow(motion).start()
        time.sleep(0.6)             # let the window map before anything moves

    voice = None
    if not silent:
        try:
            from pathlib import Path
            from piper import PiperVoice, SynthesisConfig
            model = Path(__file__).resolve().parents[2] / "en_GB-alan-medium.onnx"
            voice = PiperVoice.load(str(model))
            syn = SynthesisConfig(length_scale=1.0)
            rate = voice.config.sample_rate
            import sounddevice as sd
            stream = sd.RawOutputStream(samplerate=rate, channels=1, dtype="int16")
            write_bytes = int(rate * 0.03) * 2
            print(f"{DIM}[head] piper ready ({rate} Hz){RESET}")
        except Exception as e:
            print(f"{DIM}[head] no piper ({e}); using a synthetic envelope{RESET}")
            voice = None

    sentences = [
        "No, sir.",
        "The server room is clear.",
        "I have detected no movement in the past hour.",
    ]

    try:
        print(f"\n{DIM}--- idle ---{RESET}")
        time.sleep(2.0)

        print(f"{DIM}--- user speaking ---{RESET}")
        for _ in range(9):          # transcript fragments arriving
            motion.saw_input()
            time.sleep(0.2)

        print(f"{DIM}--- gemini thinking ---{RESET}")
        time.sleep(0.7)

        for text in sentences:
            plan = plan_sentence(text)
            motion.begin_gesture(plan)
            print(f"  {text}")

            if voice is not None:
                stream.start()
                for chunk in voice.synthesize(text, syn_config=syn):
                    buf = chunk.audio_int16_bytes
                    for i in range(0, len(buf), write_bytes):
                        slice_ = buf[i:i + write_bytes]
                        motion.push_rms(rms_level(slice_))
                        stream.write(slice_)
                stream.stop()
            else:
                # Fake a loudness contour at the same 30 ms cadence.
                steps = int(plan.duration / 0.03)
                for i in range(steps):
                    u = i / steps
                    motion.push_rms(0.10 * abs(math.sin(u * math.pi * 7)) * _bell(u)
                                    + 0.01)
                    time.sleep(0.03)
            motion.end_speech()
            time.sleep(0.12)

        motion.turn_complete()
        print(f"{DIM}--- turn complete ---{RESET}")
        time.sleep(4.0)
        print(f"\n{DIM}Demo finished. Ctrl+C to close the window.{RESET}")
        while not no_window:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        if voice is not None:
            stream.close()
        motion.stop()


if __name__ == "__main__":
    _demo()
