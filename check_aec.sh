#!/usr/bin/env bash
# Measure how much echo the canceller is actually removing (ERLE, in dB).
#
# "Module loaded" is not "echo cancelled" -- a routing mistake leaves the
# canceller running happily with no reference signal, cancelling nothing, and
# nothing in pactl's output says so. This is the test that caught the
# ReSpeaker's firmware AEC doing nothing (ch0 measured LOUDER than the raw
# mics). Run it before trusting any AEC setup.
#
# Method: play the same sound twice through the speaker, recording once from
# the raw microphone and once from the cancelled source. The difference in RMS
# is the cancellation depth.
#
# Usage:  ./check_aec.sh            # auto-detects the raw mic from the module
#         ./check_aec.sh <raw_src>  # or name it explicitly
#
# Keep the room quiet and DO NOT touch the volume between the two recordings,
# or the comparison is meaningless.

set -uo pipefail

DUR=4
TONE=/usr/share/sounds/alsa/Front_Center.wav
OUT="${TMPDIR:-/tmp}/aec_check"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()  { printf '  \033[32mOK\033[0m  %s\n' "$*"; }
bad() { printf '  \033[31mXX\033[0m  %s\n' "$*"; }

mkdir -p "$OUT"
[ -f "$TONE" ] || { bad "test sound missing: $TONE"; exit 1; }

say "1. Locating devices"
# Captured, not piped into grep -q: under pipefail a matching `grep -q` kills
# its upstream with SIGPIPE and the pipeline reports failure on success.
SOURCES=$(pactl list short sources)
case "$SOURCES" in
  *aec_source*) ok "aec_source present" ;;
  *)            bad "aec_source does not exist -- run ./setup_aec_usb.sh first"; exit 1 ;;
esac

# The raw mic is whatever the canceller was pointed at. Read it back out of the
# loaded module's own arguments rather than guessing.
RAW_SRC="${1:-}"
if [ -z "$RAW_SRC" ]; then
  RAW_SRC=$(pactl list modules | grep -A1 "Name: module-echo-cancel" \
            | grep -oE "source_master=[^ ]+" | cut -d= -f2 | head -1)
fi
[ -z "$RAW_SRC" ] && { bad "could not determine the raw source -- pass it as an argument"; exit 1; }
ok "raw mic:   $RAW_SRC"
ok "cancelled: aec_source"

# Play EXPLICITLY to aec_sink, never "the default". GNOME reassigns the default
# sink whenever a card profile changes or a device appears, and it did exactly
# that here mid-session -- playback silently went to the raw hardware sink, the
# canceller got no reference, and the test reported ERLE 0 for a setup that was
# otherwise correct. Naming the device makes the measurement independent of
# whatever the desktop has decided the default should be this minute.
play_and_record() {
  local dev="$1" out="$2"
  ( end=$((SECONDS+DUR)); while [ $SECONDS -lt $end ]; do paplay --device=aec_sink "$TONE" 2>/dev/null; done ) &
  local pid=$!
  parecord --device="$dev" --file-format=wav "$out" 2>/dev/null &
  local rec=$!
  sleep "$DUR"
  kill $pid $rec 2>/dev/null
  wait $pid $rec 2>/dev/null
}

# Measure the room first. ERLE is echo-minus-cancelled, so if the echo barely
# rises above ambient noise there is nothing to subtract and the ratio just
# measures the noise floor -- reporting a low number that looks like a routing
# failure when the canceller is fine. Caught exactly that on this machine: a
# tone only 4.6 dB over the floor produced "ERLE 5.5 dB, NOT WORKING".
say "2. Room noise floor (${DUR}s) -- silence, nothing playing"
play_and_record "$RAW_SRC" "$OUT/floor.wav"

say "3. Recording from the RAW mic (${DUR}s) -- stay quiet"
play_and_record "$RAW_SRC" "$OUT/raw.wav"

say "4. Recording from aec_source (${DUR}s) -- stay quiet"
play_and_record "aec_source" "$OUT/aec.wav"

say "5. Result"
python3 - "$OUT/raw.wav" "$OUT/aec.wav" "$OUT/floor.wav" <<'PY'
import array, math, sys, wave

def rms_db(path):
    """RMS of a wav in dB. Handles the float32 that module-echo-cancel emits
    as well as ordinary 16-bit PCM."""
    try:
        with wave.open(path) as w:
            width, n = w.getsampwidth(), w.getnframes()
            raw = w.readframes(n)
    except Exception as e:
        return None, f"unreadable ({e})"
    if not raw:
        return None, "empty recording"
    codes = {1: 'b', 2: 'h', 4: 'i'}
    if width not in codes:
        return None, f"unsupported sample width {width}"
    a = array.array(codes[width])
    a.frombytes(raw[:len(raw) - len(raw) % width])
    if not len(a):
        return None, "no samples"
    full = float(1 << (8 * width - 1))
    mean_sq = sum((s / full) ** 2 for s in a) / len(a)
    if mean_sq <= 0:
        return -120.0, "silent"
    return 10 * math.log10(mean_sq), ""

raw, raw_err = rms_db(sys.argv[1])
aec, aec_err = rms_db(sys.argv[2])
floor, _     = rms_db(sys.argv[3])

if raw is None or aec is None or floor is None:
    print(f"  could not measure: raw={raw_err or 'ok'} aec={aec_err or 'ok'}")
    sys.exit(1)

print(f"  room floor : {floor:7.1f} dBFS")
print(f"  raw        : {raw:7.1f} dBFS   ({raw - floor:+.1f} dB over the floor)")
print(f"  cancelled  : {aec:7.1f} dBFS")
print(f"  ERLE       : {raw - aec:7.1f} dB")

# Cancellation can only be measured down to the noise floor. Below ~12 dB of
# echo-over-floor the result is meaningless, so say so rather than print a
# verdict the number cannot support.
headroom = raw - floor
if headroom < 12:
    print(f"\n  MEASUREMENT INVALID -- the echo is only {headroom:.1f} dB above the room")
    print("  noise floor, so this is measuring noise, not cancellation. It does")
    print("  NOT mean the canceller is broken. Turn the speaker up, quieten the")
    print("  room, or move the mic nearer the speaker, then re-run.")
    if aec <= floor + 2:
        print("\n  (Encouraging sign: the cancelled signal sits at or below the room")
        print("   floor, which is the best any canceller can do.)")
    sys.exit(0)

if raw < -70:
    print("\n  The raw recording is near silent -- the speaker was not actually")
    print("  playing, or the mic is not the one picking up the room. The ERLE")
    print("  number above is meaningless; fix that first.")
    sys.exit(1)

erle = raw - aec
if   erle <  6: v = "NOT WORKING -- almost certainly a routing error. Playback is\n         not going through aec_sink, so the canceller has no reference."
elif erle < 15: v = "Weak. Check analog_gain_control=0 took effect, and lower the\n         speaker volume."
elif erle < 25: v = "Acceptable -- self-interruption should stop."
elif erle < 40: v = "Good. This is what a correct setup looks like."
else:           v = "Excellent (verify the raw recording really wasn't silent)."
print(f"\n  {v}")
PY

printf '\n  recordings kept in %s -- listen to aec.wav; the tone should be\n' "$OUT"
printf '  dramatically quieter than the room sounded.\n\n'
