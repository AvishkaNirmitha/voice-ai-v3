#!/usr/bin/env python3
"""
voice_recorder.py

Record audio from a chosen microphone, controlled with keyboard hotkeys.

Controls:
    R  -> start recording
    S  -> stop recording (saves a .wav file)
    Q  -> quit the program

Usage:
    python voice_recorder.py               # lists devices the same way your
                                             # OS Sound Settings page does
    python voice_recorder.py --raw          # lists raw ALSA/PortAudio devices
                                             # instead (old behavior)
    python voice_recorder.py --channels 4 --outdir recordings

Install dependencies first:
    pip install sounddevice soundfile numpy pynput

Notes:
    - Default mode lists input sources via `pactl`, the same source PipeWire/
      PulseAudio feeds to your Settings app, so the numbers you see here
      should match what you see there. Recording is then routed through
      PulseAudio's virtual "pulse" device, pinned to the source you pick via
      the PULSE_SOURCE environment variable.
    - --raw falls back to asking PortAudio to enumerate ALSA hardware
      directly, which is what the previous version of this script did. Use
      it only if `pactl` isn't available on your system.
    - Uses 'pynput' (not 'keyboard') so it does NOT require root/sudo on
      Linux X11. Wayland restricts global key capture, so this may not work
      there — click the terminal window before pressing R/S/Q either way.
"""

import argparse
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
from pynput import keyboard


# ---------------------------------------------------------------------------
# Device listing: PulseAudio/PipeWire sources (matches OS Settings page)
# ---------------------------------------------------------------------------

def list_pulse_sources():
    """Return real (non-monitor) input sources as reported by pactl.

    This mirrors what GNOME/KDE Settings -> Sound -> Input shows, since both
    read from the same PipeWire/PulseAudio daemon.
    """
    try:
        output = subprocess.check_output(["pactl", "list", "sources"], text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None  # signal "pactl not usable" to caller

    sources = []
    current = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line.startswith("Source #"):
            if current:
                sources.append(current)
            current = {"index": line.split("#", 1)[1]}
        elif line.startswith("Name:"):
            current["name"] = line.split("Name:", 1)[1].strip()
        elif line.startswith("Description:"):
            current["description"] = line.split("Description:", 1)[1].strip()
        elif line.startswith("State:"):
            current["state"] = line.split("State:", 1)[1].strip()
    if current:
        sources.append(current)

    # Monitor sources capture what's being *played*, not a microphone input.
    real_sources = [s for s in sources if not s.get("name", "").endswith(".monitor")]
    return real_sources


def choose_pulse_source(sources):
    print("\nInput devices (matches your OS Sound Settings page):\n")
    for i, s in enumerate(sources):
        desc = s.get("description", s.get("name", "unknown"))
        state = s.get("state", "")
        marker = " (default)" if state == "RUNNING" else ""
        print(f"  [{i}] {desc}{marker}")

    while True:
        choice = input("\nSelect input device index: ").strip()
        try:
            idx = int(choice)
            if 0 <= idx < len(sources):
                return sources[idx]
        except ValueError:
            pass
        print("Invalid selection, please enter one of the listed indices.")


# ---------------------------------------------------------------------------
# Device listing: raw PortAudio/ALSA enumeration (fallback / --raw mode)
# ---------------------------------------------------------------------------

def list_input_devices():
    devices = sd.query_devices()
    input_indices = []

    print("\nAvailable input devices (raw PortAudio/ALSA list):\n")
    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0:
            input_indices.append(i)
            default_sr = int(d["default_samplerate"])
            print(f"  [{i}] {d['name']}  "
                  f"(channels: {d['max_input_channels']}, default SR: {default_sr})")

    if not input_indices:
        print("No input devices found. Is a microphone connected?")
        sys.exit(1)

    return input_indices


def choose_device(input_indices):
    while True:
        choice = input("\nSelect input device index: ").strip()
        try:
            idx = int(choice)
            if idx in input_indices:
                return idx
        except ValueError:
            pass
        print("Invalid selection, please enter one of the listed indices.")


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

class Recorder:
    def __init__(self, device, samplerate, channels, outdir):
        self.device = device
        self.samplerate = samplerate
        self.channels = channels
        self.outdir = Path(outdir)
        self.outdir.mkdir(parents=True, exist_ok=True)

        self.stream = None
        self.frames = []
        self.recording = False
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):
        if status:
            print(status, file=sys.stderr)
        with self._lock:
            if self.recording:
                self.frames.append(indata.copy())

    def start(self):
        with self._lock:
            if self.recording:
                return
            self.frames = []
            self.recording = True

        self.stream = sd.InputStream(
            device=self.device,
            channels=self.channels,
            samplerate=self.samplerate,
            callback=self._callback,
        )
        self.stream.start()
        print("\n[REC] Recording started...")

    def stop(self):
        with self._lock:
            if not self.recording:
                return
            self.recording = False

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        print("[STOP] Recording stopped.")

        if self.frames:
            audio = np.concatenate(self.frames, axis=0)
            filename = self.outdir / f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
            sf.write(str(filename), audio, self.samplerate)
            print(f"Saved to: {filename.resolve()}")
        else:
            print("No audio captured (recording was too short or empty).")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Keyboard-controlled microphone recorder.")
    parser.add_argument("--samplerate", type=int, default=44100, help="Sample rate in Hz (default: 44100)")
    parser.add_argument("--channels", type=int, default=1, help="Number of channels (default: 1 = mono)")
    parser.add_argument("--outdir", type=str, default=".", help="Directory to save recordings (default: current dir)")
    parser.add_argument("--raw", action="store_true",
                         help="List raw ALSA/PortAudio devices instead of PulseAudio/PipeWire sources")
    args = parser.parse_args()

    device_for_stream = None

    if not args.raw:
        sources = list_pulse_sources()
        if sources is None:
            print("Could not query 'pactl' (is PulseAudio/PipeWire installed?). Falling back to --raw mode.\n")
            args.raw = True
        elif not sources:
            print("pactl reported no input sources. Falling back to --raw mode.\n")
            args.raw = True
        else:
            chosen = choose_pulse_source(sources)
            os.environ["PULSE_SOURCE"] = chosen["name"]
            device_for_stream = "pulse"  # PortAudio's PulseAudio passthrough device

    if args.raw:
        input_indices = list_input_devices()
        device_for_stream = choose_device(input_indices)

    recorder = Recorder(
        device=device_for_stream,
        samplerate=args.samplerate,
        channels=args.channels,
        outdir=args.outdir,
    )

    print("\nControls:")
    print("  [R] Start recording")
    print("  [S] Stop recording")
    print("  [Q] Quit\n")
    print("Ready. Press a key (make sure this window has focus)...")

    def on_press(key):
        try:
            char = key.char.lower() if key.char else None
        except AttributeError:
            char = None

        if char == "r":
            recorder.start()
        elif char == "s":
            recorder.stop()
        elif char == "q":
            if recorder.recording:
                recorder.stop()
            print("Exiting.")
            return False  # stops the listener

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()


if __name__ == "__main__":
    main()

    