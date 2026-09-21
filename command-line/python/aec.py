"""Software echo cancellation for the voice loop: WebRTC AEC3, via livekit.

The same canceller Chrome runs, and for the same reason it works there: the app
knows exactly what it played. Every 10 ms slice handed to the speaker is also
handed to feed_reference(), and every 10 ms mic frame goes through
process_mic() before it leaves the machine. AEC3 then finds the speaker->mic
delay and the room's echo path itself, so it copes with a separate mic and
speaker -- different clocks, different buffers -- which PulseAudio's
module-echo-cancel does not.

Measured with mic_channels _aec_test.py --aec before being wired in here.

Both directions must run at RATE, in whole FRAME-sized pieces. Do not stack
this on a PulseAudio echo-cancel source (setup_respeaker.sh): two cancellers in
series fight each other. Give it a raw mic.
"""

import os
import re
import subprocess
import sys
import threading

import numpy as np
# Imported here, not where it is used: the speaker thread needs it for every
# sentence, and a missing module there kills that thread silently -- no voice,
# no error. Failing at startup instead makes the cause obvious.
import soxr

RATE = 16000                  # Gemini's input rate; the processor runs here too
FRAME = RATE // 100           # the processor accepts exactly 10 ms frames
FRAME_BYTES = FRAME * 2       # int16 mono


def route(mic=None, speaker=None):
    """Point PortAudio's "pulse" device at a pactl source / sink by name.

    Must run before sounddevice is imported: the pulse plugin reads these when
    PortAudio initialises.
    """
    if mic:
        os.environ["PULSE_SOURCE"] = mic
    if speaker:
        os.environ["PULSE_SINK"] = speaker


def _pactl(*args):
    try:
        return subprocess.run(["pactl", *args], capture_output=True,
                              text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def list_sources():
    """Every real input source as {name, channels, desc}. Monitors are skipped:
    they are loopbacks of an output, not microphones."""
    out = []
    for block in re.split(r"\nSource #", "\n" + _pactl("list", "sources")):
        name = re.search(r"^\s*Name:\s*(\S+)", block, re.M)
        if not name or name.group(1).endswith(".monitor"):
            continue
        spec = re.search(r"^\s*Sample Specification:\s*\S+\s+(\d+)ch", block, re.M)
        desc = re.search(r"^\s*Description:\s*(.+)$", block, re.M)
        out.append({"name": name.group(1),
                    "channels": int(spec.group(1)) if spec else 1,
                    "desc": desc.group(1).strip() if desc else name.group(1)})
    return out


def _match(sources, needle):
    hits = [s for s in sources if needle.lower() in s["name"].lower()]
    # Prefer the exact name, then anything that is not already echo-cancelled.
    hits.sort(key=lambda s: (s["name"] != needle, "echo-cancel" in s["name"]))
    if not hits:
        raise SystemExit(f"No mic matching {needle!r}. Available:\n  "
                         + "\n  ".join(s["name"] for s in sources))
    return hits[0]["name"]


def choose_mic(argv):
    """The pactl source to listen on, or None for the system default.

        --mic NAME      exact name, or any unique part of it
        --default-mic   the system default, no questions
        --laptop        the built-in mic
        --respeaker     the ReSpeaker array
        (none)          ask, when there is a terminal to ask on
    """
    sources = list_sources()
    if "--mic" in argv and argv.index("--mic") + 1 < len(argv):
        return _match(sources, argv[argv.index("--mic") + 1])
    if "--default-mic" in argv or not sources:
        return None
    if "--laptop" in argv:
        # Onboard audio: any real ALSA capture device that is not the array.
        # Not "pci-" -- on a Jetson it shows up as platform-/tegra- instead.
        builtin = [s for s in sources if s["name"].startswith("alsa_input.")
                   and "respeaker" not in s["name"].lower()]
        if not builtin:
            raise SystemExit("No built-in mic found.")
        return builtin[0]["name"]
    if "--respeaker" in argv:
        return _match(sources, "respeaker")
    if not sys.stdin.isatty():
        return None     # headless (a service): nobody to ask

    default = _pactl("get-default-source").strip()
    print("\nAvailable microphones:\n")
    for i, s in enumerate(sources):
        notes = []
        if s["name"] == default:
            notes.append("current default")
        if "echo-cancel" in s["name"]:
            notes.append("already echo-cancelled -- not recommended")
        print(f"  [{i}] {s['desc']}")
        print(f"      {s['name']}")
        print(f"      {s['channels']} channel(s)"
              + (f"  <- {', '.join(notes)}" if notes else "") + "\n")
    while True:
        raw = input(f"Which mic? [0-{len(sources) - 1}, Enter = default] ").strip()
        if not raw:
            return None
        if raw.isdigit() and int(raw) < len(sources):
            return sources[int(raw)]["name"]
        print("  not a valid number")


def source_info():
    """(name, channel count) of the mic the pulse device will open."""
    name = os.environ.get("PULSE_SOURCE") or _pactl("get-default-source").strip()
    for block in re.split(r"\nSource #", "\n" + _pactl("list", "sources")):
        m = re.search(r"^\s*Name:\s*(\S+)", block, re.M)
        if m and m.group(1) == name:
            ch = re.search(r"^\s*Sample Specification:\s*\S+\s+(\d+)ch", block, re.M)
            return name, int(ch.group(1)) if ch else 1
    return name, 1


def pulse_device():
    """PortAudio's "pulse" device when there is one, so route() applies."""
    import sounddevice as sd
    return "pulse" if any(d["name"] == "pulse" for d in sd.query_devices()) else None


def to_16k(pcm, rate):
    """int16 mono at any rate -> int16 mono at RATE, padded to whole frames."""
    if rate != RATE:
        pcm = soxr.resample(pcm, rate, RATE)
    return np.pad(pcm, (0, (-len(pcm)) % FRAME)).astype(np.int16)


class EchoCanceller:
    """AEC3 + noise suppression + high-pass, shared by the speaker and mic threads.

    enabled=False turns every call into a pass-through, so the audio path stays
    identical for an A/B comparison.
    """

    def __init__(self, enabled=True, agc=False):
        self._lock = threading.Lock()   # both threads call into one module
        self._mic_s = 0.0
        self._speaker_s = 0.0
        self._apm = None
        if enabled:
            from livekit import rtc
            self._rtc = rtc
            # AGC is off by default: that is the configuration that was measured.
            self._apm = rtc.AudioProcessingModule(
                echo_cancellation=True, noise_suppression=True,
                high_pass_filter=True, auto_gain_control=agc)

    @property
    def enabled(self):
        return self._apm is not None

    @property
    def delay_ms(self):
        return int((self._mic_s + self._speaker_s) * 1000)

    def set_latency(self, mic=None, speaker=None):
        """Stream latencies in seconds -- the starting guess AEC3 refines."""
        if mic is not None:
            self._mic_s = mic
        if speaker is not None:
            self._speaker_s = speaker

    def feed_reference(self, pcm):
        """What was just written to the speaker. Call right after the write."""
        with self._lock:
            if self._apm is None:
                return
            for i in range(0, len(pcm) - FRAME_BYTES + 1, FRAME_BYTES):
                self._apm.process_reverse_stream(
                    self._rtc.AudioFrame(pcm[i:i + FRAME_BYTES], RATE, 1, FRAME))

    def process_mic(self, frame):
        """One 10 ms mic frame in, the same frame with the echo removed out."""
        with self._lock:
            if self._apm is None:
                return frame
            f = self._rtc.AudioFrame(frame, RATE, 1, FRAME)
            self._apm.set_stream_delay_ms(self.delay_ms)
            self._apm.process_stream(f)     # in place
            return f.data.tobytes()

    def close(self):
        # Released explicitly: livekit asserts if it is still alive at exit.
        with self._lock:
            self._apm = None
