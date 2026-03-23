"""Historical message log showing past CAN events for the selected message."""
from __future__ import annotations

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.lib.application import gui_app, FontWeight, FONT_SCALE
from openpilot.tools.cabana.can_stream import CanStream, MessageId
from openpilot.tools.cabana.dbc_manager import DBCManager
from openpilot.tools.cabana.desktop_scroll import DesktopScrollPanel
from openpilot.tools.cabana import styles

ROW_H = 22
HEADER_H = 30
TOOLBAR_H = 28
MAX_VISIBLE = 500  # max rows to render


class HistoryLogView(Widget):
  """Table showing historical CAN events: time + hex bytes or decoded signal values."""

  def __init__(self, stream: CanStream, dbc: DBCManager):
    super().__init__()
    self._stream = stream
    self._dbc = dbc
    self._selected_mid: MessageId | None = None
    self._hex_mode = True  # True = hex bytes, False = decoded signals
    self._scroll = DesktopScrollPanel()

  def set_message(self, mid: MessageId | None) -> None:
    self._selected_mid = mid

  def _render(self, rect: rl.Rectangle):
    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height), styles.BG)
    font = gui_app.font(FontWeight.NORMAL)

    if self._selected_mid is None:
      rl.draw_text_ex(font, "No message selected",
                      rl.Vector2(rect.x + styles.PAD, rect.y + rect.height / 2 - 10),
                      styles.SMALL_FONT, 0, styles.TEXT_MUTED)
      return

    mid = self._selected_mid
    events = self._stream.get_events(mid)
    if not events:
      rl.draw_text_ex(font, "No events",
                      rl.Vector2(rect.x + styles.PAD, rect.y + rect.height / 2 - 10),
                      styles.SMALL_FONT, 0, styles.TEXT_MUTED)
      return

    t0 = self._stream.time_range[0]
    signals = self._dbc.signals(mid[1])

    # Toolbar
    self._render_toolbar(rect, font, len(events))
    body_y = rect.y + TOOLBAR_H

    # Header
    rl.draw_rectangle(int(rect.x), int(body_y), int(rect.width), HEADER_H, styles.HEADER_BG)
    rl.draw_text_ex(font, "Time",
                    rl.Vector2(rect.x + styles.PAD, body_y + (HEADER_H - styles.SMALL_FONT) / 2),
                    styles.SMALL_FONT, 0, styles.TEXT_DIM)

    if self._hex_mode:
      rl.draw_text_ex(font, "Data (hex)",
                      rl.Vector2(rect.x + 100, body_y + (HEADER_H - styles.SMALL_FONT) / 2),
                      styles.SMALL_FONT, 0, styles.TEXT_DIM)
    else:
      col_x = 100.0
      for sig in signals:
        rl.draw_text_ex(font, sig.name,
                        rl.Vector2(rect.x + col_x, body_y + (HEADER_H - styles.SMALL_FONT) / 2),
                        styles.SMALL_FONT, 0, styles.TEXT_DIM)
        col_x += 80

    body_rect = rl.Rectangle(rect.x, body_y + HEADER_H, rect.width,
                              rect.height - TOOLBAR_H - HEADER_H)

    # Limit to MAX_VISIBLE most recent events up to current time
    abs_time_ns = int((t0 + self._stream.current_sec) * 1e9)
    # Find end index
    end_idx = len(events)
    for i in range(len(events) - 1, -1, -1):
      if events[i].mono_time <= abs_time_ns:
        end_idx = i + 1
        break

    start_idx = max(0, end_idx - MAX_VISIBLE)
    visible_events = events[start_idx:end_idx]
    content_h = len(visible_events) * ROW_H

    scroll_offset = self._scroll.update(body_rect, content_h)

    rl.begin_scissor_mode(int(body_rect.x), int(body_rect.y),
                          int(body_rect.width), int(body_rect.height))

    first_row = max(0, int(-scroll_offset / ROW_H))
    last_row = min(len(visible_events), int((-scroll_offset + body_rect.height) / ROW_H) + 1)

    for ri in range(first_row, last_row):
      ev = visible_events[ri]
      ry = body_rect.y + scroll_offset + ri * ROW_H

      # Alternating background
      bg = styles.ROW_ALT_BG if ri % 2 else styles.ROW_BG
      rl.draw_rectangle(int(rect.x), int(ry), int(rect.width), ROW_H, bg)

      # Time
      t = ev.mono_time / 1e9 - t0
      time_str = f"{t:.3f}s"
      rl.draw_text_ex(font, time_str,
                      rl.Vector2(rect.x + styles.PAD, ry + (ROW_H - styles.SMALL_FONT) / 2),
                      styles.SMALL_FONT, 0, styles.TEXT)

      if self._hex_mode:
        hex_str = ev.dat.hex(' ')
        rl.draw_text_ex(font, hex_str,
                        rl.Vector2(rect.x + 100, ry + (ROW_H - styles.SMALL_FONT) / 2),
                        styles.SMALL_FONT, 0, styles.TEXT)
      else:
        col_x = 100.0
        for sig in signals:
          try:
            val = self._dbc.decode_signal(ev.dat, sig)
            val_str = f"{val:.1f}" if val != int(val) else f"{val:.0f}"
          except Exception:
            val_str = "?"
          rl.draw_text_ex(font, val_str,
                          rl.Vector2(rect.x + col_x, ry + (ROW_H - styles.SMALL_FONT) / 2),
                          styles.SMALL_FONT, 0, rl.Color(220, 200, 80, 255))
          col_x += 80

    rl.end_scissor_mode()

  def _render_toolbar(self, rect: rl.Rectangle, font, total_events: int):
    ty = rect.y
    rl.draw_rectangle(int(rect.x), int(ty), int(rect.width), TOOLBAR_H, styles.PANEL_BG)
    rl.draw_line(int(rect.x), int(ty + TOOLBAR_H), int(rect.x + rect.width),
                 int(ty + TOOLBAR_H), styles.BORDER)

    rl.draw_text_ex(font, f"Log ({total_events} events)",
                    rl.Vector2(rect.x + styles.PAD, ty + (TOOLBAR_H - styles.SMALL_FONT) / 2),
                    styles.SMALL_FONT, 0, styles.TEXT)

    # Hex/Signal toggle
    toggle_x = rect.x + rect.width - 80
    toggle_rect = rl.Rectangle(toggle_x, ty + 4, 70, TOOLBAR_H - 8)
    toggle_text = "Hex" if self._hex_mode else "Signals"
    hovered = rl.check_collision_point_rec(gui_app.last_mouse_event.pos, toggle_rect)
    rl.draw_text_ex(font, toggle_text,
                    rl.Vector2(toggle_x + 4, ty + (TOOLBAR_H - styles.SMALL_FONT) / 2),
                    styles.SMALL_FONT, 0, styles.ACCENT if hovered else styles.TEXT_DIM)

    for ev in gui_app.mouse_events:
      if ev.left_released and rl.check_collision_point_rec(ev.pos, toggle_rect):
        self._hex_mode = not self._hex_mode
