# ReSpeaker 4 Mic Array — Fresh Jetson Setup Guide

Verified working 2026-08-24 on a **Jetson Orin Nano Developer Kit (Super), JetPack 6**
(PipeWire 1.0.5 / PulseAudio 16.1 available). The same steps should apply to any
JetPack 6 image.

## Why this guide exists

JetPack 6 runs **PipeWire** as its audio server, pretending to be PulseAudio
(`pulseaudio --version` reports 16.1, but `pactl list` tags every device
`PipeWire`). The setup script loads without any error under PipeWire, **but
PipeWire's `module-echo-cancel` performs no usable echo cancellation** — the mic
hears the robot's own speaker at full strength. Verified even though
`libspa-aec-webrtc.so` is installed.

The fix: switch the Jetson to **real PulseAudio** (already installed on the
JetPack image, just not active). With real PulseAudio running, `setup_respeaker.sh`
works identically to the Ubuntu laptop — no script changes needed.

## Hardware checklist (before any software)

- ReSpeaker 4 Mic Array (UAC1.0, USB `2886:0018`) into a USB port — short,
  good-quality cable, no extensions.
- **Speaker into the ReSpeaker's 3.5mm AUX jack.** Not the Jetson's own audio
  out. Playback and the AEC reference must be the same physical device or
  cancellation is impossible.
- Power the Jetson from the proper DC supply. If the array keeps dropping off
  USB (see Troubleshooting), put it behind a **powered USB hub**.

## Step 1 — Switch audio from PipeWire to real PulseAudio

Run as the normal user (no sudo on the `systemctl --user` lines):

```bash
systemctl --user mask pipewire pipewire.socket pipewire-pulse pipewire-pulse.socket wireplumber
systemctl --user stop pipewire pipewire.socket pipewire-pulse pipewire-pulse.socket wireplumber
systemctl --user unmask pulseaudio.service pulseaudio.socket 2>/dev/null
systemctl --user enable --now pulseaudio.service pulseaudio.socket
sudo reboot
```

After reboot, verify:

```bash
pactl info | grep -E "Server Name|Server Version"
```

Must print `Server Name: pulseaudio` — **not** "PulseAudio (on PipeWire)".
If it still says PipeWire, the masks didn't take; re-run step 1 and reboot again.

> Trade-off: masking PipeWire breaks GNOME screen-sharing / remote-desktop
> capture on the Jetson. Audio and the voice app are unaffected. To revert:
> `systemctl --user unmask` the same units and reboot.

## Step 2 — Copy and run the setup script

Copy `setup_respeaker.sh` from this repo to the Jetson (e.g. `~/setup_respeaker.sh`),
then:

```bash
bash ~/setup_respeaker.sh
```

Every step should print green `OK`. Notes:

- On the laptop the card profile resolves to `input:multichannel-input`; on
  other stacks the script's fallback picks `input:analog-surround-51`. Both are
  correct — the script handles this automatically. (Do **not** use the old
  trimmed `setup_respeaker_jetson.sh`; it lacks the fallback and dies at step 3.)
- Final lines must show:
  - `source : respeaker.echo-cancel`
  - `sink   : respeaker`

## Step 3 — Prove the echo cancellation works

With the speaker in the ReSpeaker AUX jack:

```bash
paplay --device=respeaker /usr/share/sounds/alsa/Front_Center.wav &
parecord --device=respeaker.echo-cancel --rate=16000 --channels=1 /tmp/aec_test.wav
```

Ctrl+C after ~5 seconds, then listen:

```bash
paplay /tmp/aec_test.wav
```

The "Front Center" voice should be quiet or nearly gone; your own voice (if you
spoke) should be clear. If the played voice is loud, AEC is not working — check
`pactl info` again (step 1) before anything else.

## Step 4 — Start the app

```bash
# always AFTER the setup script:
python main.py
```

Order matters: PortAudio resolves the "default" devices **once, when the stream
opens**. If the app starts before the script (or before a replug is fixed), it
binds to the raw hardware and captures uncancelled audio until restarted.

While the robot is speaking you can sanity-check routing:

```bash
pactl list short sink-inputs   # the app's stream must sit on the "respeaker" sink
```

## Troubleshooting

### Mic hears the robot's own voice again
In order of likelihood:
1. **Defaults got reset.** Any reboot or USB re-enumeration points the defaults
   back at the raw hardware. Check `pactl get-default-source` (want
   `respeaker.echo-cancel`) and `pactl get-default-sink` (want `respeaker`).
   Fix: re-run `setup_respeaker.sh`, then **restart the app**.
2. **App started before the script.** Restart the app.
3. **PipeWire came back** (e.g. after a system update). Check
   `pactl info | grep "Server Name"`; redo step 1 if needed.
4. **Speaker not in the ReSpeaker AUX jack.**

### ReSpeaker disappears (`pactl list cards` shows no respeaker)
```bash
lsusb | grep -i 2886        # empty = array is off the USB bus: power/cable problem
sudo dmesg | grep -iE "usb" | tail -30
```
Repeated `USB disconnect` / `reset ... device` lines mean power or cable. Use a
powered hub and a short cable. The script prints the USB device number on each
run — if it climbs between runs, the array is re-enumerating. After the device
is stable on the bus, re-run the setup script (it clears stale modules first).

### Script fails at step 3 ("No 6-channel profile found")
The card is present but in a bad state or half-enumerated. Replug the array,
wait 5 s, re-run. If it persists, check `pactl list cards | grep -iA30 respeaker`
to see which profiles the card is actually offering.

### Everything must survive reboots
The pactl modules and defaults do **not** persist. Until an autostart unit is
set up, `setup_respeaker.sh` must be re-run after every boot and every USB
replug, followed by an app restart. (Recommended next step: a systemd user
service for boot plus a udev-triggered re-run on device plug.)

## Quick reference — known-good state

| Check | Expected |
|---|---|
| `pactl info` server name | `pulseaudio` (16.x) |
| `pactl get-default-source` | `respeaker.echo-cancel` |
| `pactl get-default-sink` | `respeaker` |
| `pactl list short modules \| grep -cE "echo\|remap"` | `3` |
| `lsusb \| grep -i 2886` | one Seeed device line |
| Speaker location | ReSpeaker 3.5mm AUX jack |
