"""
Whisper STT microphone listener.

Continuously transcribes microphone input using local Whisper model.
Applies VAD (voice activity detection) via silence detection.
Passes complete utterances to the reaction filter.
"""

import asyncio
import queue
import threading
import numpy as np
import sounddevice as sd
import whisper
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)

# Audio settings
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 0.5        # seconds per audio chunk
SILENCE_THRESHOLD = 0.01    # RMS below this = silence
SILENCE_DURATION = 1.2      # seconds of silence to end an utterance
MAX_UTTERANCE = 30.0        # seconds - maximum utterance length


class STTListener:
    def __init__(self, on_utterance):
        """
        on_utterance: async callable that receives a transcribed string.
        Called in the asyncio event loop when a complete utterance is detected.
        """
        self._on_utterance = on_utterance
        self._model = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._running = False
        self._loop = None

    def _load_model(self):
        """Load Whisper model. Runs once on first start."""
        log.info("stt.loading_model", model=settings.stt_model)
        self._model = whisper.load_model(settings.stt_model)
        log.info("stt.model_loaded", model=settings.stt_model)

    def _audio_callback(self, indata, frames, time, status):
        """Called by sounddevice on each audio chunk."""
        if status:
            log.debug("stt.audio_status", status=str(status))
        self._audio_queue.put(indata.copy())

    def _process_audio(self):
        """
        Background thread: collects audio chunks into utterances,
        transcribes complete utterances with Whisper.
        """
        chunks = []
        silence_chunks = 0
        silence_threshold_chunks = int(SILENCE_DURATION / CHUNK_DURATION)
        max_chunks = int(MAX_UTTERANCE / CHUNK_DURATION)

        while self._running:
            try:
                chunk = self._audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            rms = float(np.sqrt(np.mean(chunk ** 2)))
            is_silent = rms < SILENCE_THRESHOLD

            if not is_silent:
                chunks.append(chunk)
                silence_chunks = 0
            elif chunks:
                silence_chunks += 1
                chunks.append(chunk)

                # End of utterance: enough silence, or max length reached
                if silence_chunks >= silence_threshold_chunks or len(chunks) >= max_chunks:
                    audio = np.concatenate(chunks, axis=0).flatten().astype(np.float32)
                    chunks = []
                    silence_chunks = 0
                    self._transcribe_and_dispatch(audio)

    def _transcribe_and_dispatch(self, audio: np.ndarray):
        """Transcribe audio and dispatch to async handler."""
        try:
            # Build initial prompt with character names to improve STT accuracy
            from party.models import CHARACTERS
            names = ", ".join(c.display_name for c in CHARACTERS.values())
            initial_prompt = f"The characters are: {names}, Moonie, The Dungeon Arcade. Please transcribe accurately."

            result = self._model.transcribe(
                audio,
                language=settings.stt_language,
                initial_prompt=initial_prompt,
                fp16=False,
            )
            text = result["text"].strip()

            if not text:
                return

            word_count = len(text.split())
            if word_count < settings.stt_min_words:
                log.debug("stt.utterance_too_short", words=word_count, text=text)
                return

            log.info("stt.utterance_transcribed", words=word_count, text=text[:80])

            # Dispatch to async event loop
            if self._loop and not self._loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    self._on_utterance(text),
                    self._loop,
                )

        except Exception as e:
            log.warning("stt.transcription_failed", reason=str(e))

    async def start(self):
        """Start the STT listener."""
        if not settings.stt_enabled:
            log.info("stt.disabled")
            return

        self._loop = asyncio.get_event_loop()
        self._running = True

        # Load model in thread pool to avoid blocking
        await asyncio.get_event_loop().run_in_executor(None, self._load_model)

        # Start audio processing thread
        processing_thread = threading.Thread(
            target=self._process_audio,
            daemon=True,
            name="stt-processor",
        )
        processing_thread.start()

        # Start microphone stream
        device = settings.stt_device_index if settings.stt_device_index >= 0 else None
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=np.float32,
            blocksize=int(SAMPLE_RATE * CHUNK_DURATION),
            device=device,
            callback=self._audio_callback,
        )
        self._stream.start()
        log.info("stt.started", model=settings.stt_model, device=device or "default")

    async def stop(self):
        """Stop the STT listener cleanly."""
        self._running = False
        if hasattr(self, "_stream"):
            self._stream.stop()
            self._stream.close()
        log.info("stt.stopped")
