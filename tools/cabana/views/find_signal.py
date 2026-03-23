"""Find a signal value across all messages."""
from __future__ import annotations

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.lib.application import gui_app, FontWeight, FONT_SCALE
from openpilot.tools.cabana.can_stream import CanStream
from openpilot.tools.cabana.dbc_manager import DBCManager
from openpilot.tools.cabana.desktop_scroll import DesktopScrollPanel
from openpilot.tools.cabana import styles

DIALOG_W = 500
DIALOG_H = 450
ROW_H = 24


class FindSignal(Widget):
  """Search for a numeric value across all decoded signals."""

  def __init__(self, stream: CanStream, dbc: DBCManager, on_close: callable = None):
    super().__init__()
    self._stream = stream
    self._dbc = dbc
    self._on_close = on_close
    self._search_value: str = ""
    self._results: list[tuple[str, str, float]] = []  # (msg_name, sig_name, value)
    self._scroll = DesktopScrollPanel()
    self._input_active = True

  def _search(self):
    """Search all current signal values for matching number."""
    try:
      target = float(self._search_value)
    except ValueError:
      self._results = []
      return

    current_msgs = self._stream.current_messages()
    results = []
    for mid, data in current_msgs.items():
      signals = self._dbc.signals(mid[1])
      for sig in signals:
        try:
          val = self._dbc.decode_signal(data.dat, sig)
          # Match if within 1% or exact
          if target == 0:
            if val == 0:
              results.append((data.name, sig.name, val))
          elif abs(val - target) / abs(target) < 0.01:
            results.append((data.name, sig.name, val))
        except Exception:
          pass

    self._results = results

  def _render(self, rect: rl.Rectangle):
    rl.draw_rectangle(0, 0, int(rect.width), int(rect.height), rl.Color(0, 0, 0, 150))

    font = gui_app.font(FontWeight.NORMAL)
    dx = (rect.width - DIALOG_W) / 2
    dy = (rect.height - DIALOG_H) / 2

    rl.draw_rectangle(int(dx), int(dy), DIALOG_W, DIALOG_H, styles.PANEL_BG)
    rl.draw_rectangle_lines(int(dx), int(dy), DIALOG_W, DIALOG_H, styles.BORDER)

    rl.draw_text_ex(font, "Find Signal by Value",
                    rl.Vector2(dx + styles.PAD, dy + 8),
                    styles.FONT_SIZE, 0, styles.TEXT)

    # Search input
    input_rect = rl.Rectangle(dx + styles.PAD, dy + 36, DIALOG_W - styles.PAD * 2 - 70, 26)
    rl.draw_rectangle(int(input_rect.x), int(input_rect.y),
                      int(input_rect.width), int(input_rect.height), styles.BG)
    rl.draw_rectangle_lines(int(input_rect.x), int(input_rect.y),
                            int(input_rect.width), int(input_rect.height), styles.BORDER)

    display_text = self._search_value or "Enter value..."
    text_color = styles.TEXT if self._search_value else styles.TEXT_MUTED
    rl.draw_text_ex(font, display_text,
                    rl.Vector2(input_rect.x + 4, input_rect.y + 3),
                    styles.SMALL_FONT, 0, text_color)

    # Handle keyboard input
    if self._input_active:
      char = rl.get_char_pressed()
      while char > 0:
        c = chr(char)
        if c in '0123456789.-+':
          self._search_value += c
          self._search()
        char = rl.get_char_pressed()
      if rl.is_key_pressed(rl.KeyboardKey.KEY_BACKSPACE) and self._search_value:
        self._search_value = self._search_value[:-1]
        self._search()
      if rl.is_key_pressed(rl.KeyboardKey.KEY_ENTER):
        self._search()

    # Search button
    btn_x = dx + DIALOG_W - styles.PAD - 60
    btn_rect = rl.Rectangle(btn_x, dy + 36, 50, 26)
    hovered = rl.check_collision_point_rec(gui_app.last_mouse_event.pos, btn_rect)
    rl.draw_rectangle_rounded(btn_rect, 0.3, 4, styles.SELECTED_BG if hovered else styles.HOVER_BG)
    rl.draw_text_ex(font, "Find", rl.Vector2(btn_x + 8, dy + 40),
                    styles.SMALL_FONT, 0, styles.TEXT)
    for ev in gui_app.mouse_events:
      if ev.left_released and rl.check_collision_point_rec(ev.pos, btn_rect):
        self._search()

    # Results
    body_rect = rl.Rectangle(dx, dy + 70, DIALOG_W, DIALOG_H - 110)
    content_h = len(self._results) * ROW_H
    scroll_offset = self._scroll.update(body_rect, content_h)

    rl.begin_scissor_mode(int(body_rect.x), int(body_rect.y),
                          int(body_rect.width), int(body_rect.height))

    for i, (msg_name, sig_name, val) in enumerate(self._results):
      ry = body_rect.y + scroll_offset + i * ROW_H
      if ry + ROW_H < body_rect.y or ry > body_rect.y + body_rect.height:
        continue

      bg = styles.ROW_ALT_BG if i % 2 else styles.ROW_BG
      rl.draw_rectangle(int(dx), int(ry), DIALOG_W, ROW_H, bg)

      text = f"{msg_name}.{sig_name} = {val:.4g}"
      rl.draw_text_ex(font, text,
                      rl.Vector2(dx + styles.PAD, ry + (ROW_H - styles.SMALL_FONT) / 2),
                      styles.SMALL_FONT, 0, styles.TEXT)

    rl.end_scissor_mode()

    # Close
    close_rect = rl.Rectangle(dx + DIALOG_W - 80, dy + DIALOG_H - 36, 60, 28)
    hovered = rl.check_collision_point_rec(gui_app.last_mouse_event.pos, close_rect)
    rl.draw_rectangle_rounded(close_rect, 0.3, 4, styles.SELECTED_BG if hovered else styles.HOVER_BG)
    rl.draw_text_ex(font, "Close", rl.Vector2(close_rect.x + 8, close_rect.y + 4),
                    styles.SMALL_FONT, 0, styles.TEXT)

    for ev in gui_app.mouse_events:
      if ev.left_released and rl.check_collision_point_rec(ev.pos, close_rect):
        if self._on_close:
          self._on_close()

    if rl.is_key_pressed(rl.KeyboardKey.KEY_ESCAPE):
      if self._on_close:
        self._on_close()
