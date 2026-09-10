#!/usr/bin/env python3
"""
feetech_sts.py -- self-contained driver for Feetech STS-series serial bus servos
                  (STS3215, STS3032, STS3046, SM/STS family; protocol "v0",
                  little-endian 16-bit registers).

Only dependency: pyserial   ->   pip install pyserial

Wiring
------
USB-to-TTL adapter (or Feetech FE-URT-1 / Waveshare bus driver board) in
HALF-DUPLEX on the servo bus.  Servos are daisy-chained and need their own
6-12.6 V supply -- do NOT power them from USB.  Default baud is 1 000 000.

Quick start
-----------
    python feetech_sts.py --port /dev/ttyUSB0 scan
    python feetech_sts.py --port /dev/ttyUSB0 pos   --ids 1 2 --deg 90 -90 --speed 1500 --accel 30
    python feetech_sts.py --port /dev/ttyUSB0 vel   --ids 1 2 --rpm 20 -20 --seconds 3
    python feetech_sts.py --port /dev/ttyUSB0 watch --ids 1 2

Library use
-----------
    from feetech_sts import STSBus

    with STSBus("/dev/ttyUSB0") as bus:
        bus.set_torque(1, True)
        bus.set_position(1, 2048, speed=1200, accel=30)   # counts, counts/s, 100*counts/s^2
        print(bus.read_state(1))

        bus.set_wheel_mode(2)          # continuous rotation
        bus.set_velocity(2, 800)       # signed counts/s, negative = reverse
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

import serial  # pyserial

# --------------------------------------------------------------------------
# Protocol constants
# --------------------------------------------------------------------------

BROADCAST_ID = 0xFE

INST_PING = 0x01
INST_READ = 0x02
INST_WRITE = 0x03
INST_REG_WRITE = 0x04
INST_ACTION = 0x05
INST_RESET = 0x06
INST_SYNC_WRITE = 0x83


class Reg:
    """STS / SMS memory table addresses."""

    # ---- EEPROM (persistent; limited write cycles) ----
    MODEL = 3           # 2 bytes, read-only (address 3..4 on some tables)
    ID = 5
    BAUD_RATE = 6
    RETURN_DELAY = 7
    RESPONSE_LEVEL = 8
    MIN_ANGLE_LIMIT = 9         # 2 bytes
    MAX_ANGLE_LIMIT = 11        # 2 bytes
    MAX_TEMPERATURE = 13
    MAX_VOLTAGE = 14
    MIN_VOLTAGE = 15
    MAX_TORQUE = 16             # 2 bytes
    PHASE = 18
    UNLOADING_COND = 19
    LED_ALARM_COND = 20
    POS_P = 21
    POS_D = 22
    POS_I = 23
    STARTUP_FORCE = 24          # 2 bytes
    CW_DEADBAND = 26
    CCW_DEADBAND = 27
    PROTECTION_CURRENT = 28     # 2 bytes
    ANGULAR_RESOLUTION = 30
    POSITION_OFFSET = 31        # 2 bytes, signed (sign-magnitude bit 11)
    MODE = 33                   # 0=position 1=wheel/velocity 2=PWM 3=step
    PROTECTIVE_TORQUE = 34
    PROTECTION_TIME = 35
    OVERLOAD_TORQUE = 36
    SPEED_P = 37
    OVERCURRENT_TIME = 38
    SPEED_I = 39

    # ---- SRAM (volatile; write as often as you like) ----
    TORQUE_ENABLE = 40
    GOAL_ACC = 41
    GOAL_POSITION = 42          # 2 bytes
    GOAL_TIME = 44              # 2 bytes
    GOAL_SPEED = 46             # 2 bytes
    LOCK = 55                   # 0 = EEPROM writable, 1 = locked
    PRESENT_POSITION = 56       # 2 bytes
    PRESENT_SPEED = 58          # 2 bytes, sign-magnitude
    PRESENT_LOAD = 60           # 2 bytes, sign-magnitude (bit 10)
    PRESENT_VOLTAGE = 62        # 0.1 V
    PRESENT_TEMPERATURE = 63    # degC
    ASYNC_WRITE_FLAG = 64
    HARDWARE_ERROR = 65
    MOVING = 66
    PRESENT_CURRENT = 69        # 2 bytes, 6.5 mA / unit


MODE_POSITION = 0
MODE_WHEEL = 1
MODE_PWM = 2
MODE_STEP = 3

# STS3215 defaults. Adjust if your model differs.
COUNTS_PER_REV = 4096
DEG_PER_COUNT = 360.0 / COUNTS_PER_REV
# Goal/present speed unit is 1 count/s  ->  rpm = counts_per_s * 60 / 4096
COUNTS_PER_S_PER_RPM = COUNTS_PER_REV / 60.0
# Acceleration unit is 100 counts/s^2
ACCEL_UNIT = 100.0
CURRENT_UNIT_MA = 6.5


class STSError(Exception):
    pass


class STSTimeout(STSError):
    pass


HW_ERROR_BITS = {
    0x01: "voltage",
    0x02: "angle/sensor",
    0x04: "overheat",
    0x08: "overcurrent",
    0x20: "overload",
}


@dataclass
class ServoState:
    id: int
    position: int            # counts
    speed: int               # counts/s, signed
    load: int                # -1000..1000 (0.1 % of max torque)
    voltage: float           # V
    temperature: int         # degC
    current_ma: float        # mA
    moving: bool

    @property
    def degrees(self) -> float:
        return self.position * DEG_PER_COUNT

    @property
    def rpm(self) -> float:
        return self.speed / COUNTS_PER_S_PER_RPM

    def __str__(self) -> str:
        return (
            f"id={self.id:<3} pos={self.position:>5} ({self.degrees:7.2f} deg)  "
            f"spd={self.speed:>6} ({self.rpm:6.1f} rpm)  load={self.load:>5}  "
            f"{self.voltage:4.1f}V  {self.temperature:>3}C  "
            f"{self.current_ma:6.1f}mA  {'MOVING' if self.moving else 'idle'}"
        )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _to_sign_magnitude(value: int, sign_bit: int = 15) -> int:
    """Feetech encodes signed values as magnitude + a sign bit, not two's complement."""
    if value < 0:
        return (-value) | (1 << sign_bit)
    return value


def _from_sign_magnitude(value: int, sign_bit: int = 15) -> int:
    if value & (1 << sign_bit):
        return -(value & ((1 << sign_bit) - 1))
    return value


def _lo_hi(value: int) -> List[int]:
    """STS registers are little-endian (SCS servos are big-endian -- different family)."""
    return [value & 0xFF, (value >> 8) & 0xFF]


def _word(lo: int, hi: int) -> int:
    return (hi << 8) | lo


# --------------------------------------------------------------------------
# Bus
# --------------------------------------------------------------------------

class STSBus:
    """Half-duplex serial bus carrying one or more Feetech STS servos."""

    def __init__(
        self,
        port: str,
        baudrate: int = 1_000_000,
        timeout: float = 0.05,
        retries: int = 2,
        write_ack: bool = True,
    ) -> None:
        self.retries = retries
        # Servos with "response level" set to 0 only answer READ/PING. If your
        # writes time out, construct the bus with write_ack=False.
        self.write_ack = write_ack
        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
            write_timeout=timeout,
        )
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    # -- context manager ---------------------------------------------------
    def __enter__(self) -> "STSBus":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self.ser.is_open:
            self.ser.close()

    # -- packet layer ------------------------------------------------------
    @staticmethod
    def _build(servo_id: int, instruction: int, params: Sequence[int] = ()) -> bytes:
        length = len(params) + 2
        body = [servo_id, length, instruction, *params]
        checksum = (~sum(body)) & 0xFF
        return bytes([0xFF, 0xFF, *body, checksum])

    def _read_status(self, expect_id: int) -> bytes:
        """Read one status packet, returning its parameter bytes."""
        deadline = time.monotonic() + max(self.ser.timeout or 0.05, 0.02) * 4

        # Sync on the 0xFF 0xFF header.
        header = b""
        while time.monotonic() < deadline:
            b = self.ser.read(1)
            if not b:
                continue
            header = (header + b)[-2:]
            if header == b"\xff\xff":
                break
        else:
            raise STSTimeout(f"no response from servo {expect_id}")

        head = self.ser.read(2)             # id, length
        if len(head) < 2:
            raise STSTimeout(f"truncated header from servo {expect_id}")
        sid, length = head[0], head[1]
        rest = self.ser.read(length)        # error + params + checksum
        if len(rest) < length:
            raise STSTimeout(f"truncated packet from servo {expect_id}")

        error, params, checksum = rest[0], rest[1:-1], rest[-1]
        if ((~(sid + length + error + sum(params))) & 0xFF) != checksum:
            raise STSError(f"bad checksum from servo {sid}")
        if sid != expect_id:
            raise STSError(f"reply from servo {sid}, expected {expect_id}")
        if error:
            names = [n for bit, n in HW_ERROR_BITS.items() if error & bit] or [hex(error)]
            raise STSError(f"servo {sid} reports error: {', '.join(names)}")
        return params

    def _txrx(self, servo_id: int, instruction: int, params: Sequence[int], read_len: int,
              retries: Optional[int] = None) -> bytes:
        last: Optional[Exception] = None
        attempts = (self.retries if retries is None else retries) + 1
        for _ in range(attempts):
            try:
                self.ser.reset_input_buffer()
                self.ser.write(self._build(servo_id, instruction, params))
                self.ser.flush()
                if read_len == 0 and servo_id == BROADCAST_ID:
                    return b""
                return self._read_status(servo_id)
            except (STSTimeout, STSError) as exc:
                last = exc
                time.sleep(0.002)
        raise last  # type: ignore[misc]

    # -- register access ---------------------------------------------------
    def write_bytes(self, servo_id: int, address: int, data: Sequence[int], expect_reply: bool = True) -> None:
        if servo_id == BROADCAST_ID or not (expect_reply and self.write_ack):
            self.ser.write(self._build(servo_id, INST_WRITE, [address, *data]))
            self.ser.flush()
            return
        self._txrx(servo_id, INST_WRITE, [address, *data], read_len=0)

    def read_bytes(self, servo_id: int, address: int, count: int) -> bytes:
        data = self._txrx(servo_id, INST_READ, [address, count], read_len=count)
        if len(data) != count:
            raise STSError(f"servo {servo_id}: expected {count} bytes, got {len(data)}")
        return data

    def write_u8(self, servo_id: int, address: int, value: int) -> None:
        self.write_bytes(servo_id, address, [value & 0xFF])

    def write_u16(self, servo_id: int, address: int, value: int) -> None:
        self.write_bytes(servo_id, address, _lo_hi(value))

    def read_u8(self, servo_id: int, address: int) -> int:
        return self.read_bytes(servo_id, address, 1)[0]

    def read_u16(self, servo_id: int, address: int) -> int:
        d = self.read_bytes(servo_id, address, 2)
        return _word(d[0], d[1])

    # -- discovery ---------------------------------------------------------
    def ping(self, servo_id: int, retries: int = 0) -> bool:
        """Absent IDs cost one full timeout each, so scans default to no retries."""
        try:
            self._txrx(servo_id, INST_PING, [], read_len=0, retries=retries)
            return True
        except STSError:
            return False

    def scan(self, id_range: Iterable[int] = range(0, 253)) -> List[int]:
        found = []
        for sid in id_range:
            if self.ping(sid):
                found.append(sid)
        return found

    # -- EEPROM lock -------------------------------------------------------
    def unlock_eeprom(self, servo_id: int) -> None:
        self.write_u8(servo_id, Reg.LOCK, 0)

    def lock_eeprom(self, servo_id: int) -> None:
        self.write_u8(servo_id, Reg.LOCK, 1)

    # -- basics ------------------------------------------------------------
    def set_torque(self, servo_id: int, on: bool) -> None:
        self.write_u8(servo_id, Reg.TORQUE_ENABLE, 1 if on else 0)

    def get_mode(self, servo_id: int) -> int:
        return self.read_u8(servo_id, Reg.MODE)

    def set_mode(self, servo_id: int, mode: int) -> None:
        """MODE lives in EEPROM -- don't call this in a control loop."""
        if self.get_mode(servo_id) == mode:
            return
        self.unlock_eeprom(servo_id)
        time.sleep(0.01)
        self.write_u8(servo_id, Reg.MODE, mode)
        time.sleep(0.02)
        self.lock_eeprom(servo_id)
        time.sleep(0.01)

    def set_position_mode(self, servo_id: int) -> None:
        self.set_mode(servo_id, MODE_POSITION)

    def set_wheel_mode(self, servo_id: int) -> None:
        self.set_mode(servo_id, MODE_WHEEL)

    # -- POSITION CONTROL --------------------------------------------------
    def set_position(
        self,
        servo_id: int,
        position: int,
        speed: int = 0,
        accel: int = 0,
    ) -> None:
        """Move to `position` (counts, 0..4095 for one turn).

        speed : travel speed in counts/s (0 = servo maximum, ~3400 for STS3215)
        accel : acceleration in units of 100 counts/s^2 (0 = no ramp)
        """
        position = int(round(position))
        payload = [
            accel & 0xFF,
            *_lo_hi(_to_sign_magnitude(position)),   # goal position
            0x00, 0x00,                              # goal time (unused)
            *_lo_hi(abs(int(speed)) & 0x7FFF),       # goal speed (magnitude)
        ]
        self.write_bytes(servo_id, Reg.GOAL_ACC, payload)

    def set_position_deg(self, servo_id: int, degrees: float, speed_rpm: float = 0.0, accel: int = 0) -> None:
        self.set_position(
            servo_id,
            round(degrees / DEG_PER_COUNT),
            speed=round(speed_rpm * COUNTS_PER_S_PER_RPM),
            accel=accel,
        )

    def sync_set_positions(self, targets: Dict[int, int], speed: int = 0, accel: int = 0) -> None:
        """Command several servos in ONE packet so they start together."""
        per_servo = 7
        params: List[int] = [Reg.GOAL_ACC, per_servo]
        for sid, pos in targets.items():
            params += [
                sid,
                accel & 0xFF,
                *_lo_hi(_to_sign_magnitude(int(round(pos)))),
                0x00, 0x00,
                *_lo_hi(abs(int(speed)) & 0x7FFF),
            ]
        self.ser.write(self._build(BROADCAST_ID, INST_SYNC_WRITE, params))
        self.ser.flush()

    def sync_set_targets(self, targets: Dict[int, Sequence[int]]) -> None:
        """Like sync_set_positions, but each servo gets its OWN speed and accel.

        `targets` maps servo id -> (counts, speed, accel). The sync-write frame
        already carries an accel byte and a speed word per servo; the simpler
        call above just repeats one value across all of them.

        Per-servo profiles matter when one packet drives a neck: a pan servo
        swinging 60 degrees and a tilt servo nudging 4 want different speeds,
        and splitting them into two packets loses the one property sync-write
        exists for -- both servos starting on the same instruction.

        Broadcast, so no servo replies. That is what makes it usable in a
        50 Hz control loop, where a status round-trip per servo would put a
        timeout in the path of every frame.
        """
        per_servo = 7
        params: List[int] = [Reg.GOAL_ACC, per_servo]
        for sid, (pos, speed, accel) in targets.items():
            params += [
                sid,
                int(accel) & 0xFF,
                *_lo_hi(_to_sign_magnitude(int(round(pos)))),
                0x00, 0x00,
                *_lo_hi(abs(int(speed)) & 0x7FFF),
            ]
        self.ser.write(self._build(BROADCAST_ID, INST_SYNC_WRITE, params))
        self.ser.flush()

    # -- VELOCITY CONTROL --------------------------------------------------
    def set_velocity(self, servo_id: int, speed: int, accel: Optional[int] = None) -> None:
        """Continuous rotation at `speed` counts/s. Negative = reverse.

        Requires wheel mode (call set_wheel_mode once first).
        """
        if accel is not None:
            self.write_u8(servo_id, Reg.GOAL_ACC, accel & 0xFF)
        self.write_u16(servo_id, Reg.GOAL_SPEED, _to_sign_magnitude(int(round(speed))))

    def set_velocity_rpm(self, servo_id: int, rpm: float, accel: Optional[int] = None) -> None:
        self.set_velocity(servo_id, round(rpm * COUNTS_PER_S_PER_RPM), accel=accel)

    def stop(self, servo_id: int) -> None:
        """Zero velocity in wheel mode; hold current position in position mode."""
        if self.get_mode(servo_id) == MODE_WHEEL:
            self.set_velocity(servo_id, 0)
        else:
            self.set_position(servo_id, self.read_position(servo_id))

    # -- limits / tuning ---------------------------------------------------
    def set_angle_limits(self, servo_id: int, min_counts: int, max_counts: int) -> None:
        """0,0 = multi-turn / unlimited. Written to EEPROM."""
        self.unlock_eeprom(servo_id)
        time.sleep(0.01)
        self.write_u16(servo_id, Reg.MIN_ANGLE_LIMIT, min_counts)
        self.write_u16(servo_id, Reg.MAX_ANGLE_LIMIT, max_counts)
        time.sleep(0.02)
        self.lock_eeprom(servo_id)

    def set_position_pid(self, servo_id: int, p: int, i: int, d: int) -> None:
        self.write_u8(servo_id, Reg.POS_P, p)
        self.write_u8(servo_id, Reg.POS_D, d)
        self.write_u8(servo_id, Reg.POS_I, i)

    def set_id(self, servo_id: int, new_id: int) -> None:
        """Do this with ONE servo on the bus at a time."""
        self.unlock_eeprom(servo_id)
        time.sleep(0.01)
        self.write_u8(servo_id, Reg.ID, new_id)
        time.sleep(0.02)
        self.lock_eeprom(new_id)

    # -- telemetry ---------------------------------------------------------
    def read_position(self, servo_id: int) -> int:
        return _from_sign_magnitude(self.read_u16(servo_id, Reg.PRESENT_POSITION))

    def read_velocity(self, servo_id: int) -> int:
        return _from_sign_magnitude(self.read_u16(servo_id, Reg.PRESENT_SPEED))

    def read_load(self, servo_id: int) -> int:
        return _from_sign_magnitude(self.read_u16(servo_id, Reg.PRESENT_LOAD), sign_bit=10)

    def is_moving(self, servo_id: int) -> bool:
        return bool(self.read_u8(servo_id, Reg.MOVING))

    def read_state(self, servo_id: int) -> ServoState:
        """One 15-byte burst read: position through hardware status."""
        d = self.read_bytes(servo_id, Reg.PRESENT_POSITION, 11)   # 56..66
        cur = self.read_u16(servo_id, Reg.PRESENT_CURRENT)
        return ServoState(
            id=servo_id,
            position=_from_sign_magnitude(_word(d[0], d[1])),
            speed=_from_sign_magnitude(_word(d[2], d[3])),
            load=_from_sign_magnitude(_word(d[4], d[5]), sign_bit=10),
            voltage=d[6] / 10.0,
            temperature=d[7],
            current_ma=_from_sign_magnitude(cur) * CURRENT_UNIT_MA,
            moving=bool(d[10]),
        )

    def wait_until_stopped(self, servo_id: int, timeout: float = 5.0, poll: float = 0.02) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if not self.is_moving(servo_id):
                return True
            time.sleep(poll)
        return False


# --------------------------------------------------------------------------
# CLI demo
# --------------------------------------------------------------------------

def _cmd_scan(bus: STSBus, args) -> None:
    print(f"Scanning IDs 0-{args.max_id} at {args.baud} baud ...")
    ids = bus.scan(range(0, args.max_id + 1))
    if not ids:
        print("No servos found. Check power, wiring (half-duplex A/B), baud rate and port.")
        return
    for sid in ids:
        mode = bus.get_mode(sid)
        st = bus.read_state(sid)
        mode_name = {0: "position", 1: "wheel", 2: "pwm", 3: "step"}.get(mode, str(mode))
        print(f"  ID {sid:<3} mode={mode_name:<8} {st}")


def _cmd_pos(bus: STSBus, args) -> None:
    if len(args.deg) != len(args.ids):
        raise SystemExit("--deg needs one value per --ids entry")
    targets = {}
    for sid, deg in zip(args.ids, args.deg):
        bus.set_position_mode(sid)
        bus.set_torque(sid, True)
        targets[sid] = round(deg / DEG_PER_COUNT)
    print(f"Moving {targets} at speed={args.speed} counts/s accel={args.accel}")
    bus.sync_set_positions(targets, speed=args.speed, accel=args.accel)

    end = time.monotonic() + args.timeout
    while time.monotonic() < end:
        states = [bus.read_state(sid) for sid in args.ids]
        print("  " + " | ".join(f"{s.id}:{s.degrees:7.2f}deg" for s in states), end="\r")
        if all(not s.moving for s in states):
            break
        time.sleep(0.05)
    print()
    for sid in args.ids:
        print("  " + str(bus.read_state(sid)))


def _cmd_vel(bus: STSBus, args) -> None:
    if len(args.rpm) != len(args.ids):
        raise SystemExit("--rpm needs one value per --ids entry")
    for sid in args.ids:
        bus.set_wheel_mode(sid)
        bus.set_torque(sid, True)
    print(f"Spinning for {args.seconds}s -- Ctrl-C to stop early")
    try:
        for sid, rpm in zip(args.ids, args.rpm):
            bus.set_velocity_rpm(sid, rpm, accel=args.accel)
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            states = [bus.read_state(sid) for sid in args.ids]
            print("  " + " | ".join(f"{s.id}:{s.rpm:6.1f}rpm load={s.load:>5}" for s in states), end="\r")
            time.sleep(0.05)
        print()
    finally:
        for sid in args.ids:
            bus.set_velocity(sid, 0)
        print("Stopped.")


def _cmd_watch(bus: STSBus, args) -> None:
    print("Ctrl-C to quit. (Torque is off, so you can back-drive the horn by hand.)")
    if args.release:
        for sid in args.ids:
            bus.set_torque(sid, False)
    try:
        while True:
            for sid in args.ids:
                print("  " + str(bus.read_state(sid)))
            print(f"\033[{len(args.ids)}A", end="")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n" * len(args.ids))


def _cmd_torque(bus: STSBus, args) -> None:
    for sid in args.ids:
        bus.set_torque(sid, args.on)
    print(f"Torque {'enabled' if args.on else 'disabled'} on {args.ids}")


def main() -> None:
    p = argparse.ArgumentParser(description="Feetech STS servo position/velocity control")
    p.add_argument("--port", required=True, help="e.g. /dev/ttyUSB0, /dev/tty.usbserial-XXXX, COM5")
    p.add_argument("--baud", type=int, default=1_000_000)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="find servos on the bus")
    s.add_argument("--max-id", type=int, default=20)
    s.set_defaults(func=_cmd_scan)

    s = sub.add_parser("pos", help="position control")
    s.add_argument("--ids", type=int, nargs="+", required=True)
    s.add_argument("--deg", type=float, nargs="+", required=True, help="target angle per servo")
    s.add_argument("--speed", type=int, default=1000, help="counts/s (0 = max, ~3400)")
    s.add_argument("--accel", type=int, default=30, help="units of 100 counts/s^2")
    s.add_argument("--timeout", type=float, default=8.0)
    s.set_defaults(func=_cmd_pos)

    s = sub.add_parser("vel", help="continuous-rotation velocity control")
    s.add_argument("--ids", type=int, nargs="+", required=True)
    s.add_argument("--rpm", type=float, nargs="+", required=True, help="signed rpm per servo")
    s.add_argument("--accel", type=int, default=20)
    s.add_argument("--seconds", type=float, default=3.0)
    s.set_defaults(func=_cmd_vel)

    s = sub.add_parser("watch", help="stream telemetry")
    s.add_argument("--ids", type=int, nargs="+", required=True)
    s.add_argument("--release", action="store_true", help="disable torque first")
    s.set_defaults(func=_cmd_watch)

    s = sub.add_parser("torque", help="enable/disable torque")
    s.add_argument("--ids", type=int, nargs="+", required=True)
    s.add_argument("--off", dest="on", action="store_false", default=True)
    s.set_defaults(func=_cmd_torque)

    args = p.parse_args()
    with STSBus(args.port, baudrate=args.baud) as bus:
        args.func(bus, args)


if __name__ == "__main__":
    main()
