#!/usr/bin/env python3
"""
Sends jog commands to a UDP server as JSON datagrams.

Wire format (one JSON object per datagram):
    {"type": "jog", "yaw": 22.11, "pitch": -6.69, "v": 1,
     "sid": "8b6cd5b2", "seq": 1601, "sent": 1789016851.439}

Examples:
    # one packet
    python udp_jog_sender.py --yaw 22.11 --pitch -6.69

    # stream 20 packets/sec for 5 seconds
    python udp_jog_sender.py --yaw 22.11 --pitch -6.69 --rate 20 --duration 5

    # type "yaw pitch" lines by hand, blank line to quit
    python udp_jog_sender.py --interactive
"""

import argparse
import json
import socket
import time
import uuid


class JogSender:
    def __init__(self, host="127.0.0.1", port=8770, sid=None, seq=1):
        self.addr = (host, port)
        self.sid = sid or uuid.uuid4().hex[:8]
        self.seq = seq
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, yaw, pitch, v=1, msg_type="jog"):
        packet = {
            "type": msg_type,
            "yaw": round(float(yaw), 2),
            "pitch": round(float(pitch), 2),
            "v": v,
            "sid": self.sid,
            "seq": self.seq,
            "sent": round(time.time(), 3),
        }
        self.sock.sendto(json.dumps(packet).encode("utf-8"), self.addr)
        self.seq += 1
        return packet

    def close(self):
        self.sock.close()


def main():
    p = argparse.ArgumentParser(description="Send jog commands over UDP.")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8770)
    p.add_argument("--yaw", type=float, default=0.0)
    p.add_argument("--pitch", type=float, default=0.0)
    p.add_argument("--v", type=int, default=1, help="protocol version field")
    p.add_argument("--type", dest="msg_type", default="jog")
    p.add_argument("--sid", default=None, help="session id (random if omitted)")
    p.add_argument("--seq", type=int, default=1, help="starting sequence number")
    p.add_argument("--rate", type=float, default=0.0,
                   help="packets per second; 0 = send once and exit")
    p.add_argument("--duration", type=float, default=0.0,
                   help="seconds to stream; 0 = until Ctrl+C")
    p.add_argument("--interactive", action="store_true",
                   help="read 'yaw pitch' lines from stdin")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    tx = JogSender(args.host, args.port, args.sid, args.seq)
    log = (lambda pkt: None) if args.quiet else (lambda pkt: print(json.dumps(pkt)))
    print(f"-> {args.host}:{args.port}  sid={tx.sid}")

    try:
        if args.interactive:
            print("Enter: yaw pitch   (blank line quits)")
            while True:
                line = input("> ").strip()
                if not line:
                    break
                parts = line.split()
                if len(parts) != 2:
                    print("need two numbers, e.g. 22.11 -6.69")
                    continue
                try:
                    log(tx.send(parts[0], parts[1], args.v, args.msg_type))
                except ValueError:
                    print("not a number")

        elif args.rate > 0:
            interval = 1.0 / args.rate
            deadline = time.time() + args.duration if args.duration > 0 else float("inf")
            next_at = time.time()
            while time.time() < deadline:
                log(tx.send(args.yaw, args.pitch, args.v, args.msg_type))
                next_at += interval
                time.sleep(max(0.0, next_at - time.time()))

        else:
            log(tx.send(args.yaw, args.pitch, args.v, args.msg_type))

    except (KeyboardInterrupt, EOFError):
        print("\nstopped")
    finally:
        tx.close()


if __name__ == "__main__":
    main()