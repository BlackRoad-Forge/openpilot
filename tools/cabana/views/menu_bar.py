"""Menu bar widget with dropdown menus and keyboard shortcuts."""
from __future__ import annotations

import pyray as rl
from dataclasses import dataclass, field
from collections.abc import Callable

from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.lib.application import gui_app, FontWeight, FONT_SCALE
from openpilot.tools.cabana import styles


@dataclass
class MenuItem:
  label: str = ""
  shortcut_text: str = ""
  callback: Callable[[], None] | None = None
  enabled: bool | Callable[[], bool] = True
  separator: bool = False
  children: list[MenuItem] = field(default_factory=list)

  @property
  def is_enabled(self) -> bool:
    return self.enabled() if callable(self.enabled) else self.enabled


def separator() -> MenuItem:
  return MenuItem(separator=True)


MENU_ITEM_H = 24
MENU_ITEM_PAD = 6
MENU_PAD = 4
DROPDOWN_MIN_W = 200


class MenuBar(Widget):
  """Horizontal menu bar with dropdown menus."""

  def __init__(self):
    super().__init__()
    self._menus: list[tuple[str, list[MenuItem]]] = []
    self._open_menu: int = -1  # index of open dropdown, -1 = none
    self._hovering_menu: int = -1

  def set_menus(self, menus: list[tuple[str, list[MenuItem]]]) -> None:
    self._menus = menus

  def _render(self, rect: rl.Rectangle):
    font = gui_app.font(FontWeight.NORMAL)
    bar_h = styles.MENU_BAR_H

    # Bar background
    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), bar_h, styles.PANEL_BG)
    rl.draw_line(int(rect.x), int(rect.y + bar_h), int(rect.x + rect.width),
                 int(rect.y + bar_h), styles.BORDER)

    mouse_pos = gui_app.last_mouse_event.pos
    menu_x = rect.x + MENU_PAD

    # Draw menu titles
    for i, (title, _items) in enumerate(self._menus):
      tw = rl.measure_text_ex(font, title, styles.SMALL_FONT * FONT_SCALE, 0).x
      title_w = tw + MENU_PAD * 4
      title_rect = rl.Rectangle(menu_x, rect.y, title_w, bar_h)

      hovered = rl.check_collision_point_rec(mouse_pos, title_rect)

      # If a menu is open and we hover another title, switch to it
      if hovered and self._open_menu >= 0 and self._open_menu != i:
        self._open_menu = i

      # Background
      if i == self._open_menu or hovered:
        rl.draw_rectangle(int(menu_x), int(rect.y), int(title_w), bar_h, styles.SELECTED_BG)

      rl.draw_text_ex(font, title,
                      rl.Vector2(menu_x + MENU_PAD * 2, rect.y + (bar_h - styles.SMALL_FONT) / 2),
                      styles.SMALL_FONT, 0, styles.TEXT)

      # Click to toggle dropdown
      for ev in gui_app.mouse_events:
        if ev.left_pressed and rl.check_collision_point_rec(ev.pos, title_rect):
          self._open_menu = i if self._open_menu != i else -1

      menu_x += title_w

    # Draw open dropdown
    if 0 <= self._open_menu < len(self._menus):
      self._render_dropdown(rect, font)

    # Close on click outside
    if self._open_menu >= 0:
      for ev in gui_app.mouse_events:
        if ev.left_pressed:
          # Check if click is on bar or dropdown — if not, close
          if not rl.check_collision_point_rec(ev.pos, rl.Rectangle(rect.x, rect.y, rect.width, bar_h)):
            if not self._is_in_dropdown(ev.pos, rect):
              self._open_menu = -1

    # Handle keyboard shortcuts
    self._handle_shortcuts()

  def _render_dropdown(self, bar_rect: rl.Rectangle, font):
    title, items = self._menus[self._open_menu]

    # Calculate dropdown position
    x = bar_rect.x + MENU_PAD
    for i in range(self._open_menu):
      tw = rl.measure_text_ex(font, self._menus[i][0], styles.SMALL_FONT * FONT_SCALE, 0).x
      x += tw + MENU_PAD * 4
    y = bar_rect.y + styles.MENU_BAR_H

    # Calculate dropdown dimensions
    max_label_w = 0
    max_shortcut_w = 0
    for item in items:
      if not item.separator:
        lw = rl.measure_text_ex(font, item.label, styles.SMALL_FONT * FONT_SCALE, 0).x
        max_label_w = max(max_label_w, lw)
        if item.shortcut_text:
          sw = rl.measure_text_ex(font, item.shortcut_text, styles.SMALL_FONT * FONT_SCALE, 0).x
          max_shortcut_w = max(max_shortcut_w, sw)

    dropdown_w = max(DROPDOWN_MIN_W, max_label_w + max_shortcut_w + MENU_PAD * 6)
    dropdown_h = sum(4 if item.separator else MENU_ITEM_H for item in items) + MENU_ITEM_PAD * 2

    # Store dropdown rect for hit testing
    self._dropdown_rect = rl.Rectangle(x, y, dropdown_w, dropdown_h)

    # Shadow
    rl.draw_rectangle(int(x + 2), int(y + 2), int(dropdown_w), int(dropdown_h),
                      rl.Color(0, 0, 0, 80))
    # Background
    rl.draw_rectangle(int(x), int(y), int(dropdown_w), int(dropdown_h), styles.PANEL_BG)
    rl.draw_rectangle_lines(int(x), int(y), int(dropdown_w), int(dropdown_h), styles.BORDER)

    mouse_pos = gui_app.last_mouse_event.pos
    iy = y + MENU_ITEM_PAD

    for item in items:
      if item.separator:
        rl.draw_line(int(x + MENU_PAD), int(iy + 2),
                     int(x + dropdown_w - MENU_PAD), int(iy + 2), styles.BORDER)
        iy += 4
        continue

      item_rect = rl.Rectangle(x + 1, iy, dropdown_w - 2, MENU_ITEM_H)
      hovered = rl.check_collision_point_rec(mouse_pos, item_rect) and item.is_enabled

      if hovered:
        rl.draw_rectangle(int(item_rect.x), int(item_rect.y),
                          int(item_rect.width), int(item_rect.height), styles.SELECTED_BG)

      text_color = styles.TEXT if item.is_enabled else styles.TEXT_MUTED
      rl.draw_text_ex(font, item.label,
                      rl.Vector2(x + MENU_PAD * 2, iy + (MENU_ITEM_H - styles.SMALL_FONT) / 2),
                      styles.SMALL_FONT, 0, text_color)

      if item.shortcut_text:
        sw = rl.measure_text_ex(font, item.shortcut_text, styles.SMALL_FONT * FONT_SCALE, 0).x
        rl.draw_text_ex(font, item.shortcut_text,
                        rl.Vector2(x + dropdown_w - sw - MENU_PAD * 2,
                                   iy + (MENU_ITEM_H - styles.SMALL_FONT) / 2),
                        styles.SMALL_FONT, 0, styles.TEXT_DIM)

      # Click handler
      if hovered:
        for ev in gui_app.mouse_events:
          if ev.left_released and rl.check_collision_point_rec(ev.pos, item_rect):
            if item.callback:
              item.callback()
            self._open_menu = -1

      iy += MENU_ITEM_H

  def _is_in_dropdown(self, pos, bar_rect: rl.Rectangle) -> bool:
    if not hasattr(self, '_dropdown_rect'):
      return False
    return rl.check_collision_point_rec(pos, self._dropdown_rect)

  def _handle_shortcuts(self):
    ctrl = rl.is_key_down(rl.KeyboardKey.KEY_LEFT_CONTROL) or rl.is_key_down(rl.KeyboardKey.KEY_RIGHT_CONTROL)
    shift = rl.is_key_down(rl.KeyboardKey.KEY_LEFT_SHIFT) or rl.is_key_down(rl.KeyboardKey.KEY_RIGHT_SHIFT)

    for _title, items in self._menus:
      for item in items:
        if item.separator or not item.shortcut_text or not item.is_enabled or not item.callback:
          continue
        if self._check_shortcut(item.shortcut_text, ctrl, shift):
          item.callback()

  @staticmethod
  def _check_shortcut(shortcut: str, ctrl_down: bool, shift_down: bool) -> bool:
    parts = shortcut.replace("Ctrl+", "").replace("Shift+", "")
    needs_ctrl = "Ctrl" in shortcut
    needs_shift = "Shift" in shortcut

    if needs_ctrl != ctrl_down or needs_shift != shift_down:
      return False

    key_name = parts.strip()
    key_map = {
      "N": rl.KeyboardKey.KEY_N, "O": rl.KeyboardKey.KEY_O, "S": rl.KeyboardKey.KEY_S,
      "Z": rl.KeyboardKey.KEY_Z, "Y": rl.KeyboardKey.KEY_Y, "Q": rl.KeyboardKey.KEY_Q,
      ",": rl.KeyboardKey.KEY_COMMA,
      "F1": rl.KeyboardKey.KEY_F1, "F11": rl.KeyboardKey.KEY_F11,
    }
    key = key_map.get(key_name)
    if key and rl.is_key_pressed(key):
      return True
    return False
