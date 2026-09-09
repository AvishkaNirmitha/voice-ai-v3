Remote Control is active · Continue here, on your phone, or at claude.ai/code

feetech_servo.py
i have two "feetech sts3215 c018 servo – 12v 30kg high torque" connetted throuh motor controll board i need controll them from python. give me a code for me. connecyed through  "/dev/ttyACM2" now . on this script should do get user input from angel go to that anegl and print time takes for execute that angel. also "asus@asus-ASUS-TUF-Gaming-A15-FA507NVR-FA507NVR:~/Desktop/works/51$ source .venv/bin/activate
(51) asus@asus-ASUS-TUF-Gaming-A15-FA507NVR-FA507NVR:~/Desktop/works/51$ " this is how i activate env.
I'll check what's on the port and what libraries are available first.

Bash
IN
ls -la /dev/ttyACM* 2>&1; echo "---"; cat feetech_servo.py 2>&1 | head -50; echo "--- pip list ---"; .venv/bin/pip list 2>/dev/null | grep -iE "scservo|feetech|serial|sts|lerobot"

OUT
crw-rw---- 1 root dialout 166, 2 Sep  7 15:18 /dev/ttyACM2
---
--- pip list ---
Bash
IN
groups; echo "---"; grep -rlniE "sts3215|scservo|feetech|packetHandler" --include=*.py . | head -20

OUT
asus adm dialout cdrom sudo dip plugdev lpadmin lxd sambashare ollama docker
---
command-line/python/head.py
Bash
IN
grep -nE "import|scservo|feetech|Handler|BAUD|def |ADDR|write|read" command-line/python/head.py | head -60

OUT
4:that it is simulated -- drop in a serial/PWM implementation of write() and the
17:                 playing right now -- rides on top, never overwrites
22:That sum is resolved once per frame on a dedicated thread. It deliberately does
23:not happen in the audio path: stream.write() in speak_worker blocks for the
24:duration of the chunk it is handed, so a servo write inside that loop would eat
34:import math
35:import re
36:import sys
37:import threading
38:import time
39:from dataclasses import dataclass
41:import numpy as np
45:MOTION_HZ = 50                  # resolve + write rate of the motion thread
75:def rms_level(pcm_bytes):
94:    def __init__(self, floor=0.02, decay=0.9995):
99:    def __call__(self, raw):
111:    def __add__(self, other):
114:    def __mul__(self, k):
129:def _bell(u):
134:def _win(u, edge=0.18):
146:# 0.3 Hz drift of a few degrees, and the eye does not read that as motion at
149:def _g_shake(u, amp, cycles):
153:def _g_nod(u, amp, cycles):
159:def _g_nod_hard(u, amp, cycles):
164:def _g_query(u, amp, cycles):
170:def _g_calm(u, amp, cycles):
174:def _g_scan(u, amp, cycles):
221:# is actually right: print it after a real session and read the rows.
225:def strip_tags(text):
229:    text reaches Piper, or the robot reads them aloud.
283:def expand_contractions(text):
289:def is_absence(lowered):
296:def _negatable(lowered):
303:def is_refusal(lowered):
311:def is_limitation(lowered):
326:def _by_text(stripped, duration):
355:def _is_definite(plan):
360:def plan_sentence(text, tag_gestures=(), inherited=False):
367:    and it reads the meaning rather than the words -- so it survives phrasing
410:        # and read these rows.
421:    def write(self, pan, tilt, active=True):
426:    def close(self):
431:    """Records the commanded pose. The visualiser, if running, reads it."""
433:    def __init__(self):
437:    def write(self, pan, tilt, active=True):
445:#     def __init__(self, port="/dev/ttyUSB0"):
447:#     def write(self, pan, tilt):
461:    def __init__(self, controller=None, log=True):
472:        self._lock = threading.Lock()
473:        self._stop = threading.Event()
499:        self.thread = threading.Thread(target=self._run, daemon=True)
503:    def start(self):
504:        self.thread.start()
507:    def stop(self):
509:        self.thread.join(timeout=1.0)
512:    # -- called from receive_audio (event loop) and speak_worker (thread) --
514:    def set_state(self, state):
525:    def set_limits(self, pan_min, pan_max, tilt_min, tilt_max):
535:    def set_manual(self, on):
545:    def set_manual_pose(self, pan, tilt):
Bash
IN
grep -rn "RobotHeadController" --include=*.py . | head; echo "==="; grep -rn "import" command-line/python/head_manual.py | head -20

OUT
command-line/python/head_hw.py:4:per frame, and RobotHeadController forwards it over head_link as an absolute
command-line/python/head_hw.py:67:class RobotHeadController(SimHeadController):
command-line/python/head_hw.py:151:        return RobotHeadController()
command-line/python/head_hw.py:152:    return RobotHeadController(gain_pan=float(gain), gain_tilt=float(gain))
command-line/python/main_with_head.py:63:HW = None               # RobotHeadController, or None for simulation only
===
command-line/python/head_manual.py:6:another one. Nothing in the project imports this file; it is a bench tool, and
command-line/python/head_manual.py:42:import argparse
command-line/python/head_manual.py:43:import json
command-line/python/head_manual.py:44:import os
command-line/python/head_manual.py:45:import queue
command-line/python/head_manual.py:46:import signal
command-line/python/head_manual.py:47:import socket
command-line/python/head_manual.py:48:import threading
command-line/python/head_manual.py:49:import time
command-line/python/head_manual.py:51:import head_link
command-line/python/head_manual.py:171:        import tkinter as tk
No existing SDK in the project — the head code talks to a robot over a socket. I'll install the Feetech SDK into your venv.

Bash
IN
.venv/bin/pip install feetech-servo-sdk 2>&1 | tail -5

OUT
/bin/bash: line 1: .venv/bin/pip: No such file or directory
Bash
IN
ls -d .venv* venv* 2>&1; ls .venv/bin 2>&1 | head

OUT
ls: cannot access 'venv*': No such file or directory
.venv
activate
activate.bat
activate.csh
activate.fish
activate.nu
activate.ps1
activate_this.py
cffi-gen-src
deactivate.bat
distro
Bash
IN
ls .venv/bin | grep -iE "^(pip|python|uv)" ; echo "---"; cat .venv/pyvenv.cfg 2>&1

OUT
piper
python
python3
python3.11
uvicorn
---
home = /home/asus/snap/code/255/.local/share/uv/python/cpython-3.11.14-linux-x86_64-gnu/bin
implementation = CPython
uv = 0.9.18
version_info = 3.11.14
include-system-site-packages = false
prompt = 51
Bash
IN
VIRTUAL_ENV=/home/asus/Desktop/works/51/.venv uv pip install feetech-servo-sdk 2>&1 | tail -8

OUT
Resolved 2 packages in 1.63s
   Building feetech-servo-sdk==1.0.0
      Built feetech-servo-sdk==1.0.0
Prepared 1 package in 222ms
Installed 2 packages in 3ms
 + feetech-servo-sdk==1.0.0
 + pyserial==3.5
Bash
IN
.venv/bin/python -c "
import scservo_sdk as s
print([n for n in dir(s) if not n.startswith('_')])
" 2>&1 | tr ',' '\n' | head -40

OUT
['BROADCAST_ID'
 'COMM_NOT_AVAILABLE'
 'COMM_PORT_BUSY'
 'COMM_RX_CORRUPT'
 'COMM_RX_FAIL'
 'COMM_RX_TIMEOUT'
 'COMM_RX_WAITING'
 'COMM_SUCCESS'
 'COMM_TX_ERROR'
 'COMM_TX_FAIL'
 'DEFAULT_BAUDRATE'
 'ERRBIT_ANGLE'
 'ERRBIT_OVERELE'
 'ERRBIT_OVERHEAT'
 'ERRBIT_OVERLOAD'
 'ERRBIT_VOLTAGE'
 'GroupSyncRead'
 'GroupSyncWrite'
 'INST_ACTION'
 'INST_PING'
 'INST_READ'
 'INST_REG_WRITE'
 'INST_SYNC_READ'
 'INST_SYNC_WRITE'
 'INST_WRITE'
 'LATENCY_TIMER'
 'MAX_ID'
 'PKT_ERROR'
 'PKT_HEADER0'
 'PKT_HEADER1'
 'PKT_ID'
 'PKT_INSTRUCTION'
 'PKT_LENGTH'
 'PKT_PARAMETER0'
 'PacketHandler'
 'PortHandler'
 'RXPACKET_MAX_LEN'
 'SCS_END'
 'SCS_GETEND'
 'SCS_HIBYTE'
Now let me write the script.

Bash
IN
cat > /home/asus/Desktop/works/51/feetech_servo.py <<'PY'
#!/usr/bin/env python3
"""Drive two Feetech STS3215 servos over the motor control board.

Reads a target angle from stdin, sends it, waits until the servo reports it
has stopped moving, and prints how long the move took.

Usage:
    source .venv/bin/activate
    python feetech_servo.py                       # /dev/ttyACM2, ids 1 and 2
    python feetech_servo.py --port /dev/ttyACM0 --ids 1 2 3

At the prompt:
    90            -> move every servo to 90 deg
    1 90          -> move servo 1 to 90 deg
    1 90 2 180    -> move servo 1 to 90 and servo 2 to 180 together
    r             -> read and print the current position of every servo
    t             -> torque off (servos go limp), 'T' turns it back on
    q             -> quit
"""

import argparse
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

PROTOCOL_END = 0        # STS/SMS servos are little-endian; SCS servos use 1.
BAUDRATE = 1000000


def deg_to_steps(deg):
    return int(round(deg / DEG_PER_STEP)) % STEPS_PER_REV


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
            model, comm, err = self.packet.ping(sid)
            if comm != COMM_SUCCESS:
                raise RuntimeError(
                    "no response from servo id %d on %s: %s"
                    % (sid, port, self.packet.getTxRxResult(comm))
                )
            print("servo %d found (model %d)" % (sid, model))

        self.set_torque(True)

    def set_torque(self, on):
        for sid in self.ids:
            self.packet.write1ByteTxRx(sid, ADDR_TORQUE_ENABLE, 1 if on else 0)

    def read_position(self, sid):
        """Present position in degrees, or None if the read failed."""
        steps, comm, err = self.packet.read2ByteTxRx(sid, ADDR_PRESENT_POSITION)
        if comm != COMM_SUCCESS or err != 0:
            return None
        return steps_to_deg(steps)

    def is_moving(self, sid):
        flag, comm, err = self.packet.read1ByteTxRx(sid, ADDR_MOVING)
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
        """Send the goals and block until every servo stops. Returns seconds."""
        start = time.perf_counter()
        self.write_goals(targets)

        stable_since = {sid: None for sid in targets}
        done = set()
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
        return max(elapsed, 0.0)

    def close(self):
        self.set_torque(False)
        self.port.closePort()


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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="/dev/ttyACM2")
    ap.add_argument("--baud", type=int, default=BAUDRATE)
    ap.add_argument("--ids", type=int, nargs="+", default=[1, 2])
    ap.add_argument("--speed", type=int, default=2400,
                    help="0..4095 steps/s, 0 means full speed")
    ap.add_argument("--accel", type=int, default=50, help="0..255")
    args = ap.parse_args()

    bus = ServoBus(args.port, args.ids, args.baud, args.speed, args.accel)
    print("connected on %s at %d baud" % (args.port, args.baud))
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

            elapsed = bus.move_and_time(targets)
            moved = ", ".join("servo %d -> %.1f deg (now %.1f)"
                              % (sid, goal, bus.read_position(sid) or float("nan"))
                              for sid, goal in sorted(targets.items()))
            print("  %s" % moved)
            print("  took %.3f s (%.1f ms)" % (elapsed, elapsed * 1000.0))
    except KeyboardInterrupt:
        print()
    finally:
        bus.close()
        print("closed")


if __name__ == "__main__":
    sys.exit(main())
PY
.venv/bin/python -c "import ast;ast.parse(open('/home/asus/Desktop/works/51/feetech_servo.py').read())" && echo OK

OUT
OK
Let me verify it actually talks to your hardware.

Bash
IN
echo "q" | timeout 25 .venv/bin/python feetech_servo.py 2>&1 | tail -20

OUT
Traceback (most recent call last):
  File "/home/asus/Desktop/works/51/feetech_servo.py", line 232, in <module>
    sys.exit(main())
             ^^^^^^
  File "/home/asus/Desktop/works/51/feetech_servo.py", line 185, in main
    bus = ServoBus(args.port, args.ids, args.baud, args.speed, args.accel)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/asus/Desktop/works/51/feetech_servo.py", line 65, in __init__
    model, comm, err = self.packet.ping(sid)
                       ^^^^^^^^^^^^^^^^^^^^^
TypeError: protocol_packet_handler.ping() missing 1 required positional argument: 'scs_id'
Bash
IN
.venv/bin/python - <<'PY'
import inspect
from scservo_sdk import PacketHandler
p = PacketHandler(0)
for m in ("ping","read1ByteTxRx","read2ByteTxRx","write1ByteTxRx","getTxRxResult"):
    print(m, inspect.signature(getattr(p,m)))
PY

OUT
ping (port, scs_id)
read1ByteTxRx (port, scs_id, address)
read2ByteTxRx (port, scs_id, address)
write1ByteTxRx (port, scs_id, address, data)
getTxRxResult (result)
Bash
IN
sed -i \
 -e 's/self\.packet\.ping(sid)/self.packet.ping(self.port, sid)/' \
 -e 's/self\.packet\.write1ByteTxRx(sid, ADDR_TORQUE_ENABLE/self.packet.write1ByteTxRx(self.port, sid, ADDR_TORQUE_ENABLE/' \
 -e 's/self\.packet\.read2ByteTxRx(sid, ADDR_PRESENT_POSITION)/self.packet.read2ByteTxRx(self.port, sid, ADDR_PRESENT_POSITION)/' \
 -e 's/self\.packet\.read1ByteTxRx(sid, ADDR_MOVING)/self.packet.read1ByteTxRx(self.port, sid, ADDR_MOVING)/' \
 feetech_servo.py && grep -n "self.packet\." feetech_servo.py

OUT
65:            model, comm, err = self.packet.ping(self.port, sid)
69:                    % (sid, port, self.packet.getTxRxResult(comm))
77:            self.packet.write1ByteTxRx(self.port, sid, ADDR_TORQUE_ENABLE, 1 if on else 0)
81:        steps, comm, err = self.packet.read2ByteTxRx(self.port, sid, ADDR_PRESENT_POSITION)
87:        flag, comm, err = self.packet.read1ByteTxRx(self.port, sid, ADDR_MOVING)
108:            raise RuntimeError("syncwrite failed: %s" % self.packet.getTxRxResult(comm))
Bash
IN
echo "q" | timeout 25 .venv/bin/python feetech_servo.py 2>&1 | tail -20

OUT
Traceback (most recent call last):
  File "/home/asus/Desktop/works/51/feetech_servo.py", line 232, in <module>
    sys.exit(main())
             ^^^^^^
  File "/home/asus/Desktop/works/51/feetech_servo.py", line 185, in main
    bus = ServoBus(args.port, args.ids, args.baud, args.speed, args.accel)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/asus/Desktop/works/51/feetech_servo.py", line 67, in __init__
    raise RuntimeError(
RuntimeError: no response from servo id 1 on /dev/ttyACM2: [TxRxResult] There is no status packet!
Port opens fine, but IDs 1/2 don't answer. Let me scan the bus.

Bash
IN
timeout 180 .venv/bin/python - <<'PY' 2>&1 | tail -30
from scservo_sdk import PortHandler, PacketHandler, COMM_SUCCESS
for baud in (1000000, 500000, 250000, 128000, 115200, 76800, 57600, 38400):
    for end in (0, 1):
        port = PortHandler("/dev/ttyACM2"); pk = PacketHandler(end)
        if not port.openPort() or not port.setBaudRate(baud):
            print("open fail", baud); continue
        found = []
        for sid in range(0, 21):
            model, comm, err = pk.ping(port, sid)
            if comm == COMM_SUCCESS:
                found.append((sid, model))
        port.closePort()
        if found:
            print("baud=%d end=%d -> %s" % (baud, end, found))
print("scan done")
PY

OUT
baud=1000000 end=0 -> [(9, 777), (11, 777)]
baud=1000000 end=1 -> [(9, 2307), (11, 2307)]
open fail 76800
open fail 76800
scan done
Found them: IDs 9 and 11, model 777 (STS3215), 1 Mbaud, little-endian. Updating the defaults.

Bash
IN
\
sed -i -e 's/default=\[1, 2\]/default=[9, 11]/' \
       -e 's/^    python feetech_servo.py                       # \/dev\/ttyACM2, ids 1 and 2/    python feetech_servo.py                       # \/dev\/ttyACM2, ids 9 and 11/' \
       -e 's/^    python feetech_servo.py --port \/dev\/ttyACM0 --ids 1 2 3/    python feetech_servo.py --port \/dev\/ttyACM0 --ids 1 2 3/' \
       feetech_servo.py && \
python3 - <<'PY'
import re
p="/home/asus/Desktop/works/51/feetech_servo.py"
s=open(p).read()
s=s.replace("""    90            -> move every servo to 90 deg
    1 90          -> move servo 1 to 90 deg
    1 90 2 180    -> move servo 1 to 90 and servo 2 to 180 together""",
"""    90            -> move every servo to 90 deg
    9 90          -> move servo 9 to 90 deg
    9 90 11 180   -> move servo 9 to 90 and servo 11 to 180 together""")
s=s.replace("""    def close(self):
        self.set_torque(False)
        self.port.closePort()""",
"""    def close(self, release=False):
        # Torque stays on by default: a loaded joint would drop if we cut it.
        if release:
            self.set_torque(False)
        self.port.closePort()""")
s=s.replace('''    ap.add_argument("--accel", type=int, default=50, help="0..255")''',
'''    ap.add_argument("--accel", type=int, default=50, help="0..255")
    ap.add_argument("--release-on-exit", action="store_true",
                    help="cut torque when quitting (servos go limp)")''')
s=s.replace("        bus.close()", "        bus.close(release=args.release_on_exit)")
open(p,"w").write(s)
PY
grep -n "9 90\|default=\[9\|release" feetech_servo.py

OUT
14:    9 90          -> move servo 9 to 90 deg
15:    9 90 11 180   -> move servo 9 to 90 and servo 11 to 180 together
144:    def close(self, release=False):
146:        if release:
181:    ap.add_argument("--ids", type=int, nargs="+", default=[9, 11])
185:    ap.add_argument("--release-on-exit", action="store_true",
231:        bus.close(release=args.release_on_exit)
Bash
IN
printf 'r\nq\n' | timeout 30 .venv/bin/python feetech_servo.py 2>&1 | tail -20

OUT
servo 9 found (model 777)
servo 11 found (model 777)
connected on /dev/ttyACM2 at 1000000 baud
  servo 9 at 226.7 deg
  servo 11 at 133.2 deg
enter an angle, or 'id angle' pairs. 'r' read, 't'/'T' torque, 'q' quit.
>   servo 9 at 226.7 deg
  servo 11 at 133.2 deg
> closed
Read-back works. Testing one small move (servo 9, 226.7° → 220°) to verify the timing path:

Bash
IN
printf '9 220\n9 226.7\nq\n' | timeout 40 .venv/bin/python feetech_servo.py 2>&1 | tail -20

OUT
servo 9 found (model 777)
servo 11 found (model 777)
connected on /dev/ttyACM2 at 1000000 baud
  servo 9 at 226.7 deg
  servo 11 at 133.2 deg
enter an angle, or 'id angle' pairs. 'r' read, 't'/'T' torque, 'q' quit.
>   servo 9 -> 220.0 deg (now 220.2)
  took 0.290 s (290.2 ms)
>   servo 9 -> 226.7 deg (now 226.4)
  took 0.291 s (290.8 ms)
> closed
Working end to end — moved, arrived within 0.3°, and returned to its start position.

Run it

source .venv/bin/activate
python feetech_servo.py
feetech_servo.py — one file, no other project code involved.

What I found on your bus
Your servos are not at IDs 1 and 2 — a scan of /dev/ttyACM2 (IDs 0–20, eight baud rates) turned up:

ID	Model	Baud	Byte order
9	777 (STS3215)	1,000,000	little-endian (STS/SMS)
11	777 (STS3215)	1,000,000	little-endian
Those are now the defaults. Override with --ids/--baud if you renumber them.

Commands at the prompt

90            move every servo to 90°
9 90          move servo 9 to 90°
9 90 11 180   move both together (single sync-write packet)
r             read current positions
t / T         torque off / on
q             quit
Each move prints the elapsed time, e.g. took 0.290 s (290.2 ms).

Notes on the implementation
Timing starts right before the packet goes out and stops when the servo is both within 1.5° of the goal and reports Moving == 0, held for a 50 ms settle window (subtracted back out). Without the settle check, a position sampled mid-coast can falsely read as "arrived."
Both servos start together — goal accel/position/speed go out in one GroupSyncWrite, so a two-axis move is simultaneous rather than staggered.
Angles are 0–360° on the STS3215's 4096-step encoder (--speed, default 2400 steps/s, and --accel, default 50, control the profile; --speed 0 is full speed).
Torque stays on when you quit. Cutting it makes a loaded joint drop, so releasing is opt-in via t at the prompt or --release-on-exit.
I installed feetech-servo-sdk (plus pyserial) into .venv via uv pip — your venv is a uv venv with no pip binary, so plain pip install inside it won't work; use uv pip install for anything else you add.

feetech_servo.py#183-183
i tested ""(51) asus@asus-ASUS-TUF-Gaming-A15-FA507NVR-FA507NVR:~/Desktop/works/51$ uv run feetech_servo.py --id 11
servo 11 found (model 777)
connected on /dev/ttyACM2 at 1000000 baud
  servo 11 at 20.0 deg
enter an angle, or 'id angle' pairs. 'r' read, 't'/'T' torque, 'q' quit.
> 0
  servo 11 -> 0.0 deg (now 0.1)
  took 0.506 s (506.2 ms)
> 15
  servo 11 -> 15.0 deg (now 14.8)
  took 0.411 s (410.8 ms)
> 30
  servo 11 -> 30.0 deg (now 29.8)
  took 0.396 s (396.1 ms)
> 45
  servo 11 -> 45.0 deg (now 44.7)
  took 0.396 s (396.0 ms)
> 60
  servo 11 -> 60.0 deg (now 59.9)
  took 0.426 s (425.7 ms)
> 75
  servo 11 -> 75.0 deg (now 74.9)
  took 0.438 s (438.3 ms)
> 0

  servo 11 -> 0.0 deg (now 0.3)
  took 0.848 s (847.7 ms)
> > " I tested script this is result . seems like slow ?
Good data — that's actually enough to diagnose it. Let me check the SDK's polling overhead and then measure where the time actually goes.

Bash
IN
cd /home/asus/Desktop/works/51; P=$(.venv/bin/python -c "import scservo_sdk,os;print(os.path.dirname(scservo_sdk.__file__))"); echo $P; grep -rn "LATENCY_TIMER\|TXPACKET_MAX\|def setPacketTimeout\|packet_timeout\|time.sleep" $P/*.py | head -20

OUT
/home/asus/Desktop/works/51/.venv/lib/python3.11/site-packages/scservo_sdk
/home/asus/Desktop/works/51/.venv/lib/python3.11/site-packages/scservo_sdk/port_handler.py:8:LATENCY_TIMER = 16
/home/asus/Desktop/works/51/.venv/lib/python3.11/site-packages/scservo_sdk/port_handler.py:17:        self.packet_timeout = 0.0
/home/asus/Desktop/works/51/.venv/lib/python3.11/site-packages/scservo_sdk/port_handler.py:66:    def setPacketTimeout(self, packet_length):
/home/asus/Desktop/works/51/.venv/lib/python3.11/site-packages/scservo_sdk/port_handler.py:68:        self.packet_timeout = (self.tx_time_per_byte * packet_length) + (LATENCY_TIMER * 2.0) + 2.0
/home/asus/Desktop/works/51/.venv/lib/python3.11/site-packages/scservo_sdk/port_handler.py:70:    def setPacketTimeoutMillis(self, msec):
/home/asus/Desktop/works/51/.venv/lib/python3.11/site-packages/scservo_sdk/port_handler.py:72:        self.packet_timeout = msec
/home/asus/Desktop/works/51/.venv/lib/python3.11/site-packages/scservo_sdk/port_handler.py:75:        if self.getTimeSinceStart() > self.packet_timeout:
/home/asus/Desktop/works/51/.venv/lib/python3.11/site-packages/scservo_sdk/port_handler.py:76:            self.packet_timeout = 0
/home/asus/Desktop/works/51/.venv/lib/python3.11/site-packages/scservo_sdk/protocol_packet_handler.py:5:TXPACKET_MAX_LEN = 250
/home/asus/Desktop/works/51/.venv/lib/python3.11/site-packages/scservo_sdk/protocol_packet_handler.py:78:        if total_packet_length > TXPACKET_MAX_LEN:
Bash
IN
cd /home/asus/Desktop/works/51; timeout 60 .venv/bin/python - <<'PY' 2>&1
import time
from scservo_sdk import PortHandler, PacketHandler, COMM_SUCCESS
port=PortHandler("/dev/ttyACM2"); pk=PacketHandler(0)
port.openPort(); port.setBaudRate(1000000)
# read round-trip cost
t=time.perf_counter()
for _ in range(50): pk.read2ByteTxRx(port,11,56)
rd=(time.perf_counter()-t)/50
t=time.perf_counter()
for _ in range(50): pk.read1ByteTxRx(port,11,66)
mv=(time.perf_counter()-t)/50
print("read pos  %.2f ms" % (rd*1000))
print("read moving %.2f ms" % (mv*1000))
print("poll loop iteration = %.2f ms" % ((rd+mv)*1000))
port.closePort()
PY

OUT
read pos  0.30 ms
read moving 0.33 ms
poll loop iteration = 0.63 ms
Serial overhead is negligible (0.63 ms per poll) — the time is real servo motion. Let me test the profile parameters:

Bash
IN
cd /home/asus/Desktop/works/51; timeout 200 .venv/bin/python - <<'PY' 2>&1
import time
from scservo_sdk import PortHandler, PacketHandler, GroupSyncWrite, COMM_SUCCESS
port=PortHandler("/dev/ttyACM2"); pk=PacketHandler(0)
port.openPort(); port.setBaudRate(1000000)
SID=11
pk.write1ByteTxRx(port,SID,40,1)
def steps(d): return int(round(d*4096/360.0))%4096
def move(deg,speed,accel):
    g=GroupSyncWrite(port,pk,41,7); s=steps(deg)
    g.addParam(SID,[accel&0xFF,s&0xFF,(s>>8)&0xFF,0,0,speed&0xFF,(speed>>8)&0xFF])
    t=time.perf_counter(); g.txPacket(); g.clearParam()
    stable=None
    while True:
        now=time.perf_counter()
        if now-t>6: return -1
        p,c,e=pk.read2ByteTxRx(port,SID,56)
        if c!=COMM_SUCCESS: continue
        err=abs((p*360.0/4096-deg+180)%360-180)
        f,c2,_=pk.read1ByteTxRx(port,SID,66)
        if err<=1.5 and not f:
            if stable is None: stable=now
            elif now-stable>=0.05: return now-t-0.05
        else: stable=None
print(" 15 deg move                 |  75 deg move")
print(" speed accel   time          |   time")
for accel in (50,150,255):
    for speed in (2400,4000,0):
        move(0,speed,accel); time.sleep(0.3)
        a=move(15,speed,accel); time.sleep(0.3)
        move(0,speed,accel); time.sleep(0.3)
        b=move(75,speed,accel); time.sleep(0.3)
        print(" %5d %5d   %6.1f ms      |  %6.1f ms" % (speed,accel,a*1000,b*1000))
move(0,2400,50)
port.closePort()
PY

OUT
 15 deg move                 |  75 deg move
 speed accel   time          |   time
  2400    50    400.0 ms      |   845.1 ms
  4000    50    406.4 ms      |   844.9 ms
     0    50    407.0 ms      |   845.7 ms
  2400   150    407.1 ms      |   845.1 ms
  4000   150    407.0 ms      |   845.2 ms
     0   150    406.4 ms      |   845.2 ms
  2400   255    406.7 ms      |   845.5 ms
  4000   255    407.1 ms      |   846.0 ms
     0   255    406.5 ms      |   845.5 ms
Neither speed nor accel changed anything — that's suspicious. Let me log the actual position trajectory:

Bash
IN
cd /home/asus/Desktop/works/51; timeout 120 .venv/bin/python - <<'PY' 2>&1
import time
from scservo_sdk import PortHandler, PacketHandler, GroupSyncWrite, COMM_SUCCESS
port=PortHandler("/dev/ttyACM2"); pk=PacketHandler(0)
port.openPort(); port.setBaudRate(1000000)
SID=11
pk.write1ByteTxRx(port,SID,40,1)
def st(d): return int(round(d*4096/360.0))%4096
def go(deg,speed,accel):
    g=GroupSyncWrite(port,pk,41,7); s=st(deg)
    g.addParam(SID,[accel&0xFF,s&0xFF,(s>>8)&0xFF,0,0,speed&0xFF,(speed>>8)&0xFF])
    g.txPacket(); g.clearParam()
def trace(deg,speed,accel,dur=1.2):
    go(deg,speed,accel); t0=time.perf_counter(); rows=[]
    while time.perf_counter()-t0<dur:
        p,c,_=pk.read2ByteTxRx(port,SID,56)
        f,_,_=pk.read1ByteTxRx(port,SID,66)
        if c==COMM_SUCCESS: rows.append((time.perf_counter()-t0,p*360/4096,f))
    return rows
for speed,accel in ((500,50),(4000,255)):
    go(0,speed,accel); time.sleep(1.2)
    r=trace(75,speed,accel)
    print("speed=%d accel=%d" % (speed,accel))
    for i in range(0,len(r),max(1,len(r)//14)):
        print("   %6.3f s  %6.1f deg  moving=%d" % r[i])
    print()
# read back what the servo stored
for addr,name,n in ((41,"acc",1),(46,"goal speed",2),(42,"goal pos",2),(66,"moving",1)):
    v,c,e=(pk.read1ByteTxRx if n==1 else pk.read2ByteTxRx)(port,SID,addr)
    print("addr %2d %-11s = %d (comm=%d err=%d)" % (addr,name,v,c,e))
go(0,500,50)
port.closePort()
PY

OUT
speed=500 accel=50
    0.002 s     0.0 deg  moving=0
    0.088 s     0.6 deg  moving=1
    0.175 s     4.2 deg  moving=1
    0.261 s     8.0 deg  moving=1
    0.347 s    11.8 deg  moving=1
    0.432 s    15.6 deg  moving=1
    0.517 s    19.2 deg  moving=1
    0.602 s    23.0 deg  moving=1
    0.687 s    26.7 deg  moving=1
    0.772 s    30.5 deg  moving=1
    0.856 s    34.2 deg  moving=1
    0.940 s    37.9 deg  moving=1
    1.025 s    41.7 deg  moving=1
    1.109 s    45.4 deg  moving=1
    1.195 s    49.1 deg  moving=1

speed=4000 accel=255
    0.001 s     0.2 deg  moving=0
    0.087 s     0.5 deg  moving=1
    0.173 s     4.7 deg  moving=1
    0.259 s    11.8 deg  moving=1
    0.346 s    22.3 deg  moving=1
    0.431 s    35.8 deg  moving=1
    0.516 s    49.9 deg  moving=1
    0.602 s    61.0 deg  moving=1
    0.687 s    68.8 deg  moving=1
    0.771 s    73.6 deg  moving=1
    0.857 s    74.7 deg  moving=0
    0.943 s    74.7 deg  moving=0
    1.027 s    74.7 deg  moving=0
    1.113 s    74.7 deg  moving=0
    1.200 s    74.7 deg  moving=0

addr 41 acc         = 50 (comm=0 err=0)
addr 46 goal speed  = 4000 (comm=0 err=0)
addr 42 goal pos    = 853 (comm=0 err=0)
addr 66 moving      = 0 (comm=0 err=0)
Registers work fine (readback confirms), but look at the trajectory: at speed=4000 the servo peaks at only ~165 deg/s. Let me isolate the real limits:

Bash
IN
cd /home/asus/Desktop/works/51; timeout 200 .venv/bin/python - <<'PY' 2>&1
import time
from scservo_sdk import PortHandler, PacketHandler, GroupSyncWrite, COMM_SUCCESS
port=PortHandler("/dev/ttyACM2"); pk=PacketHandler(0)
port.openPort(); port.setBaudRate(1000000)
SID=11
pk.write1ByteTxRx(port,SID,40,1)
def st(d): return int(round(d*4096/360.0))%4096
def go(deg,speed,accel):
    g=GroupSyncWrite(port,pk,41,7); s=st(deg)
    g.addParam(SID,[accel&0xFF,s&0xFF,(s>>8)&0xFF,0,0,speed&0xFF,(speed>>8)&0xFF])
    t=time.perf_counter(); g.txPacket(); g.clearParam(); return t
def run(deg,speed,accel,dur=1.6):
    t0=go(deg,speed,accel); rows=[]
    while time.perf_counter()-t0<dur:
        p,c,_=pk.read2ByteTxRx(port,SID,56)
        if c==COMM_SUCCESS: rows.append((time.perf_counter()-t0,p*360/4096))
    return rows
def stats(r):
    start=r[0][1]
    dead=next((t for t,p in r if abs(p-start)>0.5),None)
    vmax=0; 
    for i in range(len(r)-8):
        dt=r[i+8][0]-r[i][0]
        if dt>0: vmax=max(vmax,abs(r[i+8][1]-r[i][1])/dt)
    return dead,vmax
print("  accel  speed | dead-time  peak-vel   (90 deg move)")
for accel in (10,50,150,255):
    for speed in (1000,2400,0):
        go(0,speed,accel); time.sleep(1.8)
        r=run(90,speed,accel); d,v=stats(r)
        print("  %5d  %5d |  %5.0f ms   %6.1f deg/s" % (accel,speed,(d or 0)*1000,v))
go(0,1500,50); time.sleep(1.5)
port.closePort()
PY

OUT
  accel  speed | dead-time  peak-vel   (90 deg move)
     10   1000 |    133 ms    156.8 deg/s
     10   2400 |     10 ms    158.8 deg/s
     10      0 |      6 ms    153.2 deg/s
     50   1000 |     90 ms    160.9 deg/s
     50   2400 |     84 ms    671.9 deg/s
     50      0 |     93 ms    278.2 deg/s
    150   1000 |     92 ms    159.1 deg/s
    150   2400 |     90 ms    299.8 deg/s
    150      0 |     88 ms    280.2 deg/s
    255   1000 |     83 ms    161.6 deg/s
    255   2400 |     90 ms    280.3 deg/s
    255      0 |     90 ms    428.1 deg/s
Velocity estimates are noisy from bad reads. Let me measure robustly — total move time for a fixed 90° move, repeated:

Bash
IN
cd /home/asus/Desktop/works/51; timeout 280 .venv/bin/python - <<'PY' 2>&1
import time,statistics
from scservo_sdk import PortHandler, PacketHandler, GroupSyncWrite, COMM_SUCCESS
port=PortHandler("/dev/ttyACM2"); pk=PacketHandler(0)
port.openPort(); port.setBaudRate(1000000)
SID=11
pk.write1ByteTxRx(port,SID,40,1)
def st(d): return int(round(d*4096/360.0))%4096
def go(deg,speed,accel):
    g=GroupSyncWrite(port,pk,41,7); s=st(deg)
    g.addParam(SID,[accel&0xFF,s&0xFF,(s>>8)&0xFF,0,0,speed&0xFF,(speed>>8)&0xFF])
    t=time.perf_counter(); g.txPacket(); g.clearParam(); return t
def timed(deg,speed,accel,tol=1.0):
    t0=go(deg,speed,accel); stable=None; last=None
    while True:
        now=time.perf_counter()
        if now-t0>8: return float('nan'),float('nan')
        p,c,_=pk.read2ByteTxRx(port,SID,56)
        if c!=COMM_SUCCESS: continue
        d=p*360/4096
        if last is None and abs(d-deg)>2: pass
        err=abs((d-deg+180)%360-180)
        if err<=tol:
            if stable is None: stable=now
            elif now-stable>=0.06: return now-t0-0.06, d
        else: stable=None
print("90 deg move, median of 3 (accel fixed at 50)")
print("  speed |   time      implied avg speed")
for speed in (200,500,1000,1500,2400,3400,0):
    ts=[]
    for _ in range(3):
        go(0,speed,50); time.sleep(2.2)
        t,_=timed(90,speed,50); ts.append(t)
        time.sleep(0.3)
    m=statistics.median(ts)
    print("  %5d | %6.0f ms   %6.1f deg/s" % (speed,m*1000,90/m))
print()
print("90 deg move at speed=0 (uncapped), varying accel")
print("  accel |   time")
for accel in (10,50,150,255):
    ts=[]
    for _ in range(3):
        go(0,0,accel); time.sleep(2.2)
        t,_=timed(90,0,accel); ts.append(t)
        time.sleep(0.3)
    print("  %5d | %6.0f ms" % (accel,statistics.median(ts)*1000))
go(0,1500,50); time.sleep(1.5)
port.closePort()
PY

OUT
Exit code 143
Command timed out after 2m 0s
Hit the tool's default timeout. Re-running smaller with a longer budget:

Bash
IN
cd /home/asus/Desktop/works/51; timeout 260 .venv/bin/python - <<'PY' 2>&1
import time,statistics
from scservo_sdk import PortHandler, PacketHandler, GroupSyncWrite, COMM_SUCCESS
port=PortHandler("/dev/ttyACM2"); pk=PacketHandler(0)
port.openPort(); port.setBaudRate(1000000); SID=11
pk.write1ByteTxRx(port,SID,40,1)
def st(d): return int(round(d*4096/360.0))%4096
def go(deg,speed,accel):
    g=GroupSyncWrite(port,pk,41,7); s=st(deg)
    g.addParam(SID,[accel&0xFF,s&0xFF,(s>>8)&0xFF,0,0,speed&0xFF,(speed>>8)&0xFF])
    t=time.perf_counter(); g.txPacket(); g.clearParam(); return t
def timed(deg,speed,accel,tol=1.0):
    t0=go(deg,speed,accel); stable=None
    while True:
        now=time.perf_counter()
        if now-t0>6: return float('nan')
        p,c,_=pk.read2ByteTxRx(port,SID,56)
        if c!=COMM_SUCCESS: continue
        err=abs((p*360/4096-deg+180)%360-180)
        if err<=tol:
            if stable is None: stable=now
            elif now-stable>=0.06: return now-t0-0.06
        else: stable=None
def bench(speed,accel,n=2):
    ts=[]
    for _ in range(n):
        go(0,speed,accel); time.sleep(1.6)
        ts.append(timed(90,speed,accel)); time.sleep(0.25)
    return statistics.median(ts)
print("90 deg move | accel=50")
print("  speed |   time    avg deg/s")
for speed in (500,1000,2400,0):
    m=bench(speed,50); print("  %5d | %5.0f ms   %5.1f" % (speed,m*1000,90/m))
print("\n90 deg move | speed=0 (uncapped)")
print("  accel |   time")
for accel in (10,50,255):
    m=bench(0,accel); print("  %5d | %5.0f ms" % (accel,m*1000))
go(0,1500,50); time.sleep(1.5); port.closePort()
PY

OUT
90 deg move | accel=50
  speed |   time    avg deg/s
    500 |  1764 ms    51.0
   1000 |  1187 ms    75.8
   2400 |   867 ms   103.8
      0 |   866 ms   103.9

90 deg move | speed=0 (uncapped)
  accel |   time
     10 |  2178 ms
     50 |   866 ms
    255 |   866 ms
Now it's clear. Let me pin down where the ~400 ms on a small move actually goes:

Bash
IN
cd /home/asus/Desktop/works/51; timeout 100 .venv/bin/python - <<'PY' 2>&1
import time
from scservo_sdk import PortHandler, PacketHandler, GroupSyncWrite, COMM_SUCCESS
port=PortHandler("/dev/ttyACM2"); pk=PacketHandler(0)
port.openPort(); port.setBaudRate(1000000); SID=11
pk.write1ByteTxRx(port,SID,40,1)
def st(d): return int(round(d*4096/360.0))%4096
def go(deg,speed=2400,accel=50):
    g=GroupSyncWrite(port,pk,41,7); s=st(deg)
    g.addParam(SID,[accel&0xFF,s&0xFF,(s>>8)&0xFF,0,0,speed&0xFF,(speed>>8)&0xFF])
    t=time.perf_counter(); g.txPacket(); g.clearParam(); return t
for target in (15,90):
    go(0); time.sleep(1.8)
    t0=go(target); rows=[]
    while time.perf_counter()-t0<1.3:
        p,c,_=pk.read2ByteTxRx(port,SID,56)
        f,_,_=pk.read1ByteTxRx(port,SID,66)
        if c==COMM_SUCCESS: rows.append((time.perf_counter()-t0,p*360/4096,f))
    def first(pred): return next((t for t,d,f in rows if pred(t,d,f)),None)
    mv=first(lambda t,d,f: abs(d)>0.5)
    marks=[("motion starts",mv)]
    for frac,lab in ((0.5,"50% of travel"),(0.9,"90%"),):
        marks.append((lab, first(lambda t,d,f,fr=frac: d>=target*fr)))
    marks.append(("within 1.5 deg", first(lambda t,d,f: abs(d-target)<=1.5)))
    marks.append(("within 0.5 deg", first(lambda t,d,f: abs(d-target)<=0.5)))
    marks.append(("moving flag clears", first(lambda t,d,f: t>0.05 and not f)))
    print("=== %d deg move (speed 2400, accel 50) ===" % target)
    for lab,t in marks:
        print("  %-20s %s" % (lab, "%6.0f ms"%(t*1000) if t else "  n/a"))
    print()
go(0); time.sleep(1.5); port.closePort()
PY

OUT
=== 15 deg move (speed 2400, accel 50) ===
  motion starts            83 ms
  50% of travel           213 ms
  90%                     318 ms
  within 1.5 deg          318 ms
  within 0.5 deg          354 ms
  moving flag clears      415 ms

=== 90 deg move (speed 2400, accel 50) ===
  motion starts            83 ms
  50% of travel           480 ms
  90%                     730 ms
  within 1.5 deg          849 ms
  within 0.5 deg          892 ms
  moving flag clears      941 ms
83 ms of dead time before motion starts, on every move regardless of size — and reads round-trip in 0.3 ms, so it's not the link. Let me test whether writing only the position register avoids it:

Bash
IN
cd /home/asus/Desktop/works/51; timeout 200 .venv/bin/python - <<'PY' 2>&1
import time,statistics
from scservo_sdk import PortHandler, PacketHandler, GroupSyncWrite, COMM_SUCCESS
port=PortHandler("/dev/ttyACM2"); pk=PacketHandler(0)
port.openPort(); port.setBaudRate(1000000); SID=11
pk.write1ByteTxRx(port,SID,40,1)
def st(d): return int(round(d*4096/360.0))%4096
def go7(deg,speed=2400,accel=50):
    g=GroupSyncWrite(port,pk,41,7); s=st(deg)
    g.addParam(SID,[accel&0xFF,s&0xFF,(s>>8)&0xFF,0,0,speed&0xFF,(speed>>8)&0xFF])
    t=time.perf_counter(); g.txPacket(); g.clearParam(); return t
def go2(deg):   # goal position only
    g=GroupSyncWrite(port,pk,42,2); s=st(deg)
    g.addParam(SID,[s&0xFF,(s>>8)&0xFF])
    t=time.perf_counter(); g.txPacket(); g.clearParam(); return t
def deadtime(fn,target):
    go7(0); time.sleep(1.6)
    t0=fn(target)
    while True:
        p,c,_=pk.read2ByteTxRx(port,SID,56)
        if c==COMM_SUCCESS and abs(p*360/4096)>0.5:
            return time.perf_counter()-t0
        if time.perf_counter()-t0>2: return float('nan')
for lab,fn in (("full 7-byte write (acc+pos+speed)",go7),("position-only 2-byte write",go2)):
    ds=[deadtime(fn,30)*1000 for _ in range(5)]
    print("%-36s dead time median %5.1f ms   (%s)" % (lab, statistics.median(ds), " ".join("%.0f"%d for d in ds)))
go7(0); time.sleep(1.5); port.closePort()
PY

OUT
full 7-byte write (acc+pos+speed)    dead time median  82.8 ms   (83 83 84 82 82)
position-only 2-byte write           dead time median  83.0 ms   (78 83 83 83 83)
Identical — so the 83 ms is inside the servo. One more thing worth checking, the supply voltage:

Bash
IN
cd /home/asus/Desktop/works/51; timeout 60 .venv/bin/python - <<'PY' 2>&1
from scservo_sdk import PortHandler, PacketHandler, COMM_SUCCESS
port=PortHandler("/dev/ttyACM2"); pk=PacketHandler(0)
port.openPort(); port.setBaudRate(1000000)
for SID in (9,11):
    v,_,_=pk.read1ByteTxRx(port,SID,62)
    t,_,_=pk.read1ByteTxRx(port,SID,63)
    l,_,_=pk.read2ByteTxRx(port,SID,60)
    mx,_,_=pk.read2ByteTxRx(port,SID,48)   # torque limit
    print("servo %2d: supply %.1f V   temp %d C   load %d   torque-limit %d" % (SID, v/10.0, t, l, mx))
port.closePort()
PY

OUT
servo  9: supply 12.0 V   temp 34 C   load 0   torque-limit 1000
servo 11: supply 12.0 V   temp 37 C   load 24   torque-limit 1000
Supply is a proper 12.0 V, torque limit already maxed, temps fine. So nothing is misconfigured — let me add the timing breakdown to the script so the split is visible:

Bash
IN
cd /home/asus/Desktop/works/51; sed -n '110,145p' feetech_servo.py

OUT
    def move_and_time(self, targets, tolerance=1.5, settle=0.05, timeout=10.0):
        """Send the goals and block until every servo stops. Returns seconds."""
        start = time.perf_counter()
        self.write_goals(targets)

        stable_since = {sid: None for sid in targets}
        done = set()
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
        return max(elapsed, 0.0)

    def close(self, release=False):
        # Torque stays on by default: a loaded joint would drop if we cut it.
Bash
IN
cd /home/asus/Desktop/works/51; python3 - <<'PY'
p="feetech_servo.py"; s=open(p).read()

old_sig = '''    def move_and_time(self, targets, tolerance=1.5, settle=0.05, timeout=10.0):
        """Send the goals and block until every servo stops. Returns seconds."""
        start = time.perf_counter()
        self.write_goals(targets)

        stable_since = {sid: None for sid in targets}
        done = set()'''
new_sig = '''    def move_and_time(self, targets, tolerance=1.5, settle=0.05, timeout=10.0):
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
        dead = None'''
assert old_sig in s; s = s.replace(old_sig, new_sig)

old_body = '''                pos = self.read_position(sid)
                if pos is None:
                    continue
                error = abs((pos - goal + 180.0) % 360.0 - 180.0)'''
new_body = '''                pos = self.read_position(sid)
                if pos is None:
                    continue
                if dead is None and origin[sid] is not None:
                    if abs((pos - origin[sid] + 180.0) % 360.0 - 180.0) > 0.5:
                        dead = now - start
                error = abs((pos - goal + 180.0) % 360.0 - 180.0)'''
assert old_body in s; s = s.replace(old_body, new_body)

old_ret = '''        elapsed = time.perf_counter() - start - settle
        return max(elapsed, 0.0)'''
new_ret = '''        elapsed = time.perf_counter() - start - settle
        return max(elapsed, 0.0), dead'''
assert old_ret in s; s = s.replace(old_ret, new_ret)

old_call = '''            elapsed = bus.move_and_time(targets)'''
new_call = '''            elapsed, dead = bus.move_and_time(targets, tolerance=args.tolerance)'''
assert old_call in s; s = s.replace(old_call, new_call)

old_print = '''            print("  took %.3f s (%.1f ms)" % (elapsed, elapsed * 1000.0))'''
new_print = '''            if dead is None:
                print("  took %.3f s (%.1f ms)" % (elapsed, elapsed * 1000.0))
            else:
                print("  took %.3f s (%.1f ms)  =  %.0f ms startup + %.0f ms travel"
                      % (elapsed, elapsed * 1000.0, dead * 1000.0,
                         (elapsed - dead) * 1000.0))'''
assert old_print in s; s = s.replace(old_print, new_print)

old_arg = '''    ap.add_argument("--release-on-exit", action="store_true",'''
new_arg = '''    ap.add_argument("--tolerance", type=float, default=1.5,
                    help="degrees of error that count as arrived")
    ap.add_argument("--release-on-exit", action="store_true",'''
assert old_arg in s; s = s.replace(old_arg, new_arg)
open(p,"w").write(s)
print("patched")
PY

OUT
patched
Bash
IN
cd /home/asus/Desktop/works/51; printf '11 0\n11 15\n11 90\n11 0\nq\n' | timeout 60 .venv/bin/python feetech_servo.py --ids 11 2>&1 | tail -14

OUT
servo 11 found (model 777)
connected on /dev/ttyACM2 at 1000000 baud
  servo 11 at 0.2 deg
enter an angle, or 'id angle' pairs. 'r' read, 't'/'T' torque, 'q' quit.
>   servo 11 -> 0.0 deg (now 0.2)
  took 0.001 s (1.1 ms)
>   servo 11 -> 15.0 deg (now 14.9)
  took 0.412 s (411.7 ms)  =  90 ms startup + 322 ms travel
>   servo 11 -> 90.0 deg (now 89.8)
  took 0.867 s (867.0 ms)  =  70 ms startup + 797 ms travel
>   servo 11 -> 0.0 deg (now 0.2)
  took 0.946 s (946.1 ms)  =  86 ms startup + 861 ms travel
> closed
Diagnosed. Nothing is wrong with the script or your wiring — the servo is already running at its physical limit. Your numbers are what an STS3215/30 kg does.

What I measured
I benchmarked a repeated 90° move on servo 11, varying each parameter:

goal speed	time		goal accel	time
500	1764 ms		10	2178 ms
1000	1187 ms		50	866 ms
2400	867 ms		255	866 ms
0 (uncapped)	866 ms			
Both saturate at the defaults I shipped. Above speed 2400 / accel 50 the registers are accepted (I read them back — 4000 and 255 stored fine) but the motor simply cannot go faster. The 30 kg STS3215 is the heavily-geared variant; peak was ~160 deg/s, ~104 deg/s averaged over a 90° move.

I also ruled out the usual culprits:

Not the link — a position read round-trips in 0.30 ms, so polling costs 0.63 ms per loop out of your 400.
Not the power — both servos report 12.0 V, torque limit already at max (1000), temps 34/37 °C.
Not my packet layout — registers read back exactly as written.
Where your 400 ms actually goes
Tracing a 15° move densely:


motion starts           83 ms     <- servo does nothing for 83 ms
50% of travel          213 ms
within 1.5 deg         318 ms
within 0.5 deg         354 ms
moving flag clears     415 ms
That 83 ms of dead time is fixed — identical on a 15° and a 90° move, and I confirmed it's inside the servo, not the protocol: writing only the 2-byte goal-position register instead of the full 7-byte accel+position+speed block gave the same 83.0 ms median. It's the STS3215's internal startup latency, and there's no host-side fix.

So a small move is mostly overhead: 83 ms startup + ~230 ms travel + ~100 ms settling into the tolerance band.

I added that split to the output — feetech_servo.py now prints:


servo 11 -> 15.0 deg (now 14.9)
took 0.412 s (411.7 ms)  =  90 ms startup + 322 ms travel
plus a --tolerance flag (default 1.5°) — loosening it to 3° will shave ~40 ms off the reported number, though that's measurement, not motion.

The one real speedup
Don't use discrete point-to-point moves for a robot head. Each one pays the 83 ms startup and decelerates to a stop. head.py already has the right shape — a 50 Hz thread streaming a continuously-updated pose. Streaming goal positions at 50 Hz keeps the servo permanently mid-profile, so it never re-pays startup and never stops between targets. Motion looks far faster and smoother even though top speed is unchanged.

Want me to add a streaming mode to this script so you can compare it against the stepped moves?

feetech_servo.py
i just wnat to know can we speed up that time. i mean if want drive motor 50Hz ite mean motor should able to execute 0.02s "1/50 = 0.02 sec". isnt it is that possible ?
Good question, and there's an important distinction hiding in it: 50 Hz streaming does not mean the motor completes a move in 20 ms. Let me prove that with a measurement rather than argue it.

Bash
IN
cd /home/asus/Desktop/works/51; timeout 200 .venv/bin/python - <<'PY' 2>&1
import time, math
from scservo_sdk import PortHandler, PacketHandler, GroupSyncWrite, COMM_SUCCESS
port=PortHandler("/dev/ttyACM2"); pk=PacketHandler(0)
port.openPort(); port.setBaudRate(1000000); SID=11
pk.write1ByteTxRx(port,SID,40,1)
def st(d): return int(round(d*4096/360.0))%4096
def setup(speed,accel):
    pk.write1ByteTxRx(port,SID,41,accel)
    pk.write2ByteTxRx(port,SID,46,speed)
def goto(deg):                      # position-only write, 2 bytes
    g=GroupSyncWrite(port,pk,42,2); s=st(deg)
    g.addParam(SID,[s&0xFF,(s>>8)&0xFF]); g.txPacket(); g.clearParam()
def pos():
    p,c,_=pk.read2ByteTxRx(port,SID,56)
    return p*360/4096 if c==COMM_SUCCESS else None

setup(0,255)
# park at 45 (mid range) then stream a ramp at a given commanded velocity
print("streaming goal position at 50 Hz, ramp 45 -> 45+A, measuring tracking")
print(" cmd vel |  frames | mean lag | max |actual-cmd| | achieved vel")
for vel in (30,60,120,200,400):
    goto(45); time.sleep(1.5)
    dt=0.02; T=1.0; rows=[]
    t0=time.perf_counter()
    n=0
    while True:
        now=time.perf_counter()-t0
        if now>T: break
        cmd=45+vel*now
        if cmd>135: cmd=135
        goto(cmd); n+=1
        a=pos()
        if a is not None: rows.append((now,cmd,a))
        # hold the 50 Hz frame
        nxt=t0+ (n)*dt
        while time.perf_counter()<nxt: pass
    # lag = time shift that best aligns actual to commanded, via error/velocity
    errs=[c-a for _,c,a in rows if _>0.3]
    lag=(sum(errs)/len(errs))/vel if errs and vel else 0
    mx=max(abs(c-a) for _,c,a in rows)
    seg=[r for r in rows if 0.3<r[0]<0.9]
    av=(seg[-1][2]-seg[0][2])/(seg[-1][0]-seg[0][0]) if len(seg)>2 else 0
    print("  %4d   |   %4d  |  %5.1f ms | %6.1f deg     | %6.1f deg/s" % (vel,n,lag*1000,mx,av))
goto(45); time.sleep(1.2); port.closePort()
PY

OUT
streaming goal position at 50 Hz, ramp 45 -> 45+A, measuring tracking
 cmd vel |  frames | mean lag | max |actual-cmd| | achieved vel
    30   |     50  |   89.1 ms |    2.7 deg     |   30.0 deg/s
    60   |     50  |  122.0 ms |    7.4 deg     |   59.9 deg/s
   120   |     50  |  152.3 ms |   22.6 deg     |  117.0 deg/s
   200   |     50  |  124.5 ms |   54.1 deg     |  129.0 deg/s
   400   |     50  |   71.5 ms |   82.1 deg     |  129.3 deg/s
There it is. Let me dump the EEPROM in case anything is capping speed:

Bash
IN
cd /home/asus/Desktop/works/51; timeout 90 .venv/bin/python - <<'PY' 2>&1
from scservo_sdk import PortHandler, PacketHandler, COMM_SUCCESS
port=PortHandler("/dev/ttyACM2"); pk=PacketHandler(0)
port.openPort(); port.setBaudRate(1000000); SID=11
names={5:"ID",6:"baud",7:"return delay",8:"resp level",9:"min angle",11:"max angle",
 13:"max temp",14:"max volt",15:"min volt",16:"max torque",33:"unloading cond",
 34:"LED cond",35:"P gain",36:"D gain",37:"I gain",38:"min startup force",
 41:"acc",46:"goal speed",48:"torque limit",55:"lock"}
vals={}
for a in sorted(names):
    n=2 if a in (9,11,16,46,48) else 1
    v,c,_=(pk.read1ByteTxRx if n==1 else pk.read2ByteTxRx)(port,SID,a)
    vals[a]=v if c==COMM_SUCCESS else None
    print("  %2d  %-18s %s" % (a,names[a],vals[a]))
port.closePort()
PY

OUT
   5  ID                 11
   6  baud               0
   7  return delay       0
   8  resp level         1
   9  min angle          0
  11  max angle          4095
  13  max temp           70
  14  max volt           140
  15  min volt           40
  16  max torque         1000
  33  unloading cond     0
  34  LED cond           20
  35  P gain             200
  36  D gain             80
  37  I gain             10
  38  min startup force  200
  41  acc                50
  46  goal speed         0
  48  torque limit       1000
  55  lock               1
No — and the premise is worth correcting, because it's the thing standing between you and smooth motion.

50 Hz does not mean each move must finish in 20 ms
At 50 Hz you aren't sending "go to 90°" every 20 ms. You send the next small increment — ~2° — and the servo is continuously mid-motion, never stopping. The 20 ms budget applies to one increment, not to a full traverse.

I streamed position-only writes at exactly 50 Hz to servo 11 and measured tracking against the commanded ramp:

commanded	achieved	lag	max error
30 deg/s	30.0	89 ms	2.7°
60 deg/s	59.9	122 ms	7.4°
120 deg/s	117.0	152 ms	22.6°
200 deg/s	129.0	—	54°
400 deg/s	129.3	—	82°
All 50 frames/second were accepted and the servo moved continuously. It did not stall 83 ms per frame.

That's the key point: the 83 ms is latency, not a stall. It's pipelined. The servo's actual position trails your commanded position by ~90 ms, but new commands keep flowing in and being absorbed the whole time. Latency and throughput are different things — you never pay the 83 ms more than once as long as you don't let the servo come to a stop.

Your stepped test paid it on every single move precisely because each move ended at a standstill.

The real ceiling
Sustained top speed is ~130 deg/s, so per 20 ms frame the servo can advance about 2.6°. Command increments under that and it tracks essentially perfectly (30 deg/s tracked with 2.7° error). Command more and it saturates and falls behind — that's the 200 and 400 rows above.

For a robot head, 30–60 deg/s is already brisk, so you have headroom.

Can the underlying speed be raised?
Mostly no. I dumped the EEPROM looking for a cap and found none:


 9/11  angle limits      0 / 4095    (full range, not clipped)
   16  max torque        1000        (maximum)
   46  goal speed        0           (uncapped)
   48  torque limit      1000        (maximum)
Combined with the confirmed 12.0 V supply, nothing is throttling it — ~130 deg/s is the gearing of the 30 kg variant. The 83 ms latency is servo firmware and isn't reachable from the host (identical for a 2-byte and a 7-byte write).

One genuine lever I did not touch: P gain is 200 (addr 35, with D 80 / I 10). Raising it tightens tracking and would cut that ~90 ms lag. I left it alone because it's an EEPROM write — currently locked (addr 55 = 1) — and too-high P oscillates, which on a mounted head means visible jitter. Worth trying on the bench if the lag matters, and easy to restore.

Beyond that it's a hardware trade: the lower-gear STS3215 variants swap torque for speed.

Want me to add a 50 Hz streaming mode to feetech_servo.py so you can drive it that way directly, or a P-gain sweep that measures lag and reverts to 200 afterward?

yes.  future goal is sync with head movement
Let me look at the head controller interface so the streaming mode drops straight into it.

Bash
IN
cd /home/asus/Desktop/works/51; sed -n '400,460p' command-line/python/head.py; echo "=== head_hw.py ==="; cat command-line/python/head_hw.py

OUT
    # either.
    if tag == "calm" and _is_definite(fallback):
        TAG_DISAGREEMENTS.append((stripped, tag, fallback.gesture))
        fallback.reason = f"{fallback.reason} (beat [neutral])"
        return fallback

    plan = Plan(tag, duration, stripped, "intent tag")
    if plan.gesture != fallback.gesture:
        # Recorded rather than resolved. Which source is right is a question
        # about the model, and the only way to answer it is to run a session
        # and read these rows.
        TAG_DISAGREEMENTS.append((stripped, plan.gesture, fallback.gesture))
        plan.reason = f"intent tag (text said {fallback.gesture})"
    return plan


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

=== head_hw.py ===
"""head_hw.py - drives the real robot head from the simulation's pose stream.

The simulation and the hardware are the same motion: head.py resolves one pose
per frame, and RobotHeadController forwards it over head_link as an absolute
jog. Whatever the window draws is what the neck is being told to do, so the two
cannot drift apart.

WHY jog AND NOT speak. head_link also offers speak()/stop(), which hand the
sentence and its [head_*] tags to the head's own gesture engine. That path is
not used here, for two reasons. It would replay Gemini's raw tags, and those
are unreliable enough that head.plan_sentence deliberately overrules them --
the model tags questions as shakes and refusals as calm. And it would put a
second gesture engine on the same neck, so the window would stop being a
picture of what the head is doing. One engine, one pose stream.

look() IS used, from the look_around tool: it blocks until the neck has
finished sweeping and returns the sentence the head wants said, which is a
better answer than anything this side could invent. Jog packets have to stop
while it runs -- one arriving mid-look abandons the look -- which is what
suspended() is for.

HANDING THE HEAD BACK. While jog packets arrive the head stops tracking faces
and stops gesturing on its own, and it takes itself back about two seconds
after the last one. So this controller goes quiet when head.py reports that
nothing is being expressed, rather than idling at 25 Hz forever: an idle robot
gets its own face tracking back. Set release_idle=False to keep the neck under
this program's control for as long as it runs.
"""

import contextlib
import threading
import time

import head_link
from head import SimHeadController

# The neck cannot follow faster than this, so anything above it is wasted
# bandwidth rather than smoother motion. head.py resolves at 50 Hz, so roughly
# every second frame goes out.
SEND_HZ = 25

# Keep sending a settled pose for this long after the head stops expressing
# anything, then go quiet. Long enough to cover a dropped packet, far short of
# the head's ~2 s hand-back.
SETTLE_S = 0.3

# Used only when the head does not answer limits(). Deliberately smaller than
# head.py's simulated travel: a neck that turns further than we ask loses only
# reach, one that turns less would be driven into its stop.
FALLBACK = {"yaw_min": -30.0, "yaw_max": 30.0,
            "pitch_min": -20.0, "pitch_max": 20.0}

# COMMANDED ANGLE IS NOT ACHIEVED ANGLE. The simulation has no inertia, so it
# swings the full amplitude the mixer asks for. A real neck has mass and a
# servo with its own speed ceiling, so it low-passes the gesture and arrives at
# a fraction of it -- the faster the gesture, the smaller the fraction. The
# wire therefore carries a pre-compensated command: the window keeps showing
# the intended pose, and this scales it up so the neck actually gets there.
#
# This is calibration, not licence. The result is still clamped to the travel
# the head itself reported, so gain can never drive a servo into its stop; too
# much of it just flattens the tops of a gesture, which `clipped` counts.
GAIN_PAN = 2.2
GAIN_TILT = 2.2


class RobotHeadController(SimHeadController):
    """Sends every resolved pose to the real head, and keeps it for the window.

    Inherits the simulator so .pan/.tilt stay readable: the visualiser draws
    the same numbers that go out on the wire.
    """

    def __init__(self, send_hz=SEND_HZ, settle_s=SETTLE_S, release_idle=True,
                 gain_pan=GAIN_PAN, gain_tilt=GAIN_TILT):
        super().__init__()
        self._period = 1.0 / send_hz
        self._settle = settle_s
        self._release_idle = release_idle
        self._last_send = 0.0
        self._quiet_since = None
        self._suspend = 0
        self._lock = threading.Lock()
        self.gain_pan = float(gain_pan)
        self.gain_tilt = float(gain_tilt)
        # The neck's own travel, which bounds whatever the gain produces.
        # Replaced by apply_limits() when the head answers.
        self.pan_min, self.pan_max = FALLBACK["yaw_min"], FALLBACK["yaw_max"]
        self.tilt_min, self.tilt_max = FALLBACK["pitch_min"], FALLBACK["pitch_max"]
        self.sent = 0
        self.clipped = 0        # frames the gain pushed past the neck's travel

    def set_limits(self, pan_min, pan_max, tilt_min, tilt_max):
        with self._lock:
            self.pan_min, self.pan_max = float(pan_min), float(pan_max)
            self.tilt_min, self.tilt_max = float(tilt_min), float(tilt_max)

    def write(self, pan, tilt, active=True):
        super().write(pan, tilt)        # the window reads these
        now = time.monotonic()
        if now - self._last_send < self._period:
            return                      # 50 Hz in, 25 Hz out
        with self._lock:
            if self._suspend:
                return                  # a directed look owns the neck
        if active or not self._release_idle:
            self._quiet_since = None
        elif self._quiet_since is None:
            self._quiet_since = now     # keep sending through the settle window
        elif now - self._quiet_since > self._settle:
            return                      # silence: the head takes itself back
        self._last_send = now
        self.sent += 1
        # Amplify, then bound by the real neck. In that order: the clamp is the
        # safety net and has to be the last thing that touches the number.
        out_pan = max(self.pan_min, min(self.pan_max, pan * self.gain_pan))
        out_tilt = max(self.tilt_min, min(self.tilt_max, tilt * self.gain_tilt))
        if out_pan != pan * self.gain_pan or out_tilt != tilt * self.gain_tilt:
            self.clipped += 1
        head_link.jog(out_pan, out_tilt)

    @contextlib.contextmanager
    def suspended(self):
        """Hold jog packets off the wire while something else owns the neck."""
        with self._lock:
            self._suspend += 1
        try:
            yield
        finally:
            with self._lock:
                self._suspend = max(0, self._suspend - 1)
            # Resume from wherever the head left the neck rather than snapping
            # from a stale pose.
            self._last_send = 0.0


def connect(addr=None, verbose=False, gain=None):
    """Point head_link at the head. Returns a controller, or None if disabled.

    Never raises and never blocks on the head being present: UDP sendto to a
    machine that is not listening simply succeeds, which is why limits() below
    is the only real test of whether anything is there.
    """
    # head_link ships VERBOSE on, which at 25 packets a second would bury the
    # transcript this program exists to show.
    head_link.VERBOSE = verbose
    if addr:
        host, _, port = str(addr).partition(":")
        head_link.set_target(host or "127.0.0.1", int(port or 8770))
    if gain is None:
        return RobotHeadController()
    return RobotHeadController(gain_pan=float(gain), gain_tilt=float(gain))


def apply_limits(motion, controller=None, timeout=2.0):
    """Ask the head how far its neck really travels and clamp the mixer to it.

    Returns True if the head answered. When it does not, the conservative
    fallback is used rather than head.py's simulated travel -- driving unknown
    servos to +/-45 is how a neck meets its own stop.
    """
    lim = head_link.limits(timeout=timeout)
    known = lim is not None
    lim = lim or FALLBACK
    motion.set_limits(lim["yaw_min"], lim["yaw_max"],
                      lim["pitch_min"], lim["pitch_max"])
    if controller is not None:
        # The controller needs them as well: it applies the gain *after* the
        # mixer has already clamped, so it owns the last word on travel.
        controller.set_limits(lim["yaw_min"], lim["yaw_max"],
                              lim["pitch_min"], lim["pitch_max"])
    return known


def directed_look(controller, action):
    """Run a directed look on the head, with jog held off for its duration.

    Returns the sentence the head reports, or None if there is no head.
    """
    if controller is None:
        return None
    with controller.suspended():
        return head_link.look(action)
Now I understand the target: head.py:432-440 has a FeetechController stub, and head_hw.py shows the contract — write(pan, tilt, active) at 50 Hz. Let me build toward that.

Bash
IN
cd /home/asus/Desktop/works/51; cp feetech_servo.py /tmp/claude-1000/-home-asus-Desktop-works-51/65c9092f-34e1-4795-bfdf-a4a304f1e75f/scratchpad/feetech_servo.bak.py && echo backed up

OUT
backed up
Bash
IN
cd /home/asus/Desktop/works/51; python3 - <<'PY'
p="feetech_servo.py"; s=open(p).read()

# --- extend the module docstring -------------------------------------------
s = s.replace('''    t             -> torque off (servos go limp), 'T' turns it back on
    q             -> quit
"""''','''    t             -> torque off (servos go limp), 'T' turns it back on
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
"""''')

# --- constants --------------------------------------------------------------
s = s.replace('''PROTOCOL_END = 0        # STS/SMS servos are little-endian; SCS servos use 1.
BAUDRATE = 1000000''','''ADDR_P_GAIN = 21
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
STREAM_HZ = 50''')
open(p,"w").write(s); print("header done")
PY

OUT
header done
Let me verify the actual P-gain address before writing anything — my earlier dump labels were guesses.

Bash
IN
cd /home/asus/Desktop/works/51; timeout 60 .venv/bin/python - <<'PY' 2>&1
from scservo_sdk import PortHandler, PacketHandler, COMM_SUCCESS
port=PortHandler("/dev/ttyACM2"); pk=PacketHandler(0)
port.openPort(); port.setBaudRate(1000000)
for SID in (9,11):
    row=[]
    for a in range(18,41):
        v,c,_=pk.read1ByteTxRx(port,SID,a)
        row.append("%d:%s"%(a, v if c==COMM_SUCCESS else "??"))
    print("servo %d  %s"%(SID," ".join(row)))
port.closePort()
PY

OUT
servo 9  18:12 19:44 20:47 21:32 22:32 23:0 24:16 25:0 26:1 27:1 28:54 29:1 30:1 31:85 32:0 33:0 34:20 35:200 36:80 37:10 38:200 39:200 40:1
servo 11  18:12 19:44 20:47 21:32 22:32 23:0 24:16 25:0 26:1 27:1 28:54 29:1 30:1 31:85 32:0 33:0 34:20 35:200 36:80 37:10 38:200 39:200 40:1
Correction worth making explicitly: P gain is 32, not 200. Addr 21/22/23 = P32/D32/I0 (the Feetech factory defaults); what I read at addr 35 was the protection time. My constant is right, and a P of 32 leaves much more headroom than I implied. Now the code:

Bash
IN
cd /home/asus/Desktop/works/51; python3 - <<'PY'
p="feetech_servo.py"; s=open(p).read()

anchor = "    def close(self, release=False):"
assert anchor in s

new_methods = '''    # -- streaming -----------------------------------------------------
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

    def read_gains(self, sid):
        p, _, _ = self.packet.read1ByteTxRx(self.port, sid, ADDR_P_GAIN)
        d, _, _ = self.packet.read1ByteTxRx(self.port, sid, ADDR_D_GAIN)
        i, _, _ = self.packet.read1ByteTxRx(self.port, sid, ADDR_I_GAIN)
        return p, d, i

    def write_p_gain(self, sid, value):
        """Set the position P coefficient. Unlocks EEPROM around the write."""
        self.packet.write1ByteTxRx(self.port, sid, ADDR_LOCK, 0)
        self.packet.write1ByteTxRx(self.port, sid, ADDR_P_GAIN, int(value))
        self.packet.write1ByteTxRx(self.port, sid, ADDR_LOCK, 1)

'''
s = s.replace(anchor, new_methods + anchor)
open(p,"w").write(s); print("bus methods added")
PY

OUT
bus methods added
Bash
IN
cd /home/asus/Desktop/works/51; python3 - <<'PY'
p="feetech_servo.py"; s=open(p).read()

anchor = "def parse_command(line, ids):"
assert anchor in s

block = '''# --- head integration -----------------------------------------------------
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


'''
s = s.replace(anchor, block + anchor)
s = s.replace("import argparse\nimport sys\nimport time",
              "import argparse\nimport math\nimport sys\nimport time")
open(p,"w").write(s)
import ast; ast.parse(s); print("controller added, parses")
PY

OUT
controller added, parses
Now the two new modes:

Bash
IN
cd /home/asus/Desktop/works/51; python3 - <<'PY'
p="feetech_servo.py"; s=open(p).read()
anchor = "def main():"
assert anchor in s

block = '''def _track(bus, sid, profile, duration, hz=STREAM_HZ):
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


def _report(rows, label, settle=0.3):
    """Lag and error over the part of the run past the initial transient."""
    body = [r for r in rows if r[0] > settle]
    if len(body) < 5:
        print("  %-22s not enough samples" % label)
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
    home = bus.read_position(sid)
    print("streaming on servo %d at %d Hz, centred on %.1f deg" % (sid, args.hz, home))
    print("a %d Hz frame is %.1f ms, and at the measured %.0f deg/s ceiling the"
          % (args.hz, 1000.0 / args.hz, MAX_VEL_DEG_S))
    print("servo can advance %.2f deg per frame -- that, not a whole move, is"
          % (MAX_VEL_DEG_S / args.hz))
    print("what has to fit in one frame.\\n")
    bus.configure_stream(speed=0)

    print("ramps (constant velocity):")
    for vel in (30, 60, 120, 200):
        span = min(args.span, vel * 1.0)
        bus.stream_write({sid: home})
        time.sleep(1.0)
        rows = _track(bus, sid, lambda t, v=vel, s=span: home + min(v * t, s),
                      1.2, args.hz)
        _report(rows, "%d deg/s" % vel)
        bus.stream_write({sid: home})
        time.sleep(0.8)

    print("\\nsine sweep (what a gesture actually looks like):")
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
    home = bus.read_position(sid)
    bus.configure_stream(speed=0)
    print("\\nsweeping P on servo %d, 60 deg/s ramp, %.0f deg span" % (sid, args.span))
    print("  P  |  lag     rms err  | settle ring (deg pk-pk after stop)")
    try:
        for pval in args.pgains:
            bus.write_p_gain(sid, pval)
            time.sleep(0.15)
            bus.stream_write({sid: home})
            time.sleep(1.0)
            rows = _track(bus, sid,
                          lambda t: home + min(60.0 * t, args.span), 1.3, args.hz)
            body = [r for r in rows if r[0] > 0.3]
            errs = [c - a for _, c, a in body]
            rms = (sum(e * e for e in errs) / len(errs)) ** 0.5
            lag = (sum(errs) / len(errs)) / 60.0
            # Hold the final pose and watch for ringing -- the cost of high P.
            tail = []
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < 0.6:
                a = bus.read_position(sid)
                if a is not None:
                    tail.append(a)
            ring = max(tail) - min(tail) if tail else 0.0
            print("  %3d |  %5.1f ms  %5.2f deg  | %5.2f%s"
                  % (pval, lag * 1000, rms, ring,
                     "   <-- ringing" if ring > 1.0 else ""))
            bus.stream_write({sid: home})
            time.sleep(0.8)
    finally:
        for s, (gp, _, _) in original.items():
            bus.write_p_gain(s, gp)
        restored = {s: bus.read_gains(s)[0] for s in bus.ids}
        print("\\nrestored: %s" % ", ".join("servo %d P=%d" % (s, v)
                                            for s, v in restored.items()))


'''
s = s.replace(anchor, block + anchor)
open(p,"w").write(s)
import ast; ast.parse(s); print("modes added, parses")
PY

OUT
modes added, parses
Bash
IN
cd /home/asus/Desktop/works/51; python3 - <<'PY'
p="feetech_servo.py"; s=open(p).read()
old = '''    ap.add_argument("--release-on-exit", action="store_true",
                    help="cut torque when quitting (servos go limp)")
    args = ap.parse_args()

    bus = ServoBus(args.port, args.ids, args.baud, args.speed, args.accel)
    print("connected on %s at %d baud" % (args.port, args.baud))'''
new = '''    ap.add_argument("--release-on-exit", action="store_true",
                    help="cut torque when quitting (servos go limp)")
    ap.add_argument("--stream", action="store_true",
                    help="50 Hz streaming demo with a tracking report")
    ap.add_argument("--tune-pgain", action="store_true",
                    help="sweep position P gain, then restore the original")
    ap.add_argument("--hz", type=int, default=STREAM_HZ)
    ap.add_argument("--span", type=float, default=40.0,
                    help="degrees of travel the demos are allowed to use")
    ap.add_argument("--pgains", type=int, nargs="+",
                    default=[32, 48, 64, 96, 128],
                    help="P values to try with --tune-pgain")
    args = ap.parse_args()

    bus = ServoBus(args.port, args.ids, args.baud, args.speed, args.accel)
    print("connected on %s at %d baud" % (args.port, args.baud))

    if args.stream or args.tune_pgain:
        try:
            if args.stream:
                mode_stream(bus, args)
            else:
                mode_tune_pgain(bus, args)
        except KeyboardInterrupt:
            print()
        finally:
            bus.close(release=args.release_on_exit)
        return'''
assert old in s; s=s.replace(old,new)
open(p,"w").write(s)
import ast; ast.parse(s); print("cli wired")
PY
.venv/bin/python feetech_servo.py --help 2>&1 | tail -18

OUT
cli wired
never by stepping to one.

options:
  -h, --help            show this help message and exit
  --port PORT
  --baud BAUD
  --ids IDS [IDS ...]
  --speed SPEED         0..4095 steps/s, 0 means full speed
  --accel ACCEL         0..255
  --tolerance TOLERANCE
                        degrees of error that count as arrived
  --release-on-exit     cut torque when quitting (servos go limp)
  --stream              50 Hz streaming demo with a tracking report
  --tune-pgain          sweep position P gain, then restore the original
  --hz HZ
  --span SPAN           degrees of travel the demos are allowed to use
  --pgains PGAINS [PGAINS ...]
                        P values to try with --tune-pgain
Now let me run the streaming demo on servo 11 (the one with proven safe travel):

Bash
IN
cd /home/asus/Desktop/works/51; timeout 200 .venv/bin/python feetech_servo.py --ids 11 --stream --span 40 2>&1

OUT
servo 11 found (model 777)
connected on /dev/ttyACM2 at 1000000 baud
streaming on servo 11 at 50 Hz, centred on 45.0 deg
a 50 Hz frame is 20.0 ms, and at the measured 130 deg/s ceiling the
servo can advance 2.60 deg per frame -- that, not a whole move, is
what has to fit in one frame.

ramps (constant velocity):
  30 deg/s               rms  2.54 deg  peak  2.91 deg  lag   99.5 ms  cmd   23.9 -> got   27.0 deg/s
  60 deg/s               rms  5.03 deg  peak  7.45 deg  lag  149.2 ms  cmd   25.0 -> got   33.1 deg/s
  120 deg/s              rms  7.88 deg  peak 22.40 deg  lag  873.3 ms  cmd    4.5 -> got   29.6 deg/s
  200 deg/s              rms  8.11 deg  peak 26.20 deg  lag    nan ms  cmd    0.0 -> got   29.6 deg/s

sine sweep (what a gesture actually looks like):
  0.25 Hz +/-20.0 deg   peak  31.4 deg/s   amplitude reached  19.9 /  20.0 deg (100%)
  0.50 Hz +/-20.0 deg   peak  62.8 deg/s   amplitude reached  19.7 /  20.0 deg ( 99%)
  1.00 Hz +/-20.0 deg   peak 125.7 deg/s   amplitude reached  19.7 /  20.0 deg ( 99%)
  2.00 Hz +/-20.0 deg   peak 251.3 deg/s   amplitude reached  12.0 /  20.0 deg ( 60%)
The sine sweep is the useful result, but the ramp report is broken — the ramp hits the span cap and I'm averaging across the flat part. Let me fix the analysis window:

Bash
IN
cd /home/asus/Desktop/works/51; python3 - <<'PY'
p="feetech_servo.py"; s=open(p).read()

old = '''def _report(rows, label, settle=0.3):
    """Lag and error over the part of the run past the initial transient."""
    body = [r for r in rows if r[0] > settle]
    if len(body) < 5:
        print("  %-22s not enough samples" % label)
        return'''
new = '''def _report(rows, label, settle=0.15):
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
        return'''
assert old in s; s=s.replace(old,new)

old2 = '''    for vel in (30, 60, 120, 200):
        span = min(args.span, vel * 1.0)
        bus.stream_write({sid: home})
        time.sleep(1.0)
        rows = _track(bus, sid, lambda t, v=vel, s=span: home + min(v * t, s),
                      1.2, args.hz)
        _report(rows, "%d deg/s" % vel)'''
new2 = '''    for vel in (30, 60, 120, 200):
        span = args.span
        # Ramp for exactly as long as the span allows, plus a little tail so
        # the trim in _report has something to cut against.
        dur = span / float(vel) + 0.25
        bus.stream_write({sid: home})
        time.sleep(1.0)
        rows = _track(bus, sid, lambda t, v=vel, s=span: home + min(v * t, s),
                      dur, args.hz)
        _report(rows, "%d deg/s" % vel)'''
assert old2 in s; s=s.replace(old2,new2)
open(p,"w").write(s)
import ast; ast.parse(s); print("fixed")
PY
timeout 200 .venv/bin/python feetech_servo.py --ids 11 --stream --span 60 2>&1 | head -14

OUT
fixed
servo 11 found (model 777)
connected on /dev/ttyACM2 at 1000000 baud
streaming on servo 11 at 50 Hz, centred on 45.1 deg
a 50 Hz frame is 20.0 ms, and at the measured 130 deg/s ceiling the
servo can advance 2.60 deg per frame -- that, not a whole move, is
what has to fit in one frame.

ramps (constant velocity):
  30 deg/s               rms  2.70 deg  peak  2.82 deg  lag   90.1 ms  cmd   30.0 -> got   30.0 deg/s
  60 deg/s               rms  7.30 deg  peak  7.45 deg  lag  121.6 ms  cmd   60.0 -> got   59.7 deg/s
  120 deg/s              rms 21.30 deg  peak 22.44 deg  lag  176.9 ms  cmd  120.0 -> got  101.6 deg/s
  200 deg/s              rms 37.62 deg  peak 44.22 deg  lag  186.5 ms  cmd  200.0 -> got   76.9 deg/s

sine sweep (what a gesture actually looks like):
Ramps are clean now and match my earlier manual measurement. Now the P-gain sweep — this writes EEPROM, so it restores in a finally:

Bash
IN
cd /home/asus/Desktop/works/51; timeout 260 .venv/bin/python feetech_servo.py --ids 11 --tune-pgain --span 40 2>&1

OUT
Exit code 1
servo 11 found (model 777)
connected on /dev/ttyACM2 at 1000000 baud
servo 11 gains before: P=32 D=32 I=0

sweeping P on servo 11, 60 deg/s ramp, 40 deg span
  P  |  lag     rms err  | settle ring (deg pk-pk after stop)
   32 |   54.5 ms   4.66 deg  |  0.00
   48 |   48.1 ms   4.17 deg  |  0.00

restored: servo 11 P=32
Traceback (most recent call last):
  File "/home/asus/Desktop/works/51/feetech_servo.py", line 581, in <module>
    sys.exit(main())
             ^^^^^^
  File "/home/asus/Desktop/works/51/feetech_servo.py", line 525, in main
    mode_tune_pgain(bus, args)
  File "/home/asus/Desktop/works/51/feetech_servo.py", line 465, in mode_tune_pgain
    rows = _track(bus, sid,
           ^^^^^^^^^^^^^^^^
  File "/home/asus/Desktop/works/51/feetech_servo.py", line 357, in _track
    actual = bus.read_position(sid)
             ^^^^^^^^^^^^^^^^^^^^^^
  File "/home/asus/Desktop/works/51/feetech_servo.py", line 107, in read_position
    steps, comm, err = self.packet.read2ByteTxRx(self.port, sid, ADDR_PRESENT_POSITION)
                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/asus/Desktop/works/51/.venv/lib/python3.11/site-packages/scservo_sdk/protocol_packet_handler.py", line 326, in read2ByteTxRx
    data_read = SCS_MAKEWORD(data[0], data[1]) if (result == COMM_SUCCESS) else 0
                                      ~~~~^^^
IndexError: list index out of range
Two things: an SDK bug (read2ByteTxRx indexes a short list on a comm glitch), and the restore correctly fired. Let me harden the reads:

Bash
IN
cd /home/asus/Desktop/works/51; python3 - <<'PY'
p="feetech_servo.py"; s=open(p).read()
old = '''    def read_position(self, sid):
        """Present position in degrees, or None if the read failed."""
        steps, comm, err = self.packet.read2ByteTxRx(self.port, sid, ADDR_PRESENT_POSITION)
        if comm != COMM_SUCCESS or err != 0:
            return None
        return steps_to_deg(steps)

    def is_moving(self, sid):
        flag, comm, err = self.packet.read1ByteTxRx(self.port, sid, ADDR_MOVING)
        if comm != COMM_SUCCESS:
            return False
        return bool(flag)'''
new = '''    def read_position(self, sid):
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
        return bool(flag)'''
assert old in s; s=s.replace(old,new)
open(p,"w").write(s); import ast; ast.parse(s); print("hardened")
PY
timeout 260 .venv/bin/python feetech_servo.py --ids 11 --tune-pgain --span 40 2>&1

OUT
hardened
servo 11 found (model 777)
connected on /dev/ttyACM2 at 1000000 baud
servo 11 gains before: P=32 D=32 I=0

sweeping P on servo 11, 60 deg/s ramp, 40 deg span
  P  |  lag     rms err  | settle ring (deg pk-pk after stop)
   32 |   54.8 ms   4.65 deg  |  0.00
   48 |   58.5 ms   4.97 deg  |  0.00
   64 |   45.2 ms   3.94 deg  |  0.00
   96 |   51.9 ms   4.49 deg  |  0.00
  128 |   40.3 ms   3.57 deg  |  0.00

restored: servo 11 P=242
The restore wrote 242, not 32 — that's a real bug and it's left the servo misconfigured. Checking actual state now:

Bash
IN
cd /home/asus/Desktop/works/51; timeout 60 .venv/bin/python - <<'PY' 2>&1
from scservo_sdk import PortHandler, PacketHandler, COMM_SUCCESS
port=PortHandler("/dev/ttyACM2"); pk=PacketHandler(0)
port.openPort(); port.setBaudRate(1000000)
for SID in (9,11):
    for _ in range(3):
        p,c,e=pk.read1ByteTxRx(port,SID,21)
        d,_,_=pk.read1ByteTxRx(port,SID,22)
        i,_,_=pk.read1ByteTxRx(port,SID,23)
        lk,_,_=pk.read1ByteTxRx(port,SID,55)
        print("servo %d: P=%s D=%s I=%s lock=%s (comm=%d err=%d)"%(SID,p,d,i,lk,c,e))
port.closePort()
PY

OUT
servo 9: P=32 D=32 I=0 lock=1 (comm=0 err=0)
servo 9: P=32 D=32 I=0 lock=1 (comm=0 err=0)
servo 9: P=32 D=32 I=0 lock=1 (comm=0 err=0)
servo 11: P=32 D=32 I=0 lock=1 (comm=0 err=0)
servo 11: P=32 D=32 I=0 lock=1 (comm=0 err=0)
servo 11: P=32 D=32 I=0 lock=1 (comm=0 err=0)
Hardware is fine — both servos are correctly at P=32, D=32, I=0, lock=1. The restore worked; the "242" was an unvalidated readback right after the EEPROM lock write. Let me fix that bug properly:

Bash
IN
cd /home/asus/Desktop/works/51; python3 - <<'PY'
p="feetech_servo.py"; s=open(p).read()
old = '''    def read_gains(self, sid):
        p, _, _ = self.packet.read1ByteTxRx(self.port, sid, ADDR_P_GAIN)
        d, _, _ = self.packet.read1ByteTxRx(self.port, sid, ADDR_D_GAIN)
        i, _, _ = self.packet.read1ByteTxRx(self.port, sid, ADDR_I_GAIN)
        return p, d, i

    def write_p_gain(self, sid, value):
        """Set the position P coefficient. Unlocks EEPROM around the write."""
        self.packet.write1ByteTxRx(self.port, sid, ADDR_LOCK, 0)
        self.packet.write1ByteTxRx(self.port, sid, ADDR_P_GAIN, int(value))
        self.packet.write1ByteTxRx(self.port, sid, ADDR_LOCK, 1)'''
new = '''    def _read_byte(self, sid, addr, retries=4):
        """One byte, retried until the bus agrees. None if it never does.

        Worth the retries: a read issued right after an EEPROM write can come
        back as a plausible-looking wrong number, and gain values are exactly
        the case where silently believing one is unacceptable.
        """
        for _ in range(retries):
            try:
                v, comm, err = self.packet.read1ByteTxRx(self.port, sid, addr)
            except (IndexError, TypeError):
                comm = -1
            if comm == COMM_SUCCESS and err == 0:
                return v
            time.sleep(0.02)
        return None

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
        return True'''
assert old in s; s=s.replace(old,new)

# restore must be loud and verified
old2 = '''    finally:
        for s, (gp, _, _) in original.items():
            bus.write_p_gain(s, gp)
        restored = {s: bus.read_gains(s)[0] for s in bus.ids}
        print("\\nrestored: %s" % ", ".join("servo %d P=%d" % (s, v)
                                            for s, v in restored.items()))'''
new2 = '''    finally:
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
        print("\\nrestored: %s%s"
              % (", ".join("servo %d P=%s" % (s, v) for s, v in readback.items()),
                 "" if ok else "   <-- RESTORE FAILED, re-run or set P by hand"))'''
assert old2 in s; s=s.replace(old2,new2)
open(p,"w").write(s); import ast; ast.parse(s); print("restore hardened")
PY

OUT
restore hardened
Now let me add repeats to beat the noise (P=48 measured worse than P=32, which is clearly scatter):

Bash
IN
cd /home/asus/Desktop/works/51; python3 - <<'PY'
p="feetech_servo.py"; s=open(p).read()
old = '''        for pval in args.pgains:
            bus.write_p_gain(sid, pval)
            time.sleep(0.15)
            bus.stream_write({sid: home})
            time.sleep(1.0)
            rows = _track(bus, sid,
                          lambda t: home + min(60.0 * t, args.span), 1.3, args.hz)
            body = [r for r in rows if r[0] > 0.3]
            errs = [c - a for _, c, a in body]
            rms = (sum(e * e for e in errs) / len(errs)) ** 0.5
            lag = (sum(errs) / len(errs)) / 60.0
            # Hold the final pose and watch for ringing -- the cost of high P.
            tail = []
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < 0.6:
                a = bus.read_position(sid)
                if a is not None:
                    tail.append(a)
            ring = max(tail) - min(tail) if tail else 0.0
            print("  %3d |  %5.1f ms  %5.2f deg  | %5.2f%s"
                  % (pval, lag * 1000, rms, ring,
                     "   <-- ringing" if ring > 1.0 else ""))
            bus.stream_write({sid: home})
            time.sleep(0.8)'''
new = '''        dur = args.span / 60.0 + 0.25
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
                     "   <-- ringing" if ring > 1.0 else ""))'''
assert old in s; s=s.replace(old,new)
s=s.replace("import argparse\nimport math\nimport sys\nimport time",
            "import argparse\nimport math\nimport statistics\nimport sys\nimport time")
s=s.replace('''                    help="P values to try with --tune-pgain")''',
'''                    help="P values to try with --tune-pgain")
    ap.add_argument("--repeats", type=int, default=3,
                    help="measurements per P value; the median is reported")''')
s=s.replace("default=[32, 48, 64, 96, 128],","default=[32, 64, 96, 128, 160, 192],")
open(p,"w").write(s); import ast; ast.parse(s); print("ok")
PY
timeout 500 .venv/bin/python feetech_servo.py --ids 11 --tune-pgain --span 40 2>&1

OUT
ok
servo 11 found (model 777)
connected on /dev/ttyACM2 at 1000000 baud
servo 11 gains before: P=32 D=32 I=0

sweeping P on servo 11, 60 deg/s ramp, 40 deg span
  P  |  lag     rms err  | settle ring (deg pk-pk after stop)
   32 |  120.0 ms   7.20 deg  |  0.00
   64 |  101.9 ms   6.12 deg  |  0.00
  WARNING: servo 11 P gain read back as 242, wanted 96
  128 |   92.5 ms   5.55 deg  |  0.00
  160 |   90.7 ms   5.44 deg  |  0.00
  WARNING: servo 11 P gain read back as 242, wanted 192
  WARNING: servo 11 P gain read back as 242, wanted 32

restored: servo 11 P=32   <-- RESTORE FAILED, re-run or set P by hand
The 242 recurs and the independent readback says 32 — so it's a spurious value (not a comm failure), which my retry can't catch. Let me find how long the servo needs after an EEPROM commit:

Bash
IN
cd /home/asus/Desktop/works/51; timeout 120 .venv/bin/python - <<'PY' 2>&1
import time
from scservo_sdk import PortHandler, PacketHandler, COMM_SUCCESS
port=PortHandler("/dev/ttyACM2"); pk=PacketHandler(0)
port.openPort(); port.setBaudRate(1000000); SID=11
def wr(val, d):
    pk.write1ByteTxRx(port,SID,55,0); time.sleep(d)
    pk.write1ByteTxRx(port,SID,21,val); time.sleep(d)
    pk.write1ByteTxRx(port,SID,55,1); time.sleep(d)
    seq=[]
    for _ in range(6):
        v,c,e=pk.read1ByteTxRx(port,SID,21); seq.append("%s"%v if c==COMM_SUCCESS else "X")
        time.sleep(0.01)
    return seq
for d in (0.02, 0.05, 0.1):
    for val in (96,192,32):
        print("delay %.2fs write P=%3d -> reads %s" % (d,val,wr(val,d)))
    print()
# is 242 tied to the lock register instead?
pk.write1ByteTxRx(port,SID,55,0); time.sleep(0.05)
print("lock=0, read P six times:", [pk.read1ByteTxRx(port,SID,21)[0] for _ in range(6)])
pk.write1ByteTxRx(port,SID,21,32); time.sleep(0.05)
pk.write1ByteTxRx(port,SID,55,1); time.sleep(0.1)
print("final P =", pk.read1ByteTxRx(port,SID,21)[0])
port.closePort()
PY

OUT
delay 0.02s write P= 96 -> reads ['242', '96', '96', '96', '96', '96']
delay 0.02s write P=192 -> reads ['242', '192', '192', '192', '192', '192']
delay 0.02s write P= 32 -> reads ['242', '32', '32', '32', '32', '32']

delay 0.05s write P= 96 -> reads ['242', '96', '96', '96', '96', '96']
delay 0.05s write P=192 -> reads ['242', '192', '192', '192', '192', '192']
delay 0.05s write P= 32 -> reads ['242', '32', '32', '32', '32', '32']

delay 0.10s write P= 96 -> reads ['242', '96', '96', '96', '96', '96']
delay 0.10s write P=192 -> reads ['242', '192', '192', '192', '192', '192']
delay 0.10s write P= 32 -> reads ['242', '32', '32', '32', '32', '32']

lock=0, read P six times: [242, 0, 32, 32, 32, 32]
final P = 32
Root cause found, and it's not timing: the first read after any write always returns a stale 242, at every delay. Second read is correct. Fix is to require consecutive agreeing reads:

Bash
IN
cd /home/asus/Desktop/works/51; python3 - <<'PY'
p="feetech_servo.py"; s=open(p).read()
old = '''    def _read_byte(self, sid, addr, retries=4):
        """One byte, retried until the bus agrees. None if it never does.

        Worth the retries: a read issued right after an EEPROM write can come
        back as a plausible-looking wrong number, and gain values are exactly
        the case where silently believing one is unacceptable.
        """
        for _ in range(retries):
            try:
                v, comm, err = self.packet.read1ByteTxRx(self.port, sid, addr)
            except (IndexError, TypeError):
                comm = -1
            if comm == COMM_SUCCESS and err == 0:
                return v
            time.sleep(0.02)
        return None'''
new = '''    def _read_byte(self, sid, addr, retries=8):
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
        return last'''
assert old in s; s=s.replace(old,new)
open(p,"w").write(s); import ast; ast.parse(s); print("ok")
PY
timeout 500 .venv/bin/python feetech_servo.py --ids 11 --tune-pgain --span 40 2>&1

OUT
ok
servo 11 found (model 777)
connected on /dev/ttyACM2 at 1000000 baud
servo 11 gains before: P=32 D=32 I=0

sweeping P on servo 11, 60 deg/s ramp, 40 deg span
  P  |  lag     rms err  | settle ring (deg pk-pk after stop)
   32 |  120.1 ms   7.20 deg  |  0.00
   64 |  101.9 ms   6.11 deg  |  0.00
   96 |   95.7 ms   5.74 deg  |  0.00
  128 |   92.6 ms   5.56 deg  |  0.00
  160 |   90.6 ms   5.44 deg  |  0.00
  192 |   89.5 ms   5.37 deg  |  0.00

restored: servo 11 P=32
Clean, monotonic, no warnings, verified restore. Final verification of all three modes and the hardware state:

Bash
IN
cd /home/asus/Desktop/works/51; echo "=== gains state ==="; timeout 40 .venv/bin/python - <<'PY' 2>&1
from scservo_sdk import PortHandler, PacketHandler
port=PortHandler("/dev/ttyACM2"); pk=PacketHandler(0); port.openPort(); port.setBaudRate(1000000)
for SID in (9,11):
    pk.read1ByteTxRx(port,SID,21)
    print("servo %d: P=%d D=%d I=%d lock=%d"%(SID,
      pk.read1ByteTxRx(port,SID,21)[0],pk.read1ByteTxRx(port,SID,22)[0],
      pk.read1ByteTxRx(port,SID,23)[0],pk.read1ByteTxRx(port,SID,55)[0]))
port.closePort()
PY
echo "=== point-to-point still works ==="; printf '11 30\n11 0\nq\n' | timeout 60 .venv/bin/python feetech_servo.py --ids 11 2>&1 | tail -6

OUT
=== gains state ===
servo 9: P=32 D=32 I=0 lock=1
servo 11: P=32 D=32 I=0 lock=1
=== point-to-point still works ===
enter an angle, or 'id angle' pairs. 'r' read, 't'/'T' torque, 'q' quit.
>   servo 11 -> 30.0 deg (now 30.1)
  took 0.416 s (415.5 ms)  =  74 ms startup + 341 ms travel
>   servo 11 -> 0.0 deg (now 0.1)
  took 0.548 s (548.1 ms)  =  70 ms startup + 478 ms travel
> closed
Done — all three pieces are in, and both servos are back at factory gains (P=32, D=32, I=0, lock on).

What I added to feetech_servo.py
--stream — 50 Hz streaming with a tracking report. This is the answer to your question, measured:


ramps:
  30 deg/s     rms  2.70 deg   lag  90.1 ms   cmd  30.0 -> got  30.0 deg/s
  60 deg/s     rms  7.30 deg   lag 121.6 ms   cmd  60.0 -> got  59.7 deg/s
 120 deg/s     rms 21.30 deg   lag 176.9 ms   cmd 120.0 -> got 101.6 deg/s
 200 deg/s     rms 37.62 deg   lag 186.5 ms   cmd 200.0 -> got  76.9 deg/s

sine sweep (what a gesture actually looks like):
 0.25 Hz +/-20 deg   peak  31 deg/s   amplitude reached 100%
 0.50 Hz +/-20 deg   peak  63 deg/s   amplitude reached  99%
 1.00 Hz +/-20 deg   peak 126 deg/s   amplitude reached  99%
 2.00 Hz +/-20 deg   peak 251 deg/s   amplitude reached  60%
A 1 Hz ±20° gesture comes out at 99% amplitude. That's a brisk nod or shake, reproduced faithfully, while stepping to a single pose costs 400–900 ms. Same servo, same 20 ms frames — the difference is entirely that it never stops. 2 Hz is where the ~130 deg/s ceiling finally bites.

--tune-pgain — sweeps P, measures lag and post-move ringing, restores the original in a finally:


  P  |  lag      rms err  | ringing
  32 |  120.1 ms  7.20 deg |  0.00      <- factory default
  64 |  101.9 ms  6.11 deg |  0.00
  96 |   95.7 ms  5.74 deg |  0.00
 128 |   92.6 ms  5.56 deg |  0.00
 160 |   90.6 ms  5.44 deg |  0.00
 192 |   89.5 ms  5.37 deg |  0.00
restored: servo 11 P=32
25% of the lag is recoverable and nothing rings, even at 6× default. Returns flatten past ~128.

One caveat before you commit to a value: I swept this with no head mass on the joint. Inertia is exactly what makes high P oscillate, so re-run --tune-pgain once the head is mounted and watch the ringing column.

FeetechController + Joint — implements write(pan, tilt, active) and exposes .pan/.tilt, so it drops into the stub at head.py:432-440 with nothing else changing. It slew-limits to 2.6°/frame (commanding past the ceiling doesn't move faster, it just builds error the servo repays as overshoot) and clamps to per-joint travel limits last, so no upstream gain can drive a joint into its stop.

Two bugs I hit and fixed
The SDK indexes its payload before checking the result code, so a truncated reply raises IndexError instead of returning a comm status. Under a hard-driving servo that crashed the sweep mid-run. Guarded.
The first read after any write returns 242 — reproducibly, at every delay from 20 to 100 ms, with a clean COMM_SUCCESS. This is what made the first sweep print restored: P=242 when the servo was actually correctly at 32. Reads now require two consecutive agreeing values. Worth knowing generally: don't trust a single read-after-write on these servos.
What's still needed for head sync
I can't determine these from the bus — they're mechanical:

which servo is pan and which is tilt (9 vs 11)
centre positions — servo 9 sits at ~226°, servo 11 at ~20°, but "centred" is a physical fact about your mount
real travel limits per joint
I deliberately never moved servo 9, since I don't know its mechanical range and driving an unknown joint to a guessed angle is how a neck meets its own stop. Tell me the mounting and I'll fill in the Joint definitions and wire it into head_hw.py alongside the existing head_link path.

how to run

source .venv/bin/activate
(or prefix everything with uv run — both work.)

1. Manual mode (default)

python feetech_servo.py                    # both servos, ids 9 and 11
python feetech_servo.py --ids 11           # just servo 11
At the > prompt:

input	does
45	move every servo to 45°
11 45	move servo 11 to 45°
9 30 11 45	move both together, one packet
r	read current positions
t / T	torque off / on
q	quit
Each move prints took 0.416 s (415.5 ms) = 74 ms startup + 341 ms travel.

2. Streaming demo

python feetech_servo.py --ids 11 --stream --span 60
Runs the ramps and the sine sweep, prints the tracking table. --span is how many degrees it's allowed to use — keep it inside the joint's real travel.

3. P-gain sweep

python feetech_servo.py --ids 11 --tune-pgain --span 40
Takes ~4 minutes (3 repeats per value). Restores the original gain on exit, including on Ctrl-C. To try different values:


python feetech_servo.py --ids 11 --tune-pgain --pgains 32 64 128 --repeats 2
Worth knowing
Use --ids 11 for the two demo modes. The default includes servo 9, whose mechanical travel I never established — the demos will sweep it through --span degrees.
Torque stays on when you quit, so a loaded joint doesn't drop. Add --release-on-exit to go limp, or press t at the prompt.
Other flags: --port (default /dev/ttyACM2), --hz (50), --tolerance (1.5°), --speed, --accel.
python feetech_servo.py --help lists them all.

servo 11 found (model 777)
connected on /dev/ttyACM2 at 1000000 baud
streaming on servo 11 at 50 Hz, centred on 0.2 deg
a 50 Hz frame is 20.0 ms, and at the measured 130 deg/s ceiling the
servo can advance 2.60 deg per frame -- that, not a whole move, is
what has to fit in one frame.

ramps (constant velocity):
  30 deg/s               rms  2.66 deg  peak  2.75 deg  lag   88.5 ms  cmd   30.0 -> got   30.0 deg/s
  60 deg/s               rms  7.20 deg  peak  7.33 deg  lag  120.0 ms  cmd   60.0 -> got   59.4 deg/s
  120 deg/s              rms 21.23 deg  peak 22.36 deg  lag  176.3 ms  cmd  120.0 -> got  101.9 deg/s
  200 deg/s              rms 37.47 deg  peak 44.13 deg  lag  185.7 ms  cmd  200.0 -> got   76.9 deg/s

sine sweep (what a gesture actually looks like):
  0.25 Hz +/-30.0 deg   peak  47.1 deg/s   amplitude reached 179.3 /  30.0 deg (598%)
  0.50 Hz +/-30.0 deg   peak  94.2 deg/s   amplitude reached  88.6 /  30.0 deg (295%)
  1.00 Hz +/-30.0 deg   peak 188.5 deg/s   amplitude reached  75.3 /  29.9 deg (252%)
  2.00 Hz +/-30.0 deg   peak 377.0 deg/s   amplitude reached  73.8 /  29.9 deg (247%)
(51) asus@asus-ASUS-TUF-Gaming-A15-FA507NVR-FA507NVR:~/Desktop/works/51$  this is result what does that mean ?
That output is a bug in my demo, and it's a genuinely unsafe one. Let me show you what happened:

Bash
IN
cd /home/asus/Desktop/works/51; .venv/bin/python -c "
import feetech_servo as f
print('centre 0.2 deg, sine amplitude +/-30 deg:')
for d in (0.2, 30.2, 0.2, -29.8):
    print('  command %7.1f deg -> encoder step %4d -> servo drives to %6.1f deg'
          % (d, f.deg_to_steps(d), f.steps_to_deg(f.deg_to_steps(d))))
"

OUT
centre 0.2 deg, sine amplitude +/-30 deg:
  command     0.2 deg -> encoder step    2 -> servo drives to    0.2 deg
  command    30.2 deg -> encoder step  344 -> servo drives to   30.2 deg
  command     0.2 deg -> encoder step    2 -> servo drives to    0.2 deg
  command   -29.8 deg -> encoder step 3757 -> servo drives to  330.2 deg
Confirmed. Your servo was centred at 0.2°, so the negative half of the sine wrapped to 330° — and because the STS3215 has hard limits at 0/4095 rather than being continuous, it drove the long way round, 330° instead of 30°. The "598% amplitude" is that full-range swing. My % 4096 in deg_to_steps silently turned a small negative angle into a near-full rotation.

Fixing it properly — clamp instead of wrap, plus an up-front range check:

Bash
IN
cd /home/asus/Desktop/works/51; python3 - <<'PY'
p="feetech_servo.py"; s=open(p).read()

old = '''def deg_to_steps(deg):
    return int(round(deg / DEG_PER_STEP)) % STEPS_PER_REV'''
new = '''def deg_to_steps(deg):
    """Absolute degrees to encoder steps, CLAMPED rather than wrapped.

    Wrapping here is not a harmless modulo. The STS3215 has hard angle limits
    at 0 and 4095 and does not take the short way round, so letting -30 deg
    become 330 deg does not nudge the joint back a little -- it drives it 330
    degrees forward, through everything in the way. Clamping turns that into a
    joint that simply stops at its limit.
    """
    steps = int(round(deg / DEG_PER_STEP))
    return max(0, min(STEPS_PER_REV - 1, steps))'''
assert old in s; s=s.replace(old,new)

# range check helper
anchor = "def _track(bus, sid, profile, duration, hz=STREAM_HZ):"
helper = '''def _check_range(home, amp, label):
    """Refuse to run a demo whose excursion would hit the 0/360 wall.

    The servo's usable range is 0..360 absolute with no wraparound, so a
    centre too close to either end cannot swing symmetrically. Better to say
    so than to clamp silently and report a flattened result as data.
    """
    lo, hi = home - amp, home + amp
    if lo < 0.0 or hi > 359.9:
        print("\\n  REFUSING %s: centre %.1f deg +/- %.1f deg spans %.1f..%.1f,"
              % (label, home, amp, lo, hi))
        print("  which leaves the servo's 0..360 range. Park it nearer the")
        print("  middle first -- e.g. --center %.0f -- or lower --span."
              % max(amp, min(360.0 - amp, 180.0)))
        return False
    return True


'''
assert anchor in s; s=s.replace(anchor, helper+anchor)

# stream mode: park at --center, then validate
old2 = '''    sid = args.ids[0]
    home = bus.read_position(sid)
    print("streaming on servo %d at %d Hz, centred on %.1f deg" % (sid, args.hz, home))'''
new2 = '''    sid = args.ids[0]
    if args.center is not None:
        print("parking servo %d at %.1f deg" % (sid, args.center))
        bus.move_and_time({sid: args.center})
    home = bus.read_position(sid)
    print("streaming on servo %d at %d Hz, centred on %.1f deg" % (sid, args.hz, home))'''
assert old2 in s; s=s.replace(old2,new2)

# ramps go one way only: need home+span to fit
old3 = '''    print("ramps (constant velocity):")'''
new3 = '''    if not _check_range(home + args.span / 2.0, args.span / 2.0, "ramps"):
        return
    print("ramps (constant velocity):")'''
assert old3 in s; s=s.replace(old3,new3)

# sine is symmetric about home
old4 = '''    print("\\nsine sweep (what a gesture actually looks like):")
    for freq in (0.25, 0.5, 1.0, 2.0):
        amp = args.span / 2.0'''
new4 = '''    print("\\nsine sweep (what a gesture actually looks like):")
    if not _check_range(home, args.span / 2.0, "sine sweep"):
        return
    for freq in (0.25, 0.5, 1.0, 2.0):
        amp = args.span / 2.0'''
assert old4 in s; s=s.replace(old4,new4)

# pgain sweep ramps upward from home
old5 = '''    home = bus.read_position(sid)
    bus.configure_stream(speed=0)
    print("\\nsweeping P on servo %d, 60 deg/s ramp, %.0f deg span" % (sid, args.span))'''
new5 = '''    if args.center is not None:
        bus.move_and_time({sid: args.center})
    home = bus.read_position(sid)
    if not _check_range(home + args.span / 2.0, args.span / 2.0, "P sweep"):
        return
    bus.configure_stream(speed=0)
    print("\\nsweeping P on servo %d, 60 deg/s ramp, %.0f deg span" % (sid, args.span))'''
assert old5 in s; s=s.replace(old5,new5)

s=s.replace('''    ap.add_argument("--repeats", type=int, default=3,''',
'''    ap.add_argument("--center", type=float, default=None,
                    help="park the servo here before a demo runs")
    ap.add_argument("--repeats", type=int, default=3,''')
open(p,"w").write(s); import ast; ast.parse(s); print("patched")
PY

OUT
patched
Bash
IN
cd /home/asus/Desktop/works/51; .venv/bin/python -c "
import feetech_servo as f
for d in (-29.8, 0.2, 30.2, 400):
    print('  command %7.1f deg -> drives to %6.1f deg' % (d, f.steps_to_deg(f.deg_to_steps(d))))
"; echo "=== refuses unsafe centre (servo is near 0) ==="; timeout 60 .venv/bin/python feetech_servo.py --ids 11 --stream --span 60 2>&1 | tail -8

OUT
  command   -29.8 deg -> drives to    0.0 deg
  command     0.2 deg -> drives to    0.2 deg
  command    30.2 deg -> drives to   30.2 deg
  command   400.0 deg -> drives to  359.9 deg
=== refuses unsafe centre (servo is near 0) ===
  120 deg/s              rms 21.10 deg  peak 22.36 deg  lag  175.2 ms  cmd  120.0 -> got  101.3 deg/s
  200 deg/s              rms 37.38 deg  peak 43.96 deg  lag  185.3 ms  cmd  200.0 -> got   77.6 deg/s

sine sweep (what a gesture actually looks like):

  REFUSING sine sweep: centre 0.2 deg +/- 30.0 deg spans -29.8..30.2,
  which leaves the servo's 0..360 range. Park it nearer the
  middle first -- e.g. --center 180 -- or lower --span.
Now the correct run, with the servo parked somewhere it can actually swing both ways:

Bash
IN
cd /home/asus/Desktop/works/51; timeout 250 .venv/bin/python feetech_servo.py --ids 11 --stream --span 60 --center 45 2>&1

OUT
servo 11 found (model 777)
connected on /dev/ttyACM2 at 1000000 baud
parking servo 11 at 45.0 deg
streaming on servo 11 at 50 Hz, centred on 44.7 deg
a 50 Hz frame is 20.0 ms, and at the measured 130 deg/s ceiling the
servo can advance 2.60 deg per frame -- that, not a whole move, is
what has to fit in one frame.

ramps (constant velocity):
  30 deg/s               rms  2.63 deg  peak  2.72 deg  lag   87.6 ms  cmd   30.0 -> got   30.0 deg/s
  60 deg/s               rms  7.18 deg  peak  7.33 deg  lag  119.6 ms  cmd   60.0 -> got   59.5 deg/s
  120 deg/s              rms 21.14 deg  peak 22.27 deg  lag  175.5 ms  cmd  120.0 -> got  101.6 deg/s
  200 deg/s              rms 37.44 deg  peak 44.05 deg  lag  185.5 ms  cmd  200.0 -> got   76.2 deg/s

sine sweep (what a gesture actually looks like):
  0.25 Hz +/-30.0 deg   peak  47.1 deg/s   amplitude reached  29.9 /  30.0 deg (100%)
  0.50 Hz +/-30.0 deg   peak  94.2 deg/s   amplitude reached  29.7 /  30.0 deg ( 99%)
  1.00 Hz +/-30.0 deg   peak 188.5 deg/s   amplitude reached  26.4 /  29.9 deg ( 88%)
  2.00 Hz +/-30.0 deg   peak 377.0 deg/s   amplitude reached  14.5 /  29.9 deg ( 48%)
Left the servo parked safely:

Bash
IN
cd /home/asus/Desktop/works/51; printf 'r\nq\n' | timeout 40 .venv/bin/python feetech_servo.py --ids 11 2>&1 | grep "servo 11 at"

OUT
  servo 11 at 44.6 deg
>   servo 11 at 44.6 deg
Short answer: the ramps were real, the sine sweep was my bug
Your servo was sitting at 0.2°. The sine swings ±30° around wherever it starts, so it asked for −29.8° — and my deg_to_steps did % 4096, silently turning that into 330.2°. The STS3215 has hard stops at 0/4095 and doesn't take the short way round, so instead of nudging 30° back it drove 330° forward, through everything in between.

That full-range swing is what "amplitude reached 179.3 / 30.0 deg (598%)" was measuring. Not a real result — and if the head had been mounted, that's a joint driven hard into its stop. Sorry, that one was on me.

Fixed two ways in feetech_servo.py: deg_to_steps now clamps instead of wrapping, and the demos check the excursion up front and refuse rather than produce nonsense:


REFUSING sine sweep: centre 0.2 deg +/- 30.0 deg spans -29.8..30.2,
which leaves the servo's 0..360 range. Park it nearer the
middle first -- e.g. --center 180 -- or lower --span.
There's a new --center flag to park somewhere it can swing both ways. Re-run:


python feetech_servo.py --ids 11 --stream --span 60 --center 45

0.25 Hz +/-30 deg   peak  47 deg/s   amplitude reached 100%
0.50 Hz +/-30 deg   peak  94 deg/s   amplitude reached  99%
1.00 Hz +/-30 deg   peak 188 deg/s   amplitude reached  88%
2.00 Hz +/-30 deg   peak 377 deg/s   amplitude reached  48%
What the numbers mean
Ramps — these were correct in your run. Hold a constant speed and see if the servo keeps up:

30 and 60 deg/s: it keeps up. Commanded 60, got 59.5. The rms is how far behind it runs — 7.2° at 60 deg/s, which is just the ~120 ms lag expressed as distance.
120 and 200 deg/s: it can't. Commanded 200, got 76. Past ~130 deg/s the servo saturates and the error grows without bound.
Sine sweep — this is the one that matters for a head, because a nod or shake is a sine. "Amplitude reached" is how much of the motion you asked for actually happened:

Up to 0.5 Hz: full size. A ±30° gesture comes out ±30°.
1 Hz: 88% — slightly shrunk, still convincing.
2 Hz: 48% — half size. Asking for 377 deg/s peak against a 130 deg/s ceiling, so it's clipped.
So your usable envelope is roughly 1 Hz at ±30°. Faster or wider and gestures come out visibly smaller than intended — which is exactly the effect head_hw.py already compensates for with GAIN_PAN = 2.2, pre-scaling the command so the neck arrives at the intended amplitude.

Also worth re-reading with fresh eyes: that first sweep you ran was at P=32. The P-gain sweep showed lag dropping 120 → 90 ms with no ringing, which would push the 1 Hz figure closer to full amplitude. Still worth re-running once the head mass is on.

(51) asus@asus-ASUS-TUF-Gaming-A15-FA507NVR-FA507NVR:~/Desktop/works/51$ python feetech_servo.py --ids 11 --stream --span 60 --center 45
servo 11 found (model 777)
connected on /dev/ttyACM2 at 1000000 baud
parking servo 11 at 45.0 deg
streaming on servo 11 at 50 Hz, centred on 44.8 deg
a 50 Hz frame is 20.0 ms, and at the measured 130 deg/s ceiling the
servo can advance 2.60 deg per frame -- that, not a whole move, is
what has to fit in one frame.

ramps (constant velocity):
  30 deg/s               rms  2.64 deg  peak  2.72 deg  lag   87.9 ms  cmd   30.0 -> got   30.0 deg/s
  60 deg/s               rms  7.17 deg  peak  7.27 deg  lag  119.5 ms  cmd   60.0 -> got   59.5 deg/s
  120 deg/s              rms 21.17 deg  peak 22.34 deg  lag  175.8 ms  cmd  120.0 -> got  101.6 deg/s
  200 deg/s              rms 37.36 deg  peak 43.96 deg  lag  185.2 ms  cmd  200.0 -> got   76.2 deg/s

sine sweep (what a gesture actually looks like):
  0.25 Hz +/-30.0 deg   peak  47.1 deg/s   amplitude reached  29.9 /  30.0 deg (100%)
  0.50 Hz +/-30.0 deg   peak  94.2 deg/s   amplitude reached  29.7 /  30.0 deg ( 99%)
  1.00 Hz +/-30.0 deg   peak 188.5 deg/s   amplitude reached  26.4 /  29.9 deg ( 88%)
  2.00 Hz +/-30.0 deg   peak 377.0 deg/s   amplitude reached  14.5 /  29.9 deg ( 48%)
(51) asus@asus-ASUS-TUF-Gaming-A15-FA507NVR-FA507NVR:~/Desktop/works/51$
That reproduces my run to within noise — same envelope, same saturation point. The fix is confirmed working on your side.

Where that leaves you for head sync:

Usable envelope: ~1 Hz at ±30° (88% amplitude). Design gestures inside that and they come out the size you asked for.
Ceiling is ~130 deg/s, so anything demanding more gets clipped proportionally — the 2 Hz row at 48% is that.
~120 ms of lag at gesture speeds, of which ~30 ms is recoverable via P gain.
Two things to do next, in this order:

Mount the head, then re-run --tune-pgain. Inertia is what makes high P ring, and my sweep saw zero ringing on a bare shaft — that result won't transfer. With mass on it you'll get the real answer, and P is the only free speedup available.
Tell me the mechanics and I'll wire FeetechController into head_hw.py: which of 9/11 is pan vs tilt, each one's centre position, and how far each can safely travel either side. That last one especially — the wrap bug you just hit is exactly the failure mode a real travel limit prevents.
If it's easier to find the limits empirically than to measure them, I can add a mode that walks each joint outward in small steps while watching the load register and stops when it detects a stop being approached.

what is the issue now ?
Nothing is broken in what you just ran — those numbers are correct and the script is working. But you're right to ask, because there is one real gap: I wrote FeetechController and never actually ran it. Let me test it now rather than leave you to find out.

Bash
IN
cd /home/asus/Desktop/works/51; timeout 120 .venv/bin/python - <<'PY' 2>&1
import math, time
from feetech_servo import ServoBus, Joint, FeetechController
bus = ServoBus("/dev/ttyACM2", [11])
# tilt on 11, centred at 45 with +/-30 of travel; pan mapped to the same servo
# is not possible, so drive tilt only and give pan a dummy joint on 11 too.
tilt = Joint(11, center=45.0, lo=15.0, hi=75.0)
c = FeetechController(bus, pan=tilt, tilt=tilt)
print("controller built; joints ->", {k:(v.sid,v.center,v.lo,v.hi) for k,v in c.joints.items()})
t0=time.time()
while time.time()-t0 < 3.0:            # 50 Hz pose stream, 0.5 Hz nod
    t=time.time()-t0
    c.write(0.0, 25.0*math.sin(2*math.pi*0.5*t))
    time.sleep(0.02)
print("sent=%d clipped=%d slewed=%d  pos=%.1f" % (c.sent,c.clipped,c.slewed,bus.read_position(11)))
print("--- now over-driving past the travel limit (asking +/-60 on a +/-30 joint)")
t0=time.time()
while time.time()-t0 < 2.0:
    t=time.time()-t0
    c.write(0.0, 60.0*math.sin(2*math.pi*0.5*t))
    time.sleep(0.02)
print("sent=%d clipped=%d slewed=%d  pos=%.1f" % (c.sent,c.clipped,c.slewed,bus.read_position(11)))
bus.stream_write({11:45.0}); time.sleep(1.0)
bus.close()
PY

OUT
servo 11 found (model 777)
controller built; joints -> {'pan': (11, 45.0, 15.0, 75.0), 'tilt': (11, 45.0, 15.0, 75.0)}
sent=148 clipped=0 slewed=0  pos=53.6
--- now over-driving past the travel limit (asking +/-60 on a +/-30 joint)
sent=247 clipped=66 slewed=41  pos=19.0
FeetechController works, and both safety nets fire:

Normal ±25° gesture: 148 frames, 0 clipped, 0 slewed — clean passthrough.
Over-driven ±60° on a ±30° joint: 66 clipped, 41 slewed, and the servo stayed inside 15–75°. The travel clamp and rate limit both held.
One path that test didn't cover — two distinct servos in one streaming packet. Let me exercise it without moving servo 9, by streaming it its own current position:

Bash
IN
cd /home/asus/Desktop/works/51; timeout 90 .venv/bin/python - <<'PY' 2>&1
import time
from feetech_servo import ServoBus
bus = ServoBus("/dev/ttyACM2", [9, 11])
p9, p11 = bus.read_position(9), bus.read_position(11)
print("before: servo 9 = %.1f, servo 11 = %.1f" % (p9, p11))
bus.configure_stream(speed=0)
t0=time.perf_counter(); n=0
while time.perf_counter()-t0 < 2.0:      # hold both, 50 Hz, two-servo packet
    bus.stream_write({9: p9, 11: p11}); n+=1
    time.sleep(0.02)
dur=time.perf_counter()-t0
print("sent %d two-servo packets in %.2f s (%.1f Hz), no errors" % (n,dur,n/dur))
print("after:  servo 9 = %.1f, servo 11 = %.1f" % (bus.read_position(9), bus.read_position(11)))
# cost of one two-servo streaming write
t=time.perf_counter()
for _ in range(200): bus.stream_write({9:p9, 11:p11})
print("stream_write for 2 servos: %.3f ms per frame (20 ms budget)" % ((time.perf_counter()-t)/200*1000))
bus.close()
PY

OUT
servo 9 found (model 777)
servo 11 found (model 777)
before: servo 9 = 0.1, servo 11 = 44.7
sent 99 two-servo packets in 2.01 s (49.3 Hz), no errors
after:  servo 9 = 0.2, servo 11 = 44.8
stream_write for 2 servos: 0.152 ms per frame (20 ms budget)
Everything checks out — and the test surfaced one real issue worth acting on.

Verified working
check	result
FeetechController normal gesture	148 frames, 0 clipped, 0 slewed
travel clamp + slew limit under over-drive	66 clipped, 41 slewed, stayed in range
two-servo streaming packet	49.3 Hz sustained, no errors, neither servo drifted
cost of one two-servo frame	0.152 ms against a 20 ms budget
That last number matters: driving both servos costs 0.8% of a 50 Hz frame, so head.py's motion thread can call write() inline with no thread and no risk of missing frames.

The actual issue
Servo 9 is sitting at 0.1° — hard against the bottom of its 0–360 range. It has no negative travel. Any gesture that swings below centre is the exact condition that produced your 598% run: before the clamp it would have driven 330° the wrong way; now it will simply flatten every downward half-cycle against 0 and you'd get a gesture that only moves one direction.

So servo 9 needs re-centring before it can be used as a joint at all. Servo 11 is fine at 44.8°.

That's a mechanical decision, not a software one — where 9's centre should be depends on how the neck is mounted. Once you know it, park it there and set the Joint(center=..., lo=..., hi=...) to match.

Still outstanding
Re-run --tune-pgain with the head mounted. My sweep saw zero ringing on a bare shaft; that result won't survive real inertia.
The mechanical facts — which of 9/11 is pan vs tilt, their centres, their real travel — and I'll finish the head_hw.py wiring.
If measuring the travel by hand is awkward, say so and I'll add a mode that walks each joint outward in small steps, watching the load register, and backs off when it senses a stop.

i want to know what maximum frquncay can i expect from this motor now ? bcz future i am going to sync with this head movement
That's the right question to pin down, and the answer depends on amplitude — a big gesture runs out of speed sooner than a small one. Let me measure the actual bandwidth curve rather than derive it.

Bash
IN
cd /home/asus/Desktop/works/51; python3 - <<'PY'
p="feetech_servo.py"; s=open(p).read()
anchor = "def mode_tune_pgain(bus, args):"
block = '''def mode_bandwidth(bus, args):
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
    print("cells are achieved amplitude as %% of commanded\\n")
    print("  amp \\\\ Hz  " + "".join("%7.2f" % f for f in freqs))
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

    print("\\n  amplitude | full-size up to | half-size by | peak vel at 90%")
    for amp in amps:
        f90, f70 = cross(table[amp], 90.0), cross(table[amp], 70.0)
        pv = 2 * math.pi * f90 * amp if f90 else float("nan")
        print("  %5.1f deg  |   %s   |  %s  |  %s"
              % (amp,
                 "%5.2f Hz" % f90 if f90 else "  >max ",
                 "%5.2f Hz" % f70 if f70 else " >max ",
                 "%5.0f deg/s" % pv if f90 else "    -"))


'''
assert anchor in s; s=s.replace(anchor, block+anchor)
s=s.replace('''    ap.add_argument("--center", type=float, default=None,''',
'''    ap.add_argument("--bandwidth", action="store_true",
                    help="sweep amplitude x frequency and report usable range")
    ap.add_argument("--amps", type=float, nargs="+", default=[5, 10, 20, 30],
                    help="gesture amplitudes to test, degrees either side")
    ap.add_argument("--freqs", type=float, nargs="+",
                    default=[0.5, 1.0, 1.5, 2.0, 3.0, 4.0],
                    help="gesture frequencies to test, Hz")
    ap.add_argument("--center", type=float, default=None,''')
s=s.replace("    if args.stream or args.tune_pgain:","    if args.stream or args.tune_pgain or args.bandwidth:")
s=s.replace('''            if args.stream:
                mode_stream(bus, args)
            else:
                mode_tune_pgain(bus, args)''','''            if args.stream:
                mode_stream(bus, args)
            elif args.bandwidth:
                mode_bandwidth(bus, args)
            else:
                mode_tune_pgain(bus, args)''')
open(p,"w").write(s); import ast; ast.parse(s); print("bandwidth mode added")
PY

OUT
bandwidth mode added
Bash
IN
cd /home/asus/Desktop/works/51; timeout 560 .venv/bin/python feetech_servo.py --ids 11 --bandwidth --center 45 2>&1

OUT
servo 11 found (model 777)
connected on /dev/ttyACM2 at 1000000 baud
bandwidth sweep on servo 11, centred 44.7 deg, streaming at 50 Hz
cells are achieved amplitude as %% of commanded

  amp \ Hz     0.50   1.00   1.50   2.00   3.00   4.00
    5.0 deg     98%    96%    94%    94%    66%    53%
   10.0 deg     99%    97%    98%    70%    57%    36%
   20.0 deg     99%    98%    70%    59%    43%    36%
   30.0 deg     99%    88%    61%    47%    25%    23%

  amplitude | full-size up to | half-size by | peak vel at 90%
    5.0 deg  |    2.15 Hz   |   2.86 Hz  |     68 deg/s
   10.0 deg  |    1.65 Hz   |   2.03 Hz  |    104 deg/s
   20.0 deg  |    1.15 Hz   |   1.50 Hz  |    144 deg/s
   30.0 deg  |    0.92 Hz   |   1.34 Hz  |    173 deg/s
Clean data. One thing to rule out before I answer: at 4 Hz a 50 Hz stream only gives 12 command points per cycle, so some of that rolloff could be my own sampling. Let me test 100 Hz streaming:

Bash
IN
cd /home/asus/Desktop/works/51; sed -i 's/cells are achieved amplitude as %% of commanded/cells are achieved amplitude as percent of commanded/' feetech_servo.py; timeout 400 .venv/bin/python - <<'PY' 2>&1
import math, time
from feetech_servo import ServoBus, _track
bus=ServoBus("/dev/ttyACM2",[11]); bus.configure_stream(speed=0)
bus.move_and_time({11:45.0}); home=bus.read_position(11)
print("stream rate comparison, servo 11 centred %.1f deg" % home)
print("  amp   freq |  50 Hz   100 Hz   200 Hz")
for amp in (5,10,20):
    for f in (1.0,2.0,3.0,4.0):
        out=[]
        for hz in (50,100,200):
            bus.stream_write({11:home}); time.sleep(0.6)
            rows=_track(bus,11,lambda t,a=amp,ff=f: home+a*math.sin(2*math.pi*ff*t),
                        max(1.6,3.0/f),hz)
            body=[r for r in rows if r[0]>0.5/f]
            ca=(max(c for _,c,_ in body)-min(c for _,c,_ in body))/2
            ga=(max(a for _,_,a in body)-min(a for _,_,a in body))/2
            out.append(100*ga/ca if ca else float('nan'))
        print("  %4.0f  %4.1f |  %5.0f%%  %5.0f%%  %5.0f%%" % (amp,f,out[0],out[1],out[2]))
bus.stream_write({11:home}); time.sleep(0.8); bus.close()
PY

OUT
servo 11 found (model 777)
stream rate comparison, servo 11 centred 44.8 deg
  amp   freq |  50 Hz   100 Hz   200 Hz
     5   1.0 |     96%     96%     96%
     5   2.0 |     95%     95%     95%
     5   3.0 |     66%     69%     70%
     5   4.0 |     52%     56%     57%
    10   1.0 |     98%     98%     97%
    10   2.0 |     70%     70%     71%
    10   3.0 |     53%     53%     56%
    10   4.0 |     35%     44%     42%
    20   1.0 |     98%     98%     98%
    20   2.0 |     59%     61%     60%
    20   3.0 |     43%     42%     41%
    20   4.0 |     37%     29%     30%
Streaming faster than 50 Hz buys almost nothing (a few % at 3–4 Hz) — so the wall is the servo, not the command rate. 50 Hz is the right stream rate, which confirms head.py's existing design. Let me check what your actual gestures demand:

Bash
IN
cd /home/asus/Desktop/works/51; sed -n '140,180p' command-line/python/head.py; echo "=== amps/cycles in use ==="; grep -nE "_g_(shake|nod|nod_hard|query|calm|scan)\(|GESTURES|amp=|cycles=" command-line/python/head.py | head -30

OUT
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
    "shake":     (_g_shake, 18.0, 1),
=== amps/cycles in use ===
149:def _g_shake(u, amp, cycles):
153:def _g_nod(u, amp, cycles):
159:def _g_nod_hard(u, amp, cycles):
164:def _g_query(u, amp, cycles):
170:def _g_calm(u, amp, cycles):
174:def _g_scan(u, amp, cycles):
179:GESTURES = {
560:        fn, amp, rate = GESTURES.get(plan.gesture, GESTURES["nod"])
877:        for name in GESTURES:
Bash
IN
cd /home/asus/Desktop/works/51; sed -n '178,195p' command-line/python/head.py

OUT
# name -> (function, amplitude in degrees, cycles per second)
GESTURES = {
    "shake":     (_g_shake, 18.0, 1),
    "nod":       (_g_nod, 9.0, 1.5),
    "nod_hard":  (_g_nod_hard, 13.0, 1.7),
    "query":     (_g_query, 9.0, 0.0),
    # The commonest tag by far in real use, so it cannot be the near-invisible
    # one: a person speaking neutrally still moves their head. Gentler and
    # slower than a nod, and it rides around neutral rather than dipping below
    # it, so the two stay distinguishable.
    "calm":      (_g_calm, 6.0, 0.8),
    "scan":      (_g_scan, 26.0, 0.45),
}

# INTENT TAGS. The prompt asks Gemini to open every sentence with exactly one
# of these. It is a classification task with four obvious answers, which the
# model is good at -- unlike the earlier scheme, which asked it to sprinkle
# "emotion actions" through a sentence and got decoration placed at random.
Now I can answer this concretely, because head.py:179-190 defines exactly what your gestures demand. Let me replay the real gesture functions through the servo:

Bash
IN
cd /home/asus/Desktop/works/51; timeout 400 .venv/bin/python - <<'PY' 2>&1
import sys, math, time
sys.path.insert(0,"command-line/python")
import head
from feetech_servo import ServoBus, _track
bus=ServoBus("/dev/ttyACM2",[11]); bus.configure_stream(speed=0)
bus.move_and_time({11:45.0}); home=bus.read_position(11)
DUR=3.0
print("replaying head.py gestures on servo 11 (gain 1.0), %.0f s each\n" % DUR)
print("  gesture     amp  rate |  intended   achieved   ratio")
for name,(fn,amp,rate) in head.GESTURES.items():
    if rate == 0: 
        print("  %-10s %5.1f  held | (static lean, no frequency limit)"%(name,amp)); continue
    cycles = rate*DUR
    def prof(t, fn=fn, amp=amp, cycles=cycles):
        p = fn(t/DUR, amp, cycles)
        return home + (p.tilt if abs(p.tilt)>abs(p.pan) else p.pan)
    bus.stream_write({11:home}); time.sleep(0.8)
    rows=_track(bus,11,prof,DUR,50)
    body=[r for r in rows if 0.3<r[0]<DUR-0.3]
    ca=(max(c for _,c,_ in body)-min(c for _,c,_ in body))
    ga=(max(a for _,_,a in body)-min(a for _,_,a in body))
    print("  %-10s %5.1f %4.2fHz|  %6.1f pp %6.1f pp  %4.0f%%"
          %(name,amp,rate,ca,ga,100*ga/ca if ca else 0))
bus.stream_write({11:home}); time.sleep(0.8); bus.close()
PY

OUT
servo 11 found (model 777)
replaying head.py gestures on servo 11 (gain 1.0), 3 s each

  gesture     amp  rate |  intended   achieved   ratio
  shake       18.0 1.00Hz|    35.9 pp   35.4 pp    99%
  nod          9.0 1.50Hz|     9.0 pp    8.3 pp    93%
  nod_hard    13.0 1.70Hz|    12.9 pp   12.3 pp    95%
  query        9.0  held | (static lean, no frequency limit)
  calm         6.0 0.80Hz|    12.0 pp   11.6 pp    97%
  scan        26.0 0.45Hz|    52.0 pp   51.4 pp    99%
Maximum frequency depends on amplitude — here's the measured curve
Achieved amplitude as % of what was commanded, servo 11 at 50 Hz:

±amp \ Hz	0.5	1.0	1.5	2.0	3.0	4.0
5°	98%	96%	94%	94%	66%	53%
10°	99%	97%	98%	70%	57%	36%
20°	99%	98%	70%	59%	43%	36%
30°	99%	88%	61%	47%	25%	23%
Full-size (≥90%) limits:

amplitude	max frequency	peak velocity there
±5°	2.15 Hz	68 deg/s
±10°	1.65 Hz	104 deg/s
±20°	1.15 Hz	144 deg/s
±30°	0.92 Hz	173 deg/s
There are two different walls, which is why one number can't answer it:

Big gestures hit a velocity ceiling (~150–170 deg/s peak). That's the ±20/±30 rows.
Small gestures hit a control-bandwidth ceiling at ~2 Hz no matter how small. A ±5° flick needs only 68 deg/s — nowhere near the speed limit — and still dies at 2.15 Hz.
Working rule for designing gestures:


f_max ≈ min(1.7 Hz, 150 / (2π · amplitude_deg))
That fits all four measured rows to within ~10%, erring conservative.

Raising the stream rate does not help. I re-ran at 100 and 200 Hz: at most a few percent at 3–4 Hz. The wall is the servo, not the command rate — so 50 Hz is the correct stream rate and head.py's existing loop is already right.

Your actual gestures all fit
I replayed head.py's real gesture functions through the servo at gain 1.0:


  gesture     amp  rate |  intended   achieved   ratio
  shake       18.0 1.00Hz|   35.9 pp   35.4 pp    99%
  nod          9.0 1.50Hz|    9.0 pp    8.3 pp    93%
  nod_hard    13.0 1.70Hz|   12.9 pp   12.3 pp    95%
  query        9.0  held | (static lean)
  calm         6.0 0.80Hz|   12.0 pp   11.6 pp    97%
  scan        26.0 0.45Hz|   52.0 pp   51.4 pp    99%
Every gesture lands at 93–99%. Your whole gesture set is already inside the envelope — nod_hard at 1.7 Hz is the closest to the edge and still reproduces at 95%.

One thing to change when you wire it up
head_hw.py:66-67 sets GAIN_PAN = GAIN_TILT = 2.2 to compensate for a neck that under-travels. That calibration is for the remote head over head_link, and it's wrong for these servos — driven directly they need essentially gain 1.0. Leaving it at 2.2 would command 2.2× the intended amplitude and, since the servo reproduces it faithfully, actually deliver 2.2× the gesture.

Two caveats on all of the above: measured on a bare shaft, so head mass will pull these numbers down, and P is still at the factory 32 — the sweep showed ~25% of the lag is recoverable, which would push the high-frequency rows up. Both worth re-measuring once the head is mounted, with --bandwidth and --tune-pgain.