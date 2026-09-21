#!/usr/bin/env bash
# Software AEC for a plain mic + external USB speaker -- no ReSpeaker involved.
#
# This is the same job setup_respeaker.sh does, minus the array. There the
# script had to split six firmware channels apart first; here the mic is
# already one ordinary capture device, so it goes straight into PulseAudio's
# webrtc canceller:
#
#     mic --------------------\
#                              module-echo-cancel --> aec_source  [default source]
#     main.py --> aec_sink ---/          |
#                                        \--> USB speaker --> (room) --> mic
#
# CLOCKS MATTER. The canceller subtracts a predicted echo from the capture
# stream, which only works while reference and capture stay time-aligned. Two
# USB/PCI devices run off two independent crystals and drift apart, so the
# filter spends its time chasing the delay instead of modelling the room.
# Prefer the USB dongle's own mic jack (mic=usb): one device, one clock, no
# drift. That -- not the DSP -- is also why the ReSpeaker needed its speaker in
# its own AUX jack.
#
# Usage:
#   ./setup_aec_usb.sh            # mic on the USB dongle's jack (recommended)
#   ./setup_aec_usb.sh aux        # mic on the laptop's 3.5mm jack
#   ./setup_aec_usb.sh --undo     # tear it all down again
#
# HARDWARE: clip-on mic in the USB dongle's pink/mic socket, speaker in its
# green/line-out socket.

set -uo pipefail

MIC_VOL=84    # capture gain %
SPK_VOL=60    # playback %  -- keep moderate; loud output raises the echo floor
              # beyond what any canceller removes cleanly

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()  { printf '  \033[32mOK\033[0m  %s\n' "$*"; }
bad() { printf '  \033[31mXX\033[0m  %s\n' "$*"; }

MODE="${1:-usb}"

# ---------------------------------------------------------------- undo --
if [ "$MODE" = "--undo" ] || [ "$MODE" = "undo" ]; then
  say "Unloading AEC modules"
  for i in $(pactl list short modules | grep -E "module-echo-cancel" | awk '{print $1}' | tac); do
    pactl unload-module "$i" 2>/dev/null && ok "unloaded module #$i"
  done
  SNK=$(pactl list short sinks   | grep -iv monitor | grep -i "usb-GeneralPlus" | awk '{print $2}' | head -1)
  SRC=$(pactl list short sources | grep -iv monitor | grep -i "usb-GeneralPlus" | awk '{print $2}' | head -1)
  [ -n "$SNK" ] && pactl set-default-sink   "$SNK" && ok "default sink   -> $SNK"
  [ -n "$SRC" ] && pactl set-default-source "$SRC" && ok "default source -> $SRC"
  printf '\n  Persistence (if installed): rm ~/.config/pulse/default.pa && pulseaudio -k\n\n'
  exit 0
fi

say "1. Checking the audio server"
SERVER=$(pactl info 2>/dev/null | grep "Server Name" | cut -d: -f2- | xargs)
[ -z "$SERVER" ] && { bad "PulseAudio is not responding."; exit 1; }
case "$SERVER" in
  # "PulseAudio (on PipeWire 1.0.5)" is PipeWire despite the prefix, and it
  # re-implements module-echo-cancel with a different argument set.
  *PipeWire*) bad "$SERVER -- this script targets real PulseAudio. Use the PipeWire config drop-in (guide Path B)."; exit 1 ;;
esac
ok "$SERVER"

# Both engines ship in Ubuntu's build, but webrtc is the only one worth using:
# speex is mono-only and falls apart during double-talk.
#
# Capture the output first, THEN match it. Piping straight into `grep -q` under
# `set -o pipefail` reports failure even on a match: grep -q exits at the first
# hit, `strings` then dies of SIGPIPE (141), and pipefail surfaces that as the
# pipeline's status. The check ends up claiming webrtc is missing precisely
# because it IS there and was found early.
AEC_ENGINES=$(strings /usr/lib/pulse-*/modules/module-echo-cancel.so 2>/dev/null | grep -xE "webrtc|speex")
case "$AEC_ENGINES" in
  *webrtc*) ok "webrtc engine available" ;;
  *)        bad "webrtc AEC not compiled into this module -- apt install libwebrtc-audio-processing1"; exit 1 ;;
esac

say "2. Clearing previous modules"
for i in $(pactl list short modules | grep -E "module-echo-cancel" | awk '{print $1}' | tac); do
  pactl unload-module "$i" 2>/dev/null && ok "unloaded module #$i"
done

say "3. Finding the speaker"
CARD=$(pactl list short cards | grep -i "usb-GeneralPlus" | awk '{print $2}' | head -1)
[ -z "$CARD" ] && { bad "USB audio device not found. Plug it in and re-run."; exit 1; }

# analog-stereo is the 3.5mm line-out; iec958 is digital S/PDIF. MEASURED on
# this dongle by playing a tone to each endpoint and recording the room: analog
# came back +6.5 dB over the noise floor, iec958 only +2.1 dB -- i.e. silent.
# GNOME will happily select iec958, which leaves the speaker dead AND gives the
# canceller a reference for audio nobody can hear, so force analog here.
# Set unconditionally: aux mode doesn't need the dongle's mic, but it still
# needs the analog SINK to exist.
pactl set-card-profile "$CARD" output:analog-stereo+input:mono-fallback 2>/dev/null \
  && ok "profile: analog out + mono in" \
  || bad "could not set combined profile (continuing with whatever is active)"
sleep 1

MASTER_SNK=$(pactl list short sinks | grep -i "usb-GeneralPlus" | grep -vi iec958 | awk '{print $2}' | head -1)
[ -z "$MASTER_SNK" ] && { bad "no analog sink on the USB device -- speaker would be silent"; exit 1; }
ok "speaker: $MASTER_SNK"

say "4. Finding the microphone"
case "$MODE" in
  usb)
    MASTER_SRC=$(pactl list short sources | grep -vi monitor | grep -i "usb-GeneralPlus" | awk '{print $2}' | head -1)
    [ -z "$MASTER_SRC" ] && {
      bad "no capture device on the USB dongle."
      bad "Is the mic in its mic socket? Otherwise re-run as: $0 aux"
      exit 1
    }
    ok "mic: $MASTER_SRC  (same clock as the speaker -- no drift)"
    ;;
  aux)
    MASTER_SRC=$(pactl list short sources | grep -vi monitor | grep -i "alsa_input.pci" | awk '{print $2}' | head -1)
    [ -z "$MASTER_SRC" ] && { bad "no laptop analog input found"; exit 1; }
    ok "mic: $MASTER_SRC"
    # The combo jack and the built-in mic are the SAME source -- they differ
    # only by active port. Cancelling the laptop's internal mic instead of the
    # clip-on would look identical in every pactl listing, so check explicitly.
    # awk, not `grep -A<n>`: Active Port sits ~48 lines below the name here,
    # but the offset moves with however many properties and ports a card has.
    # Scan from the name to the first Active Port and stop -- no magic number.
    PORT=$(pactl list sources | awk -v n="Name: $MASTER_SRC" \
           '$0 ~ n {f=1} f && /Active Port:/ {sub(/.*Active Port: */,""); print; exit}')
    case "$PORT" in
      *headset*|*headphone*) ok "port: $PORT (the clip-on)" ;;
      *) bad "port: $PORT -- that is NOT the headset jack. Select the headset"
         bad "microphone in Settings > Sound > Input, then re-run." ;;
    esac
    bad "mic and speaker are on separate clocks -- expect weaker, drifting"
    bad "cancellation. Move the mic to the USB dongle's jack and re-run without 'aux'."
    ;;
  *)
    bad "unknown mode '$MODE' -- use: usb | aux | --undo"; exit 1 ;;
esac

say "5. Loading the echo canceller"
# Two gotchas, both verified on PulseAudio 15.99.1 (same build setup_respeaker.sh
# is written against):
#  * digital_gain_control and transient_noise_suppression do NOT exist in this
#    webrtc build -- including either one fails the module load outright.
#  * aec_args needs literal single quotes inside the double quotes. pactl
#    re-joins argv into one string, so an unquoted space makes the parser read
#    noise_suppression=1 as a stray top-level argument and init fails.
#  * NO source_properties/sink_properties here. Because pactl re-joins argv and
#    re-tokenizes, a second quoted value collides with the quoted aec_args above
#    and the module fails to initialise -- verified: adding
#    source_properties="device.description='AEC Microphone'" to this exact
#    command turns a working load into "Module initialization failed", and no
#    quoting style for the description survives (double quotes and backslash
#    escapes both fail; only a space-free value works). Omitting them is better
#    anyway: PulseAudio then generates its own description, which is more
#    informative than a hand-written one --
#    "USB Audio Device Mono (echo cancelled with USB Audio Device Analog Stereo)".
#
# analog_gain_control=0 is the important one: analog AGC physically moves the
# preamp gain, which changes the echo path mid-stream and forces the adaptive
# filter to re-converge -- you hear a burst of echo on every adjustment.
pactl load-module module-echo-cancel \
  aec_method=webrtc \
  source_name=aec_source sink_name=aec_sink \
  source_master="$MASTER_SRC" sink_master="$MASTER_SNK" \
  use_volume_sharing=true \
  aec_args="'analog_gain_control=0 noise_suppression=1 high_pass_filter=1 extended_filter=1 voice_detection=1'" \
  >/dev/null \
  && ok "aec_source / aec_sink" || { bad "echo-cancel failed to load"; exit 1; }

# BOTH directions, or nothing works. A cancelled mic with raw playback gives
# the canceller no reference signal and cancels exactly nothing -- while
# 'pactl list modules' cheerfully shows it loaded.
pactl set-default-source aec_source && ok "default source: aec_source"
pactl set-default-sink   aec_sink   && ok "default sink:   aec_sink"

say "6. Levels"
# Loading modules resets volumes to whatever stream-restore remembers, which
# has landed on 33% mic / 117% speaker before -- both wrong for AEC.
for s in aec_sink "$MASTER_SNK"; do pactl set-sink-volume   "$s" "${SPK_VOL}%" 2>/dev/null; done
for s in aec_source "$MASTER_SRC"; do pactl set-source-volume "$s" "${MIC_VOL}%" 2>/dev/null; done
ok "mic ${MIC_VOL}%  speaker ${SPK_VOL}%"

say "Done"
printf '  source : %s\n' "$(pactl get-default-source)"
printf '  sink   : %s\n' "$(pactl get-default-sink)"
printf '\n  Measure it before trusting it -- "module loaded" is not "echo cancelled":\n'
printf '    ./check_aec.sh\n'
printf '\n  Start main.py AFTER this script -- PortAudio resolves "default" once, at stream open:\n'
printf '    PULSE_SOURCE=aec_source PULSE_SINK=aec_sink uv run python/main.py\n\n'
