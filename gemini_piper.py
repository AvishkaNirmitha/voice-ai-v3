#!/usr/bin/env python3
"""Gemini Live with local Piper TTS.

Audio in -> Gemini -> output transcript -> Piper -> speakers.

The obvious route would be response_modalities=["TEXT"], but every live model
reachable today is native-audio and rejects TEXT ("The requested combination of
response modalities (TEXT) is not supported"); the half-cascade models that did
support it are retired. So we stay on AUDIO, turn on output_audio_transcription,
speak the transcript with Piper and drop Gemini's own audio on the floor.

Gemini still handles VAD, turn taking and interruption on the input side. Note
that the discarded audio is still generated and billed.

Usage:
    source .venv/bin/activate
    python gemini_piper.py
    python gemini_piper.py --length-scale 1.15      # slower voice
    python gemini_piper.py --barge-in               # headphones / real AEC only
"""

import argparse
import asyncio
import queue
import re
import sys
import threading
import time

import sounddevice as sd
from google import genai
from google.genai import types
from piper import PiperVoice, SynthesisConfig

DEFAULT_MODEL = "en_US-lessac-medium.onnx"
LIVE_MODEL = "gemini-3.1-flash-live-preview"

DEFAULT_MODEL = "en_GB-alan-medium.onnx"
LIVE_MODEL = "gemini-3.1-flash-live-preview"


SEND_SAMPLE_RATE = 16000  # what the Live API expects on input
BLOCKSIZE = 1600  # 100 ms at 16 kHz

SYSTEM_PROMPT = (
    "You are 'Spera Security Robot', an intelligent AI-powered security assistant "
    "developed by the Spera Team Using most advanced AI technologies in the planet. "
    "Your highest priority is maintaining a safe and secure environment. "
    "You continuously monitor the surrounding environment, observe movements "
    "Core skills: continuous environmental monitoring, movement and walk, "
    "suspicious-activity detection, real-time incident fast analysis, have capability to get immediate decision, "
    "Keep replies short and spoken-friendly: no markdown, no bullet points, no emoji."
)

# Flush to the voice on sentence boundaries so Piper is never handed a
# three-word fragment. Trailing quote/bracket stays with the sentence.
SENTENCE_END = re.compile(r'(.+?[.!?…]["\')\]]*(?:\s|$))', re.S)
MAX_BUFFER = 220  # ...but never stall forever on text with no punctuation

mic_q: asyncio.Queue = asyncio.Queue(maxsize=10)
tts_q: queue.Queue = queue.Queue()
stop_tts = threading.Event()  # set to abandon whatever is being spoken
speaking = threading.Event()  # set while Piper owns the speakers
out_stream = None  # owned by the TTS thread, aborted by the interrupting one


def drain(q: queue.Queue) -> None:
    while True:
        try:
            q.get_nowait()
        except queue.Empty:
            return


def speak(text: str) -> None:
    """Queue a sentence for the TTS thread."""
    stop_tts.clear()
    tts_q.put(text)


def tts_thread(model_path: str, syn_config: SynthesisConfig, device) -> None:
    """Owns the Piper voice and the output stream, start to finish.

    Synthesis is CPU-bound and blocking, so it lives on its own thread and
    writes straight to the speakers rather than shuttling PCM back to asyncio.
    """
    try:
        voice = PiperVoice.load(model_path)
    except Exception as exc:
        print(f"\n[tts] could not load {model_path}: {exc}", file=sys.stderr)
        return

    global out_stream
    stream = sd.RawOutputStream(
        samplerate=voice.config.sample_rate, channels=1, dtype="int16", device=device
    )
    stream.start()
    out_stream = stream
    print(f"[tts] piper ready ({voice.config.sample_rate} Hz)")

    try:
        while True:
            text = tts_q.get()
            if text is None:
                break
            if stop_tts.is_set():
                continue  # queued before an interruption, no longer wanted

            speaking.set()
            if stream.stopped:
                stream.start()  # a previous interrupt aborted it
            started = time.monotonic()
            written = 0
            try:
                for chunk in voice.synthesize(text, syn_config=syn_config):
                    if stop_tts.is_set():
                        break
                    pcm = chunk.audio_int16_bytes
                    stream.write(pcm)
                    written += len(pcm)
            except sd.PortAudioError:
                pass  # expected: interrupt() aborted the stream under us
            except Exception as exc:
                print(f"\n[tts] synthesis failed: {exc}", file=sys.stderr)
            finally:
                if stop_tts.is_set():
                    speaking.clear()
                elif tts_q.empty():
                    # stream.write() returns once the audio is buffered, not
                    # once it is heard. Hold the mic gate for the rest of the
                    # real playback time, or we re-open on our own tail.
                    audio_secs = written / 2 / voice.config.sample_rate
                    remaining = audio_secs - (time.monotonic() - started)
                    if remaining > 0 and not stop_tts.is_set():
                        stop_tts.wait(remaining)  # returns early if interrupted
                    speaking.clear()
    finally:
        stream.stop()
        stream.close()


def interrupt() -> None:
    """Drop the current utterance the moment the user starts talking.

    Must abort the stream from *this* thread: the TTS thread is blocked inside
    stream.write() waiting for buffer space, so it cannot react to the flag
    until PortAudio lets go. Aborting discards the buffered audio and unblocks
    that write immediately.
    """
    stop_tts.set()
    drain(tts_q)
    print(' interruption listen.....')
    if out_stream is not None:
        try:
            out_stream.abort()
        except Exception:
            pass
    speaking.clear()


async def listen_audio(loop: asyncio.AbstractEventLoop, barge_in: bool, device) -> None:
    """Capture the mic and feed it to the send queue."""

    def callback(indata, frames, time_info, status):
        if status:
            print(f"\n[mic] {status}", file=sys.stderr)
        # Without real echo cancellation the mic hears Piper, Gemini's VAD
        # treats that as the user talking, and the session talks to itself.
        # Gating the mic while speaking is the cheap, reliable fix.
        if not barge_in and speaking.is_set():
            return
        loop.call_soon_threadsafe(_offer, bytes(indata))

    def _offer(data: bytes) -> None:
        try:
            mic_q.put_nowait(data)
        except asyncio.QueueFull:
            pass  # better to drop a stale frame than to lag behind live audio

    with sd.RawInputStream(
        samplerate=SEND_SAMPLE_RATE,
        blocksize=BLOCKSIZE,
        channels=1,
        dtype="int16",
        device=device,
        callback=callback,
    ):
        await asyncio.Event().wait()  # run until the task group is cancelled


async def send_realtime(session) -> None:
    while True:
        chunk = await mic_q.get()
        await session.send_realtime_input(
            audio=types.Blob(data=chunk, mime_type=f"audio/pcm;rate={SEND_SAMPLE_RATE}")
        )


async def receive_text(session) -> None:
    """Turn Gemini's streamed text into whole sentences for Piper."""
    buf = ""
    last_was_input = False

    while True:
        async for response in session.receive():
            sc = response.server_content
            if not sc:
                continue

            if sc.interrupted:
                buf = ""
                interrupt()
                continue

            if sc.input_transcription and sc.input_transcription.text:
                if not last_was_input:
                    print()
                    last_was_input = True
                print(f"\033[3m{sc.input_transcription.text}\033[0m", end="", flush=True)

            # Gemini's own audio arrives in sc.model_turn and is deliberately
            # ignored -- Piper is the voice now.
            if sc.output_transcription and sc.output_transcription.text:
                text = sc.output_transcription.text
                if last_was_input:
                    print()
                    last_was_input = False
                print(text, end="", flush=True)
                buf += text

                while (m := SENTENCE_END.match(buf)) is not None:
                    speak(m.group(1).strip())
                    buf = buf[m.end():]

                if len(buf) > MAX_BUFFER and " " in buf:
                    head, _, buf = buf.rpartition(" ")
                    speak(head.strip())

            if sc.turn_complete:
                if buf.strip():
                    speak(buf.strip())
                buf = ""
                print()


async def run(args) -> None:
    syn_config = SynthesisConfig(
        length_scale=args.length_scale,
        noise_scale=args.noise_scale,
        noise_w_scale=args.noise_w,
    )
    worker = threading.Thread(
        target=tts_thread,
        args=(args.model, syn_config, args.output_device),
        daemon=True,
    )
    worker.start()

    client = genai.Client()
    config = {
        # AUDIO because native-audio models refuse TEXT; the transcription is
        # what actually reaches Piper. See the module docstring.
        "response_modalities": ["AUDIO"],
        "system_instruction": SYSTEM_PROMPT,
        "output_audio_transcription": {},
        "input_audio_transcription": {},
    }

    loop = asyncio.get_running_loop()
    try:
        async with client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
            print("Connected to Gemini. Start speaking!")
            if not args.barge_in:
                print("[mic] gated while speaking (pass --barge-in to disable)")
            async with asyncio.TaskGroup() as tg:
                tg.create_task(listen_audio(loop, args.barge_in, args.input_device))
                tg.create_task(send_realtime(session))
                tg.create_task(receive_text(session))
    except asyncio.CancelledError:
        pass
    finally:
        interrupt()
        tts_q.put(None)
        worker.join(timeout=2)
        print("\nConnection closed.")


def device_arg(value):
    return int(value) if value is not None and value.isdigit() else value


def parse_args():
    p = argparse.ArgumentParser(description="Gemini Live speaking through Piper TTS.")
    p.add_argument("-m", "--model", default=DEFAULT_MODEL, help="path to .onnx voice")
    p.add_argument("--length-scale", type=float, default=1.0,
                   help="speech rate; >1 is slower, <1 is faster")
    p.add_argument("--noise-scale", type=float, default=0.667, help="audio variation")
    p.add_argument("--noise-w", type=float, default=0.8, help="phoneme duration variation")
    p.add_argument("--barge-in", action="store_true",
                   help="keep the mic open while speaking (needs headphones or real AEC)")
    p.add_argument("--input-device", type=device_arg, help="sounddevice input device")
    p.add_argument("--output-device", type=device_arg, help="sounddevice output device")
    return p.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
