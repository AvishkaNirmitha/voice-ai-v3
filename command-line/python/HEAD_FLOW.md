# `main_with_head.py` — flow and head movement reference

Voice conversation with a Gemini Live session, spoken through Piper, with a
two-axis (pan/tilt) neck driven in sync with the speech. `head.py` owns all of
the motion; `main_with_head.py` only reports events to it.

```
python main_with_head.py                     # window + hardware if present
python main_with_head.py --no-window         # headless (Jetson)
python main_with_head.py --no-head           # simulation only
```

---

## 1. What is running

Five concurrent workers. The split is not incidental — each boundary exists to
keep a blocking call out of something that must not stall.

| Worker | Started by | Does | Why it is separate |
|---|---|---|---|
| asyncio event loop | `run()` TaskGroup | `listen_audio`, `send_realtime`, `receive_audio` | non-blocking mic + websocket I/O |
| `speak_worker` | `asyncio.to_thread` | Piper ONNX synthesis, audio playback | `voice.synthesize` blocks; it would stall the mic and the websocket |
| `HeadMotion._run` | `HEAD.start()` | 50 Hz pose mixer, servo write | a servo write inside the audio loop eats the audio budget → underruns |
| `HeadWindow._run` | `run()`, optional | Tk visualiser | Tk demands its own thread; skipped with `--no-window` |
| `RobotHeadController` | rides the motion thread | 25 Hz UDP jog to the neck | halves the rate; the neck cannot follow faster |

Startup order in `run()`:

```
HEAD.start()                    motion thread begins at 50 Hz
   │
   ├─ head_hw.apply_limits()    ask the neck its real travel (blocks ≤2 s,
   │                            so it runs in a thread); mixer clamps to it
   ├─ HeadWindow(HEAD).start()  unless --no-window
   ├─ speak_worker              on its own thread
   └─ client.aio.live.connect() → TaskGroup: send_realtime
                                              listen_audio
                                              receive_audio
```

---

## 2. The full pipeline

One sentence's journey, and which thread owns each stage.

```
  ASYNCIO EVENT LOOP              SPEAK_WORKER THREAD           MOTION THREAD 50 Hz
 ┌──────────────────────┐
 │ Microphone           │
 │ 16 kHz, 1024 frames  │  pyaudio
 └──────────┬───────────┘
            │ audio_queue_mic (maxsize 5)
            ▼
 ┌──────────────────────┐
 │ GEMINI LIVE API      │  gemini-3.1-flash-live-preview
 │ response_modalities  │  = AUDIO   ← the audio is DISCARDED
 │ output_transcription │  ← only the transcript is used
 └──────────┬───────────┘
            │ text fragments
            ▼
 ┌──────────────────────┐
 │ split_speakable()    │  cut on . ! ?
 │ text_buffer          │  …or the last "," once past 60 chars
 └──────────┬───────────┘
            │ one sentence
            ▼
 ┌──────────────────────┐
 │ enqueue()            │
 │  strip_tags()        │  "[deny] I cannot fly, sir."
 │  plan_sentence()     │        └─tag──┘ └── clean text ──┘
 │                      │  → Plan(gesture, duration, text, reason)
 └──────────┬───────────┘
            │ sentence_queue.put((turn_id, text, plan))
            └──────────────────►┌───────────────────────┐
                                │ begin_gesture(plan)   │──── gesture ────►┐
                                │  BEFORE synthesis     │                  │
                                └───────────┬───────────┘                  │
                                            ▼                              │
                                ┌───────────────────────┐                  │
                                │ voice.synthesize()    │  blocks ~200 ms  │
                                │ Piper ONNX            │  ← that gap IS   │
                                └───────────┬───────────┘    the wind-up   │
                                            ▼                              │
                                ┌───────────────────────┐                  │
                                │ for each 30 ms slice: │                  │
                                │   push_rms(level) ────┼──── loudness ───►│
                                │   stream.write() 🔊   │                  │
                                └───────────┬───────────┘                  │
                                            ▼                              │
                                ┌───────────────────────┐                  │
                                │ end_speech()          │──── settle ─────►│
                                └───────────────────────┘                  │
                                                                           ▼
                                                            ┌──────────────────────┐
                                                            │  HeadMotion mixer    │
                                                            │  50 Hz — section 4   │
                                                            └──────────┬───────────┘
                                                                       ▼
                                                          controller.write(pan, tilt, active)
                                                                 │              │
                                                            Tk window      real neck
```

**Why `begin_gesture` comes before synthesis, not after.** `voice.synthesize`
blocks for a couple of hundred milliseconds. Starting the gesture first spends
that time as the wind-up, so the motion *lands on* the first word instead of
trailing it.

---

## 3. Choosing a gesture

Two sources compete for every sentence, and `plan_sentence()` resolves them.

```
                          sentence text
                                │
             ┌──────────────────┴──────────────────┐
             ▼                                     ▼
 ┌───────────────────────┐             ┌───────────────────────────┐
 │ MODEL'S INTENT TAG    │             │ KEYWORD LADDER _by_text() │
 │ the prompt demands    │             │ English-only, checked in  │
 │ exactly one per       │             │ this order:               │
 │ sentence, at the      │             │                           │
 │ front:                │             │  ends "?"      → query    │
 │                       │             │  ends "!"      → nod_hard │
 │  [deny]   → shake     │             │  opens no/not  → shake    │
 │  [affirm] → nod       │             │  is_refusal()  → shake    │
 │  [ask]    → query     │             │  is_limitation()→ shake   │
 │  [neutral]→ calm      │             │  under 18 chars→ calm     │
 │                       │             │  else          → nod      │
 └───────────┬───────────┘             └─────────────┬─────────────┘
             │                                       │
             │  committed tag wins                   │  always computed,
             │                                       │  even when a tag exists
             └──────────────────┬────────────────────┘
                                ▼
                 ┌─────────────────────────────────┐
                 │ plan_sentence() resolution      │
                 ├─────────────────────────────────┤
                 │ 1. no tag        → ladder       │
                 │ 2. [deny]/[affirm]/[ask] → tag  │
                 │ 3. [neutral] LOSES to a         │
                 │    definite text signal         │
                 │    (question / exclamation /    │
                 │     refusal / negation opener)  │
                 │ 4. inherited [deny] on a        │
                 │    trailing clause fades to     │
                 │    the ladder                   │
                 │ 5. disagreements recorded in    │
                 │    TAG_DISAGREEMENTS            │
                 └────────────────┬────────────────┘
                                  ▼
                    Plan(gesture, duration, text, reason)
```

**Why `[neutral]` is distrusted.** It is the prompt's catch-all, so it is what
the model reaches for when it has not really decided — in one real session it
came back on plain questions and outright refusals alike, 12 sentences out of
19. The other three tags are commitments, and those have held up.

**Why an inherited `[deny]` fades.** The model tags whole sentences, but
`split_speakable` cuts at commas past 60 chars. `"[deny] I cannot fly, sir, /
as I operate on the ground."` hands the second fragment a refusal it does not
contain, and the head keeps shaking through the explanation. A person shakes
once, on the refusal, then talks normally through the reason.

**Sizing.** Both come from the text length:

```
duration = clamp(len(text) / 13.5, 0.5, 9.0)          seconds
cycles   = max(1.0, round(rate × GESTURE_RATE_SCALE × duration))
```

`cycles` is rounded to a **whole** number. Because a gesture is now left where
it ends (§5.6), where it ends matters: a fractional cycle would strand a shake
mid-sweep and the head would sit cocked to one side until the next sentence.

---

## 4. The 50 Hz mixer

`HeadMotion._frame()`. Four sources are summed, then bounded.

```
  STATE_POSE[state] ──► eased 10 %/frame ──┐   posture glides
                                            │
  held pose from the last gesture ─────────┤   crossfaded out as a new
                                            │   gesture takes over
  gesture fn(u, amp, cycles) ──────────────┤   NOT eased
                                            │
  RMS accent   tilt −9.0° × envelope ──────┤   attack 0.55 / decay 0.12
                                            │
  breath   0.18 Hz sine ───────────────────┤   ±1.5° idle, ±0.4° busy
                                            │
                                            ▼
                                          Σ sum
                                            │
                                            ▼
                              ┌──────────────────────────┐
                              │ clamp to the neck's      │
                              │ real travel              │
                              └────────────┬─────────────┘
                                           ▼
                              ┌──────────────────────────┐
                              │ slew limit ≤ 420 °/s     │
                              │ = 8.4° per frame         │
                              └────────────┬─────────────┘
                                           ▼
                          controller.write(pan, tilt, active)
```

**Only the state pose is eased.** Running a gesture through that filter was the
original bug: a 0.1 per-frame lag at 50 Hz corners at roughly 0.8 Hz, which
attenuates exactly the 1.5–2.5 Hz motion the eye reads as a nod. Gesture,
accent and breath are added *after* it.

**`active`** is the hand-back signal — true when the head is expressing
something (`manual or state != "idle" or gesture or env > 0.02`). When it goes
false, jog packets stop after a 0.3 s settle and the neck resumes its own face
tracking about 2 s later.

---

## 5. Available head movements

### 5.1 Gestures — one per sentence, synced to speech

Amplitudes are **simulation** degrees, before the hardware gain.

| Gesture | Drives | Amplitude | Rate | Shape | **Leaves behind** | Triggered by |
|---|---|---|---|---|---|---|
| `shake` | pan **+** tilt | pan ±24.0°, tilt −5.0° | 1.0 Hz | sine sweep, ramps in | **tilt −5.0°** | `[deny]`; sentence opening with a negation; `is_refusal()`; `is_limitation()` |
| `nod` | tilt | 0 → −9.0° | 1.5 Hz | dips below neutral and recovers | nothing | `[affirm]`; declarative fallback |
| `nod_hard` | tilt | 0 → −13.0° | 1.7 Hz | same, `swing^0.7` — snappier | nothing | sentence ends `!` |
| `query` | pan + tilt | pan +4.05°, tilt +4.95° | held | one sustained lean, no repeat | **the whole lean** | `[ask]`; sentence ends `?` |
| `calm` | tilt | ±6.0° | 0.8 Hz | rides *around* neutral | nothing | `[neutral]`; phrase under 18 chars |
| `scan` | pan | ±26.0° | 0.45 Hz | sine | nothing | `look_around` tool only — never from text |

Cycles actually played over a 3-second sentence: `shake` 3.0, `nod` 4.5,
`nod_hard` 5.1, `query` 1.0, `calm` 2.4, `scan` 1.35.

The periodic gestures come to rest at zero on their own, because `cycles` is a
whole number. Only `shake` and `query` end somewhere other than neutral, and
those poses are **held** — see §5.6.

`calm` is deliberately the gentlest: it is by far the commonest tag in real
use, so it cannot be the near-invisible one, and it rides around neutral rather
than dipping below it so it stays distinguishable from `nod`.

### 5.2 State poses — where the head rests between gestures

Eased at 10 % per frame, so posture changes glide.

| State | pan | tilt | Meaning | Entered when |
|---|---|---|---|---|
| `idle` | 0.0 | 0.0 | at rest | nothing happening; after `yield` holds 0.8 s |
| `listening` | 0.0 | +4.0 | lifted and still, attentive | `saw_input()` — user speech arriving |
| `thinking` | −6.0 | +7.0 | up and away, considering | 0.25 s of silence while listening |
| `speaking` | 0.0 | 0.0 | neutral, gesture carries it | `begin_gesture()` |
| `yield` | 0.0 | +3.5 | small lift, "your turn" | `turn_complete()` — nothing left to say |

### 5.3 Ambient motion — always on, never planned

| Source | Axis | Size | Notes |
|---|---|---|---|
| RMS accent | tilt | −9.0° × envelope | driven by the loudness of the audio playing right now; auto-gained against a decaying peak, so it is independent of voice and volume |
| Breath | tilt | ±1.5° idle, ±0.4° busy | 0.18 Hz; a quiet robot is not a dead one |

### 5.4 Directed looks — the `look_around` tool

Gemini calls this only when asked to look, check, scan, inspect or patrol.

```
default        HEAD.begin_gesture(Plan("scan", 2.4s))   ← ordinary gesture
               sleep 1.5 s, end_speech()                   over jog
               returns "I am looking around the environment…"

--blocking-look  head_link.look("look_around")           ← the head's own
                 5-stop sweep, blocks ~9 s                  gesture engine
                 returns the sentence the head reports
```

The blocking path is **opt-in** on purpose. Function calling is synchronous, so
those nine seconds are dead air — long enough that a stray noise barges in and
cancels the reply entirely, which is what it did to a greeting in testing.

The protocol in `head_link.look()` also accepts `look_up`, `look_down`,
`look_left`, `look_right` and `look_center`, but no tool is wired to them in
this script.

### 5.5 The head keeps the pose a gesture leaves it in

Gestures used to ramp back to zero before retiring, so the head visibly *un-did*
each nod and shake. That return trip is a movement of its own, it means
nothing, and it arrives just as the sentence it belonged to finishes. A person
shakes their head and leaves it where it stopped.

```
 gesture playing                retired
 ─────────────────────────────┬──────────────────────────────►
                              │
   shake sweeps ±24° pan      │   pan back at 0 (whole cycles)
   and holds tilt −5°         │   tilt STAYS at −5°  ← held, indefinitely
                              │
   next gesture begins ───────┴──► the held pose crossfades out over
                                    GESTURE_BLEND (18 %) of its length
```

Three rules keep this bounded:

- **Replace, never accumulate.** A gesture's held pose replaces the previous
  one, so `shake, shake, shake` rests at −5.0° and never at −15.0°.
- **Whole cycles.** Periodic gestures return to their own centre, so only a
  deliberately-held component survives.
- **Ease toward the end pose, not toward zero.** When speech stops early, the
  gesture settles into the posture it was heading for rather than undoing
  itself — measured at 1.8 °/frame worst case, well under the 8.4 °/frame slew
  ceiling.

Barge-in is the exception: `interrupt()` clears the held pose, because snapping
to attention means neutral.

`RESIDUAL_RELAX` in `head.py` decays the held pose per frame. It ships at
`0.0` — hold indefinitely. Set it to `0.01` for a slow ~2 s settle instead.

### 5.6 Manual control

The Tk window's sliders call `HEAD.set_manual(True)`, which takes the head off
the mixer entirely — gesture, accent and breath are all silenced so the sliders
read as commanded. This is how you check travel and find the mechanical limits
without holding a conversation with the robot.

---

## 6. Simulation frame → hardware frame

`RobotHeadController.write()` is the single boundary. Everything above it is in
the simulation's frame; the wire is in the head's.

```
  mixer pose (sim frame)
        │
        ▼
  × GAIN 2.2            inertia compensation — a real neck low-passes a
        │               gesture and arrives at a fraction of it
        ▼
  clamp to the neck's travel, expressed in the SIM frame
        │               (mirrored axes swap the bounds, they do not just
        │                negate them: pitch −24.9..+33.7 → tilt −33.7..+24.9)
        ▼
  mirror pan and tilt   INVERT_PAN = True, INVERT_TILT = True on this build
        │               — the window keeps showing the intended pose,
        │                 only the datagram is flipped
        ▼
  head_link.jog(yaw, pitch)  → UDP JSON → :8770 at 25 Hz
```

Measured, with the neck reporting yaw ±42.4° and pitch −24.9..+33.7°:

```
sim(pan  +20.0 right)  ->  jog(yaw  -42.40)
sim(pan  -20.0 left )  ->  jog(yaw  +42.40)
sim(tilt +10.0 up   )  ->  jog(pitch -22.00)
```

**Clipping.** With `GAIN_PAN = 2.2` the most sim pan the neck can follow is
±19.3°. The ±24° shake therefore spends about 41 % of each swing pinned at full
travel, flattening the tops of the sine. `HW.clipped` counts those frames.

---

## 7. Barge-in

```
sc.interrupted
     │
     ├─ speak_turn += 1        every queued sentence carries its turn_id;
     │                         the worker drops any stale one, mid-slice
     ├─ text_buffer = ""
     ├─ drain sentence_queue
     ├─ pending_tag = ()       a cancelled turn's tag must not carry forward
     ├─ HEAD.interrupt()       gesture dropped, snap to "listening"
     └─ stream.abort()         discards the buffer — silent at once
```

Latency is bounded by `WRITE_MS = 30`: the slice loop is the only place an
interruption can be noticed, because `stream.write` blocks for the duration of
whatever it is handed.

---

## 8. Flags

| Flag | Effect |
|---|---|
| `--no-window` | no Tk visualiser (headless Jetson) |
| `--no-head` | simulation only; no hardware link attempted |
| `--head 192.168.1.159:8770` | where the neck is |
| `--gain 2.2` | scale the angle sent to the neck, not the simulation |
| `--gesture-rate 0.7` | slow every gesture down so the neck can keep up |
| `--invert pan,tilt` | mirror axes on the wire (the shipped default) |
| `--invert none` | trust the protocol's convention as written |
| `--verbose` | print every UDP datagram |
| `--llm-print` | Gemini's raw transcript, tags and all |
| `--blocking-look` | let the head run its own 9 s sweep (silences the reply) |

## 9. Shutdown report

On exit `run()` prints two things worth reading:

- **`TAG_DISAGREEMENTS`** — every sentence where the model's tag and the
  keyword ladder disagreed, as `tag=… text=… <sentence>`. If the text column
  reads better, the prompt needs work; if the tag column does, the ladder does.
- **jog statistics** — `N jogs sent, M clipped at the neck's travel (X %)`.
  A high clip rate means the gain is asking for more than the neck has.
