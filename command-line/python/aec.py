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

NOISE, as opposed to echo. AEC3 removes the robot's own voice and nothing else;
a fan, a hiss, a barking dog are all still there afterwards, because none of
them were ever in the reference. Denoiser (RNNoise, from xiph) handles those,
and runs after the canceller. Off unless asked for -- see EchoCanceller.
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

RN_RATE = 48000               # RNNoise was trained at 48 kHz and accepts nothing else
RN_FRAME = 480                # its fixed 10 ms frame


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


# A port line inside a source block, e.g.
#     \t\tanalog-input-headset-mic: Headset Microphone (type: Headset, ...)
# Nothing else indented that far carries a "(type:", so this cannot collide
# with the Formats or Properties sections.
_PORT = re.compile(r"^\t\t(\S+?): (.+?) \(type:([^)]*)\)$", re.M)


def list_sources():
    """Every real input source as {name, channels, desc, ports, active_port}.

    Monitors are skipped: they are loopbacks of an output, not microphones.

    A source's PORTS are the sockets behind it. A laptop's built-in mic and
    whatever is plugged into its 3.5 mm jack are almost always one source with
    two ports, not two sources -- so a headset that the desktop's sound panel
    lists plainly does not appear anywhere in `pactl list sources` as a name of
    its own. Reading the ports is the only way to see it.
    """
    out = []
    for block in re.split(r"\nSource #", "\n" + _pactl("list", "sources")):
        name = re.search(r"^\s*Name:\s*(\S+)", block, re.M)
        if not name or name.group(1).endswith(".monitor"):
            continue
        spec = re.search(r"^\s*Sample Specification:\s*\S+\s+(\d+)ch", block, re.M)
        desc = re.search(r"^\s*Description:\s*(.+)$", block, re.M)
        active = re.search(r"^\s*Active Port:\s*(\S+)", block, re.M)
        out.append({"name": name.group(1),
                    "channels": int(spec.group(1)) if spec else 1,
                    "desc": desc.group(1).strip() if desc else name.group(1),
                    "active_port": active.group(1) if active else None,
                    "ports": [{"name": pn, "desc": pd.strip(),
                               "available": "not available" not in info}
                              for pn, pd, info in _PORT.findall(block)]})
    return out


def mic_options():
    """Everything a person can actually pick, the way the sound panel lists it.

    One entry per port on a multi-port source, one per source otherwise --
    there is nothing to choose between when a device has a single socket.
    """
    out = []
    for s in list_sources():
        if len(s["ports"]) < 2:
            out.append({"source": s["name"], "port": None, "desc": s["desc"],
                        "channels": s["channels"], "current": True,
                        "available": True})
            continue
        for port in s["ports"]:
            out.append({"source": s["name"], "port": port["name"],
                        "desc": f"{port['desc']} - {s['desc']}",
                        "channels": s["channels"],
                        "current": port["name"] == s["active_port"],
                        "available": port["available"]})
    return out


def _match(options, needle):
    """The option a --mic or --mic-port value names.

    Port names and labels are searched as well as source names, so --mic
    headset finds a headset jack that has no source name of its own.
    """
    n = needle.lower()
    def names_port(o):
        return n in (o["port"] or "").lower() or n in o["desc"].lower()

    hits = [o for o in options if n in o["source"].lower() or names_port(o)]
    hits.sort(key=lambda o: (
        o["source"] != needle,              # an exact source name wins
        "echo-cancel" in o["source"],       # never stack two cancellers
        not names_port(o),                  # then a port the needle actually names
        not o["current"],                   # failing that, leave the live port alone
    ))
    if not hits:
        raise SystemExit(f"No mic matching {needle!r}. Available:\n  " + "\n  ".join(
            o["desc"] + (f"  [port {o['port']}]" if o["port"] else "")
            for o in options))
    return hits[0]


def select(option):
    """Commit to an option, switching the source's port if that is what it is.

    Switching a port is what the desktop's own list does when you click it; the
    source keeps its name, which is why route() only ever needs the name.
    """
    if option["port"] and not option["current"]:
        _pactl("set-source-port", option["source"], option["port"])
        print(f"[mic] {option['source']} -> port {option['port']}")
    return option["source"]


def choose_mic(argv):
    """The pactl source to listen on, or None for the system default.

        --mic NAME       source name, port name, or any unique part of either
        --mic-port NAME  which socket of that source -- a headset jack, say
        --default-mic    the system default, no questions
        --laptop         the built-in sound card
        --respeaker      the ReSpeaker array
        (none)           ask, when there is a terminal to ask on
    """
    options = mic_options()
    want_port = (argv[argv.index("--mic-port") + 1]
                 if "--mic-port" in argv and argv.index("--mic-port") + 1 < len(argv)
                 else None)

    def commit(option):
        """Apply --mic-port to whatever source was settled on, then select it."""
        if want_port:
            source = option["source"] if option else _pactl("get-default-source").strip()
            on_source = [o for o in options if o["source"] == source and o["port"]]
            if not on_source:
                raise SystemExit(f"{source} has no switchable ports, so --mic-port "
                                 f"{want_port!r} has nothing to act on.")
            return select(_match(on_source, want_port))
        return select(option) if option else None

    if "--mic" in argv and argv.index("--mic") + 1 < len(argv):
        return commit(_match(options, argv[argv.index("--mic") + 1]))
    if "--default-mic" in argv or not options:
        return commit(None)
    if "--laptop" in argv:
        # Onboard audio: any real ALSA capture device that is not the array.
        # Not "pci-" -- on a Jetson it shows up as platform-/tegra- instead.
        builtin = [o for o in options if o["source"].startswith("alsa_input.")
                   and "respeaker" not in o["source"].lower()]
        if not builtin:
            raise SystemExit("No built-in mic found.")
        # Whichever port is already live, unless --mic-port overrides it.
        return commit(next((o for o in builtin if o["current"]), builtin[0]))
    if "--respeaker" in argv:
        return commit(_match(options, "respeaker"))
    if not sys.stdin.isatty():
        return commit(None)     # headless (a service): nobody to ask

    default = _pactl("get-default-source").strip()
    print("\nAvailable microphones:\n")
    for i, o in enumerate(options):
        notes = []
        if o["source"] == default and o["current"]:
            notes.append("current default")
        elif o["current"]:
            notes.append("selected port")
        if not o["available"]:
            notes.append("nothing plugged in")
        if "echo-cancel" in o["source"]:
            notes.append("already echo-cancelled -- not recommended")
        print(f"  [{i}] {o['desc']}")
        print(f"      {o['source']}")
        if o["port"]:
            print(f"      port {o['port']}")
        print(f"      {o['channels']} channel(s)"
              + (f"  <- {', '.join(notes)}" if notes else "") + "\n")
    while True:
        raw = input(f"Which mic? [0-{len(options) - 1}, Enter = default] ").strip()
        if not raw:
            return commit(None)
        if raw.isdigit() and int(raw) < len(options):
            return commit(options[int(raw)])
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


class Denoiser:
    """RNNoise (xiph) wrapped as a 16 kHz mono filter over raw int16 bytes.

    RNNoise only runs at 48 kHz, so every frame is resampled up, denoised, and
    resampled back down. The two soxr resamplers keep their state between calls
    so the frame joins are seamless, and soxr compensates its own group delay,
    so what comes out stays aligned with what went in.

    The cost is that the pair hold ~60 ms of audio between them: process()
    returns nothing for the first few frames, then bursts of ~30 ms at a time.
    Callers must treat it as a stream rather than frame-in, frame-out, batching
    whatever comes back -- which is what mic_worker does anyway, so in practice
    it costs one extra mic batch of latency and leaves the batches their usual
    size.

    Each frame also yields a speech probability -- RNNoise's own VAD, free with
    the denoising, and the obvious thing to gate the mic on later.
    """

    def __init__(self):
        try:
            from pyrnnoise import rnnoise
        except ImportError:
            raise SystemExit(
                "Noise suppression needs RNNoise. Run:  uv pip install pyrnnoise")
        self._rn = rnnoise
        self._state = rnnoise.create()
        self._up = soxr.ResampleStream(RATE, RN_RATE, 1, dtype="int16", quality="HQ")
        self._down = soxr.ResampleStream(RN_RATE, RATE, 1, dtype="int16", quality="HQ")
        self._pending = np.empty(0, np.int16)   # 48 kHz samples, short of a frame
        self.speech_prob = 0.0                  # the most recent frame's, 0..1

    def process(self, pcm):
        """int16 bytes in, int16 bytes out -- a varying, usually smaller number."""
        self._pending = np.concatenate(
            [self._pending, self._up.resample_chunk(np.frombuffer(pcm, np.int16))])
        n = len(self._pending) // RN_FRAME
        if not n:
            return b""
        out = []
        for i in range(n):
            frame, self.speech_prob = self._rn.process_mono_frame(
                self._state, self._pending[i * RN_FRAME:(i + 1) * RN_FRAME])
            out.append(frame)
        self._pending = self._pending[n * RN_FRAME:]
        return self._down.resample_chunk(np.concatenate(out)).tobytes()


class EchoCanceller:
    """AEC3 + noise suppression + high-pass, shared by the speaker and mic threads.

    enabled=False turns every call into a pass-through, so the audio path stays
    identical for an A/B comparison.

    denoise=True adds RNNoise after the canceller, for the room noise AEC3 was
    never going to touch. ns=False then turns WebRTC's own suppressor off:
    both of them suppress noise, and stacking the two can thin the speech out
    as well, which costs more in recognition accuracy than the noise does.
    """

    def __init__(self, enabled=True, agc=False, denoise=False, ns=True):
        self._lock = threading.Lock()   # both threads call into one module
        self._mic_s = 0.0
        self._speaker_s = 0.0
        self._apm = None
        self._denoiser = Denoiser() if denoise else None
        if enabled:
            from livekit import rtc
            self._rtc = rtc
            # AGC is off by default: that is the configuration that was measured.
            self._apm = rtc.AudioProcessingModule(
                echo_cancellation=True, noise_suppression=ns,
                high_pass_filter=True, auto_gain_control=agc)

    @property
    def enabled(self):
        return self._apm is not None

    @property
    def denoising(self):
        return self._denoiser is not None

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
        """One 10 ms mic frame in, echo -- and optionally noise -- removed out.

        Frame-in, frame-out only while denoising is off. With it on the result
        is a stream: empty most calls, a longer run on the others. The caller
        batches it either way.
        """
        with self._lock:
            if self._apm is not None:
                f = self._rtc.AudioFrame(frame, RATE, 1, FRAME)
                self._apm.set_stream_delay_ms(self.delay_ms)
                self._apm.process_stream(f)     # in place
                frame = f.data.tobytes()
        # Outside the lock deliberately: only the mic thread ever touches the
        # denoiser, and holding the lock across it would stall the speaker
        # thread feeding the reference in.
        den = self._denoiser
        return den.process(frame) if den else frame

    def close(self):
        # Released explicitly: livekit asserts if it is still alive at exit.
        with self._lock:
            self._apm = None
        # Dropped, not destroyed. The mic thread can still be a frame behind
        # this call, and freeing RNNoise's state under it would be a segfault;
        # the process is ending anyway, so letting the allocation go with it is
        # the safe trade.
        self._denoiser = None
