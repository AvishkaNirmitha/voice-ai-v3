"""Spera voice robot, with head motion.

Identical to main.py except that the head is driven in sync with the speech:
head.py owns all of the motion, this file only reports events to it. The same
pose stream drives the simulation window and, when one is reachable, the real
neck over head_link -- so the window is a picture of what the hardware is
doing, not a separate animation of it.

    python main_with_head.py                     # window + hardware if present
    python main_with_head.py --no-window         # headless (Jetson)
    python main_with_head.py --no-head           # simulation only
    python main_with_head.py --head 192.168.1.159:8770
    python main_with_head.py --verbose           # print every UDP datagram
    python main_with_head.py --llm-print         # Gemini's raw text, tags and all
    python main_with_head.py --blocking-look     # let the head run its own
                                                 # 9s sweep (silences the reply)

Two knobs exist for the gap between what the simulation shows and what a real
neck achieves -- the sim has no inertia, the hardware does:

    --gain 2.2          scale the angle sent to the neck (not the simulation)
    --gesture-rate 0.7  slow every gesture down, so the neck can keep up
"""

import asyncio
import queue
import re
import sys
import threading
import time
from pathlib import Path
import pyaudio
import sounddevice as sd
from google import genai
from google.genai import types
from piper import PiperVoice, SynthesisConfig

import head
from head import (HeadMotion, HeadWindow, Plan, plan_sentence, rms_level,
                  strip_tags)

client = genai.Client()

# --- pyaudio config (microphone only; Piper owns the speaker) ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
CHUNK_SIZE = 1024

pya = pyaudio.PyAudio()

# --- Head -----------------------------------------------------------------
# Created here so the tool handlers can reach it; the motion thread, the
# window and the hardware handshake all happen in run().


def _arg(flag, default=None):
    return (sys.argv[sys.argv.index(flag) + 1]
            if flag in sys.argv and sys.argv.index(flag) + 1 < len(sys.argv)
            else default)


HW = None               # RobotHeadController, or None for simulation only
HEAD_PRESENT = False    # set in run() once the head answers limits()

# Show Gemini's transcript exactly as it arrives, tags and all, before
# strip_tags() removes them and before Piper ever sees it. This is the only
# place the model's raw output is visible: everything printed later is the
# cleaned text. Underscore spelling accepted too, since both read naturally.
LLM_PRINT = "--llm-print" in sys.argv or "--llm_print" in sys.argv

if "--no-head" not in sys.argv:
    try:
        import head_hw
        import head_link
        HW = head_hw.connect(_arg("--head"), verbose="--verbose" in sys.argv,
                             gain=_arg("--gain"))
        if _arg("--gesture-rate"):
            head.GESTURE_RATE_SCALE = float(_arg("--gesture-rate"))
    except Exception as e:
        print(f"[head] no hardware link ({e}); simulation only")

# One motion system, whichever controller it ended up with.
HEAD = HeadMotion(controller=HW)

# --- Piper TTS ------------------------------------------------------------
# Loaded once, here at import time, so no utterance ever pays the model cost.
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
# noticed. This is what bounds barge-in latency. It is also the natural clock
# for the loudness envelope the head rides on: one RMS reading per slice.
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
    "developed by the Spera Team Using most advanced AI technologies in the planet. "
    "Your highest priority is maintaining a safe and secure environment. "
    "You continuously monitor the surrounding environment, observe movements "
    "use \"sir\" when addressing people, and provide clear and concise information. "
    # HEAD GESTURES. One label per sentence, at a fixed position, from a
    # four-word vocabulary -- a classification the model can actually do. The
    # earlier instruction ("include emotion actions within each sentence") was
    # decoration and got placed at random: questions came back tagged as head
    # shakes and refusals as calm. head.plan_sentence maps these to gestures,
    # and falls back to reading the text when a tag is missing.
    "HEAD GESTURES: Begin EVERY sentence with exactly one intent tag, chosen "
    "from these four: [deny] [affirm] [ask] [neutral]. "
    "Use [deny] whenever your sentence says NO: refusing a request, denying "
    "something, saying you cannot do something, OR answering the user's "
    "yes/no question in the negative. If the user asks whether something is "
    "there and you answer that it is not, that is [deny] -- you are saying "
    "no to them, even when the news is good. "
    "Use [affirm] when you are confirming, agreeing, answering yes, or "
    "reporting unprompted that all is well. "
    "Use [ask] when the sentence is a question to the user. "
    "Use [neutral] ONLY when none of the other three apply. "
    "Never use [neutral] for a sentence that ends in a question mark -- that "
    "is always [ask]. Never use [neutral] for a sentence saying you cannot, "
    "will not, or are not allowed to do something -- that is always [deny]. "
    "The tag goes at the START of the sentence, before the first word, and "
    "never anywhere else. Use exactly one per sentence. "
    "Example: [affirm] The area is clear, sir. [deny] I cannot access the "
    "first floor. [ask] Is there anything else you need, sir? "
    # look_around costs a real head sweep and a pause in the conversation, so
    # it has to be asked for rather than merely permitted. The looser wording
    # this replaces had the model sweeping the room in response to "Hello".
    "TOOL USE GUIDE: "
    "Use the \"look_around\" tool ONLY when the user asks you to look, check, "
    "scan, inspect, or patrol the surroundings, or asks what you can see right "
    "now. Do NOT use it for greetings, for small talk, for questions about "
    "yourself or your capabilities, or for anything you can answer without "
    "looking. When in doubt, answer without the tool."
)


# --- Tools --------------------------------------------------------------
# Each entry: name -> (declaration, handler). The handler takes the call's
# args dict and returns a JSON-serializable result. To add a tool, add one
# entry here; the declaration and dispatch are derived from this registry.
# Gemini 3.1 Flash Live supports synchronous function calling only: the model
# stays silent until send_tool_response is called, so keep handlers fast.

def _tool_get_current_time(args):
    return {"time": time.strftime("%Y-%m-%d %H:%M:%S")}

def _get_current_user_name(args):
    return {"username": "spera Administration"}

SCAN_SECONDS = 1.5   # how long the sweep runs before the reply starts

def _tool_look_around(args):
    # A deliberate, discrete action, unlike the speech-synced gestures. Gemini
    # stays silent until this returns, so taking a moment here is what makes
    # the sweep visible at all -- otherwise the first sentence's gesture
    # replaces it within a few hundred milliseconds and the head never looks
    # anywhere. This runs on a worker thread, so the mic and websocket are
    # unaffected.
    #
    # The sweep is driven as an ordinary gesture over jog, NOT through
    # head_link.look(). look("look_around") is a five-stop sweep that blocks
    # for about nine seconds, and because function calling is synchronous that
    # is nine seconds of dead air -- long enough that a stray noise barges in
    # and cancels the reply entirely, which is what it did to a greeting in
    # testing. The head's own spoken report is not worth losing the answer for.
    # --blocking-look opts back into it.
    if HEAD_PRESENT and "--blocking-look" in sys.argv:
        HEAD.begin_gesture(Plan("scan", 8.0, "", "look_around tool"))
        said = head_hw.directed_look(HW, "look_around")
        HEAD.end_speech()
        if said:
            return {"result": said}
    HEAD.begin_gesture(Plan("scan", SCAN_SECONDS + 0.9, "", "look_around tool"))
    time.sleep(SCAN_SECONDS)
    HEAD.end_speech()
    return {"result": "I am looking around the environment for any suspicious activity."}

TOOLS = {
    # "get_current_time": (
    #     {
    #         "name": "get_current_time",
    #         "description": "Returns the current local date and time.",
    #     },
    #     _tool_get_current_time,
    # ),
    # "get_current_user_name": (
    #     {
    #         "name": "get_current_user_name",
    #         "description": "Returns the current user name.",
    #     },
    #     _get_current_user_name,
    # ),
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
    "tools": [{"function_declarations": [decl for decl, _ in TOOLS.values()]}],
    "output_audio_transcription": {},
    "input_audio_transcription": {},
    "speech_config": {
      "voice_config": {
        "prebuilt_voice_config": {
          "voice_name": "Orus",
        }
      },
      "language_code": "en-US"
    },
}

audio_queue_mic = asyncio.Queue(maxsize=5)
audio_stream = None

# Sentences waiting to be spoken, as (turn_id, text, plan). A plain thread
# queue because the consumer is the Piper worker thread, not the event loop.
# The plan travels with the sentence so the gesture is chosen once, at the
# moment the text is known, and simply replayed when the audio starts.
sentence_queue = queue.Queue()

# Bumped on every interruption. The worker drops any sentence tagged with an
# older id, which is how barge-in cancels speech that is queued or in flight.
speak_turn = 0

# Shared by receive_audio (user speech) and speak_worker (model speech) to
# decide when a newline is needed between the two.
last_was_input = False

# True while Gemini is still producing the current turn. An empty
# sentence_queue on its own does not mean the turn is over -- it usually just
# means the next sentence has not been streamed yet -- so the head must not
# offer the turn back on that alone.
turn_active = False


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


# The intent tag opens a sentence, but split_speakable cuts at commas once a
# chunk passes CLAUSE_FLUSH_CHARS -- so a long sentence arrives as several
# chunks and only the first carries the tag. Without this the rest fall back to
# the keyword ladder mid-sentence, which is how "[deny] I cannot fly," / "sir;
# my capabilities are restricted..." ended up planned by two different sources.
# The tag therefore sticks until the sentence actually ends.
pending_tag = ()


def enqueue(sentence):
    """Strip the model's tags, plan a gesture, queue the sentence.

    The tags have to come out here: anything still in the string when it
    reaches Piper is read aloud.
    """
    global pending_tag
    if LLM_PRINT:
        # Raw, before anything is stripped: what the model actually emitted.
        print(f"\n\033[2;36m[llm] {sentence}\033[0m", flush=True)
    clean, tags = strip_tags(sentence)
    if tags:
        pending_tag = tags
    if not clean:
        return          # a chunk that was only a tag; it now applies to the next
    # `inherited` distinguishes a tag this fragment carried itself from one
    # picked up off the sentence it belongs to; plan_sentence trusts the first
    # more than the second.
    sentence_queue.put((speak_turn, clean,
                        plan_sentence(clean, tags or pending_tag,
                                      inherited=not tags)))
    if clean.rstrip()[-1:] in ".!?":
        pending_tag = ()        # sentence finished; the tag does not carry over


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
            turn_id, text, plan = item
            if turn_id != speak_turn:
                continue  # interrupted while this sentence sat in the queue

            if last_was_input:
                print()
                last_was_input = False
            print(text, end=" ", flush=True)

            # Started before synthesis, not after: voice.synthesize blocks for
            # a couple of hundred milliseconds, and that gap is exactly the
            # wind-up the gesture needs to land on the first word rather than
            # trail it.
            HEAD.begin_gesture(plan)

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
                    slice_ = buf[i:i + WRITE_BYTES]
                    # A float handed to the motion thread. Nothing blocking
                    # happens here -- the servo write is on that thread, not
                    # in this loop, so it cannot eat into the audio budget.
                    HEAD.push_rms(rms_level(slice_))
                    stream.write(slice_)
                if interrupted:
                    break
            if interrupted:
                stream.abort()  # discards the buffer, so it goes quiet at once
            else:
                stream.stop()  # drains the buffer so the tail is not clipped
            HEAD.end_speech()
            # Nothing left to say *and* nothing more coming: offer the turn.
            if sentence_queue.empty() and not turn_active:
                HEAD.turn_complete()
    finally:
        stream.close()


async def receive_audio(session):
    """Turns Gemini's transcript into sentences for Piper to speak."""
    global last_was_input, speak_turn, turn_active, pending_tag
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
                pending_tag = ()  # do not carry a cancelled turn's tag forward
                HEAD.interrupt()  # abandon the gesture too, not just the audio
                print()
            if sc.output_transcription:
                turn_active = True
                text_buffer += sc.output_transcription.text
                ready, text_buffer = split_speakable(text_buffer)
                for sentence in ready:
                    enqueue(sentence)
            if sc.input_transcription:
                HEAD.saw_input()
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
            enqueue(text_buffer.strip())
            text_buffer = ""
        turn_active = False
        # If the worker already drained the queue it could not know the turn
        # was still open, so the offer is made from here instead. It no-ops
        # while anything is still being spoken.
        if sentence_queue.empty():
            HEAD.turn_complete()

async def run():
    """Main function to run the audio loop."""
    global speak_turn, HEAD_PRESENT
    HEAD.start()

    # Ask the neck how far it actually travels before anything is drawn or
    # driven: the sliders take their range from it, and the mixer clamps to it.
    # limits() blocks for up to its timeout, hence the thread.
    if HW is not None:
        print(f"[head] output gain pan x{HW.gain_pan:.2f} tilt x{HW.gain_tilt:.2f}"
              f"   gesture rate x{head.GESTURE_RATE_SCALE:.2f}")
        HEAD_PRESENT = await asyncio.to_thread(head_hw.apply_limits, HEAD, HW)
        if HEAD_PRESENT:
            print(f"[head] hardware at {head_link.target()} - "
                  f"travel read from the neck")
        else:
            print(f"[head] no answer from {head_link.target()} - "
                  f"jogs still sent, conservative limits, look_around simulated")

    if "--no-window" not in sys.argv:
        try:
            HeadWindow(HEAD).start()
        except Exception as e:
            print(f"[head] no window ({e}); running with the log only")
    if LLM_PRINT:
        print("[llm]  printing Gemini's raw transcript (tags included)")
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
        if head.TAG_DISAGREEMENTS:
            print(f"\n[head] {len(head.TAG_DISAGREEMENTS)} sentences where the "
                  f"model's tag and the text heuristic disagreed:")
            for text, tagged, guessed in head.TAG_DISAGREEMENTS[-15:]:
                print(f"  tag={tagged:<9} text={guessed:<9} {text[:58]}")
            print("  (the tag won. If the text column reads better, the prompt "
                  "needs work; if the tag column does, the ladder does.)")
        if HW is not None and HW.sent:
            print(f"[head] {HW.sent} jogs sent, {HW.clipped} clipped at the "
                  f"neck's travel ({100 * HW.clipped / HW.sent:.0f}%)")
        HEAD.stop()
        if audio_stream:
            audio_stream.close()
        pya.terminate()
        print("\nConnection closed.")

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("Interrupted by user.")
