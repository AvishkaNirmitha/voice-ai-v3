cat > ~/setup_respeaker.sh <<'SCRIPT_EOF'
#!/usr/bin/env bash
# ReSpeaker 4 Mic Array (UAC1.0, USB 2886:0018) -> webrtc AEC on the raw mics.
#
# The array's firmware AEC does not work. Measured on identical hardware:
# ch0 (the channel the firmware calls "processed for ASR") read RMS 201.6 while
# the speaker played, against 184.7 for the raw mics -- no cancellation at all.
# Feeding the RAW mics to PulseAudio's webrtc canceller measured 25.7, ~18 dB
# better. So ch0 is ignored and ch1-4 are used instead.
#
# HARDWARE: the speaker MUST be in the array's 3.5mm AUX jack, so that playback
# and the AEC reference are the same physical device.
#
# Based on Shulyaka's config in the Seeed issue tracker, adapted for PA 15.99.
 
set -uo pipefail
MIC_VOL=84
SPK_VOL=65
 
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()  { printf '  \033[32mOK\033[0m  %s\n' "$*"; }
bad() { printf '  \033[31mXX\033[0m  %s\n' "$*"; }
 
say "1. Looking for the ReSpeaker"
CARD=$(pactl list short cards 2>/dev/null | grep -i respeaker | awk '{print $2}' | head -1)
[ -z "$CARD" ] && { bad "No ReSpeaker card. Plug it in and re-run."; exit 1; }
ok "card: $CARD"
DEVNUM=$(lsusb 2>/dev/null | grep -i seeed | grep -oE "Device [0-9]+" | grep -oE "[0-9]+")
[ -n "$DEVNUM" ] && printf '      (USB device number %s -- if this climbs between runs, the array is re-enumerating)\n' "$DEVNUM"
 
say "2. Clearing previous modules"
for i in $(pactl list short modules | grep -E "module-echo-cancel|module-remap-source" | awk '{print $1}' | tac); do
  pactl unload-module "$i" 2>/dev/null && ok "unloaded module #$i"
done
 
say "3. Card profile: multichannel input + analog output"
PROFILE=$(pactl list cards 2>/dev/null | sed -n "/Name: $CARD\$/,/^Card #/p" \
  | grep -oE "output:analog-stereo\+input:multichannel-input" | head -1)
[ -z "$PROFILE" ] && { bad "multichannel profile not found"; exit 1; }
pactl set-card-profile "$CARD" "$PROFILE" && ok "$PROFILE"
sleep 1
 
MASTER_SRC=$(pactl list short sources | grep -i respeaker | grep -i multichannel | awk '{print $2}' | head -1)
MASTER_SNK=$(pactl list short sinks   | grep -i respeaker | grep -i analog       | awk '{print $2}' | head -1)
[ -z "$MASTER_SRC" ] && { bad "no multichannel source"; exit 1; }
[ -z "$MASTER_SNK" ] && { bad "no aux sink"; exit 1; }
 
say "4. Splitting the array into raw mics and the processed channel"
# 6ch map is FL,FR,RL,RR,FC,LFE == ch0..ch5.  ch1-4 are the four raw mics.
pactl load-module module-remap-source source_name=respeaker.raw master="$MASTER_SRC" \
  master_channel_map=front-right,rear-left,front-center,rear-right \
  channel_map=front-left,front-right,rear-left,rear-right remix=false >/dev/null \
  && ok "respeaker.raw   <- ch1-4 (raw mics)" || { bad "raw remap failed"; exit 1; }
 
pactl load-module module-remap-source source_name=respeaker.voice master="$MASTER_SRC" \
  master_channel_map=front-left channel_map=mono remix=false >/dev/null \
  && ok "respeaker.voice <- ch0 (firmware, for comparison only)"
 
say "5. Software echo cancellation over the raw mics"
# Two gotchas verified on PulseAudio 15.99.1:
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
for s in respeaker "$MASTER_SNK"; do pactl set-sink-volume "$s" "${SPK_VOL}%" 2>/dev/null; done
for s in respeaker.echo-cancel respeaker.raw "$MASTER_SRC"; do pactl set-source-volume "$s" "${MIC_VOL}%" 2>/dev/null; done
ok "mic ${MIC_VOL}%  speaker ${SPK_VOL}%"
 
say "Done"
printf '  source : %s\n' "$(pactl get-default-source)"
printf '  sink   : %s\n' "$(pactl get-default-sink)"
printf '\n  Speaker must be in the ReSpeaker AUX jack.\n'
printf '  Start the app AFTER this script -- PortAudio resolves "default" once, at stream open.\n'
SCRIPT_EOF
chmod +x ~/setup_respeaker.sh && echo "written to ~/setup_respeaker.sh"
 