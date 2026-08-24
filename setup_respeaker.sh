#!/usr/bin/env bash
# Configure the ReSpeaker 4 Mic Array (UAC1.0, USB 2886:0018) for voice chat.
#
# MEASURED 2026-08-18: this unit's firmware AEC does nothing useful. With the
# same speech played through the array's own aux output, ch0 (the channel the
# firmware calls "processed for ASR") measured RMS 201.6 against 184.7 for the
# raw mics -- no cancellation at all. Routing the RAW mics through PulseAudio's
# webrtc canceller instead measured 25.7, roughly 18 dB better.
#
# So the chain is:
#     multichannel-input ch1-4 --remap--> respeaker.raw
#     respeaker.raw + aux out --echo-cancel--> respeaker.echo-cancel / respeaker
#
# Software AEC does the work; the array is just four microphones. Windows does
# this same job invisibly in its driver, which is why the app needs no audio
# setup there and all of this here.
#
# Based on Shulyaka's config in the Seeed issue tracker, adapted for
# PulseAudio 15.99 (see the notes at steps 4 and 5).
#
# An earlier version of this file claimed channels 2-5 were dead. That was
# measured while the array was dropping off USB and is wrong -- all six
# channels carry signal when the device is connected properly.
#
# HARDWARE: the speaker must be in the ReSpeaker's 3.5mm AUX jack, so that
# playback and the AEC reference are the same physical device.
 
set -uo pipefail
 
MIC_VOL=84    # capture gain %
SPK_VOL=65    # playback %  -- keep moderate; loud output raises the echo floor
              # beyond what any canceller removes cleanly
 
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()  { printf '  \033[32mOK\033[0m  %s\n' "$*"; }
bad() { printf '  \033[31mXX\033[0m  %s\n' "$*"; }
 
say "1. Looking for the ReSpeaker"
CARD=$(pactl list short cards 2>/dev/null | grep -i respeaker | awk '{print $2}' | head -1)
[ -z "$CARD" ] && { bad "No ReSpeaker card. Plug it in and re-run."; exit 1; }
ok "card: $CARD"
 
# Re-enumeration count: USB bumps the device number on every reconnect. A high
# number relative to other devices means the array is dropping off the bus,
# which unloads every module built on top of it (see step 4).
DEVNUM=$(lsusb 2>/dev/null | grep -i seeed | grep -oE "Device [0-9]+" | grep -oE "[0-9]+")
[ -n "$DEVNUM" ] && printf '      (USB device number %s -- if this climbs between runs, the array is re-enumerating)\n' "$DEVNUM"
 
say "2. Clearing previous modules"
for i in $(pactl list short modules | grep -E "module-echo-cancel|module-remap-source" | awk '{print $1}' | tac); do
  pactl unload-module "$i" 2>/dev/null && ok "unloaded module #$i"
done
 
say "3. Card profile: 6-channel input + analog output"
# The profile that exposes all 6 firmware channels is named differently per
# audio server: PulseAudio calls it multichannel-input, PipeWire has no such
# mapping and instead surfaces the same 6 channels as analog-surround-51
# (5.1 = FL,FR,RL,RR,FC,LFE -- the exact firmware layout). pro-audio is the
# last resort: raw, unmixed, but it renames the source. Try in that order.
#
# The output half must be analog-stereo, NOT iec958. iec958 is digital S/PDIF
# and produces no signal at the 3.5mm jack, so the XVF-3000 generates nothing
# to use as its AEC reference and channe-l 0 comes back uncancelled.
PROFILES_AVAILABLE=$(pactl list cards 2>/dev/null | sed -n "/Name: $CARD\$/,/^Card #/p")
PROFILE=""
for CANDIDATE in \
    "output:analog-stereo+input:multichannel-input" \
    "output:analog-stereo+input:analog-surround-51" \
    "pro-audio"
do
  if printf '%s' "$PROFILES_AVAILABLE" | grep -qF "$CANDIDATE:"; then
    PROFILE="$CANDIDATE"
    break
  fi
done
if [ -z "$PROFILE" ]; then
  bad "No 6-channel profile found. Profiles this card offers:"
  printf '%s' "$PROFILES_AVAILABLE" | grep -E "^\s+[a-z].*sources: [1-9]" | sed 's/^/      /'
  exit 1
fi
pactl set-card-profile "$CARD" "$PROFILE" && ok "$PROFILE"
sleep 1
 
# Locate the source by channel count rather than by name: the name varies with
# the profile that produced it (.multichannel-input / .analog-surround-51 /
# .pro-input-0), but it is always the only ReSpeaker source carrying 6ch.
MASTER_SRC=""
for S in $(pactl list short sources | grep -i respeaker | grep -vi monitor | awk '{print $2}'); do
  if pactl list sources | grep -A6 "Name: $S\$" | grep -q "6ch"; then
    MASTER_SRC="$S"
    break
  fi
done
MASTER_SNK=$(pactl list short sinks | grep -i respeaker | grep -vi iec958 | awk '{print $2}' | head -1)
[ -z "$MASTER_SRC" ] && { bad "no 6-channel source after setting profile $PROFILE"; exit 1; }
[ -z "$MASTER_SNK" ] && { bad "no analog (aux) sink -- speaker output will be silent"; exit 1; }
 
# The remap below addresses channel 0 by its channel-map position, so confirm
# the map really starts at front-left before trusting it.
CHMAP=$(pactl list sources | grep -A6 "Name: $MASTER_SRC\$" | grep "Channel Map" | head -1 | sed 's/.*Channel Map: //')
case "$CHMAP" in
  front-left,*) ok "channel map: $CHMAP" ;;
  *)            bad "unexpected channel map: $CHMAP (expected front-left first -- ch0 may not be the processed channel)" ;;
esac
 
say "4. Splitting the array into raw mics and the processed channel"
# 6ch map is FL,FR,RL,RR,FC,LFE == ch0..ch5.
# ch0  = firmware "processed for ASR" channel
# ch1-4 = the four raw microphones
# ch5  = playback reference
#
# MEASURED 2026-08-18: ch0's firmware AEC does nothing useful here -- while the
# speaker played, ch0 read RMS 201.6 versus 184.7 for the raw mics. So we feed
# the RAW mics to PulseAudio's webrtc canceller instead of stacking a second
# canceller on top of ch0. That measured 25.7 -- about 18 dB better.
pactl load-module module-remap-source source_name=respeaker.raw master="$MASTER_SRC" \
  master_channel_map=front-right,rear-left,front-center,rear-right \
  channel_map=front-left,front-right,rear-left,rear-right remix=false >/dev/null \
  && ok "respeaker.raw   <- ch1-4 (raw mics)" || { bad "raw remap failed"; exit 1; }
 
# Kept for comparison/debugging; nothing routes through it by default.
pactl load-module module-remap-source source_name=respeaker.voice master="$MASTER_SRC" \
  master_channel_map=front-left channel_map=mono remix=false >/dev/null \
  && ok "respeaker.voice <- ch0 (firmware, for comparison)"
 
say "5. Software echo cancellation over the raw mics"
# Two gotchas, both verified on PulseAudio 15.99.1:
#  * digital_gain_control and transient_noise_suppression do NOT exist in this
#    webrtc build -- including either one fails the module.
#  * aec_args needs literal single quotes. pactl re-joins argv into one string,
#    so an unquoted space makes the parser read noise_suppression=1 as a stray
#    top-level argument and initialisation fails.
pactl load-module module-echo-cancel source_name=respeaker.echo-cancel \
  source_master=respeaker.raw sink_name=respeaker sink_master="$MASTER_SNK" \
  use_volume_sharing=true use_master_format=true aec_method=webrtc \
  aec_args="'analog_gain_control=0 noise_suppression=1'" save_aec=false >/dev/null \
  && ok "respeaker.echo-cancel / respeaker" || { bad "echo-cancel failed"; exit 1; }
 
pactl set-default-source respeaker.echo-cancel && ok "default source: respeaker.echo-cancel"
pactl set-default-sink   respeaker             && ok "default sink:   respeaker"
 
say "6. Levels"
# Loading modules resets volumes to whatever stream-restore remembers, which
# has landed on 33% mic / 117% speaker before -- both wrong for AEC.
for s in respeaker "$MASTER_SNK"; do pactl set-sink-volume   "$s" "${SPK_VOL}%" 2>/dev/null; done
for s in respeaker.echo-cancel respeaker.raw "$MASTER_SRC"; do pactl set-source-volume "$s" "${MIC_VOL}%" 2>/dev/null; done
ok "mic ${MIC_VOL}%  speaker ${SPK_VOL}%"
 
say "Done"
printf '  source : %s\n' "$(pactl get-default-source)"
printf '  sink   : %s\n' "$(pactl get-default-sink)"
printf '\n  Speaker must be in the ReSpeaker AUX jack.\n'
printf '  Start main.py AFTER this script -- PortAudio resolves "default" once, at stream open.\n'
 
 