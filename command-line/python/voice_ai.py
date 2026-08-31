import asyncio
import queue
import re
import time
from pathlib import Path
import pyaudio
import sounddevice as sd
from google import genai
from google.genai import types
from piper import PiperVoice, SynthesisConfig

# Robot head link. Fire-and-forget UDP: if robot_head.py is not running, every
# call here quietly does nothing, so nothing about speech depends on the neck.
# Set head_link.DEBUG = True to print the messages instead of sending them.
import head_link

print(f"robot head: sending to {head_link.target()} "
      f"(set ROBOT_HEAD_ADDR to point at the head laptop)")

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

# head movement actions (examples)
# 1. head_calm
# 2. head_up_to_down_hard
# 3. head_up_to_down_medium
# 4. head_left_to_right_hard
# 5. head_left_to_right_medium

# new systems prompt

# # You are 'Spera Security Robot', prioritizing safety and monitoring. [head_calm] Use "sir" when addressing people. 
# CRITICAL RULE: You MUST include emotion actions from this list within each sentence: 1. head_calm, 2. head_up_to_down_hard, 3. head_up_to_down_medium, 
# 4. head_left_to_right_hard, 5. head_left_to_right_medium. Example: I am Spera [head_calm] here to help sir [head_up_to_down_hard]."
#  Does that sound like a suitable refinement, sir? [head_calm]


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
    "use \"sir\" when addressing people, and provide clear and concise information. "
    "use head movement actions to express emotions and reactions. "
    "CRITCAL RULE - head movement actions (examples): "
    "1. head_calm, "
    "2. head_up_to_down_hard, "
    "3. head_up_to_down_medium, "
    "4. head_left_to_right_hard, "  
    "5. head_left_to_right_medium, "
    "examples - : I am Nuwan [head_calm] yes i [head_up_to_down_hard] have to go home [head_up_to_down_medium]. No i don't want [head_left_to_right_hard] milk rice [head_left_to_right_medium]"
    "you should follow this format on every response. "


    "Core skills: continuous environmental monitoring, movement and walk, "
    "suspicious-activity detection, real-time incident fast analysis, have capability to get immediate decision, "
)

SYSTEM_PROMPT = (
    "You are 'Spera Security Robot', an intelligent AI-powered security assistant "
    "developed by the Spera Team Using most advanced AI technologies in the planet. "
    "Your highest priority is maintaining a safe and secure environment. "
    "You continuously monitor the surrounding environment, observe movements "
    "use \"sir\" when addressing people, and provide clear and concise information. "
    "You MUST include emotion actions from this list within each sentence:"
    "1. head_calm, 2. head_up_to_down_hard, 3. head_up_to_down_medium, 4. head_left_to_right_hard, 5. head_left_to_right_medium."
    "Example: I am Spera [head_calm] here to help sir [head_up_to_down_hard].Does that sound like a suitable refinement, sir? [head_calm]"
    "you should follow this format on every response."

    # --- directed look --------------------------------------------------
    # The model has to be told three things it cannot work out for itself:
    # that looking away COSTS it eye contact, that the neck cannot spin, and
    # that the tool result is the ground truth about what the body did.
    " You can physically turn your head using the look_around tool: "
    "look_up, look_down, look_left, look_right, look_center, look_around. "
    "While you are looking somewhere you STOP making eye contact and STOP "
    "using head gestures; you return to both automatically after about eight "
    "seconds. look_around is ONE slow sweep - up, right, down, left, centre - "
    "not a full rotation, and it takes several seconds. "
    "Use it when asked to look somewhere, or when there is a real reason to "
    "look away - not casually mid-conversation, because you cannot watch the "
    "person while you do it. "
    "The tool returns a sentence describing what your head ACTUALLY did. Say "
    "that back to the user. NEVER describe a head movement the tool did not "
    "confirm."
)


# --- Tool: directed look ------------------------------------------------------
# The only tool the head exposes. All six directions go through the one
# function; the names must match head_poses.json on the head machine exactly
# (LOOK_SKILL_PROTOCOL.md section 3). An enum is what stops the model from
# inventing "look_behind".
LOOK_ACTIONS = ["look_up", "look_down", "look_left", "look_right",
                "look_center", "look_around"]

LOOK_TOOL = {
    "function_declarations": [{
        "name": "look_around",
        "description": (
            "Physically turn the robot's head to look in a direction. While "
            "this runs the robot stops tracking the person's face and stops "
            "gesturing, then resumes both by itself after about eight "
            "seconds. Returns a sentence describing what the head actually "
            "did - say it to the user."),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "enum": LOOK_ACTIONS,
                    "description": (
                        "Which way to look. look_around is one slow sweep "
                        "(up, right, down, left, centre), not a full "
                        "rotation."),
                },
            },
            "required": ["action"],
        },
    }]
}



# --- Live API config ---
MODEL = "gemini-3.1-flash-live-preview"
CONFIG = {
    "response_modalities": ["AUDIO"],
    "system_instruction": SYSTEM_PROMPT,
    "tools": [LOOK_TOOL],
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

            # Strip the [head_*] tags BEFORE synthesis -- left in, Piper reads
            # them aloud -- and remember how far through the sentence each one
            # sat, so the head can fire it on the right word.
            clean, tags = head_link.extract_actions(text)
            if head_link.VERBOSE:
                print(f"\n[TAGS] raw   = {text!r}")
                print(f"[TAGS] speak = {clean!r}")
                print(f"[TAGS] tags  = {tags}", flush=True)

            if last_was_input:
                print()
                last_was_input = False
            print(clean, end=" ", flush=True)

            # A chunk can be nothing but a tag: the sentence splitter cuts after
            # '.', so the last tag of a reply arrives on its own. There is
            # nothing to speak, but the gesture must still fire.
            if not clean:
                if head_link.VERBOSE:
                    print(f"[SEND] TAG-ONLY turn={turn_id} tags={tags}",
                          flush=True)
                head_link.speak(turn_id, clean, tags, 0.0)
                continue

            # Collect before playing so the exact duration is known up front.
            # Piper returns a whole sentence as one chunk (see the note at the
            # top of this file), so this costs no latency.
            audio = b"".join(c.audio_int16_bytes
                             for c in voice.synthesize(clean,
                                                       syn_config=SYN_CONFIG))
            duration = len(audio) / 2 / PIPER_RATE      # int16 mono

            # Running the stream only while audio is flowing keeps ALSA from
            # underrunning during the gaps between sentences.
            stream.start()
            # Sent at the instant playback begins: the head uses its own arrival
            # time as t=0, so the two processes need no shared clock.
            if head_link.VERBOSE:
                print(f"[SEND] turn={turn_id} duration={duration:.3f}s "
                      f"actions="
                      f"{head_link.action_times(clean, tags, duration)}",
                      flush=True)
            head_link.speak(turn_id, clean, tags, duration)

            interrupted = False
            for i in range(0, len(audio), WRITE_BYTES):
                if turn_id != speak_turn:
                    interrupted = True
                    break
                stream.write(audio[i:i + WRITE_BYTES])

            if interrupted:
                stream.abort()  # discards the buffer, so it goes quiet at once
                if head_link.VERBOSE:
                    print(f"\n[SEND] STOP turn={turn_id} (barge-in)",
                          flush=True)
                head_link.stop(turn_id)   # ...and the head stops nodding at once
            else:
                stream.stop()  # drains the buffer so the tail is not clipped
    finally:
        stream.close()


async def handle_tool_call(session, tool_call):
    """Run the head tool and send the result back to Gemini.

    THE THREAD MATTERS. head_link.look() blocks until the head has finished
    moving - about 1.2 s for one pose and about 9 s for look_around. Called
    directly here it would block the event loop, which is also what drains
    audio_queue_mic; the mic queue (maxsize=5) would fill, listen_audio would
    stall, and the model would receive several seconds of silence in the middle
    of a conversation. asyncio.to_thread keeps the audio flowing while the neck
    moves. The `await` still pauses THIS turn, which is correct: Gemini is
    waiting on the result and will send nothing else until it has one.

    Every call answers. A tool call left unanswered hangs the session, so even
    an unknown function name gets a result rather than silence.
    """
    responses = []
    for fc in tool_call.function_calls:
        if fc.name == "look_around":
            action = (fc.args or {}).get("action", "")
            print(f"\n[tool] look_around({action!r}) ...", flush=True)
            said = await asyncio.to_thread(head_link.look, action)
            print(f"[tool] -> {said!r}", flush=True)
        else:
            said = f"I do not have a tool called {fc.name}."
        responses.append(types.FunctionResponse(
            id=fc.id, name=fc.name, response={"result": said}))
    await session.send_tool_response(function_responses=responses)


async def receive_audio(session):
    """Turns Gemini's transcript into sentences for Piper to speak."""
    global last_was_input, speak_turn
    text_buffer = ""
    while True:
        turn = session.receive()
        async for response in turn:
            # BEFORE the server_content check. A tool call arrives with
            # server_content EMPTY, so `if not sc: continue` swallows it and
            # the model then waits forever for a result that never comes -
            # which looks exactly like the model deciding not to use the tool.
            if response.tool_call:
                await handle_tool_call(session, response.tool_call)
                continue
            sc = response.server_content
            if not sc:
                continue
            if sc.interrupted:
                # Barge-in: invalidate this turn so the worker drops whatever
                # it is speaking, then throw away everything still pending.
                # Tell the head BEFORE bumping, so it knows which turn to cancel.
                head_link.stop(speak_turn)
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
                    if head_link.VERBOSE:
                        print(f"\n[LLM sentence] {sentence!r}", flush=True)
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
            if head_link.VERBOSE:
                print(f"\n[LLM tail] {text_buffer.strip()!r}", flush=True)
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
        head_link.stop(speak_turn, reason="shutdown")
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
