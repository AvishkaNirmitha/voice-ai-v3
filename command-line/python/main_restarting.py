import asyncio
import queue
import re
import threading
import time
from pathlib import Path
import pyaudio
import sounddevice as sd
from google import genai
from piper import PiperVoice, SynthesisConfig

client = genai.Client()

# --- pyaudio config (microphone only; Piper owns the speaker) ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
CHUNK_SIZE = 1024

pya = pyaudio.PyAudio()

# --- Piper TTS ------------------------------------------------------------
# Loaded once, here at import time, so no utterance ever pays the model cost.
PIPER_MODEL = Path(__file__).resolve().parents[2] / "en_US-lessac-medium.onnx"
# en_GB-alan-medium.onnx
PIPER_MODEL = Path(__file__).resolve().parents[2] / "en_GB-alan-medium.onnx"

LENGTH_SCALE = 1.0  # >1 slower, <1 faster

# Gemini streams the transcript in fragments; Piper needs whole utterances or
# the prosody falls apart. Sentences are spoken as soon as they are complete.
# If a fragment runs long without ending, break at the last comma instead so
# the voice starts sooner. Raise this to trade latency for smoother phrasing.
CLAUSE_FLUSH_CHARS = 60

# Piper yields a whole sentence as one chunk -- often many seconds of audio --
# and stream.write blocks for its entire duration. Audio is therefore written
# in small slices, since that write is the only place an interruption can be
# noticed. This is what bounds barge-in latency.
WRITE_MS = 30

_t0 = time.perf_counter()
voice = PiperVoice.load(str(PIPER_MODEL))
PIPER_RATE = voice.config.sample_rate
SYN_CONFIG = SynthesisConfig(length_scale=LENGTH_SCALE)
WRITE_BYTES = int(PIPER_RATE * WRITE_MS / 1000) * 2  # int16 mono
print(f"piper loaded in {time.perf_counter() - _t0:.3f}s  ({PIPER_RATE} Hz)")

# First inference allocates ONNX buffers and is measurably slower, so burn that
# cost at startup instead of on the first reply. Nothing is played.
_t0 = time.perf_counter()
for _ in voice.synthesize("ok", syn_config=SYN_CONFIG):
    pass
print(f"piper warmed up in {time.perf_counter() - _t0:.3f}s")
# ---------------------------------------------------------------------------


SYSTEM_PROMPT = (
    "You are 'Spera Security Robot', an intelligent AI-powered security assistant "
    "developed by the Spera Team Using most advanced AI technologies. "
    "Your highest priority is maintaining a safe and secure environment. "
    "You continuously monitor the surrounding environment, observe movements "
    "Your communication and voice should sound like a professional security officer: "

    "Core skills: continuous environmental monitoring, movement and walk, "
    "suspicious-activity detection, real-time incident analysis, threat assessment, "
    "and AI-powered security monitoring."
)
SYSTEM_PROMPT = (
    "You are 'Spera Security Robot', an intelligent AI-powered security assistant "
    "developed by the Spera Team Using most advanced AI technologies in the planet. "
    "Your highest priority is maintaining a safe and secure environment. "
    "You continuously monitor the surrounding environment, observe movements "

    "Core skills: continuous environmental monitoring, movement and walk, "
    "suspicious-activity detection, real-time incident fast analysis, have capability to get immediate decision, "
)
# --- Live API config ---
MODEL = "gemini-3.1-flash-live-preview"
CONFIG = {
    "response_modalities": ["AUDIO"],
    "system_instruction": SYSTEM_PROMPT,
    "output_audio_transcription": {},
    "input_audio_transcription": {},
    "speech_config": {
      "voice_config": {
        "prebuilt_voice_config": {
          "voice_name": "Orus" ,
        #   "voice_name": "Achernar" ,
        }
      },
      "language_code": "en-US"
    },
    # Without this an audio-only session is capped at 15 minutes. The sliding
    # window drops the oldest turns once the context fills, which makes the
    # session itself unbounded; the system instruction is never evicted.
    "context_window_compression": {"sliding_window": {}},
}

# The websocket itself is separately capped at ~10 minutes, so a long
# conversation is a chain of connections, not one. The server hands out a
# resumption handle continuously; presenting the newest one on reconnect is
# what makes the next connection a continuation rather than a cold start.
# Handles stay valid for 2 hours after the session ends.
resumption_handle = None

# A dropped socket at the 10-minute mark is routine, so the first retry is
# nearly immediate and only repeated failures back off.
RECONNECT_BACKOFF_MAX = 30.0
MAX_CONSECUTIVE_FAILURES = 6

audio_queue_mic = asyncio.Queue(maxsize=5)
audio_stream = None

# Complete sentences waiting to be spoken, as (turn_id, text). A plain thread
# queue because the consumer is the Piper worker thread, not the event loop.
sentence_queue = queue.Queue()

# Bumped on every interruption. The worker drops any sentence tagged with an
# older id, which is how barge-in cancels speech that is queued or in flight.
speak_turn = 0

# Shared by receive_audio (user speech) and speak_worker (model speech) to
# decide when a newline is needed between the two.
last_was_input = False


async def listen_audio():
    """Listens for audio and puts it into the mic audio queue."""
    global audio_stream
    mic_info = pya.get_default_input_device_info()
    audio_stream = await asyncio.to_thread(
        pya.open,
        format=FORMAT,
        channels=CHANNELS,
        rate=SEND_SAMPLE_RATE,
        input=True,
        input_device_index=mic_info["index"],
        frames_per_buffer=CHUNK_SIZE,
    )
    kwargs = {"exception_on_overflow": False} if __debug__ else {}
    while True:
        data = await asyncio.to_thread(audio_stream.read, CHUNK_SIZE, **kwargs)
        msg = {"data": data, "mime_type": "audio/pcm"}
        # Nothing drains this queue while a reconnect is in flight. Blocking on
        # put would stall the read loop and back the mic up behind the gap, so
        # the oldest chunk is dropped instead: a bounded amount of speech is
        # lost rather than an unbounded amount being delivered late.
        try:
            audio_queue_mic.put_nowait(msg)
        except asyncio.QueueFull:
            try:
                audio_queue_mic.get_nowait()
            except asyncio.QueueEmpty:
                pass
            audio_queue_mic.put_nowait(msg)

async def send_realtime(session):
    """Sends audio from the mic audio queue to the GenAI session."""
    while True:
        msg = await audio_queue_mic.get()
        await session.send_realtime_input(audio=msg)


def split_speakable(buffer):
    """Split off whatever is ready to speak, returning (chunks, remainder)."""
    chunks = []
    while True:
        match = re.search(r"[.!?]+[\s\"')\]]*", buffer)
        if match:
            chunk, buffer = buffer[:match.end()], buffer[match.end():]
        elif len(buffer) >= CLAUSE_FLUSH_CHARS and "," in buffer:
            cut = buffer.rindex(",") + 1
            chunk, buffer = buffer[:cut], buffer[cut:]
        else:
            break
        if chunk.strip():
            chunks.append(chunk.strip())
    return chunks, buffer


def speak_worker():
    """Synthesizes queued sentences with Piper and plays them.

    Runs on its own thread: voice.synthesize is blocking ONNX inference and
    would otherwise stall the microphone and the websocket.
    """
    global last_was_input
    stream = sd.RawOutputStream(samplerate=PIPER_RATE, channels=1, dtype="int16")
    try:
        while True:
            item = sentence_queue.get()
            if item is None:
                break
            turn_id, text = item
            if turn_id != speak_turn:
                continue  # interrupted while this sentence sat in the queue

            if last_was_input:
                print()
                last_was_input = False
            print(text, end=" ", flush=True)

            # Running the stream only while audio is flowing keeps ALSA from
            # underrunning during the gaps between sentences.
            stream.start()
            interrupted = False
            for chunk in voice.synthesize(text, syn_config=SYN_CONFIG):
                buf = chunk.audio_int16_bytes
                for i in range(0, len(buf), WRITE_BYTES):
                    if turn_id != speak_turn:
                        interrupted = True
                        break
                    stream.write(buf[i:i + WRITE_BYTES])
                if interrupted:
                    break
            if interrupted:
                stream.abort()  # discards the buffer, so it goes quiet at once
            else:
                stream.stop()  # drains the buffer so the tail is not clipped
    finally:
        stream.close()


async def receive_audio(session):
    """Turns Gemini's transcript into sentences for Piper to speak.

    Returns when the server announces it is about to close the connection, so
    the caller can reconnect deliberately instead of being cut mid-turn.
    """
    global last_was_input, speak_turn, resumption_handle
    text_buffer = ""
    while True:
        turn = session.receive()
        async for response in turn:
            # Only the newest handle is any good, and the server declines to
            # issue one while it is mid-generation, so this keeps the last one
            # it was willing to give.
            update = response.session_resumption_update
            if update and update.resumable and update.new_handle:
                resumption_handle = update.new_handle

            if response.go_away:
                # Reconnecting now costs a short gap that Piper mostly covers,
                # since it is still speaking from the queue. Waiting for the
                # socket to be cut costs whatever turn is in flight.
                if text_buffer.strip():
                    sentence_queue.put((speak_turn, text_buffer.strip()))
                print(f"\n[server closing connection in {response.go_away.time_left}]")
                return

            sc = response.server_content
            if not sc:
                continue
            if sc.interrupted:
                # Barge-in: invalidate this turn so the worker drops whatever
                # it is speaking, then throw away everything still pending.
                speak_turn += 1
                text_buffer = ""
                while not sentence_queue.empty():
                    try:
                        sentence_queue.get_nowait()
                    except queue.Empty:
                        break
                print()
            if sc.output_transcription:
                text_buffer += sc.output_transcription.text
                ready, text_buffer = split_speakable(text_buffer)
                for sentence in ready:
                    sentence_queue.put((speak_turn, sentence))
            if sc.input_transcription:
                if not last_was_input:
                    print()
                    last_was_input = True
                t = sc.input_transcription.text
                print(f"\033[3m{t}\033[0m", end="", flush=True)
                if t.rstrip()[-1:] in '.!?':
                    print()

        # Turn is over: speak the tail that never got its own punctuation.
        # After an interruption the buffer is already empty, so nothing leaks.
        if text_buffer.strip():
            sentence_queue.put((speak_turn, text_buffer.strip()))
            text_buffer = ""

async def connect_once():
    """Runs one websocket connection, returning when it should be recycled."""
    config = dict(CONFIG)
    # An empty handle still opts in to receiving updates, which is how the
    # first connection earns the handle the second one resumes from.
    config["session_resumption"] = {"handle": resumption_handle}

    async with client.aio.live.connect(model=MODEL, config=config) as session:
        # Whatever the mic captured during the gap is stale; feeding it to the
        # fresh session would answer a question the user has already moved past.
        while not audio_queue_mic.empty():
            audio_queue_mic.get_nowait()

        print("[resumed]" if resumption_handle else "Connected to Gemini. Start speaking!")

        tasks = [
            asyncio.create_task(send_realtime(session)),
            asyncio.create_task(receive_audio(session)),
        ]
        # Either task finishing means this connection is over: receive_audio
        # returns on GoAway, and both raise once the socket is actually gone.
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            task.result()  # surfaces a dead socket to the reconnect loop


async def run():
    """Main function to run the audio loop."""
    global speak_turn, resumption_handle
    # The mic and Piper outlive any single connection. Reopening the audio
    # device every ten minutes would cost a second of dead air each time and
    # risks failing outright on constrained hardware.
    speaker = asyncio.create_task(asyncio.to_thread(speak_worker))
    mic = asyncio.create_task(listen_audio())
    failures = 0
    try:
        while True:
            try:
                await connect_once()
                failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                failures += 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    print(f"\nGiving up after {failures} failed connections: {e}")
                    break
                # A handle the server will not honour fails identically every
                # time, so after one retry prefer a cold session to no session.
                if failures >= 2 and resumption_handle:
                    print("[resumption handle rejected; starting a fresh session]")
                    resumption_handle = None
                delay = min(0.5 * 2 ** (failures - 1), RECONNECT_BACKOFF_MAX)
                print(f"[connection lost: {type(e).__name__}: {e}; retrying in {delay:.1f}s]")
                await asyncio.sleep(delay)
    except asyncio.CancelledError:
        pass
    finally:
        mic.cancel()
        await asyncio.gather(mic, return_exceptions=True)
        speak_turn += 1  # cuts any in-flight speech short
        sentence_queue.put(None)
        await speaker
        if audio_stream:
            audio_stream.close()
        pya.terminate()
        print("\nConnection closed.")

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("Interrupted by user.")
