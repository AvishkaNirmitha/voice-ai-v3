#!/usr/bin/env python3
"""
servo_gui.py -- slider control panel for Feetech STS servos.

Runs on tkinter (bundled with Python -- no extra install beyond pyserial).
It has to run on the machine the servos are plugged into, since it talks
straight to the COM port.

    python servo_gui.py                 # defaults to COM7 @ 1 Mbps
    python servo_gui.py --port COM3 --baud 115200

Layout
------
  Connect  ->  Scan  ->  one panel per servo found.

Each panel gives you a position slider (degrees), a speed slider, an
acceleration slider, a torque toggle, soft limits, and a live telemetry
readout. Sliders take effect as you drag them ("live" checkbox, on by
default); every move is speed- and accel-limited, and sliders initialise to
where the servo already is, so nothing jumps on connect.

All serial I/O happens on one background thread. The UI never touches the
bus directly -- it posts commands to a queue and reads results back, which
keeps the window responsive and keeps two threads off the same port.
"""

from __future__ import annotations

import argparse
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, List, Optional

from feetech_sts import (
    COUNTS_PER_S_PER_RPM,
    DEG_PER_COUNT,
    MODE_POSITION,
    MODE_WHEEL,
    STSBus,
    STSError,
)

TELEMETRY_PERIOD = 0.12     # seconds between telemetry sweeps
LOOP_SLEEP = 0.01
MAX_SPEED_COUNTS = 3400     # STS3215 ceiling, ~50 rpm
MAX_ACCEL = 150

# Stable by-id path: survives replug, unlike /dev/ttyACM0 vs ttyACM1.
DEFAULT_PORT = "/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B14111115-if00"


# ==========================================================================
# Serial worker
# ==========================================================================

class Bridge:
    """Owns the STSBus on a worker thread. UI talks to it through queues."""

    def __init__(self) -> None:
        self.cmdq: "queue.Queue" = queue.Queue()
        self.outq: "queue.Queue" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._pending: Dict[int, tuple] = {}   # sid -> (counts, speed, accel)
        self.watch_ids: List[int] = []

    # -- lifecycle ---------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def connect(self, port: str, baud: int) -> None:
        if self.connected:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, args=(port, baud), daemon=True)
        self._thread.start()

    def disconnect(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.5)
        self._thread = None

    # -- UI-side API -------------------------------------------------------
    def submit(self, fn) -> None:
        """Queue a callable that receives the live bus."""
        self.cmdq.put(fn)

    def set_target(self, sid: int, counts: int, speed: int, accel: int) -> None:
        """Coalescing setter -- rapid slider drags collapse to the latest value."""
        with self._lock:
            self._pending[sid] = (int(counts), int(speed), int(accel))

    def _emit(self, kind: str, payload=None) -> None:
        self.outq.put((kind, payload))

    # -- worker ------------------------------------------------------------
    def _run(self, port: str, baud: int) -> None:
        try:
            bus = STSBus(port, baudrate=baud, timeout=0.03, retries=1)
        except Exception as exc:
            self._emit("error", f"could not open {port}: {exc}")
            self._emit("disconnected")
            self._running = False
            return

        self._emit("connected", port)
        next_telemetry = 0.0
        fails = 0

        try:
            while self._running:
                # 1. run queued one-shot commands
                while True:
                    try:
                        fn = self.cmdq.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        fn(bus)
                    except Exception as exc:
                        self._emit("error", str(exc))

                # 2. push the newest slider targets
                with self._lock:
                    pending, self._pending = self._pending, {}
                for sid, (counts, speed, accel) in pending.items():
                    try:
                        bus.set_position(sid, counts, speed=speed, accel=accel)
                    except STSError as exc:
                        self._emit("error", f"servo {sid}: {exc}")

                # 3. telemetry sweep
                now = time.monotonic()
                if self.watch_ids and now >= next_telemetry:
                    next_telemetry = now + TELEMETRY_PERIOD
                    for sid in list(self.watch_ids):
                        try:
                            self._emit("state", bus.read_state(sid))
                            fails = 0
                        except STSError:
                            fails += 1
                            if fails % 25 == 1:
                                self._emit("error", f"servo {sid} not responding")

                time.sleep(LOOP_SLEEP)
        finally:
            try:
                bus.close()
            except Exception:
                pass
            self._emit("disconnected")


# ==========================================================================
# One servo's controls
# ==========================================================================

class ServoPanel(ttk.LabelFrame):
    def __init__(self, parent, app: "App", sid: int, start_counts: int):
        super().__init__(parent, text=f"  Servo ID {sid}  ", padding=10)
        self.app = app
        self.sid = sid
        self._suppress = False          # stops programmatic slider sets re-firing

        start_deg = start_counts * DEG_PER_COUNT

        self.mode = tk.StringVar(value="position")
        self.torque = tk.BooleanVar(value=True)
        self.lo = tk.DoubleVar(value=max(0.0, start_deg - 45))
        self.hi = tk.DoubleVar(value=min(360.0, start_deg + 45))
        self.pos = tk.DoubleVar(value=start_deg)
        self.speed = tk.DoubleVar(value=MAX_SPEED_COUNTS)
        self.accel = tk.DoubleVar(value=MAX_ACCEL)
        self.vel = tk.DoubleVar(value=0)

        # ---- row 0: mode + torque ----
        top = ttk.Frame(self)
        top.grid(row=0, column=0, columnspan=3, sticky="we", pady=(0, 8))
        ttk.Label(top, text="Mode").pack(side="left")
        cb = ttk.Combobox(top, textvariable=self.mode, width=10, state="readonly",
                          values=["position", "wheel"])
        cb.pack(side="left", padx=(6, 18))
        cb.bind("<<ComboboxSelected>>", self._on_mode)
        ttk.Checkbutton(top, text="Torque", variable=self.torque,
                        command=self._on_torque).pack(side="left")
        ttk.Button(top, text="Hold here", width=10,
                   command=self._hold).pack(side="right")

        # ---- soft limits ----
        lim = ttk.Frame(self)
        lim.grid(row=1, column=0, columnspan=3, sticky="we", pady=(0, 6))
        ttk.Label(lim, text="Soft limits (deg)   min").pack(side="left")
        ttk.Spinbox(lim, from_=0, to=360, increment=1, width=6, textvariable=self.lo,
                    command=self._retune).pack(side="left", padx=4)
        ttk.Label(lim, text="max").pack(side="left")
        ttk.Spinbox(lim, from_=0, to=360, increment=1, width=6, textvariable=self.hi,
                    command=self._retune).pack(side="left", padx=4)

        # ---- sliders ----
        self.pos_scale = self._slider(2, "Position", self.lo.get(), self.hi.get(),
                                      0.5, self.pos, self._on_pos, "deg")
        self._slider(3, "Speed", 0, MAX_SPEED_COUNTS, 10, self.speed,
                     self._on_pos, "counts/s")
        self._slider(4, "Accel", 0, MAX_ACCEL, 1, self.accel, self._on_pos, "units")
        self.vel_scale = self._slider(5, "Velocity", -50, 50, 0.5, self.vel,
                                      self._on_vel, "rpm")

        # ---- telemetry ----
        self.readout = ttk.Label(self, text="--", font=("Consolas", 9),
                                 foreground="#334")
        self.readout.grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self._sync_enable()

    # -- widget helpers ----------------------------------------------------
    def _slider(self, row, label, lo, hi, res, var, cmd, unit):
        ttk.Label(self, text=label, width=9).grid(row=row, column=0, sticky="w")
        s = tk.Scale(self, from_=lo, to=hi, resolution=res, orient="horizontal",
                     variable=var, length=340, showvalue=True,
                     command=lambda _v: cmd())
        s.grid(row=row, column=1, sticky="we", padx=6)
        ttk.Label(self, text=unit, width=9).grid(row=row, column=2, sticky="w")
        self.columnconfigure(1, weight=1)
        return s

    def _sync_enable(self) -> None:
        wheel = self.mode.get() == "wheel"
        self.pos_scale.configure(state="disabled" if wheel else "normal")
        self.vel_scale.configure(state="normal" if wheel else "disabled")

    def _retune(self) -> None:
        lo, hi = self.lo.get(), self.hi.get()
        if hi <= lo:
            hi = lo + 1
            self.hi.set(hi)
        self.pos_scale.configure(from_=lo, to=hi)

    # -- callbacks ---------------------------------------------------------
    def _on_pos(self) -> None:
        if self._suppress or self.mode.get() != "position":
            return
        if not self.app.live.get():
            return
        self.send_position()

    def send_position(self) -> None:
        deg = min(max(self.pos.get(), self.lo.get()), self.hi.get())
        self.app.bridge.set_target(
            self.sid,
            counts=round(deg / DEG_PER_COUNT),
            speed=round(self.speed.get()),
            accel=round(self.accel.get()),
        )

    def _on_vel(self) -> None:
        if self._suppress or self.mode.get() != "wheel":
            return
        rpm = self.vel.get()
        self.app.bridge.submit(
            lambda bus, s=self.sid, r=rpm, a=round(self.accel.get()):
            bus.set_velocity_rpm(s, r, accel=a)
        )

    def _on_torque(self) -> None:
        on = self.torque.get()
        self.app.bridge.submit(lambda bus, s=self.sid, o=on: bus.set_torque(s, o))

    def _hold(self) -> None:
        """Snap the position slider to where the servo physically is."""
        def job(bus, s=self.sid):
            counts = bus.read_position(s)
            bus.set_position(s, counts, speed=400, accel=20)
            self.app.bridge._emit("snap", (s, counts))
        self.app.bridge.submit(job)

    def _on_mode(self, _evt=None) -> None:
        target = MODE_WHEEL if self.mode.get() == "wheel" else MODE_POSITION
        if target == MODE_WHEEL:
            ok = messagebox.askokcancel(
                "Switch to wheel mode?",
                f"Servo {self.sid} will spin continuously and IGNORE the angle "
                "limits. On a mechanism with end stops this will stall the motor.\n\n"
                "Make sure the horn is free before continuing.",
            )
            if not ok:
                self.mode.set("position")
                return
        self.vel.set(0)
        self.app.bridge.submit(lambda bus, s=self.sid, m=target: bus.set_mode(s, m))
        if target == MODE_WHEEL:
            self.app.bridge.submit(lambda bus, s=self.sid: bus.set_velocity(s, 0))
        self._sync_enable()

    # -- inbound -----------------------------------------------------------
    def snap_to(self, counts: int) -> None:
        self._suppress = True
        self.pos.set(round(counts * DEG_PER_COUNT, 1))
        self._suppress = False

    def update_state(self, st) -> None:
        self.readout.configure(
            text=(f"pos {st.degrees:7.2f}deg   spd {st.rpm:6.1f}rpm   "
                  f"load {st.load:>5}   {st.voltage:4.1f}V   {st.temperature:>3}C   "
                  f"{st.current_ma:6.1f}mA   {'MOVING' if st.moving else 'idle'}"),
            foreground="#a00" if st.temperature > 60 else "#334",
        )


# ==========================================================================
# Main window
# ==========================================================================

class App(ttk.Frame):
    def __init__(self, root: tk.Tk, port: str, baud: int):
        super().__init__(root, padding=12)
        self.pack(fill="both", expand=True)
        self.root = root
        self.bridge = Bridge()
        self.panels: Dict[int, ServoPanel] = {}

        self.port = tk.StringVar(value=port)
        self.baud = tk.IntVar(value=baud)
        self.live = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="disconnected")

        self._build_toolbar()
        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True, pady=(10, 0))

        ttk.Label(self, textvariable=self.status, foreground="#666").pack(
            anchor="w", pady=(8, 0))

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._drain)

    # -- chrome ------------------------------------------------------------
    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Label(bar, text="Port").pack(side="left")
        ttk.Entry(bar, textvariable=self.port, width=10).pack(side="left", padx=(4, 10))
        ttk.Label(bar, text="Baud").pack(side="left")
        ttk.Combobox(bar, textvariable=self.baud, width=9, state="readonly",
                     values=[1000000, 500000, 250000, 115200, 57600]).pack(
                         side="left", padx=(4, 12))
        self.connect_btn = ttk.Button(bar, text="Connect", command=self._toggle_connect)
        self.connect_btn.pack(side="left")
        ttk.Button(bar, text="Scan", command=self._scan).pack(side="left", padx=6)
        ttk.Checkbutton(bar, text="Live", variable=self.live).pack(side="left", padx=12)
        ttk.Button(bar, text="Stop all", width=9,
                   command=self._stop_all).pack(side="right")
        ttk.Button(bar, text="Release all", width=12,
                   command=self._release_all).pack(side="right", padx=6)

    # -- actions -----------------------------------------------------------
    def _toggle_connect(self) -> None:
        if self.bridge.connected:
            self.bridge.watch_ids = []
            self.bridge.disconnect()
        else:
            self.status.set(f"opening {self.port.get()} ...")
            self.bridge.connect(self.port.get(), self.baud.get())

    def _scan(self) -> None:
        if not self.bridge.connected:
            messagebox.showinfo("Not connected", "Connect to the port first.")
            return
        self.status.set("scanning IDs 0-20 ...")

        def job(bus):
            found = []
            for sid in range(0, 21):
                if bus.ping(sid):
                    found.append((sid, bus.read_position(sid)))
            self.bridge._emit("scanned", found)

        self.bridge.submit(job)

    def _build_panels(self, found) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        self.panels.clear()
        if not found:
            ttk.Label(self.body, text="No servos found. Check power, wiring and baud.",
                      foreground="#a00").pack(anchor="w")
            return
        for sid, counts in found:
            p = ServoPanel(self.body, self, sid, counts)
            p.pack(fill="x", pady=6)
            self.panels[sid] = p
        self.bridge.watch_ids = [sid for sid, _ in found]
        # torque defaults to on in the panel; make the servo agree
        for sid in self.panels:
            self.bridge.submit(lambda bus, s=sid: bus.set_torque(s, True))

    def _release_all(self) -> None:
        for sid, panel in self.panels.items():
            panel.torque.set(False)
            self.bridge.submit(lambda bus, s=sid: bus.set_torque(s, False))
        self.status.set("torque released on all servos")

    def _stop_all(self) -> None:
        for sid, panel in self.panels.items():
            if panel.mode.get() == "wheel":
                panel.vel.set(0)
                self.bridge.submit(lambda bus, s=sid: bus.set_velocity(s, 0))
            else:
                panel._hold()
        self.status.set("stopped")

    # -- event pump --------------------------------------------------------
    def _drain(self) -> None:
        try:
            while True:
                kind, payload = self.bridge.outq.get_nowait()
                if kind == "connected":
                    self.status.set(f"connected to {payload}")
                    self.connect_btn.configure(text="Disconnect")
                    self._scan()
                elif kind == "disconnected":
                    self.status.set("disconnected")
                    self.connect_btn.configure(text="Connect")
                elif kind == "scanned":
                    self._build_panels(payload)
                    self.status.set(f"{len(payload)} servo(s) found")
                elif kind == "state":
                    p = self.panels.get(payload.id)
                    if p:
                        p.update_state(payload)
                elif kind == "snap":
                    sid, counts = payload
                    p = self.panels.get(sid)
                    if p:
                        p.snap_to(counts)
                elif kind == "error":
                    self.status.set(f"! {payload}")
        except queue.Empty:
            pass
        self.after(50, self._drain)

    def _on_close(self) -> None:
        try:
            self.bridge.watch_ids = []
            for sid in self.panels:
                self.bridge.submit(lambda bus, s=sid: bus.set_torque(s, False))
            time.sleep(0.15)
            self.bridge.disconnect()
        finally:
            self.root.destroy()


def main() -> None:
    ap = argparse.ArgumentParser(description="Slider UI for Feetech STS servos")
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--baud", type=int, default=1_000_000)
    args = ap.parse_args()

    root = tk.Tk()
    root.title("Feetech STS control panel")
    root.minsize(660, 420)
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root, args.port, args.baud)
    root.mainloop()


if __name__ == "__main__":
    main()
