from __future__ import annotations

import copy
import pyray as rl
from collections.abc import Callable

from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.lib.application import gui_app, FontWeight, FONT_SCALE
from openpilot.tools.cabana.can_stream import CanStream, MessageId, MessageData
from openpilot.tools.cabana.dbc_manager import DBCManager
from openpilot.tools.cabana.commands import UndoStack, EditSignalCommand
from openpilot.tools.cabana.desktop_scroll import DesktopScrollPanel
from openpilot.tools.cabana import styles
from opendbc.can.dbc import Signal

ROW_H = 32
EXPANDED_FIELD_H = 24
HEADER_H = 32


class SignalView(Widget):
  """Signal list with decoded values and expandable property editing."""

  def __init__(self, stream: CanStream, dbc: DBCManager, undo_stack: UndoStack,
               on_select_signal: Callable[[Signal], None] | None = None):
    super().__init__()
    self._stream = stream
    self._dbc = dbc
    self._undo_stack = undo_stack
    self._on_select_signal = on_select_signal
    self._selected_mid: MessageId | None = None
    self._current_data: MessageData | None = None
    self._selected_signal: Signal | None = None
    self._expanded_signal: str | None = None  # name of expanded signal
    self._scroll = DesktopScrollPanel()

  def set_message(self, mid: MessageId | None, data: MessageData | None) -> None:
    self._selected_mid = mid
    self._current_data = data

  def _get_row_height(self, sig: Signal) -> int:
    if self._expanded_signal == sig.name:
      return ROW_H + EXPANDED_FIELD_H * 5  # 5 property rows
    return ROW_H

  def _render(self, rect: rl.Rectangle):
    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height), styles.BG)

    font = gui_app.font(FontWeight.NORMAL)

    if self._selected_mid is None or self._current_data is None:
      rl.draw_text_ex(font, "No message selected",
                      rl.Vector2(rect.x + styles.PAD, rect.y + rect.height / 2 - 12),
                      styles.FONT_SIZE, 0, styles.TEXT_MUTED)
      return

    data = self._current_data
    signals = self._dbc.signals(self._selected_mid[1])

    if not signals:
      rl.draw_text_ex(font, "No signals defined",
                      rl.Vector2(rect.x + styles.PAD, rect.y + rect.height / 2 - 12),
                      styles.FONT_SIZE, 0, styles.TEXT_MUTED)
      return

    # Header
    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), HEADER_H, styles.HEADER_BG)
    rl.draw_text_ex(font, f"Signals ({len(signals)})",
                    rl.Vector2(rect.x + styles.PAD, rect.y + 5),
                    styles.FONT_SIZE, 0, styles.TEXT)

    val_x = rect.x + rect.width - 100
    rl.draw_text_ex(font, "Value",
                    rl.Vector2(val_x, rect.y + 6),
                    styles.SMALL_FONT, 0, styles.TEXT_DIM)

    body_rect = rl.Rectangle(rect.x, rect.y + HEADER_H, rect.width, rect.height - HEADER_H)
    content_h = sum(self._get_row_height(sig) for sig in signals)

    scroll_offset = self._scroll.update(body_rect, content_h)

    rl.begin_scissor_mode(int(body_rect.x), int(body_rect.y),
                          int(body_rect.width), int(body_rect.height))

    # Hover detection
    mouse_pos = gui_app.last_mouse_event.pos
    hovered_sig_name = None
    if rl.check_collision_point_rec(mouse_pos, body_rect):
      y_check = mouse_pos.y - body_rect.y - scroll_offset
      y_acc = 0.0
      for sig in signals:
        rh = self._get_row_height(sig)
        if y_acc <= y_check < y_acc + rh:
          hovered_sig_name = sig.name
          break
        y_acc += rh

    sy = body_rect.y + scroll_offset
    for i, sig in enumerate(signals):
      rh = self._get_row_height(sig)
      color_idx = i % len(styles.SIGNAL_COLORS)
      sig_color = styles.SIGNAL_COLORS[color_idx]

      # Skip if not visible
      if sy + rh < body_rect.y or sy > body_rect.y + body_rect.height:
        sy += rh
        continue

      # Row background
      is_selected = sig is self._selected_signal
      is_expanded = self._expanded_signal == sig.name
      if is_selected:
        bg = styles.SELECTED_BG
      elif sig.name == hovered_sig_name:
        bg = styles.HOVER_BG
      elif i % 2:
        bg = styles.ROW_ALT_BG
      else:
        bg = styles.ROW_BG
      rl.draw_rectangle(int(rect.x), int(sy), int(rect.width), ROW_H, bg)

      # Color indicator bar
      rl.draw_rectangle(int(rect.x), int(sy), 4, ROW_H, sig_color)

      # Expand arrow
      arrow = "\u25BC" if is_expanded else "\u25B6"
      rl.draw_text_ex(font, arrow, rl.Vector2(rect.x + 8, sy + (ROW_H - styles.SMALL_FONT) / 2),
                      styles.SMALL_FONT, 0, styles.TEXT_DIM)

      # Signal name
      name_x = rect.x + styles.PAD + 16
      rl.draw_text_ex(font, sig.name, rl.Vector2(name_x, sy + (ROW_H - styles.FONT_SIZE) / 2),
                      styles.FONT_SIZE, 0, rl.WHITE)

      # Signal info
      info = f"[{sig.start_bit}|{sig.size}]"
      info_tw = rl.measure_text_ex(font, info, styles.SMALL_FONT * FONT_SCALE, 0).x
      rl.draw_text_ex(font, info, rl.Vector2(val_x - info_tw - 12, sy + (ROW_H - styles.SMALL_FONT) / 2),
                      styles.SMALL_FONT, 0, styles.TEXT_MUTED)

      # Decoded value
      try:
        val = self._dbc.decode_signal(data.dat, sig)
        val_str = f"{val:.0f}" if val == int(val) else f"{val:.3f}"
      except Exception:
        val_str = "?"

      rl.draw_text_ex(font, val_str, rl.Vector2(val_x, sy + (ROW_H - styles.FONT_SIZE) / 2),
                      styles.FONT_SIZE, 0, rl.Color(220, 200, 80, 255))

      # Expanded properties
      if is_expanded:
        prop_y = sy + ROW_H
        self._draw_property_row(font, rect, prop_y, "Size", str(sig.size), sig_color)
        prop_y += EXPANDED_FIELD_H
        self._draw_property_row(font, rect, prop_y, "Endian", "LE" if sig.is_little_endian else "BE", sig_color)
        prop_y += EXPANDED_FIELD_H
        self._draw_property_row(font, rect, prop_y, "Signed", "Yes" if sig.is_signed else "No", sig_color)
        prop_y += EXPANDED_FIELD_H
        self._draw_property_row(font, rect, prop_y, "Factor", f"{sig.factor}", sig_color)
        prop_y += EXPANDED_FIELD_H
        self._draw_property_row(font, rect, prop_y, "Offset", f"{sig.offset}", sig_color)
        prop_y += EXPANDED_FIELD_H
        self._draw_property_row(font, rect, prop_y, "MSB", str(sig.msb), sig_color)
        prop_y += EXPANDED_FIELD_H
        self._draw_property_row(font, rect, prop_y, "LSB", str(sig.lsb), sig_color)

      sy += rh

    rl.end_scissor_mode()

    # Handle clicks
    for ev in gui_app.mouse_events:
      if ev.left_released and rl.check_collision_point_rec(ev.pos, body_rect):
        y_check = ev.pos.y - body_rect.y - scroll_offset
        y_acc = 0.0
        for sig in signals:
          rh = self._get_row_height(sig)
          if y_acc <= y_check < y_acc + ROW_H:  # clicked on main row (not expanded area)
            # Check if clicked on arrow area (first 24px)
            if ev.pos.x < rect.x + 24:
              self._expanded_signal = sig.name if self._expanded_signal != sig.name else None
            else:
              self._selected_signal = sig
              if self._on_select_signal:
                self._on_select_signal(sig)
            break
          y_acc += rh

  def _draw_property_row(self, font, rect: rl.Rectangle, y: float, label: str, value: str,
                         color: rl.Color):
    rl.draw_rectangle(int(rect.x), int(y), int(rect.width), EXPANDED_FIELD_H,
                      rl.Color(styles.BG.r, styles.BG.g, styles.BG.b, 200))
    rl.draw_rectangle(int(rect.x), int(y), 2, EXPANDED_FIELD_H, color)
    rl.draw_text_ex(font, label,
                    rl.Vector2(rect.x + 24, y + (EXPANDED_FIELD_H - styles.SMALL_FONT) / 2),
                    styles.SMALL_FONT, 0, styles.TEXT_DIM)
    rl.draw_text_ex(font, value,
                    rl.Vector2(rect.x + 100, y + (EXPANDED_FIELD_H - styles.SMALL_FONT) / 2),
                    styles.SMALL_FONT, 0, styles.TEXT)
