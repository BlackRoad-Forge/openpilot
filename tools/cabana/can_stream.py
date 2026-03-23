from __future__ import annotations

import bisect
import json
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path

from openpilot.tools.lib.logreader import LogReader
from openpilot.tools.lib.route import Route

DEMO_ROUTE = "5beb9b58bd12b691/0000010a--a51155e496"

FINGERPRINT_TO_DBC = json.loads(
  (Path(__file__).parent / "dbc" / "car_fingerprint_to_dbc.json").read_text()
)

_BIT_POSITIONS: list[list[int]] = []
for _i in range(256):
  _BIT_POSITIONS.append([b for b in range(8) if _i & (1 << b)])


@dataclass
class CanEvent:
  mono_time: int
  src: int
  address: int
  dat: bytes


MessageId = tuple[int, int]


@dataclass
class MessageData:
  address: int
  src: int
  dat: bytes
  count: int
  freq: float
  byte_colors: list[tuple[int, int, int]]
  name: str = ""


@dataclass
class MessageState:
  events: list[CanEvent] = field(default_factory=list)
  bit_flip_counts: list[int] = field(default_factory=list)
  _prev_dat: bytes = b''


class CanStream:
  def __init__(self, route: str):
    self.route = route
    self.fingerprint: str = ""
    self.dbc_name: str = ""

    self._messages: dict[MessageId, MessageState] = {}
    self._time_range: tuple[float, float] = (0.0, 0.0)
    self._current_sec: float = 0.0
    self._playing: bool = True
    self._speed: float = 1.0

    self._loaded = False
    self._loading = True
    self._load_progress: str = "Connecting..."
    self._load_frac: float = 0.0
    self._lock = threading.Lock()

    self._thread = threading.Thread(target=self._load, args=(route,), daemon=True)
    self._thread.start()

  @property
  def loaded(self) -> bool:
    return self._loaded

  @property
  def loading(self) -> bool:
    return self._loading

  @property
  def load_progress(self) -> str:
    return self._load_progress

  @property
  def load_frac(self) -> float:
    return self._load_frac

  def _load(self, route: str):
    print(f"Loading route: {route}")
    self._load_progress = "Connecting..."

    total_segments = 0
    try:
      total_segments = len(Route(route).log_paths())
    except Exception:
      pass

    try:
      lr = LogReader(route, sort_by_time=False)
    except Exception as e:
      self._load_progress = f"Error: {e}"
      self._loading = False
      return

    messages: dict[MessageId, MessageState] = {}
    min_time = float('inf')
    max_time = 0
    event_count = 0
    fingerprint = ""
    last_publish = 0
    last_yield = time.monotonic()

    for msg in lr:
      w = msg.which()

      if w == "carParams" and not fingerprint:
        cp = msg.carParams
        fingerprint = cp.carFingerprint
        dbc_name = FINGERPRINT_TO_DBC.get(fingerprint, "")
        print(f"Car: {fingerprint}, DBC: {dbc_name}")
        with self._lock:
          self.fingerprint = fingerprint
          self.dbc_name = dbc_name

      elif w == "can":
        mono_time = msg.logMonoTime
        for c in msg.can:
          dat = bytes(c.dat)
          mid = (c.src, c.address)
          if mid not in messages:
            messages[mid] = MessageState()
          ms = messages[mid]
          ms.events.append(CanEvent(mono_time=mono_time, src=c.src, address=c.address, dat=dat))

          n_bytes = len(dat)
          if not ms.bit_flip_counts:
            ms.bit_flip_counts = [0] * (n_bytes * 8)
            ms._prev_dat = dat
          else:
            needed = n_bytes * 8
            if len(ms.bit_flip_counts) < needed:
              ms.bit_flip_counts.extend([0] * (needed - len(ms.bit_flip_counts)))
            prev = ms._prev_dat
            for bi in range(min(len(prev), n_bytes)):
              diff = prev[bi] ^ dat[bi]
              if diff:
                base = bi * 8
                for bit in _BIT_POSITIONS[diff]:
                  ms.bit_flip_counts[base + bit] += 1
            ms._prev_dat = dat

          if mono_time < min_time:
            min_time = mono_time
          if mono_time > max_time:
            max_time = mono_time
          event_count += 1

      # Yield GIL so UI stays responsive
      now = time.monotonic()
      if now - last_yield > 0.008:
        time.sleep(0.002)
        last_yield = time.monotonic()

      # Publish snapshot
      if event_count - last_publish >= 40000:
        last_publish = event_count
        est = total_segments * 50000 if total_segments else event_count * 2
        self._load_frac = min(0.95, event_count / max(1, est))
        self._load_progress = f"Loading... {len(messages)} messages"
        tr = (min_time / 1e9, max_time / 1e9)
        snapshot = dict(messages)
        with self._lock:
          self._messages = snapshot
          self._time_range = tr

    # Sort per-message events
    for ms in messages.values():
      ms.events.sort(key=lambda e: e.mono_time)

    tr = (min_time / 1e9, max_time / 1e9) if event_count > 0 else (0.0, 0.0)
    with self._lock:
      self._messages = messages
      self._time_range = tr

    self._loaded = True
    self._loading = False
    self._load_progress = ""
    self._load_frac = 1.0
    print(f"Loaded {event_count} CAN events, {len(messages)} unique messages")

  @property
  def message_ids(self) -> list[MessageId]:
    with self._lock:
      return list(self._messages.keys())

  @property
  def time_range(self) -> tuple[float, float]:
    return self._time_range

  @property
  def current_sec(self) -> float:
    return self._current_sec

  @current_sec.setter
  def current_sec(self, val: float) -> None:
    self._current_sec = max(0.0, min(val, self.duration))

  @property
  def duration(self) -> float:
    return self._time_range[1] - self._time_range[0]

  @property
  def playing(self) -> bool:
    return self._playing

  @playing.setter
  def playing(self, val: bool) -> None:
    self._playing = val

  @property
  def speed(self) -> float:
    return self._speed

  @speed.setter
  def speed(self, val: float) -> None:
    self._speed = val

  def tick(self, dt: float) -> None:
    if self._playing and self.duration > 0:
      self._current_sec += dt * self._speed
      if self._current_sec >= self.duration:
        self._current_sec = self.duration
        self._playing = False

  def current_messages(self) -> dict[MessageId, MessageData]:
    with self._lock:
      messages = self._messages
      time_range = self._time_range

    if not messages:
      return {}

    abs_time_ns = int((time_range[0] + self._current_sec) * 1e9)
    result: dict[MessageId, MessageData] = {}

    for mid, ms in messages.items():
      events = ms.events
      if not events:
        continue

      idx = bisect.bisect_right(events, abs_time_ns, key=lambda e: e.mono_time) - 1
      if idx < 0:
        continue

      ev = events[idx]
      count = idx + 1

      freq = 0.0
      if count >= 2:
        lookback = max(0, idx - 99)
        t_span = (events[idx].mono_time - events[lookback].mono_time) / 1e9
        if t_span > 0:
          freq = (idx - lookback) / t_span

      byte_colors = []
      prev_dat = events[idx - 1].dat if idx > 0 else None
      for bi in range(len(ev.dat)):
        if prev_dat and bi < len(prev_dat):
          if ev.dat[bi] > prev_dat[bi]:
            byte_colors.append((70, 130, 230))
          elif ev.dat[bi] < prev_dat[bi]:
            byte_colors.append((230, 80, 80))
          else:
            byte_colors.append((80, 80, 80))
        else:
          byte_colors.append((80, 80, 80))

      result[mid] = MessageData(
        address=mid[1],
        src=mid[0],
        dat=ev.dat,
        count=count,
        freq=freq,
        byte_colors=byte_colors,
      )

    return result

  def get_events(self, mid: MessageId) -> list[CanEvent]:
    with self._lock:
      ms = self._messages.get(mid)
    return ms.events if ms else []

  def get_bit_flip_counts(self, mid: MessageId) -> list[int]:
    with self._lock:
      ms = self._messages.get(mid)
    return ms.bit_flip_counts if ms else []
