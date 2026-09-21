#!/usr/bin/env python3
"""Record every channel of any microphone separately, then play them back.
 
Multi-channel sources (the ReSpeaker array presents six) only ever expose one
channel to normal capture, so a bad channel choice is invisible -- it just
sounds like a quiet or noisy mic. This records every channel at once and splits
them into one WAV each, so you can listen to them in isolation. Works equally
on a plain 2-channel laptop mic.
 
    python3 mic_channels.py                 # pick a mic from a list, record 8s
    python3 mic_channels.py 15              # record 15s
    python3 mic_channels.py --laptop        # skip the picker, use the built-in mic
    python3 mic_channels.py --respeaker     # skip the picker, use the array
    python3 mic_channels.py --default       # skip the picker, use the current default source
    python3 mic_channels.py --source NAME   # use an exact pactl source name
    python3 mic_channels.py --list          # just show the available mics
    python3 mic_channels.py --play-only     # replay the last recording

AEC test -- software echo cancellation (WebRTC AEC3, the canceller Chrome uses):

    python3 mic_channels.py --aec --laptop            # 20s: Piper speaks, mic is cleaned
    python3 mic_channels.py --aec 30 --source NAME    # any mic, 30s
    python3 mic_channels.py --aec --wav out.wav       # play a WAV instead of Piper
    python3 mic_channels.py --aec --sink NAME         # play on a specific pactl sink
    python3 mic_channels.py --aec --channel 2         # which channel of a multichannel mic

  The script plays the test sound itself and hands every played frame to the
  canceller as its reference -- sound from any other app cannot be cancelled.
  First half: stay silent (measures echo removal). Second half: talk over it
  (checks your voice survives). Writes aec_raw / aec_clean / aec_ref WAVs.

 
Talk, and play audio through the speaker, while it records. Then listen:
  - a live mic channel      -> your voice, clearly
  - a dead channel          -> hiss or silence
  - an echo-cancelled one   -> your voice but NOT the speaker output
  - a raw channel           -> your voice AND the speaker
"""
 
import re
import subprocess
import sys
import wave
from pathlib import Path
 
RATE = 16000
OUTDIR = Path(__file__).resolve().parent / "mic_channels_out"

# --- AEC test ---------------------------------------------------------------
FRAME = RATE // 100           # the audio processor accepts exactly 10 ms frames
FRAME_BYTES = FRAME * 2       # int16 mono
AEC_SKIP_S = 2.0              # AEC3 is still converging at the start; not measured
PIPER_MODEL = Path(__file__).resolve().parent / "en_GB-alan-medium.onnx"
PIPER_TEXT = (
    "Hello, I am Spera, your security robot. I am monitoring this area. "
    "All doors are locked and no suspicious activity has been detected. "
    "Please stay where you are while I complete the patrol. "
    "The perimeter is secure and every camera is online."
)
 
 
def pactl(*args: str) -> str:
    return subprocess.run(["pactl", *args], capture_output=True, text=True).stdout
 
 
def list_sources() -> list[dict]:
    """Every real input source, with its channel count and description.
 
    Monitor sources are loopbacks of an output, not microphones, so they are
    skipped -- recording one would just capture whatever is playing.
    """
    blocks = re.split(r"\nSource #", "\n" + pactl("list", "sources"))
    out = []
    for b in blocks:
        if not b.strip():
            continue
        name = re.search(r"^\s*Name:\s*(\S+)", b, re.M)
        spec = re.search(r"^\s*Sample Specification:\s*\S+\s+(\d+)ch", b, re.M)
        desc = re.search(r"^\s*Description:\s*(.+)$", b, re.M)
        if not name:
            continue
        n = name.group(1)
        if n.endswith(".monitor"):
            continue
        out.append({
            "name": n,
            "channels": int(spec.group(1)) if spec else 1,
            "desc": desc.group(1).strip() if desc else n,
        })
    return out
 
 
def show_sources(sources: list[dict]) -> None:
    print("\nAvailable microphones:\n")
    for i, s in enumerate(sources):
        default = "  <- current default" if s["name"] == pactl("get-default-source").strip() else ""
        print(f"  [{i}] {s['desc']}")
        print(f"      {s['name']}")
        print(f"      {s['channels']} channel(s){default}\n")
 
 
def pick_source(sources: list[dict]) -> dict:
    show_sources(sources)
    while True:
        raw = input(f"Which mic? [0-{len(sources) - 1}] ").strip()
        if raw.isdigit() and 0 <= int(raw) < len(sources):
            return sources[int(raw)]
        print("  not a valid number")
 
 
def match_source(sources: list[dict], needle: str) -> dict:
    hits = [s for s in sources if needle.lower() in s["name"].lower()]
    if not hits:
        sys.exit(f"No input source matching {needle!r}.\n"
                 f"Run with --list to see what is available.")
    return hits[0]
 
 
def usb_devnum() -> str:
    """USB device number -- increments every time the array re-enumerates."""
    out = subprocess.run(["lsusb"], capture_output=True, text=True).stdout
    m = re.search(r"Device (\d+).*Seeed", out)
    return m.group(1) if m else None
 
 
def record(seconds: float, src: dict) -> bytes:
    ch = src["channels"]
    print(f"\nRecording {seconds:g}s x {ch} channel(s) from:\n  {src['desc']}")
    print("\n  >>> TALK NOW, and play something through the speaker <<<\n")
    proc = subprocess.run(
        ["timeout", str(seconds + 1), "parec", f"--device={src['name']}",
         f"--channels={ch}", f"--rate={RATE}", "--format=s16le", "--raw"],
        capture_output=True,
    )
    if not proc.stdout:
        sys.exit(f"Recorded nothing. parec said:\n{proc.stderr.decode(errors='replace')}")
    return proc.stdout
 
 
def split_and_write(raw: bytes, ch: int) -> list[Path]:
    """Split interleaved frames into one mono WAV per channel."""
    import array
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) // (2 * ch) * 2 * ch])
    total = len(samples) // ch
 
    # Old files from a previous mic would be confusing to play back alongside.
    OUTDIR.mkdir(exist_ok=True)
    for stale in OUTDIR.glob("ch*.wav"):
        stale.unlink()
 
    paths = []
    print(f"  {total / RATE:.1f}s captured\n")
    print("  ch    RMS     peak   level")
    for c in range(ch):
        chan = samples[c::ch]
        rms = (sum(float(v) * v for v in chan) / max(len(chan), 1)) ** 0.5
        peak = max((abs(v) for v in chan), default=0)
        print(f"  {c}   {rms:7.1f}  {peak:6d}   {'#' * min(int(rms / 60), 30)}")
 
        p = OUTDIR / f"ch{c}.wav"
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(chan.tobytes())
        paths.append(p)
    return paths
 
 
def playback(paths: list[Path]) -> None:
    print(f"\nPlaying each channel in turn. Files are in {OUTDIR}\n")
    for c, p in enumerate(paths):
        input(f"  [Enter] to play channel {c}  ({p.name}) ... ")
        subprocess.run(["paplay", str(p)])
    print("\nDone. Replay any file later with:  paplay mic_channels_out/chN.wav")


def load_test_sound(wav_path):
    """The sound to play, as 16 kHz mono int16: a Piper sentence or a WAV."""
    import numpy as np
    import soxr

    if wav_path:
        with wave.open(wav_path, "rb") as w:
            if w.getsampwidth() != 2:
                sys.exit(f"{wav_path}: only 16-bit WAV files are supported")
            ch, rate = w.getnchannels(), w.getframerate()
            pcm = np.frombuffer(w.readframes(w.getnframes()), np.int16)
        pcm = pcm.reshape(-1, ch).mean(axis=1).astype(np.int16)
        print(f"Test sound: {wav_path}  ({len(pcm) / rate:.1f}s)")
    else:
        from piper import PiperVoice
        voice = PiperVoice.load(str(PIPER_MODEL))
        rate = voice.config.sample_rate
        pcm = np.concatenate([c.audio_int16_array for c in voice.synthesize(PIPER_TEXT)])
        print(f"Test sound: Piper {PIPER_MODEL.name}  ({len(pcm) / rate:.1f}s)")

    if rate != RATE:
        pcm = soxr.resample(pcm, rate, RATE)
    return pcm.astype(np.int16)


def write_wav(path: Path, pcm) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def run_aec(src: dict, args: list[str], dur: float) -> None:
    """Play a test sound and record the mic through WebRTC AEC3 at the same time.

    Same wiring the robot needs: every 10 ms frame written to the speaker is
    also given to process_reverse_stream (the reference), and every 10 ms mic
    frame goes through process_stream. Raw and cleaned mic are both kept so
    the echo reduction can be measured and heard.
    """
    import os
    import threading

    if "echo-cancel" in src["name"]:
        print("WARNING: this source already runs PulseAudio's echo canceller, so\n"
              "         two cancellers would be stacked. Pick a raw mic instead.\n")

    # Route PortAudio's "pulse" device to the chosen source/sink. Must be set
    # before sounddevice initialises PortAudio.
    os.environ["PULSE_SOURCE"] = src["name"]
    if "--sink" in args:
        os.environ["PULSE_SINK"] = args[args.index("--sink") + 1]

    import numpy as np
    import sounddevice as sd
    from livekit import rtc

    ch = src["channels"]
    if "--channel" in args:
        chan = int(args[args.index("--channel") + 1])
    else:
        chan = 1 if ch == 6 else 0   # ReSpeaker 6ch: ch0 is firmware-processed, ch1 is a raw mic
    if not 0 <= chan < ch:
        sys.exit(f"--channel {chan}: this source only has {ch} channel(s)")

    wav_path = args[args.index("--wav") + 1] if "--wav" in args else None
    sound = load_test_sound(wav_path)

    # Loop the sound, with a short pause between repeats, to cover the whole run.
    nframes = int(dur * 100)
    gap = np.zeros(int(0.4 * RATE), np.int16)
    ref = np.resize(np.concatenate([sound, gap]), nframes * FRAME).astype(np.int16)
    ref_bytes = ref.tobytes()

    # Measure echo removal only; AGC would rescale the cleaned signal and skew it.
    apm = rtc.AudioProcessingModule(echo_cancellation=True, noise_suppression=True,
                                    high_pass_filter=True, auto_gain_control=False)
    lock = threading.Lock()           # speaker thread and mic loop share the module
    stop = threading.Event()
    ready = threading.Event()
    out_latency = [0.0]

    names = [d["name"] for d in sd.query_devices()]
    dev = "pulse" if "pulse" in names else None
    sink = os.environ.get("PULSE_SINK") or pactl("get-default-sink").strip()

    def speaker():
        with sd.RawOutputStream(samplerate=RATE, channels=1, dtype="int16",
                                blocksize=FRAME, latency="low", device=dev) as out:
            out_latency[0] = out.latency
            ready.set()
            for i in range(0, len(ref_bytes), FRAME_BYTES):
                if stop.is_set():
                    break
                piece = ref_bytes[i:i + FRAME_BYTES]
                out.write(piece)
                # The reference is exactly what was just handed to the speaker.
                with lock:
                    apm.process_reverse_stream(rtc.AudioFrame(piece, RATE, 1, FRAME))

    quiet = nframes // 2
    raw, clean = [], []
    overflows = 0
    print(f"\nMic    : {src['desc']}  (channel {chan} of {ch})")
    print(f"Speaker: {sink}")
    print(f"\n  >>> STAY SILENT for {quiet / 100:.0f}s -- measuring echo removal <<<\n")

    with sd.RawInputStream(samplerate=RATE, channels=ch, dtype="int16",
                           blocksize=FRAME, latency="low", device=dev) as inp:
        t = threading.Thread(target=speaker, daemon=True)
        t.start()
        ready.wait(5)
        delay_ms = int((inp.latency + out_latency[0]) * 1000)
        print(f"  latency: mic {inp.latency * 1000:.0f} ms + speaker "
              f"{out_latency[0] * 1000:.0f} ms -> stream delay {delay_ms} ms\n")
        try:
            for n in range(nframes):
                if n == quiet:
                    print(f"  >>> NOW TALK over it for {(nframes - quiet) / 100:.0f}s <<<\n")
                buf, overflowed = inp.read(FRAME)
                overflows += overflowed
                mic = np.frombuffer(buf, np.int16)[chan::ch].copy()
                raw.append(mic)
                frame = rtc.AudioFrame(mic.tobytes(), RATE, 1, FRAME)
                with lock:
                    apm.set_stream_delay_ms(delay_ms)
                    apm.process_stream(frame)   # in place
                clean.append(np.array(frame.data, dtype=np.int16))
        finally:
            stop.set()
            t.join()
    # Release it now: livekit asserts if it is still alive at interpreter exit.
    del apm

    raw = np.concatenate(raw)
    clean = np.concatenate(clean)

    OUTDIR.mkdir(exist_ok=True)
    paths = [OUTDIR / "aec_raw.wav", OUTDIR / "aec_clean.wav", OUTDIR / "aec_ref.wav"]
    for p, pcm in zip(paths, (raw, clean, ref[:len(raw)])):
        write_wav(p, pcm)

    def rms(x):
        return float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) if len(x) else 0.0

    a, b = int(AEC_SKIP_S * RATE), quiet * FRAME
    echo_raw, echo_clean = rms(raw[a:b]), rms(clean[a:b])
    talk_raw, talk_clean = rms(raw[b:]), rms(clean[b:])
    reduction = 20 * np.log10(max(echo_raw, 1e-9) / max(echo_clean, 1e-9))

    print(f"  {'':22} {'raw':>8} {'cleaned':>8}")
    print(f"  {'echo only (silent)':22} {echo_raw:8.1f} {echo_clean:8.1f}   "
          f"-> echo reduced by {reduction:.1f} dB")
    print(f"  {'you talking over it':22} {talk_raw:8.1f} {talk_clean:8.1f}")
    if overflows:
        print(f"\n  {overflows} mic overflow(s) -- frames were dropped, results are less reliable")
    if echo_raw < 50:
        print("\n  The raw mic barely heard the speaker -- turn the volume up, or the\n"
              "  reduction figure is just measuring background noise.")
    print("\n  Rough guide: <10 dB poor, 15-25 dB good, >25 dB excellent (Chrome-like).")

    print(f"\nFiles are in {OUTDIR}\n")
    for p in paths[:2]:
        input(f"  [Enter] to play {p.name} ... ")
        subprocess.run(["paplay", str(p)])
 
 
def main() -> None:
    args = sys.argv[1:]
    sources = list_sources()
    if not sources:
        sys.exit("No input sources at all. Is PulseAudio running?")
 
    if "--list" in args:
        show_sources(sources)
        return
 
    if "--play-only" in args:
        paths = sorted(OUTDIR.glob("ch*.wav"))
        if not paths:
            sys.exit(f"No recordings in {OUTDIR}. Run without --play-only first.")
        playback(paths)
        return
 
    # A bare number is the duration -- but not the value after a flag like --channel 2.
    flag_values = {args[i + 1] for i, a in enumerate(args[:-1])
                   if a in ("--source", "--wav", "--sink", "--channel")}
    dur = next((float(a) for a in args
                if re.fullmatch(r"[\d.]+", a) and a not in flag_values),
               20.0 if "--aec" in args else 8.0)
 
    if "--source" in args:
        src = match_source(sources, args[args.index("--source") + 1])
    elif "--laptop" in args or "--onboard" in args:
        # The built-in mic is whatever real ALSA capture device is not the
        # array. Matching on "pci-" would miss it on a Jetson or a Pi, where
        # onboard audio shows up as platform-/tegra- instead.
        builtin = [s for s in sources
                   if s["name"].startswith("alsa_input.") and "respeaker" not in s["name"].lower()]
        if not builtin:
            sys.exit("No built-in mic found. Run with --list to see what is available.")
        src = builtin[0]
    elif "--respeaker" in args:
        src = match_source(sources, "respeaker")
    elif "--default" in args:
        default = pactl("get-default-source").strip()
        src = next((s for s in sources if s["name"] == default), None)
        if not src:
            sys.exit(f"Default source {default!r} is not a usable mic "
                     f"(unset, or a .monitor). Run with --list to see what is available.")
    else:
        src = pick_source(sources)
 
    dev = usb_devnum()
    if dev and "respeaker" in src["name"].lower():
        print(f"USB device number: {dev}   "
              "(if this changes between runs, the array is re-enumerating)")

    if "--aec" in args:
        run_aec(src, args, dur)
        return

    raw = record(dur, src)
    paths = split_and_write(raw, src["channels"])
    playback(paths)
 
 
if __name__ == "__main__":
    main()
 