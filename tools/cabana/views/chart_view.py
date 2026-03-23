from __future__ import annotations

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.line_chart import LineChart, ChartSeries
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.tools.cabana.can_stream import CanStream, MessageId
from openpilot.tools.cabana.dbc_manager import DBCManager
from opendbc.can.dbc import Signal

BG_COLOR = rl.Color(15, 15, 15, 255)
PAD = 8
FONT_SIZE = 18

CHART_COLORS = [
  rl.Color(255, 100, 100, 255),
  rl.Color(100, 200, 255, 255),
  rl.Color(100, 255, 100, 255),
  rl.Color(255, 255, 100, 255),
]


class ChartView(Widget):
  """Signal line chart showing decoded values over time."""

  def __init__(self, stream: CanStream, dbc: DBCManager):
    super().__init__()
    self._stream = stream
    self._dbc = dbc
    self._chart = self._child(LineChart())
    self._selected_mid: MessageId | None = None
    self._selected_signal: Signal | None = None
    self._cached_series: list[ChartSeries] | None = None
    self._cached_key: tuple | None = None

  def set_signal(self, mid: MessageId, sig: Signal) -> None:
    self._selected_mid = mid
    self._selected_signal = sig
    self._cached_series = None
    self._cached_key = None

  def _build_series(self) -> list[ChartSeries]:
    if self._selected_mid is None or self._selected_signal is None:
      return []

    mid = self._selected_mid
    sig = self._selected_signal
    events = self._stream.get_events(mid)

    if not events:
      return []

    t0 = self._stream.time_range[0]
    points: list[tuple[float, float]] = []

    for ev in events:
      t = ev.mono_time / 1e9 - t0
      try:
        val = self._dbc.decode_signal(ev.dat, sig)
        points.append((t, val))
      except Exception:
        pass

    return [ChartSeries(label=sig.name, color=CHART_COLORS[0], points=points)]

  def _render(self, rect: rl.Rectangle):
    if self._selected_signal is None:
      rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height), BG_COLOR)
      font = gui_app.font(FontWeight.NORMAL)
      rl.draw_text_ex(font, "Click a signal to chart",
                      rl.Vector2(rect.x + PAD, rect.y + PAD),
                      FONT_SIZE, 0, rl.Color(100, 100, 100, 255))
      return

    # Build/cache series
    key = (self._selected_mid, self._selected_signal.name)
    if self._cached_key != key:
      self._cached_series = self._build_series()
      self._cached_key = key

    if self._cached_series:
      self._chart.set_series(self._cached_series)
      self._chart.set_x_range(0, self._stream.duration)
      self._chart.set_cursor(self._stream.current_sec)

    self._chart.render(rect)
