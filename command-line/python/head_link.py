"""
head_link.py - one-way link from the voice AI to the robot head.

Drop this file next to voice_ai.py and import it. Standard library only, no
dependencies, no setup. If the head is not running, every call here quietly does
nothing - the voice AI never needs a code path for "no head attached".

    import head_link

    clean, tags = head_link.extract_actions(raw_text)   # strip [head_*] tags
    ...synthesize `clean`, measure `duration`...
    head_link.speak(turn_id, clean, tags, duration)     # the instant audio starts
    head_link.stop(turn_id)                             # on barge-in

    said = head_link.look("look_left")                  # from your tool call;
                                                        # blocks, returns text

Everything here is fire-and-forget EXCEPT look(), which is a request and waits
for the head's answer - see the long note on that function.

Self-test:  python head_link.py
"""

import json
import os
import re
import socket
import time
import uuid

# ---------------------------------------------------------------- transport
# WHERE THE HEAD IS.
#   same laptop  ->  "127.0.0.1:8770"   (the default)
#   another PC   ->  set ROBOT_HEAD_ADDR to that machine's LAN IP, e.g.
#                    set ROBOT_HEAD_ADDR=192.168.1.42:8770        (Windows cmd)
#                    $env:ROBOT_HEAD_ADDR="192.168.1.42:8770"     (PowerShell)
#                    export ROBOT_HEAD_ADDR=192.168.1.42:8770     (bash)
#                 ...or just edit the fallback on the next line.
_HOST, _, _PORT = os.environ.get("ROBOT_HEAD_ADDR", "127.0.0.1:8770").partition(":")
_ADDR = (_HOST or "127.0.0.1", int(_PORT or 8770))
_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_seq = 0

# Identifies THIS run of the voice AI. `turn` numbers restart at 0 every time
# this process starts, so without a session id a head that had already seen a
# higher turn would reject everything from a freshly restarted voice AI as
# stale - silently, and for as long as it kept running.
_SID = uuid.uuid4().hex[:8]

# Set True to print every message instead of sending it - use this to develop
# the voice side before the head script exists.
DEBUG = False

# Print every datagram as it goes out. Turn off once the link is trusted.
VERBOSE = True


def target():
    """Where messages are being sent. Print this at startup - on a two-machine
    setup it is the single most useful thing to have in the log."""
    return f"{_ADDR[0]}:{_ADDR[1]}"


def session():
    """This run's session id. The head resets its turn tracking when it
    changes, so restarting the voice AI is always safe."""
    return _SID


def send(repeat=1, **msg):
    """Fire one message at the head. Never blocks, never raises.

    UDP is used precisely because sendto() cannot block: this is called from the
    audio thread microseconds before stream.write(), and a blocking send there
    would be an audible glitch.

    `repeat` sends the identical datagram more than once. Over WiFi a dropped
    packet is a real possibility, unlike loopback, and a lost `stop` is the one
    loss that is actually visible - the head would keep nodding at someone who
    has already interrupted the robot. Duplicates are harmless: `stop` is
    idempotent on the head side, and `speak` is never repeated.
    """
    global _seq
    _seq += 1
    msg["v"] = 1
    msg["sid"] = _SID
    msg["seq"] = _seq
    msg["sent"] = round(time.time(), 3)
    if DEBUG:
        print(f"[head] {json.dumps(msg)}")
        return
    blob = json.dumps(msg).encode("utf-8")
    if VERBOSE:
        print(f"[UDP OUT -> {_ADDR[0]}:{_ADDR[1]}] {blob.decode()}", flush=True)
    for _ in range(max(1, repeat)):
        try:
            _sock.sendto(blob, _ADDR)
        except OSError:
            return              # head not running; that is a normal state


# ------------------------------------------------------------ tag handling
TAG_RE = re.compile(r"\[([A-Za-z_][A-Za-z0-9_]*)\]")


def extract_actions(text):
    """Strip [head_*] tags out of a sentence.

    Returns (clean_text, [(char_pos, name), ...]) where char_pos indexes into
    clean_text - i.e. how far through the spoken words the gesture belongs.

    This must be called before synthesis whether or not the head is connected:
    left in, the tags get read aloud.
    """
    actions, clean, last = [], "", 0
    for m in TAG_RE.finditer(text):
        clean += text[last:m.start()]
        # Anchor the gesture to the end of the word it followed. A tag at the
        # very start of a chunk therefore gets position 0, which fires it
        # immediately - correct, because the sentence splitter puts a tag that
        # followed a full stop at the head of the NEXT chunk.
        actions.append((len(clean.rstrip()), m.group(1)))
        last = m.end()
    clean += text[last:]
    clean = re.sub(r"\s{2,}", " ", clean)          # tags leave double spaces
    clean = re.sub(r"\s+([.,!?;:])", r"\1", clean)  # ...and " ." before punctuation
    return clean.strip(), actions


def action_times(clean, actions, duration):
    """Character positions -> time SPANS, by proportion of the sentence.

    A tag describes how the head behaves WHILE the phrase it terminates is
    being spoken - not a single beat at one instant. So each gesture runs from
    where the previous tag ended (or the start of the sentence) up to this tag:

        "No I don't want [head_left_to_right_hard]"
            -> shake for the whole 1.37 s, stop when the audio stops

        "I am Nuwan [head_calm] yes I [head_up_to_down_hard] have to go home"
            -> calm over "I am Nuwan", then nod over "yes I", ...

    Returns [{name, t, dur}]: t = seconds from the start of this sentence's
    audio, dur = how long to keep the gesture going.

    Speaking rate inside one sentence is near enough constant that character
    proportion lands within about +/-150 ms. Do not build anything cleverer
    until a real session proves it is needed.
    """
    n = max(1, len(clean))
    out, prev = [], 0.0
    for pos, name in actions:
        end = duration * min(pos, n) / n
        out.append({"name": name,
                    "t": round(prev, 3),
                    "dur": round(max(0.0, end - prev), 3)})
        prev = end
    return out


# -------------------------------------------------------------- messages
def speak(turn, clean, tags, duration):
    """Call at the instant audio playback starts.

    Safe to call with an empty `clean`: the sentence splitter can hand you a
    chunk that is nothing but a tag (it happens on the last tag of a reply),
    and those gestures should still fire rather than being dropped.
    """
    if not tags and not clean:
        return
    send(type="speak", turn=turn, duration=round(duration, 3),
         text=clean, actions=action_times(clean, tags, duration))


def stop(turn, reason="barge_in"):
    """Call when speech is cut off. Without this the head keeps nodding at
    someone who has already interrupted the robot.

    Sent three times: this is the one message whose loss is visible, and over
    WiFi packets do occasionally go missing. It is idempotent on the head side.
    """
    send(type="stop", turn=turn, reason=reason, repeat=3)


def look(action, hold_s=None, timeout=15.0):
    """DIRECTED LOOK. Blocks until the head has finished moving, then returns
    the sentence it wants said back - use this as the tool call's result.

        result = head_link.look("look_left")
        -> "Yes, I am looking to my left now."

    This is the ONE call in this file that waits for a reply, and it has to: the
    LLM asked the robot to do something physical, and the only honest answer is
    the one the head gives after actually doing it. An LLM handed nothing back
    invents what happened.

    Valid actions (they must match head_poses.json on the head exactly):
        look_up  look_down  look_left  look_right  look_center  look_around

    While the look runs, the head stops tracking the person and stops gesturing
    - it holds the pose for about 8 seconds, then resumes both by itself. There
    is no "stop looking" call, and that is deliberate: a lost packet must not be
    able to leave the robot staring at a wall.

    HOW LONG IT BLOCKS. A single pose answers in about 1.2 s. `look_around` is
    a five-stop sweep with a deliberate pause at each one and takes closer to
    9 s - which is why the default timeout is 15 and not the 6 that felt like
    plenty. Shortening it does not make the head faster, it just makes the tool
    call give up before the answer arrives.

    Never raises. If the head is not running, or the reply is lost, you get a
    plain-language failure back rather than an exception - so the tool call
    always has something true to return.
    """
    global _seq
    _seq += 1
    rid = uuid.uuid4().hex[:8]
    msg = {"v": 1, "sid": _SID, "seq": _seq, "type": "look",
           "id": rid, "action": action, "sent": round(time.time(), 3)}
    if hold_s is not None:
        msg["hold_s"] = float(hold_s)
    blob = json.dumps(msg).encode("utf-8")

    if DEBUG:
        print(f"[head] {json.dumps(msg)}")
        return "I am looking there now."

    # A DEDICATED socket, not the shared _sock used by speak/stop. That one is
    # written to from the audio thread microseconds before playback starts;
    # reading replies on it would mean this call could swallow a datagram meant
    # for nobody, and worse, a slow tool call would sit on a socket the audio
    # path needs. A fresh socket per look is a few microseconds and removes the
    # whole question.
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(timeout)
        if VERBOSE:
            print(f"[UDP OUT -> {_ADDR[0]}:{_ADDR[1]}] {blob.decode()}",
                  flush=True)
        sock.sendto(blob, _ADDR)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            data, _src = sock.recvfrom(8192)
            try:
                reply = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            # Ignore anything that is not the answer to THIS request. Late
            # replies to an abandoned earlier look do turn up, and returning one
            # would have the robot describe a move it made ten seconds ago.
            if reply.get("type") != "look_result" or reply.get("id") != rid:
                continue
            if VERBOSE:
                print(f"[UDP IN  <- head] {data.decode('utf-8', 'replace')}",
                      flush=True)
            return str(reply.get("message") or "Done.")
    except socket.timeout:
        pass
    except OSError:
        return "I cannot move my head right now - it is not responding."
    finally:
        sock.close()
    return ("I could not tell whether my head moved - it did not answer me.")


def jog(yaw, pitch):
    """MANUAL CONTROL. Point the neck at an absolute angle, in degrees.

        head_link.jog(-12.5, 4.0)      # yaw, pitch

    yaw  + = the robot's RIGHT,  - = its left
    pitch + = UP,                - = down
    Both measured from the head's home position. Out-of-range values are
    clamped by the head, so a slider can never demand an angle the neck does
    not have - call limits() once to set the sliders' range properly.

    Fire and forget, exactly like speak(): a slider being dragged sends tens of
    packets a second and there is nothing useful to say back about any one of
    them. Send at most ~20-30 per second; more is wasted, since the neck cannot
    follow faster than that anyway.

    While jog packets are arriving the head stops tracking faces and stops
    gesturing. It hands itself back about 2 seconds after the last one - so
    letting go of the slider needs no message, and there is no "I am finished"
    packet whose loss could strand the head under manual control.
    """
    send(type="jog", yaw=round(float(yaw), 2), pitch=round(float(pitch), 2))


def limits(timeout=2.0):
    """Ask the head how far its neck actually travels. Call once, at startup.

    Returns a dict:
        {"yaw_min": -42.4, "yaw_max": 42.4,
         "pitch_min": -24.9, "pitch_max": 33.7,
         "yaw": 0.0, "pitch": 0.0}       # where it is right now

    Use it to set the sliders' range. The numbers come from the servos' real
    calibration, so they follow a re-homed or re-built neck; hardcoding them on
    this side is how a slider ends up able to ask for an angle that does not
    exist. Returns None if the head does not answer - fall back to a
    conservative +/-30 and carry on.
    """
    rid = uuid.uuid4().hex[:8]
    req = {"v": 1, "sid": _SID, "type": "limits", "id": rid}
    if DEBUG:
        print(f"[head] {json.dumps(req)}")
        return None
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(timeout)
        sock.sendto(json.dumps(req).encode("utf-8"), _ADDR)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            sock.settimeout(remaining)
            data, _src = sock.recvfrom(8192)
            try:
                reply = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if reply.get("type") == "limits_result":
                if VERBOSE:
                    print(f"[UDP IN  <- head] {data.decode('utf-8', 'replace')}",
                          flush=True)
                return reply
    except (socket.timeout, OSError):
        return None
    finally:
        sock.close()


def state(name):
    """OPTIONAL. 'idle' | 'listening' | 'thinking' | 'speaking'.

    The head infers speaking/not-speaking from speak and stop alone, so this is
    a refinement, not a requirement. Send it only where it is free.
    """
    send(type="state", state=name)


# ------------------------------------------------------------- self-test
def _selftest():
    """Parse only - prints what would be sent, sends nothing."""
    global DEBUG
    DEBUG = True
    real = ("Spera Security Robot here, [head_calm] monitoring the area for "
            "any risks, sir [head_up_to_down_medium].")
    clean, tags = extract_actions(real)
    print(f"raw   : {real}")
    print(f"speak : {clean}")
    print(f"tags  : {tags}")
    print("at 3.4 s of audio:", action_times(clean, tags, 3.4))
    print()
    print("tag-only chunk (the last tag of a reply):")
    c2, t2 = extract_actions("[head_up_to_down_hard]")
    print(f"  speak={c2!r} tags={t2}")
    speak(7, c2, t2, 0.0)
    print()
    print("normal send:")
    speak(7, clean, tags, 3.4)
    stop(7)


def _network_test(dest, action):
    """Really send, so the head visibly moves. This is the two-laptop check:
    if the head does not move, the problem is the network or the firewall on
    the head machine, not this code - sendto() cannot tell you either way."""
    global _ADDR
    host, _, port = dest.partition(":")
    _ADDR = (host, int(port or 8770))
    print(f"sending to {target()} ...")
    span = 1.4      # pretend the phrase lasts this long, so it is clearly seen
    for i in range(3):
        print(f"  {i + 1}/3  {action} over {span}s")
        send(type="speak", turn=1, duration=span, text="",
             actions=[{"name": action, "t": 0.0, "dur": span}])
        time.sleep(span + 0.6)
    stop(1, reason="shutdown")
    print("\nSent. If the head did not move, on the HEAD machine check:")
    print("  * robot_head.py is running and its HUD shows 'voice idle 8770'")
    print("  * the firewall allows inbound UDP 8770 (see command.txt)")
    print("  * both machines are on the same subnet")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="Voice AI -> robot head link. No args: parse-only self "
                    "test. --send: real network test.")
    ap.add_argument("--send", metavar="HOST:PORT",
                    help="actually send test gestures to a running head, e.g. "
                         "--send 192.168.1.253:8770")
    ap.add_argument("--action", default="head_up_to_down_hard",
                    help="which gesture the network test fires")
    ap.add_argument("--look", metavar="POSE",
                    help="send one directed look and print what the head "
                         "answers, e.g. --look look_around")
    args = ap.parse_args()

    if args.look and args.send:
        host, _, port = args.send.partition(":")
        _ADDR = (host, int(port or 8770))
    print(f"robot head target: {target()}   "
          f"(set ROBOT_HEAD_ADDR to change)\n")
    if args.look:
        print(f"look({args.look!r}) -> ", end="", flush=True)
        print(repr(look(args.look)))
    elif args.send:
        _network_test(args.send, args.action)
    else:
        _selftest()
