"""Mouse-wheel-only scroll panel for desktop cabana. Replaces touch-based GuiScrollPanel2."""
from __future__ import annotations

import pyray as rl
from openpilot.system.ui.lib.application import gui_app


class DesktopScrollPanel:
  """Scroll via mouse wheel only. No touch drag-to-scroll behavior."""

  SCROLL_SPEED = 50.0   # pixels per wheel notch
  LERP_SPEED = 15.0     # exponential smoothing factor

  def __init__(self):
    self._offset: float = 0.0
    self._target: float = 0.0

  def update(self, bounds: rl.Rectangle, content_size: float) -> float:
    bounds_h = bounds.height
    max_scroll = min(0.0, bounds_h - content_size)

    # Only respond to wheel when mouse is over bounds and shift is NOT held
    # (shift+wheel is used for horizontal scroll by the table)
    mouse_pos = gui_app.last_mouse_event.pos
    shift_held = rl.is_key_down(rl.KeyboardKey.KEY_LEFT_SHIFT) or rl.is_key_down(rl.KeyboardKey.KEY_RIGHT_SHIFT)
    if not shift_held and rl.check_collision_point_rec(mouse_pos, bounds):
      wheel = rl.get_mouse_wheel_move()
      if wheel != 0:
        self._target += wheel * self.SCROLL_SPEED
        self._target = max(max_scroll, min(0.0, self._target))

    # Clamp target if content size changed
    self._target = max(max_scroll, min(0.0, self._target))

    # Smooth lerp toward target
    dt = rl.get_frame_time() or (1.0 / 60.0)
    alpha = min(1.0, dt * self.LERP_SPEED)
    self._offset += (self._target - self._offset) * alpha

    # Snap when close
    if abs(self._target - self._offset) < 0.5:
      self._offset = self._target

    return self._offset

  def is_touch_valid(self) -> bool:
    return True

  def get_offset(self) -> float:
    return self._offset

  def set_offset(self, value: float) -> None:
    self._offset = value
    self._target = value
