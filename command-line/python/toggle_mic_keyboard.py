#!/usr/bin/env python3
"""Toggle the current default microphone on/off with a global keyboard shortcut.

Default hotkey: Ctrl+Alt+M   (quit with Ctrl+Alt+Q)

Works on PulseAudio / PipeWire via `pactl`, and listens for the hotkey
globally through pynput (X11 session).
"""

import argparse
import shutil
import subprocess
import sys

from pynput import keyboard


def pactl(*args: str) -> str:
    return subprocess.run(
        ["pactl", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def default_source() -> str:
    """Name of the microphone currently selected as default."""
    return pactl("get-default-source")


def is_muted(source: str) -> bool:
    # "Mute: yes" / "Mute: no"
    return pactl("get-source-mute", source).split(":")[1].strip() == "yes"


def notify(title: str, body: str) -> None:
    if shutil.which("notify-send"):
        subprocess.run(
            ["notify-send", "-t", "1200", "-h", "string:x-canonical-private-synchronous:mic",
             title, body],
            check=False,
        )


def toggle() -> None:
    source = default_source()          # re-read each time: default device can change
    pactl("set-source-mute", source, "toggle")
    muted = is_muted(source)
    state = "OFF (muted)" if muted else "ON (live)"
    print(f"Mic {state}  ->  {source}", flush=True)
    notify("Microphone", "Muted 🔇" if muted else "Unmuted 🎤")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hotkey", default="<ctrl>+<alt>+m",
                        help="pynput hotkey spec (default: %(default)s)")
    parser.add_argument("--quit-hotkey", default="<ctrl>+<alt>+q",
                        help="hotkey that exits the script (default: %(default)s)")
    parser.add_argument("--once", action="store_true",
                        help="just toggle the mic and exit (no hotkey listener)")
    args = parser.parse_args()

    if not shutil.which("pactl"):
        print("pactl not found — install pulseaudio-utils", file=sys.stderr)
        return 1

    if args.once:
        toggle()
        return 0

    source = default_source()
    print(f"Default mic : {source}")
    print(f"Currently   : {'OFF (muted)' if is_muted(source) else 'ON (live)'}")
    print(f"Toggle with : {args.hotkey}")
    print(f"Quit with   : {args.quit_hotkey}  (or Ctrl+C)")

    listener: keyboard.GlobalHotKeys

    def stop() -> None:
        print("\nBye.")
        listener.stop()

    listener = keyboard.GlobalHotKeys({args.hotkey: toggle, args.quit_hotkey: stop})
    listener.start()
    try:
        listener.join()
    except KeyboardInterrupt:
        print("\nBye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
