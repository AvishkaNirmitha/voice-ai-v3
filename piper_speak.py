#!/usr/bin/env python3
"""Speak text with Piper, playing audio as it is generated.

Python equivalent of:
    echo "text" | piper-tts -m model.onnx --output-raw | aplay -r 22050 -f S16_LE -t raw

Usage:
    python piper_speak.py "Hello there"
    echo "Hello there" | python piper_speak.py
    python piper_speak.py "Slower" --length-scale 1.3
    python piper_speak.py "Save a copy" --save out.wav

Loading the voice costs ~0.8s, and a one-shot run pays that every time. Use
-i to load it once and then speak many lines with no startup cost:

    python piper_speak.py -i
"""

import argparse
import sys

import sounddevice as sd
from piper import PiperVoice, SynthesisConfig

DEFAULT_MODEL = "en_US-lessac-medium.onnx"


def parse_args():
    parser = argparse.ArgumentParser(description="Stream Piper TTS to the speakers.")
    parser.add_argument("text", nargs="*", help="text to speak (default: read stdin)")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help="path to .onnx voice")
    parser.add_argument(
        "--length-scale",
        type=float,
        default=1.0,
        help="speech rate; >1 is slower, <1 is faster",
    )
    parser.add_argument("--noise-scale", type=float, default=0.667, help="audio variation")
    parser.add_argument("--noise-w", type=float, default=0.8, help="phoneme duration variation")
    parser.add_argument("--save", metavar="WAV", help="also write the audio to a .wav file")
    parser.add_argument("--device", help="sounddevice output device (name or index)")
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="load the voice once, then speak each line typed at the prompt",
    )
    return parser.parse_args()


def read_text(args):
    if args.text:
        return " ".join(args.text)
    # No positional text, so behave like the `echo ... | piper-tts` pipe.
    return sys.stdin.read().strip()


def speak(voice, stream, text, syn_config, collect=None):
    """Synthesize text, writing each chunk to the stream as it arrives.

    The stream runs only while there is audio to feed it. Leaving it active
    between utterances would starve ALSA and log underruns at the prompt.
    """
    stream.start()
    try:
        for chunk in voice.synthesize(text, syn_config=syn_config):
            pcm = chunk.audio_int16_bytes
            stream.write(pcm)
            if collect is not None:
                collect.append(pcm)
        # stop() drains what is already buffered, so the tail is not clipped.
        stream.stop()
    except KeyboardInterrupt:
        # abort() discards the buffer, so Ctrl-C silences the voice at once.
        stream.abort()
        raise


def write_wav(path, pcm_chunks, rate):
    import wave

    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"".join(pcm_chunks))
    print(f"Wrote {path}", file=sys.stderr)


def main():
    args = parse_args()

    text = None
    if not args.interactive:
        text = read_text(args)
        if not text:
            sys.exit("No text given. Pass it as an argument or pipe it on stdin.")

    voice = PiperVoice.load(args.model)
    rate = voice.config.sample_rate

    syn_config = SynthesisConfig(
        length_scale=args.length_scale,
        noise_scale=args.noise_scale,
        noise_w_scale=args.noise_w,
    )

    device = args.device
    if device is not None and device.isdigit():
        device = int(device)

    saved_chunks = [] if args.save else None

    # The stream stays open for the whole session, so in interactive mode only
    # the first line pays any setup cost.
    stream = sd.RawOutputStream(samplerate=rate, channels=1, dtype="int16", device=device)
    try:
        if args.interactive:
            print("Voice loaded. Type a line to speak it, Ctrl-D to quit.", file=sys.stderr)
            while True:
                try:
                    line = input("> ").strip()
                except EOFError:
                    print(file=sys.stderr)
                    break
                except KeyboardInterrupt:
                    # Discard the half-typed line but stay at the prompt.
                    print(file=sys.stderr)
                    continue
                if line:
                    speak(voice, stream, line, syn_config, saved_chunks)
        else:
            speak(voice, stream, text, syn_config, saved_chunks)
    except KeyboardInterrupt:
        sys.exit(130)
    finally:
        stream.close()

    if saved_chunks:
        write_wav(args.save, saved_chunks, rate)


if __name__ == "__main__":
    main()
