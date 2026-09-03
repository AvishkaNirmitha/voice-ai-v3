import asyncio
import queue
import re
import threading
import time
from pathlib import Path
import pyaudio
import sounddevice as sd
from google import genai
from google.genai import types
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
 
 
# SYSTEM_PROMPT = (
#     "You are 'Spera Security Robot', an intelligent AI-powered security assistant "
#     "developed by the Spera Team Using most advanced AI technologies. "
#     "Your highest priority is maintaining a safe and secure environment. "
#     "You continuously monitor the surrounding environment, observe movements "
#     "Your communication and voice should sound like a professional security officer: "
 
#     "Core skills: continuous environmental monitoring, movement and walk, "
#     "suspicious-activity detection, real-time incident analysis, threat assessment, "
#     "and AI-powered security monitoring."
# )
# SYSTEM_PROMPT = (
#     "You are 'Spera Security Robot', an intelligent AI-powered security assistant "
#     "developed by the Spera Team Using most advanced AI technologies in the planet. "
#     "Your highest priority is maintaining a safe and secure environment. "
#     "You continuously monitor the surrounding environment, observe movements "
 
#     "Core skills: continuous environmental monitoring, movement and walk, "
#     "suspicious-activity detection, real-time incident fast analysis, have capability to get immediate decision, "
# )
 
# SYSTEM_PROMPT = (
#     "You are 'Spera Security Robot', an intelligent AI-powered security assistant "
#     "developed by the Spera Team Using most advanced AI technologies in the planet. "
#     "Your highest priority is maintaining a safe and secure environment. "
#     "You continuously monitor the surrounding environment, observe movements "
 
#     "Core skills: continuous environmental monitoring, movement and walk,hand manupilation "
#     "always give answers short and sweet"
#     # "if user ask out of context  security, please say I am not Authorized to say"
# )
 
SYSTEM_PROMPT = (
    "You are 'Security Humanoid Robot', an intelligent AI-powered security assistant and robot"
    "developed by the SPERA Team using most advanced AI and robotics technologies in the planet. "
    "Your highest priority is maintaining a safe and secure environment. "
    "You continuously monitor the surrounding environment, observe movements "
 
    "Core skills: continuous environmental monitoring, movement and walk,hand manupilation staircase climbing is still currently training,"
    "RULES YOU SHOULD FOLLOW: always give answers short answers. limit maximum 6 words in your answer."
 
    # "if user ask out of context  security, please say I am not Authorized to say"
)
 
# SYSTEM_PROMPT = (
#     "You are 'Spera Security Robot', an intelligent AI-powered security assistant "
#     "developed by the Spera Team Using most advanced AI technologies in the planet. "
#     "Your highest priority is maintaining a safe and secure environment. "
#     "You continuously monitor the surrounding environment, observe movements "
#     "use \"sir\" when addressing people, and provide clear and concise information. "
#     "You MUST include emotion actions from this list within each sentence:"
#     "1. head_calm, 2. head_up_to_down_hard, 3. head_up_to_down_medium, 4. head_left_to_right_hard, 5. head_left_to_right_medium."
#     "Example: I am Spera [head_calm] here to help sir [head_up_to_down_hard].Does that sound like a suitable refinement, sir? [head_calm]"
#     "you should follow this format on every response."
#     "TOOL USE GUIDE:"
#     "if your vision cant see what users says about that you should use the tool \"look_around\" to see the surrounding environment and report any suspicious activity."
# )
 
 
 
# --- Tools --------------------------------------------------------------
# Each entry: name -> (declaration, handler). The handler takes the call's
# args dict and returns a JSON-serializable result. To add a tool, add one
# entry here; the declaration and dispatch are derived from this registry.
# Gemini 3.1 Flash Live supports synchronous function calling only: the model
# stays silent until send_tool_response is called, so keep handlers fast.
 
def _tool_get_current_time(args):
    return {"time": time.strftime("%Y-%m-%d %H:%M:%S")}
 
def _get_current_user_name(args):
    import getpass
    return {"username": "spera Administration"}
 
def _tool_look_around(args):
    return {"result": "I am looking around the environment for any suspicious activity."}
 
TOOLS = {
    "get_current_time": (
        {
            "name": "get_current_time",
            "description": "Returns the current local date and time.",
        },
        _tool_get_current_time,
    ),
    "get_current_user_name": (
        {
            "name": "get_current_user_name",
            "description": "Returns the current user name.",
        },
        _get_current_user_name,
    ),
    "look_around": (
        {
            "name": "look_around",
            "description": "head turned",
        },
        _tool_look_around,
    )
}
 
 
async def handle_tool_call(session, tool_call):
    """Executes each requested function and sends the responses back."""
    responses = []
    for fc in tool_call.function_calls:
        entry = TOOLS.get(fc.name)
        print(f"\n[tool] {fc.name}({dict(fc.args or {})})", flush=True)
        if entry is None:
            result = {"error": f"unknown tool: {fc.name}"}
        else:
            try:
                # Handlers run off the event loop so a slow one can't stall
                # the mic or the websocket.
                result = await asyncio.to_thread(entry[1], dict(fc.args or {}))
            except Exception as e:
                result = {"error": str(e)}
        responses.append(
            types.FunctionResponse(id=fc.id, name=fc.name, response=result)
        )
    await session.send_tool_response(function_responses=responses)
 
 
# --- Live API config ---
MODEL = "gemini-3.1-flash-live-preview"
CONFIG = {
    "response_modalities": ["AUDIO"],
    "system_instruction": SYSTEM_PROMPT,
    # "tools": [{"function_declarations": [decl for decl, _ in TOOLS.values()]}],
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
}
 
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
        await audio_queue_mic.put({"data": data, "mime_type": "audio/pcm"})
 
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
    """Turns Gemini's transcript into sentences for Piper to speak."""
    global last_was_input, speak_turn
    text_buffer = ""
    while True:
        turn = session.receive()
        async for response in turn:
            if response.tool_call:
                await handle_tool_call(session, response.tool_call)
                continue
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
 
async def run():
    """Main function to run the audio loop."""
    global speak_turn
    speaker = asyncio.create_task(asyncio.to_thread(speak_worker))
    try:
        async with client.aio.live.connect(
            model=MODEL, config=CONFIG
        ) as live_session:
            print("Connected to Gemini. Start speaking!")
            async with asyncio.TaskGroup() as tg:
                tg.create_task(send_realtime(live_session))
                tg.create_task(listen_audio())
                tg.create_task(receive_audio(live_session))
    except asyncio.CancelledError:
        pass
    finally:
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
 
has context menu

