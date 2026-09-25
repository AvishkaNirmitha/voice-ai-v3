"""Timestamped recordings of what the mic heard, written off the audio path.

Two streams are kept for every utterance: the mic as it arrived (raw) and the
mic as Gemini received it (after AEC3, and after RNNoise when --denoise is on).
The pair is the only honest way to see what the filters did to a real person in
a real room, as opposed to what they do to a test tone.

NOTHING IS WRITTEN ON THE MIC THREAD. offer() does one bounded put_nowait and
returns; a writer thread does the buffering, the cutting and the WAV encoding.
If the writer ever falls behind, frames are dropped and counted rather than
allowed to stall capture -- a recording with a gap in it is worth less than a
conversation with a gap in it.

WHERE THE CUTS COME FROM: Gemini's own voice activity detector. The Live API
reports ACTIVITY_START and ACTIVITY_END with an audio_offset, a position in the
very stream we are sending it, so each file holds exactly what the model treated
as one turn -- and there is no second VAD to disagree with it. The offset points
into the recent past, which is why the writer keeps a ring buffer: by the time
the signal arrives over the network the audio it refers to has already gone by.

A model that sends no such signal falls back to the transcript: the first
input_transcription of a turn opens a segment and the end of the turn closes
it. That is coarser -- transcription lags further behind the audio than the VAD
does -- and it says so in the log.
"""

import queue
import threading
import time
import wave
from collections import deque, namedtuple
from pathlib import Path

RATE = 16000              # both streams, the rate the whole voice loop runs at
RING_S = 3.0              # how far back a retroactive cut is allowed to reach
PRE_ROLL_S = 0.4          # kept before the cut, so the first word is not clipped
TAIL_S = 0.5              # kept after it, for the same reason
MAX_UTTERANCE_S = 120.0   # a segment whose end never arrives is flushed anyway
QUEUE_FRAMES = 3000       # 30 s of 10 ms frames before frames start being dropped

# Marks share the queue with audio so they stay in order relative to it.
Mark = namedtuple("Mark", "start offset_s")


def _stamp():
    """Sortable local timestamp, to the millisecond.

    Milliseconds are not decoration: two utterances inside one second is normal
    when someone speaks in short bursts, and without them the second recording
    would overwrite the first.
    """
    t = time.time()
    return time.strftime("%Y%m%d-%H%M%S", time.localtime(t)) + f"-{int(t % 1 * 1000):03d}"


def _offset_s(value):
    """A proto Duration as the Live API sends it ("12.34s") -> seconds, or None."""
    if value is None:
        return None
    try:
        text = str(value).strip()
        return float(text[:-1] if text.endswith("s") else text)
    except ValueError:
        return None


class Recorder:
    """Saves each utterance as a pair of WAVs, on its own thread.

    start() before the mic does, close() after it stops. offer() is for the mic
    thread; vad() and fallback() are for the event loop.
    """

    def __init__(self, outdir, verbose=False):
        self.outdir = Path(outdir)
        self.dropped = 0          # mic frames the writer could not keep up with
        self.written = 0          # utterances on disk
        self._verbose = verbose
        self._q = queue.Queue(maxsize=QUEUE_FRAMES)
        self._thread = threading.Thread(target=self._run, name="mic-record",
                                        daemon=True)
        self._saw_vad = False     # a real signal arrived, so ignore the fallback
        self._warned_offset = False

    @property
    def saw_vad(self):
        """True once Gemini has sent a voice activity signal of its own.

        Worth reporting: it is the difference between segments that match what
        the model treated as a turn and segments guessed from the transcript.
        """
        return self._saw_vad

    # --- the mic thread ----------------------------------------------------

    def offer(self, raw, clean):
        """One mic frame, before and after filtering. Never blocks."""
        try:
            self._q.put_nowait((raw, clean))
        except queue.Full:
            self.dropped += 1

    # --- the event loop ----------------------------------------------------

    def vad(self, start, offset=None):
        """Gemini's ACTIVITY_START / ACTIVITY_END. Authoritative once seen."""
        if not self._saw_vad:
            self._saw_vad = True
            print("[rec] cutting on Gemini's voice activity signals", flush=True)
        self._mark(start, _offset_s(offset))

    def fallback(self, start):
        """Transcript-derived activity, used only until a real VAD signal arrives."""
        if not self._saw_vad:
            self._mark(start, None)

    def _mark(self, start, offset_s):
        try:
            self._q.put_nowait(Mark(start, offset_s))
        except queue.Full:
            pass    # a lost mark costs one segment boundary, not the recording

    # --- lifecycle ---------------------------------------------------------

    def start(self):
        self.outdir.mkdir(parents=True, exist_ok=True)
        self._thread.start()
        print(f"[rec] saving utterances to {self.outdir}", flush=True)

    def close(self):
        """Flush whatever is open and stop. Safe to call once the mic has gone."""
        try:
            self._q.put(None, timeout=1)
        except queue.Full:
            return      # pathological, and the writer is a daemon: let it go
        self._thread.join(timeout=10)

    # --- the writer thread -------------------------------------------------

    def _run(self):
        # While nothing is being recorded, frames go here and the oldest fall
        # off the end. This is what lets a cut reach backwards in time.
        ring = deque(maxlen=int(RING_S * 100))
        seg = None
        clean_total = 0     # samples of filtered audio seen, the VAD's timeline

        while True:
            item = self._q.get()
            if item is None:
                break

            if isinstance(item, Mark):
                if item.start:
                    if seg is None:
                        seg = self._open(ring, clean_total, item.offset_s)
                    else:
                        # Still inside an utterance. A second start means the
                        # VAD re-triggered after a pause it had called the end,
                        # so cancel the pending flush and keep one file.
                        seg["close_at"] = None
                elif seg is not None and seg["close_at"] is None:
                    end = self._target(item.offset_s, clean_total)
                    seg["close_at"] = end + int(TAIL_S * RATE)
                continue

            raw, clean = item
            clean_total += len(clean) // 2
            if seg is None:
                ring.append((raw, clean, clean_total))
                continue

            seg["raw"].append(raw)
            seg["clean"].append(clean)
            seg["samples"] += len(raw) // 2
            if ((seg["close_at"] is not None and clean_total >= seg["close_at"])
                    or seg["samples"] >= MAX_UTTERANCE_S * RATE):
                self._flush(seg)
                seg = None

        if seg is not None:
            self._flush(seg)    # the session ended mid-utterance; keep it anyway

    def _target(self, offset_s, clean_total):
        """The sample in the filtered stream that a VAD offset points at.

        The offset is trusted only when it lands inside audio we have actually
        sent. A model that measures it from somewhere else, or a session that
        resumed, would otherwise cut in entirely the wrong place -- and "the
        position right now" is a safe answer, just a less precise one.
        """
        if offset_s is None:
            return clean_total
        target = int(offset_s * RATE)
        if 0 <= target <= clean_total + RATE:
            return min(target, clean_total)
        if not self._warned_offset:
            self._warned_offset = True
            print(f"[rec] ignoring voice-activity offsets: {offset_s:g}s does not fit "
                  f"{clean_total / RATE:.1f}s of audio; cutting on arrival instead",
                  flush=True)
        return clean_total

    def _open(self, ring, clean_total, offset_s):
        cut = self._target(offset_s, clean_total) - int(PRE_ROLL_S * RATE)
        seg = {"stamp": _stamp(), "raw": [], "clean": [], "samples": 0,
               "close_at": None}
        for raw, clean, clean_end in ring:
            if clean_end > cut:
                seg["raw"].append(raw)
                seg["clean"].append(clean)
                seg["samples"] += len(raw) // 2
        ring.clear()        # its contents are in the segment now, or discarded
        return seg

    def _flush(self, seg):
        for kind in ("raw", "clean"):
            pcm = b"".join(seg[kind])
            if not pcm:
                continue    # no filtered audio yet: the utterance was very short
            path = self.outdir / f"mic-{seg['stamp']}-{kind}.wav"
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(pcm)
        self.written += 1
        if self._verbose:
            print(f"[rec] mic-{seg['stamp']}-*.wav  {seg['samples'] / RATE:.1f}s",
                  flush=True)
