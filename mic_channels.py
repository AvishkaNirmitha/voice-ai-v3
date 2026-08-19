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
    python3 mic_channels.py --source NAME   # use an exact pactl source name
    python3 mic_channels.py --list          # just show the available mics
    python3 mic_channels.py --play-only     # replay the last recording


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

    dur = next((float(a) for a in args if re.fullmatch(r"[\d.]+", a)), 8.0)

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
    else:
        src = pick_source(sources)

    dev = usb_devnum()
    if dev and "respeaker" in src["name"].lower():
        print(f"USB device number: {dev}   "
              "(if this changes between runs, the array is re-enumerating)")

    raw = record(dur, src)
    paths = split_and_write(raw, src["channels"])
    playback(paths)


if __name__ == "__main__":
    main()
