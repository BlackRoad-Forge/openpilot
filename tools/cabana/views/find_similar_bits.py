"""Find messages with similar bit-flip patterns."""
from __future__ import annotations

import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.tools.cabana.can_stream import CanStream
from openpilot.tools.cabana.dbc_manager import DBCManager
from openpilot.tools.cabana.desktop_scroll import DesktopScrollPanel
from openpilot.tools.cabana import styles

DIALOG_W = 500
DIALOG_H = 450
ROW_H = 24


class FindSimilarBits(Widget):
  """Compare bit-flip patterns across messages to find related signals."""

  def __init__(self, stream: CanStream, dbc: DBCManager, on_close: callable = None):
    super().__init__()
    self._stream = stream
    self._dbc = dbc
    self._on_close = on_close
    self._results: list[tuple[float, int, int]] = []  # (similarity, src, addr)
    self._computed = False
    self._scroll = DesktopScrollPanel()

  def _compute(self):
    """Compare bit-flip patterns between all message pairs."""
    mids = self._stream.message_ids
    if len(mids) < 2:
      self._computed = True
      return

    # Build normalized flip vectors
    vectors: dict[tuple[int, int], list[float]] = {}
    for mid in mids:
      flips = self._stream.get_bit_flip_counts(mid)
      if not flips:
        continue
      total = sum(flips) or 1
      vectors[mid] = [f / total for f in flips]

    # Compare all pairs
    results = []
    mid_list = list(vectors.keys())
    for i in range(len(mid_list)):
      for j in range(i + 1, len(mid_list)):
        a, b = vectors[mid_list[i]], vectors[mid_list[j]]
        # Cosine similarity on overlapping bits
        min_len = min(len(a), len(b))
        dot = sum(a[k] * b[k] for k in range(min_len))
        mag_a = sum(x * x for x in a[:min_len]) ** 0.5
        mag_b = sum(x * x for x in b[:min_len]) ** 0.5
        sim = dot / (mag_a * mag_b) if mag_a > 0 and mag_b > 0 else 0
        if sim > 0.5:
          results.append((sim, mid_list[i], mid_list[j]))

    results.sort(key=lambda r: -r[0])
    self._results = results[:100]
    self._computed = True

  def _render(self, rect: rl.Rectangle):
    rl.draw_rectangle(0, 0, int(rect.width), int(rect.height), rl.Color(0, 0, 0, 150))

    font = gui_app.font(FontWeight.NORMAL)
    dx = (rect.width - DIALOG_W) / 2
    dy = (rect.height - DIALOG_H) / 2

    rl.draw_rectangle(int(dx), int(dy), DIALOG_W, DIALOG_H, styles.PANEL_BG)
    rl.draw_rectangle_lines(int(dx), int(dy), DIALOG_W, DIALOG_H, styles.BORDER)

    rl.draw_text_ex(font, "Find Similar Bit Patterns",
                    rl.Vector2(dx + styles.PAD, dy + 8),
                    styles.FONT_SIZE, 0, styles.TEXT)

    if not self._computed:
      self._compute()

    body_rect = rl.Rectangle(dx, dy + 40, DIALOG_W, DIALOG_H - 80)
    content_h = len(self._results) * ROW_H

    scroll_offset = self._scroll.update(body_rect, content_h)

    rl.begin_scissor_mode(int(body_rect.x), int(body_rect.y),
                          int(body_rect.width), int(body_rect.height))

    for i, (sim, mid_a, mid_b) in enumerate(self._results):
      ry = body_rect.y + scroll_offset + i * ROW_H
      if ry + ROW_H < body_rect.y or ry > body_rect.y + body_rect.height:
        continue

      bg = styles.ROW_ALT_BG if i % 2 else styles.ROW_BG
      rl.draw_rectangle(int(dx), int(ry), DIALOG_W, ROW_H, bg)

      name_a = self._dbc.msg_name(mid_a[1]) or f"0x{mid_a[1]:03X}"
      name_b = self._dbc.msg_name(mid_b[1]) or f"0x{mid_b[1]:03X}"
      text = f"{sim:.0%}  {name_a} <-> {name_b}"
      rl.draw_text_ex(font, text,
                      rl.Vector2(dx + styles.PAD, ry + (ROW_H - styles.SMALL_FONT) / 2),
                      styles.SMALL_FONT, 0, styles.TEXT)

    rl.end_scissor_mode()

    # Close button
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
