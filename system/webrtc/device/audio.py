import asyncio
import contextlib
import fractions
import logging
import threading
import time
import wave
from collections import deque
from pathlib import Path

import numpy as np
from av import AudioFrame, AudioResampler
from aiortc.mediastreams import AudioStreamTrack, MediaStreamError

from openpilot.common.basedir import BASEDIR

AUDIO_PTIME = 0.020
MIC_SAMPLE_RATE = 16000
SPEAKER_SAMPLE_RATE = 48000
SPEAKER_FRAME_SIZE = int(SPEAKER_SAMPLE_RATE * AUDIO_PTIME)


class PcmBuffer:
  def __init__(self):
    self._chunks: deque[np.ndarray] = deque()
    self._offset = 0
    self._size = 0

  def push(self, samples: np.ndarray):
    if samples.size == 0:
      return
    chunk = np.ascontiguousarray(samples, dtype=np.int16)
    self._chunks.append(chunk)
    self._size += chunk.size

  def available(self) -> int:
    return self._size

  def pop(self, size: int) -> np.ndarray:
    out = np.zeros(size, dtype=np.int16)
    written = 0

    while written < size and self._chunks:
      chunk = self._chunks[0]
      remaining = chunk.size - self._offset
      take = min(size - written, remaining)
      out[written:written + take] = chunk[self._offset:self._offset + take]
      written += take
      self._offset += take

      if self._offset >= chunk.size:
        self._chunks.popleft()
        self._offset = 0

    self._size -= written
    return out


def load_body_sound_clips(sound_files: dict[str, str]) -> dict[str, np.ndarray]:
  loaded: dict[str, np.ndarray] = {}
  sounds_dir = Path(BASEDIR) / "selfdrive" / "assets" / "sounds"
  for sound_name, filename in sound_files.items():
    with wave.open(str(sounds_dir / filename), "rb") as sound_file:
      assert sound_file.getnchannels() == 1
      assert sound_file.getsampwidth() == 2
      assert sound_file.getframerate() == SPEAKER_SAMPLE_RATE
      loaded[sound_name] = np.frombuffer(sound_file.readframes(sound_file.getnframes()), dtype=np.int16).copy()
  return loaded


def audio_frame_to_mono_samples(frame: AudioFrame) -> np.ndarray:
  samples = frame.to_ndarray()
  if samples.ndim == 1:
    mono = samples
  elif samples.ndim == 2:
    if samples.shape[0] <= 8 and samples.shape[0] < samples.shape[1]:
      samples = samples.T
    if samples.shape[1] == 1:
      mono = samples[:, 0]
    else:
      mono = np.mean(samples.astype(np.int32), axis=1).astype(np.int16)
  else:
    raise ValueError(f"Unsupported audio frame shape: {samples.shape}")

  return np.ascontiguousarray(mono, dtype=np.int16)


class BodyMicAudioTrack(AudioStreamTrack):
  def __init__(self):
    import sounddevice as sd

    super().__init__()
    self.logger = logging.getLogger("webrtcd")
    self._loop = asyncio.get_running_loop()
    self._buffer = PcmBuffer()
    self._buffer_event = asyncio.Event()
    self._sample_rate = MIC_SAMPLE_RATE
    self._samples_per_frame = int(self._sample_rate * AUDIO_PTIME)
    self._lock = threading.Lock()
    self._sd = sd
    self._stream = self._sd.InputStream(
      channels=1,
      samplerate=self._sample_rate,
      blocksize=self._samples_per_frame,
      callback=self._callback,
    )
    self._stream.start()

  def _callback(self, indata, frames, _time_info, status):
    if status:
      self.logger.warning("Mic input stream status: %s", status)

    pcm_samples = np.clip(indata[:, 0], -1.0, 1.0)
    pcm_int16 = (pcm_samples * 32767).astype(np.int16)

    def _push():
      with self._lock:
        self._buffer.push(pcm_int16)
      self._buffer_event.set()

    self._loop.call_soon_threadsafe(_push)

  async def recv(self):
    if self.readyState != "live":
      raise MediaStreamError

    while True:
      with self._lock:
        if self._buffer.available() >= self._samples_per_frame:
          frame_samples = self._buffer.pop(self._samples_per_frame)
          break
        self._buffer_event.clear()
      if self.readyState != "live":
        raise MediaStreamError
      await self._buffer_event.wait()

    if hasattr(self, "_timestamp"):
      self._timestamp += self._samples_per_frame
      wait = self._start + (self._timestamp / self._sample_rate) - time.time()
      await asyncio.sleep(wait)
    else:
      self._start = time.time()
      self._timestamp = 0

    frame = AudioFrame(format="s16", layout="mono", samples=self._samples_per_frame)
    frame.planes[0].update(frame_samples.tobytes())
    frame.pts = self._timestamp
    frame.sample_rate = self._sample_rate
    frame.time_base = fractions.Fraction(1, self._sample_rate)
    return frame

  def stop(self):
    super().stop()
    self._buffer_event.set()
    if self._stream is not None:
      self._stream.stop()
      self._stream.close()
      self._stream = None


class BodySpeaker:
  def __init__(self, sound_files: dict[str, str]):
    import sounddevice as sd

    self.logger = logging.getLogger("webrtcd")
    self._sd = sd
    self._lock = threading.Lock()
    self._live_buffer = PcmBuffer()
    self._sound_buffer = PcmBuffer()
    self._track_task: asyncio.Task | None = None
    self._stream = None
    self._loaded_sounds = load_body_sound_clips(sound_files)
    self._resampler = AudioResampler(
      format="s16",
      layout="mono",
      rate=SPEAKER_SAMPLE_RATE,
      frame_size=SPEAKER_FRAME_SIZE,
    )

  def _ensure_stream_started(self):
    if self._stream is not None:
      return

    self._stream = self._sd.OutputStream(
      channels=1,
      samplerate=SPEAKER_SAMPLE_RATE,
      blocksize=SPEAKER_FRAME_SIZE,
      callback=self._callback,
    )
    self._stream.start()

  def _callback(self, outdata, frames, _time_info, status):
    if status:
      self.logger.warning("Speaker output stream status: %s", status)

    with self._lock:
      live = self._live_buffer.pop(frames)
      sound = self._sound_buffer.pop(frames)

    mixed = live.astype(np.int32) + sound.astype(np.int32)
    np.clip(mixed, -32768, 32767, out=mixed)
    outdata[:, 0] = mixed.astype(np.float32) / 32768.0

  def play_sound(self, sound_name: str):
    self._ensure_stream_started()
    with self._lock:
      self._sound_buffer.push(self._loaded_sounds[sound_name].copy())

  def start_track(self, track):
    assert self._track_task is None
    self._ensure_stream_started()
    self._track_task = asyncio.create_task(self._run_track(track))

  async def _run_track(self, track):
    from aiortc.mediastreams import MediaStreamError

    try:
      while True:
        frame = await track.recv()
        for resampled_frame in self._resampler.resample(frame):
          samples = audio_frame_to_mono_samples(resampled_frame)
          with self._lock:
            self._live_buffer.push(samples)
    except MediaStreamError:
      self.logger.info("Incoming browser audio track ended")
    except asyncio.CancelledError:
      raise
    except Exception:
      self.logger.exception("Incoming browser audio failure")

  async def stop(self):
    if self._track_task is not None and not self._track_task.done():
      self._track_task.cancel()
      with contextlib.suppress(asyncio.CancelledError):
        await self._track_task
    self._track_task = None

    if self._stream is not None:
      self._stream.stop()
      self._stream.close()
      self._stream = None
