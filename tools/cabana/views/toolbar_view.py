from __future__ import annotations

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.tools.cabana import styles

BTN_W = 36
BTN_H = 28
TOOLBAR_H = 36


class ToolbarView(Widget):
  """Status bar with play/pause, time, speed, loading status. No seek bar (that's on the video timeline)."""

  def __init__(self, stream):
    super().__init__()
    self._stream = stream
    self._status_text: str = ""

  def set_status(self, text: str) -> None:
    self._status_text = text

  def _render(self, rect: rl.Rectangle):
    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height), styles.PANEL_BG)
    rl.draw_line(int(rect.x), int(rect.y), int(rect.x + rect.width), int(rect.y), styles.BORDER)

    font = gui_app.font(FontWeight.NORMAL)
    stream = self._stream
    cy = rect.y + (rect.height - BTN_H) / 2

    # Play/Pause button
    play_text = "\u25B6" if not stream.playing else "\u23F8"
    bx = rect.x + styles.PAD
    btn_rect = rl.Rectangle(bx, cy, BTN_W, BTN_H)
    hovered = rl.check_collision_point_rec(gui_app.last_mouse_event.pos, btn_rect)
    btn_color = styles.HOVER_BG if hovered else rl.Color(40, 42, 50, 255)
    rl.draw_rectangle_rounded(btn_rect, 0.3, 4, btn_color)
    rl.draw_text_ex(font, play_text, rl.Vector2(bx + 8, cy + 3), styles.FONT_SIZE, 0, rl.WHITE)

    for ev in gui_app.mouse_events:
      if ev.left_released and rl.check_collision_point_rec(ev.pos, btn_rect):
        stream.playing = not stream.playing

    # Time display
    cur = stream.current_sec
    dur = stream.duration
    time_str = f"{_fmt_time(cur)} / {_fmt_time(dur)}"
    rl.draw_text_ex(font, time_str, rl.Vector2(bx + BTN_W + 12, cy + 3),
                    styles.FONT_SIZE, 0, styles.TEXT)

    # Loading text or status
    info_x = bx + BTN_W + 200
    if stream.loading:
      load_text = stream.load_progress or "Loading..."
      rl.draw_text_ex(font, load_text, rl.Vector2(info_x, cy + 5),
                      styles.SMALL_FONT, 0, styles.ACCENT)
    elif self._status_text:
      rl.draw_text_ex(font, self._status_text, rl.Vector2(info_x, cy + 5),
                      styles.SMALL_FONT, 0, styles.TEXT_DIM)

    # Speed display (right side)
    speed_str = f"{stream.speed:.1f}x"
    speed_x = rect.x + rect.width - styles.PAD - 60
    rl.draw_text_ex(font, speed_str, rl.Vector2(speed_x, cy + 3),
                    styles.FONT_SIZE, 0, styles.TEXT_DIM)

    # Keyboard shortcuts
    if rl.is_key_pressed(rl.KeyboardKey.KEY_SPACE):
      stream.playing = not stream.playing
    if rl.is_key_pressed(rl.KeyboardKey.KEY_LEFT):
      stream.current_sec = max(0, stream.current_sec - 1)
    if rl.is_key_pressed(rl.KeyboardKey.KEY_RIGHT):
      stream.current_sec = min(stream.duration, stream.current_sec + 1)
    if rl.is_key_pressed(rl.KeyboardKey.KEY_UP):
      stream.speed = min(8.0, stream.speed * 2)
    if rl.is_key_pressed(rl.KeyboardKey.KEY_DOWN):
      stream.speed = max(0.125, stream.speed / 2)
    if rl.is_key_pressed(rl.KeyboardKey.KEY_HOME):
      stream.current_sec = 0
    if rl.is_key_pressed(rl.KeyboardKey.KEY_END):
      stream.current_sec = stream.duration


def _fmt_time(secs: float) -> str:
  m = int(secs) // 60
  s = secs - m * 60
  return f"{m}:{s:05.2f}"
