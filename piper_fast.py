#!/usr/bin/env python3
"""Low-latency Piper TTS test: edit the text below and run it.

    python piper_fast.py

The voice is loaded once at startup and reused for every line, so only the
first utterance pays any model cost. Audio streams to the speakers as it is
generated -- nothing is written to disk.
"""

import time

import sounddevice as sd
from piper import PiperVoice, SynthesisConfig

# ---------------------------------------------------------------- edit these
MODEL = "en_US-lessac-medium.onnx"

TEXTS = [
    "Hello this is",
    "The model was already loaded, so this one starts immediately.",
    "And this is the third line.",
]

LENGTH_SCALE = 1.0  # >1 slower, <1 faster
# ---------------------------------------------------------------------------


def main():
    t0 = time.perf_counter()
    voice = PiperVoice.load(MODEL)
    rate = voice.config.sample_rate
    print(f"model loaded in {time.perf_counter() - t0:.3f}s  ({rate} Hz)")

    syn_config = SynthesisConfig(length_scale=LENGTH_SCALE)

    stream = sd.RawOutputStream(samplerate=rate, channels=1, dtype="int16")

    # First inference allocates ONNX buffers and is measurably slower, so burn
    # that cost here instead of on the first real line. Nothing is played.
    t0 = time.perf_counter()
    for _ in voice.synthesize("ok", syn_config=syn_config):
        pass
    print(f"warmed up in {time.perf_counter() - t0:.3f}s\n")

    try:
        for text in TEXTS:
            t0 = time.perf_counter()
            first = None

            # Running the stream only while audio is flowing keeps ALSA from
            # underrunning during the gaps between lines.
            stream.start()
            for chunk in voice.synthesize(text, syn_config=syn_config):
                if first is None:
                    first = time.perf_counter() - t0
                stream.write(chunk.audio_int16_bytes)
            stream.stop()  # drains the buffer so the tail is not clipped

            print(f"[{first * 1000:6.1f} ms to first sound]  {text}")
    except KeyboardInterrupt:
        stream.abort()  # discard the buffer so Ctrl-C silences it at once
    finally:
        stream.close()


if __name__ == "__main__":
    main()
