"""Settings dialog for cabana preferences."""
from __future__ import annotations

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.tools.cabana.settings import Settings
from openpilot.tools.cabana import styles

DIALOG_W = 400
DIALOG_H = 350
ROW_H = 36
LABEL_W = 180


class SettingsDialog(Widget):
  """Modal settings form."""

  def __init__(self, on_close: callable = None):
    super().__init__()
    self._settings = Settings()
    self._on_close = on_close

  def _render(self, rect: rl.Rectangle):
    # Dim background
    rl.draw_rectangle(0, 0, int(rect.width), int(rect.height), rl.Color(0, 0, 0, 150))

    font = gui_app.font(FontWeight.NORMAL)

    # Dialog box centered
    dx = (rect.width - DIALOG_W) / 2
    dy = (rect.height - DIALOG_H) / 2
    dialog = rl.Rectangle(dx, dy, DIALOG_W, DIALOG_H)

    rl.draw_rectangle(int(dx), int(dy), DIALOG_W, DIALOG_H, styles.PANEL_BG)
    rl.draw_rectangle_lines(int(dx), int(dy), DIALOG_W, DIALOG_H, styles.BORDER)

    # Title
    rl.draw_text_ex(font, "Settings",
                    rl.Vector2(dx + styles.PAD, dy + 8),
                    styles.FONT_SIZE, 0, styles.TEXT)

    # Settings rows
    y = dy + 40

    # Drag direction
    y = self._render_option_row(font, dx, y, "Drag Direction",
                                 ["msb_first", "lsb_first", "always_le", "always_be"],
                                 "drag_direction")

    # Chart series type
    y = self._render_option_row(font, dx, y, "Chart Type",
                                 ["line", "step", "scatter"],
                                 "chart_series_type")

    # Chart columns
    y = self._render_option_row(font, dx, y, "Chart Columns",
                                 ["1", "2", "3", "4"],
                                 "chart_columns", is_int=True)

    # Chart height
    y = self._render_option_row(font, dx, y, "Chart Height",
                                 ["120", "160", "200", "250"],
                                 "chart_height", is_int=True)

    # FPS
    y = self._render_option_row(font, dx, y, "Target FPS",
                                 ["30", "60"],
                                 "fps", is_int=True)

    # Close button
    close_y = dy + DIALOG_H - 40
    close_rect = rl.Rectangle(dx + DIALOG_W - 80, close_y, 60, 28)
    hovered = rl.check_collision_point_rec(gui_app.last_mouse_event.pos, close_rect)
    bg = styles.SELECTED_BG if hovered else styles.HOVER_BG
    rl.draw_rectangle_rounded(close_rect, 0.3, 4, bg)
    rl.draw_text_ex(font, "Close",
                    rl.Vector2(close_rect.x + 8, close_y + 4),
                    styles.SMALL_FONT, 0, styles.TEXT)

    for ev in gui_app.mouse_events:
      if ev.left_released and rl.check_collision_point_rec(ev.pos, close_rect):
        if self._on_close:
          self._on_close()

    # Escape to close
    if rl.is_key_pressed(rl.KeyboardKey.KEY_ESCAPE):
      if self._on_close:
        self._on_close()

  def _render_option_row(self, font, dx: float, y: float, label: str,
                          options: list[str], key: str, is_int: bool = False) -> float:
    current = str(self._settings.get(key))

    rl.draw_text_ex(font, label,
                    rl.Vector2(dx + styles.PAD, y + (ROW_H - styles.SMALL_FONT) / 2),
                    styles.SMALL_FONT, 0, styles.TEXT)

    bx = dx + LABEL_W
    for opt in options:
      tw = rl.measure_text_ex(font, opt, styles.SMALL_FONT * 1.242, 0).x
      btn_w = max(tw + 12, 40)
      btn_rect = rl.Rectangle(bx, y + 4, btn_w, ROW_H - 8)

      selected = current == opt
      hovered = rl.check_collision_point_rec(gui_app.last_mouse_event.pos, btn_rect)
      bg = styles.SELECTED_BG if selected else (styles.HOVER_BG if hovered else styles.BG)
      rl.draw_rectangle_rounded(btn_rect, 0.3, 4, bg)
      rl.draw_text_ex(font, opt,
                      rl.Vector2(bx + 6, y + (ROW_H - styles.SMALL_FONT) / 2),
                      styles.SMALL_FONT, 0, styles.TEXT if selected else styles.TEXT_DIM)

      for ev in gui_app.mouse_events:
        if ev.left_released and rl.check_collision_point_rec(ev.pos, btn_rect):
          val = int(opt) if is_int else opt
          self._settings.set(key, val)

      bx += btn_w + 4

    return y + ROW_H
