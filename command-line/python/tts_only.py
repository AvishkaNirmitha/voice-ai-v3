import time
from pathlib import Path
import sounddevice as sd
from piper import PiperVoice, SynthesisConfig
import head_link

print(
    f"robot head: sending to {head_link.target()} "
    f"(set ROBOT_HEAD_ADDR to point at the head laptop)"
)

# --- Piper TTS Configuration -------------------------------------------------
# Ensure this path correctly points to your .onnx model
PIPER_MODEL = Path(__file__).resolve().parents[2] / "en_GB-alan-medium.onnx"
LENGTH_SCALE = 1.0  # >1 slower, <1 faster
WRITE_MS = 30

_t0 = time.perf_counter()
voice = PiperVoice.load(str(PIPER_MODEL))
PIPER_RATE = voice.config.sample_rate
SYN_CONFIG = SynthesisConfig(length_scale=LENGTH_SCALE)
WRITE_BYTES = int(PIPER_RATE * WRITE_MS / 1000) * 2  # int16 mono
print(f"piper loaded in {time.perf_counter() - _t0:.3f}s  ({PIPER_RATE} Hz)")

# Warmup to allocate ONNX buffers
_t0 = time.perf_counter()
for _ in voice.synthesize("ok", syn_config=SYN_CONFIG):
    pass
print(f"piper warmed up in {time.perf_counter() - _t0:.3f}s")
# ---------------------------------------------------------------------------


def speak_static_text():
    """Synthesizes static text, sends commands to the head, and plays audio."""

    # text_to_speak = (
    #     "I am Nuwan [head_calm] yes i [head_up_to_down_hard] have to go home "
    #     "[head_up_to_down_medium]. No i don't want [head_left_to_right_hard] "
    #     "milk rice [head_left_to_right_medium]"
    # )
    # text_to_speak = " No i don't want [head_left_to_right_hard]"

    text_to_speak = ("""
    Suddenly, Spera detected movement near the gate. [head_up_to_down_hard] A person was standing near the entrance and looking around suspiciously, sir. [head_left_to_right_medium]

Spera immediately checked the surrounding area using its vision system. The area was mostly clear, but the person's behavior appeared unusual, sir. [head_up_to_down_medium]

"Please remain where you are, sir. Security personnel are approaching." [head_up_to_down_hard]
    """)

    # text_to_speak = ("""head_up_to_down_medium [head_up_to_down_medium] head_up_to_down_medium. [head_up_to_down_medium] head_up_to_down_medium. [head_up_to_down_medium] head_left_to_right_hard. [head_left_to_right_hard] head_left_to_right_medium. [head_left_to_right_medium]""")

    text_to_speak = ("""head_up_to_down_hard [head_up_to_down_hard] head_left_to_right_hard [head_left_to_right_hard]""")

    turn_id = 1  # Static turn ID since there's no ongoing conversation

    # 1. Extract the [head_*] tags BEFORE synthesis
    clean, tags = head_link.extract_actions(text_to_speak)

    if head_link.VERBOSE:
        print(f"\n[TAGS] raw   = {text_to_speak!r}")
        print(f"[TAGS] speak = {clean!r}")
        print(f"[TAGS] tags  = {tags}", flush=True)

    print(f"\nSpeaking: {clean}\n")

    # 2. Synthesize audio
    # Collect before playing so the exact duration is known up front for the head
    audio = b"".join(
        c.audio_int16_bytes for c in voice.synthesize(clean, syn_config=SYN_CONFIG)
    )
    duration = len(audio) / 2 / PIPER_RATE  # int16 mono

    # 3. Send timings to the physical robot head
    if head_link.VERBOSE:
        print(
            f"[SEND] turn={turn_id} duration={duration:.3f}s "
            f"actions={head_link.action_times(clean, tags, duration)}",
            flush=True,
        )
    head_link.speak(turn_id, clean, tags, duration)

    # 4. Play the audio locally
    print(f"[AUDIO] playing current timestamp: {time.time()}") 
    stream = sd.RawOutputStream(samplerate=PIPER_RATE, channels=1, dtype="int16")
    try:
        stream.start()
        for i in range(0, len(audio), WRITE_BYTES):
            stream.write(audio[i : i + WRITE_BYTES])
    finally:
        stream.stop()  # Drains the buffer so the tail is not clipped
        stream.close()


if __name__ == "__main__":
    try:
        speak_static_text()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
