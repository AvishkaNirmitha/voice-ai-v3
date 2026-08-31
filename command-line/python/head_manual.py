"""
head_manual.py - manual, motor-by-motor control of the robot head.

A standalone Tk panel: one slider per neck motor - yaw and pitch - plus an
editable UDP address and port, so it can aim a head on this machine or on
another one. Nothing in the project imports this file; it is a bench tool, and
it can run while the voice AI is running or instead of it. The wire protocol
lives in head_link.py, not here.

    python head_manual.py                          # uses $ROBOT_HEAD_ADDR
    python head_manual.py --addr 192.168.1.42:8770 # prefill; editable in the window
    python head_manual.py --verbose                # print every datagram
    python head_manual.py --sink 8770              # no GUI: print what arrives

HOW MANUAL CONTROL IS ENTERED AND LEFT. There is no engage and no release. The
head is under manual control while jog packets are arriving - it stops tracking
faces, stops gesturing, and abandons any directed look in progress - and hands
itself back about two seconds after the last one. That shapes the whole design
of this panel:

  * moving a slider takes the head; letting go and waiting gives it back
  * this panel must NOT idle-repeat the last position. A keepalive is the
    obvious way to insure the final packet against loss, and it is exactly
    wrong here: it would hold the head under manual control for as long as the
    window stayed open. Instead the settled value is repeated for SETTLE_S and
    then the panel goes quiet - long enough to cover a dropped packet, far
    short of the head's two-second hand-back.
  * closing the window or hitting ctrl-C needs no farewell message. Nothing to
    lose means nothing that can be lost.

THE RANGES COME FROM THE HEAD. head_link.limits() reports the servos' real
calibration, so the sliders follow a re-homed or rebuilt neck; hardcoded ones
quietly stop matching it. If the head does not answer, the panel falls back to
+/-30 / +/-20 and says so in the status line rather than pretending.

If the head does not move, run --sink on the head machine to see whether the
packets are arriving at all - sendto() on this side cannot tell you, and never
will. The head's own console prints "[JOG start] manual control" on the first
packet and "[LOOK done] manual released" about 2 s after the last.
"""

import argparse
import json
import os
import queue
import signal
import socket
import threading
import time

import head_link

DEFAULT_ADDR = os.environ.get("ROBOT_HEAD_ADDR", "127.0.0.1:8770")

# Documented ceiling is 20-30 packets a second: the neck cannot follow faster,
# so anything above this is wasted bandwidth, not smoother motion.
SEND_HZ = 25

# Keep repeating a value that has stopped changing for this long, then go
# quiet. The last packet of a drag - the one the user let go on - is the only
# one whose loss would not be corrected by the next, so it is sent several
# times; SETTLE_S must stay well under the head's ~2 s hand-back or the head
# would never get itself back. See the note at the top of this file.
SETTLE_S = 0.3

# What the head waits after the last jog before resuming tracking. Only used to
# show the countdown - the head owns this timing, this panel just reports it.
RELEASE_S = 2.0

# Used only when the head does not answer limits(). Deliberately conservative:
# a neck that turns further loses nothing but reach, one that turns less would
# be driven into its stop.
FALLBACK = {"yaw_min": -30.0, "yaw_max": 30.0,
            "pitch_min": -20.0, "pitch_max": 20.0, "yaw": 0.0, "pitch": 0.0}

BG = "#111318"
FG = "#c9ced6"
DIM = "#8b93a1"
TROUGH = "#1b1f26"
ACCENT = "#4ea3ff"
WARN = "#ffc45c"
OK = "#3ddc84"


def parse_addr(text):
    """'host' or 'host:port' -> (host, port). Raises ValueError with a message
    fit to show the user as-is."""
    host, _, port = str(text).strip().partition(":")
    host = host.strip() or "127.0.0.1"
    return host, parse_port(port) if port.strip() else 8770


def parse_port(text):
    try:
        port = int(str(text).strip())
    except ValueError:
        raise ValueError(f"port {text!r} is not a number")
    if not 1 <= port <= 65535:
        raise ValueError(f"port {port} is out of range")
    return port


class Panel:
    """The window.

    Slider values live in plain attributes under a lock: the Tk thread writes
    them, a sender thread reads them at SEND_HZ, and neither waits on the
    other - so neither a slow network nor a 2 s limits() timeout can make the
    sliders feel sticky.
    """

    def __init__(self, host, port):
        self.host, self.port = host, port
        self._lock = threading.Lock()
        self._yaw = 0.0
        self._pitch = 0.0
        self._resync = False        # adopt this pose without sending it
        self._stop = threading.Event()
        self._syncing = False       # guards .set() against the Scale callback
        self.sent = 0
        self.last_sent = 0.0        # monotonic; drives the hand-back countdown
        self.error = None
        self._replies = queue.Queue()   # limits() results, for the Tk thread

    # -- shared state ------------------------------------------------------
    def _pose(self):
        with self._lock:
            resync, self._resync = self._resync, False
            return self._yaw, self._pitch, resync

    def _set_pose(self, yaw, pitch, silent=False):
        """silent=True adopts the value without driving the head - used when
        the panel is catching up to where the neck already is, which must not
        count as the user grabbing it."""
        with self._lock:
            self._yaw, self._pitch = float(yaw), float(pitch)
            if silent:
                self._resync = True

    # -- sender thread -----------------------------------------------------
    def _sender(self):
        last = None
        settled_at = float("-inf")      # so an untouched panel is silent
        period = 1.0 / SEND_HZ
        while not self._stop.wait(period):
            yaw, pitch, resync = self._pose()
            if resync or last is None:
                last = (yaw, pitch)
                continue
            now = time.monotonic()
            if (yaw, pitch) != last:
                last, settled_at = (yaw, pitch), now
            elif now - settled_at > SETTLE_S:
                continue                # settled: let the head have itself back
            head_link.jog(yaw, pitch)
            self.sent += 1
            self.last_sent = now

    # -- limits ------------------------------------------------------------
    def _ask_limits(self):
        """Off the Tk thread: limits() blocks for up to its timeout, and a
        frozen window is a worse answer than a late one."""
        self._replies.put(head_link.limits())

    def refresh_limits(self):
        threading.Thread(target=self._ask_limits, daemon=True).start()

    # -- window ------------------------------------------------------------
    def run(self):
        import tkinter as tk

        root = tk.Tk()
        root.title("Spera head - manual control")
        root.configure(bg=BG)
        root.resizable(False, False)

        wrap = tk.Frame(root, bg=BG)
        wrap.pack(fill="both", expand=True, padx=16, pady=14)

        def label(parent, text, fg=DIM, size=9):
            return tk.Label(parent, text=text, bg=BG, fg=fg,
                            font=("monospace", size))

        def button(parent, text, cmd, width=9):
            return tk.Button(parent, text=text, command=cmd, width=width,
                             bg="#232833", fg=FG, relief="flat",
                             activebackground="#2e3542", activeforeground="#fff",
                             font=("monospace", 9), bd=0, highlightthickness=0,
                             padx=4, pady=3)

        def entry(parent, value, width):
            e = tk.Entry(parent, width=width, bg=TROUGH, fg=FG,
                         insertbackground=FG, relief="flat",
                         font=("monospace", 10), highlightthickness=1,
                         highlightbackground="#2e3542", highlightcolor=ACCENT)
            e.insert(0, str(value))
            return e

        # -- target --------------------------------------------------------
        addr_row = tk.Frame(wrap, bg=BG)
        addr_row.pack(fill="x")
        label(addr_row, "head at").pack(side="left")
        ip_e = entry(addr_row, self.host, 17)
        ip_e.pack(side="left", padx=(8, 2))
        label(addr_row, ":", FG, 10).pack(side="left")
        port_e = entry(addr_row, self.port, 6)
        port_e.pack(side="left", padx=(2, 8))

        status = label(wrap, "", DIM)
        range_l = label(wrap, "reading range from head ...", DIM)

        def apply_addr(_event=None):
            """Retarget, then re-read the range: a different head is a
            different neck, and keeping the old numbers would be a lie."""
            try:
                port = parse_port(port_e.get())
            except ValueError as e:
                status.config(text=str(e), fg=WARN)
                return
            head_link.set_target(ip_e.get().strip() or "127.0.0.1", port)
            range_l.config(text="reading range from head ...", fg=DIM)
            self.refresh_limits()

        button(addr_row, "apply", apply_addr, 7).pack(side="left")
        ip_e.bind("<Return>", apply_addr)
        port_e.bind("<Return>", apply_addr)

        # -- the two motors ------------------------------------------------
        def on_slider(_=None):
            if self._syncing:
                return
            self._set_pose(yaw_s.get(), pitch_s.get())

        def slider(text):
            label(wrap, text).pack(anchor="w", pady=(10, 0))
            s = tk.Scale(wrap, from_=FALLBACK["yaw_min"],
                         to=FALLBACK["yaw_max"], resolution=0.5,
                         orient="horizontal", bg=BG, fg=FG,
                         troughcolor=TROUGH, highlightthickness=0, bd=0,
                         sliderrelief="flat", activebackground=ACCENT,
                         length=430, font=("monospace", 8))
            s.set(0.0)
            s.pack(fill="x")
            # Wired up only after the starting value is in place: a tk.Scale
            # fires its command once during construction, and attaching this
            # earlier means merely opening the window grabs the head.
            s.config(command=on_slider)
            return s

        yaw_s = slider("motor 1   yaw    - left / + right   (+ is the robot's right)")
        pitch_s = slider("motor 2   pitch  - down / + up")

        row = tk.Frame(wrap, bg=BG)
        row.pack(fill="x", pady=(12, 0))

        def centre():
            self._syncing = True
            yaw_s.set(0.0)
            pitch_s.set(0.0)
            self._syncing = False
            self._set_pose(0.0, 0.0)        # not silent: this is a real move

        button(row, "centre", centre, 8).pack(side="left")
        button(row, "re-read range", lambda: (
            range_l.config(text="reading range from head ...", fg=DIM),
            self.refresh_limits()), 14).pack(side="left", padx=6)

        range_l.pack(anchor="w", pady=(12, 0))
        status.pack(anchor="w", pady=(2, 0))

        # -- ticker --------------------------------------------------------
        # Tk is touched from this thread only. The sender thread and the
        # limits thread just leave values behind for this to pick up.
        def apply_limits(lim):
            known = lim is not None
            lim = lim or FALLBACK
            yaw_s.config(from_=lim["yaw_min"], to=lim["yaw_max"])
            pitch_s.config(from_=lim["pitch_min"], to=lim["pitch_max"])
            # Start the sliders where the neck actually is, silently: catching
            # up to the head is not the user grabbing it.
            self._syncing = True
            yaw_s.set(lim.get("yaw", 0.0))
            pitch_s.set(lim.get("pitch", 0.0))
            self._syncing = False
            self._set_pose(lim.get("yaw", 0.0), lim.get("pitch", 0.0),
                           silent=True)
            source = ("from head" if known else
                      "- HEAD DID NOT ANSWER, using safe fallback")
            range_l.config(
                text=f"yaw {lim['yaw_min']:+.1f} .. {lim['yaw_max']:+.1f}   "
                     f"pitch {lim['pitch_min']:+.1f} .. {lim['pitch_max']:+.1f}"
                     f"   {source}",
                fg=DIM if known else WARN)

        def tick():
            if self._stop.is_set():         # ctrl-C, see below
                root.destroy()
                return
            try:
                apply_limits(self._replies.get_nowait())
            except queue.Empty:
                pass
            idle = time.monotonic() - self.last_sent
            if not self.sent:
                state, colour = "idle - move a slider to take the head", DIM
            elif idle < SETTLE_S:
                state, colour = "manual control", OK
            elif idle < RELEASE_S:
                state, colour = (f"handing back in {RELEASE_S - idle:.1f}s",
                                 WARN)
            else:
                state, colour = "head released - tracking and gestures resumed", DIM
            status.config(text=f"{head_link.target()}  -  {state}  -  "
                               f"{self.sent} jogs", fg=colour)
            root.after(100, tick)

        root.protocol("WM_DELETE_WINDOW", lambda: (self._stop.set(),
                                                   root.destroy()))
        # Ctrl-C in the launching terminal otherwise lands inside whichever Tk
        # callback happens to be running, where Tk prints it and carries on -
        # leaving a window nobody can close from the keyboard. Raising a flag
        # the ticker already checks 10 times a second is the whole fix.
        try:
            signal.signal(signal.SIGINT, lambda *_: self._stop.set())
        except ValueError:
            pass                # not the main thread; the backstop below covers it
        apply_addr()
        tick()
        threading.Thread(target=self._sender, daemon=True).start()
        try:
            root.mainloop()
        except KeyboardInterrupt:
            pass                # nothing to send on the way out, by design
        finally:
            self._stop.set()


def _sink(port):
    """Print every datagram that arrives. Run this on the head machine to
    prove packets are getting there before suspecting the head code - sendto()
    on the panel side cannot tell you, and never will.

    It also answers limits requests, with the fallback numbers, so the panel
    can be driven end to end with no head on the bench.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    print(f"listening on 0.0.0.0:{port} - ctrl-c to stop", flush=True)
    while True:
        data, src = sock.recvfrom(8192)
        try:
            msg = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            print(f"{src[0]}:{src[1]}  {data!r}", flush=True)
            continue
        print(f"{src[0]}:{src[1]}  {json.dumps(msg)}", flush=True)
        if msg.get("type") == "limits":
            reply = dict(FALLBACK, v=1, type="limits_result", id=msg.get("id"))
            sock.sendto(json.dumps(reply).encode("utf-8"), src)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Manual yaw/pitch control panel for the robot head.")
    ap.add_argument("--addr", default=DEFAULT_ADDR, metavar="HOST[:PORT]",
                    help=f"prefill the target (default {DEFAULT_ADDR}); it is "
                         f"editable in the window either way")
    ap.add_argument("--verbose", action="store_true",
                    help="print every datagram; off by default because a drag "
                         "sends 25 a second")
    ap.add_argument("--sink", type=int, metavar="PORT",
                    help="no GUI: bind this port, print what arrives and "
                         "answer limits requests")
    args = ap.parse_args()

    if args.sink:
        try:
            _sink(args.sink)
        except KeyboardInterrupt:
            print("\nstopped.")
        raise SystemExit

    try:
        host, port = parse_addr(args.addr)
    except ValueError as e:
        raise SystemExit(f"--addr: {e}")

    # head_link ships with VERBOSE on for the voice AI, where a handful of
    # messages per reply is useful. Here it is 25 lines a second.
    head_link.VERBOSE = args.verbose
    head_link.set_target(host, port)
    print(f"robot head target: {head_link.target()}   "
          f"(editable in the window; $ROBOT_HEAD_ADDR sets the default)")
    Panel(host, port).run()
