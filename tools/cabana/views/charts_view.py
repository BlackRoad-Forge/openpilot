"""Multi-chart container with scrollable chart panels."""
from __future__ import annotations

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.line_chart import LineChart, ChartSeries
from openpilot.system.ui.lib.application import gui_app, FontWeight, FONT_SCALE
from openpilot.tools.cabana.can_stream import CanStream, MessageId
from openpilot.tools.cabana.dbc_manager import DBCManager
from openpilot.tools.cabana.desktop_scroll import DesktopScrollPanel
from openpilot.tools.cabana.settings import Settings
from openpilot.tools.cabana import styles
from opendbc.can.dbc import Signal

CHART_HEADER_H = 28
CHART_MIN_H = 120
TOOLBAR_H = 30
MARGIN_LEFT = 60
MARGIN_RIGHT = 10


class ChartEntry:
  """One chart panel showing one or more signals."""

  def __init__(self, mid: MessageId, sig: Signal, stream: CanStream, dbc: DBCManager):
    self.mid = mid
    self.sig = sig
    self.stream = stream
    self.dbc = dbc
    self.chart = LineChart()
    self._cached_key: tuple | None = None
    self._cached_series: list[ChartSeries] | None = None

  @property
  def label(self) -> str:
    name = self.dbc.msg_name(self.mid[1]) or f"0x{self.mid[1]:03X}"
    return f"{name}.{self.sig.name}"

  def build_series(self) -> list[ChartSeries]:
    events = self.stream.get_events(self.mid)
    if not events:
      return []

    t0 = self.stream.time_range[0]
    points: list[tuple[float, float]] = []
    for ev in events:
      t = ev.mono_time / 1e9 - t0
      try:
        val = self.dbc.decode_signal(ev.dat, self.sig)
        points.append((t, val))
      except Exception:
        pass

    color_idx = hash(self.sig.name) % len(styles.CHART_COLORS)
    return [ChartSeries(label=self.sig.name, color=styles.CHART_COLORS[color_idx], points=points)]

  def update(self):
    key = (self.mid, self.sig.name)
    if self._cached_key != key:
      self._cached_series = self.build_series()
      self._cached_key = key
    if self._cached_series:
      self.chart.set_series(self._cached_series)
      self.chart.set_x_range(0, self.stream.duration)
      self.chart.set_cursor(self.stream.current_sec)


class ChartsView(Widget):
  """Container of multiple chart panels, scrollable."""

  def __init__(self, stream: CanStream, dbc: DBCManager):
    super().__init__()
    self._stream = stream
    self._dbc = dbc
    self._entries: list[ChartEntry] = []
    self._scroll = DesktopScrollPanel()
    self._settings = Settings()

    # Layout state for click handling
    self._chart_rects: list[rl.Rectangle] = []
    self._close_rects: list[rl.Rectangle] = []
    self._col_btn_rects: list[tuple[rl.Rectangle, int]] = []
    self._clear_rect: rl.Rectangle = rl.Rectangle(0, 0, 0, 0)

  def add_signal(self, mid: MessageId, sig: Signal) -> None:
    for e in self._entries:
      if e.mid == mid and e.sig.name == sig.name:
        return
    self._entries.append(ChartEntry(mid, sig, self._stream, self._dbc))

  def remove_signal(self, mid: MessageId, sig_name: str) -> None:
    self._entries = [e for e in self._entries if not (e.mid == mid and e.sig.name == sig_name)]

  def clear(self) -> None:
    self._entries.clear()

  def set_signal(self, mid: MessageId, sig: Signal) -> None:
    self.add_signal(mid, sig)

  def _handle_mouse_release(self, mouse_pos) -> None:
    """Handle clicks via Widget event system."""
    pos = mouse_pos

    # Check close buttons
    for i, cr in enumerate(self._close_rects):
      if i < len(self._entries) and rl.check_collision_point_rec(pos, cr):
        entry = self._entries[i]
        self.remove_signal(entry.mid, entry.sig.name)
        return

    # Check chart body clicks (seek to time)
    for i, chart_rect in enumerate(self._chart_rects):
      if rl.check_collision_point_rec(pos, chart_rect):
        plot_x = chart_rect.x + MARGIN_LEFT
        plot_w = chart_rect.width - MARGIN_LEFT - MARGIN_RIGHT
        if plot_w > 0 and self._stream.duration > 0:
          frac = max(0.0, min(1.0, (pos.x - plot_x) / plot_w))
          self._stream.current_sec = frac * self._stream.duration
        return

    # Check column buttons
    for btn_rect, n in self._col_btn_rects:
      if rl.check_collision_point_rec(pos, btn_rect):
        self._settings.set("chart_columns", n)
        return

    # Check clear button
    if rl.check_collision_point_rec(pos, self._clear_rect):
      self.clear()

  def _render(self, rect: rl.Rectangle):
    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height), styles.BG)

    font = gui_app.font(FontWeight.NORMAL)

    if not self._entries:
      rl.draw_text_ex(font, "Click a signal to chart",
                      rl.Vector2(rect.x + styles.PAD, rect.y + styles.PAD),
                      styles.SMALL_FONT, 0, styles.TEXT_MUTED)
      return

    self._render_toolbar(rect, font)

    body_rect = rl.Rectangle(rect.x, rect.y + TOOLBAR_H, rect.width, rect.height - TOOLBAR_H)

    chart_h = max(CHART_MIN_H, self._settings.chart_height)
    cols = max(1, min(4, self._settings.chart_columns))
    rows = (len(self._entries) + cols - 1) // cols
    content_h = rows * (chart_h + CHART_HEADER_H)

    scroll_offset = self._scroll.update(body_rect, content_h)

    rl.begin_scissor_mode(int(body_rect.x), int(body_rect.y),
                          int(body_rect.width), int(body_rect.height))

    col_w = body_rect.width / cols
    self._chart_rects.clear()
    self._close_rects.clear()

    for idx, entry in enumerate(self._entries):
      col = idx % cols
      row = idx // cols
      cx = body_rect.x + col * col_w
      cy = body_rect.y + scroll_offset + row * (chart_h + CHART_HEADER_H)

      if cy + chart_h + CHART_HEADER_H < body_rect.y or cy > body_rect.y + body_rect.height:
        self._chart_rects.append(rl.Rectangle(0, 0, 0, 0))
        self._close_rects.append(rl.Rectangle(0, 0, 0, 0))
        continue

      # Chart header
      rl.draw_rectangle(int(cx), int(cy), int(col_w), CHART_HEADER_H, styles.HEADER_BG)
      rl.draw_text_ex(font, entry.label,
                      rl.Vector2(cx + styles.PAD, cy + (CHART_HEADER_H - styles.SMALL_FONT) / 2),
                      styles.SMALL_FONT, 0, styles.TEXT)

      # Close button
      close_x = cx + col_w - 24
      close_rect = rl.Rectangle(close_x, cy + 2, 20, CHART_HEADER_H - 4)
      self._close_rects.append(close_rect)
      close_hovered = rl.check_collision_point_rec(gui_app.last_mouse_event.pos, close_rect)
      rl.draw_text_ex(font, "x",
                      rl.Vector2(close_x + 4, cy + (CHART_HEADER_H - styles.SMALL_FONT) / 2),
                      styles.SMALL_FONT, 0,
                      styles.ACCENT if close_hovered else styles.TEXT_DIM)

      # Chart body
      chart_rect = rl.Rectangle(cx, cy + CHART_HEADER_H, col_w, chart_h)
      self._chart_rects.append(chart_rect)
      entry.update()
      entry.chart.render(chart_rect)

    rl.end_scissor_mode()

  def _render_toolbar(self, rect: rl.Rectangle, font):
    ty = rect.y
    rl.draw_rectangle(int(rect.x), int(ty), int(rect.width), TOOLBAR_H, styles.PANEL_BG)
    rl.draw_line(int(rect.x), int(ty + TOOLBAR_H), int(rect.x + rect.width),
                 int(ty + TOOLBAR_H), styles.BORDER)

    rl.draw_text_ex(font, f"Charts ({len(self._entries)})",
                    rl.Vector2(rect.x + styles.PAD, ty + (TOOLBAR_H - styles.SMALL_FONT) / 2),
                    styles.SMALL_FONT, 0, styles.TEXT)

    # Column buttons
    self._col_btn_rects.clear()
    bx = rect.x + 140
    for n in range(1, 5):
      btn_rect = rl.Rectangle(bx, ty + 4, 22, TOOLBAR_H - 8)
      self._col_btn_rects.append((btn_rect, n))
      selected = self._settings.chart_columns == n
      hovered = rl.check_collision_point_rec(gui_app.last_mouse_event.pos, btn_rect)
      bg = styles.SELECTED_BG if selected else (styles.HOVER_BG if hovered else styles.PANEL_BG)
      rl.draw_rectangle(int(bx), int(ty + 4), 22, TOOLBAR_H - 8, bg)
      rl.draw_text_ex(font, str(n), rl.Vector2(bx + 6, ty + (TOOLBAR_H - styles.SMALL_FONT) / 2),
                      styles.SMALL_FONT, 0, styles.TEXT if selected else styles.TEXT_DIM)
      bx += 26

    # Clear button
    clear_x = rect.x + rect.width - 60
    self._clear_rect = rl.Rectangle(clear_x, ty + 4, 50, TOOLBAR_H - 8)
    clear_hovered = rl.check_collision_point_rec(gui_app.last_mouse_event.pos, self._clear_rect)
    rl.draw_text_ex(font, "Clear",
                    rl.Vector2(clear_x + 4, ty + (TOOLBAR_H - styles.SMALL_FONT) / 2),
                    styles.SMALL_FONT, 0,
                    styles.ACCENT if clear_hovered else styles.TEXT_DIM)
