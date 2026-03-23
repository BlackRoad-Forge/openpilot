from __future__ import annotations

import copy
import math
import pyray as rl
from collections.abc import Callable

from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.lib.application import gui_app, FontWeight, FONT_SCALE
from openpilot.tools.cabana.can_stream import CanStream, MessageId, MessageData
from openpilot.tools.cabana.dbc_manager import DBCManager
from openpilot.tools.cabana.commands import UndoStack, AddSignalCommand, RemoveSignalCommand, EditSignalCommand
from openpilot.tools.cabana import styles
from opendbc.can.dbc import Signal

TITLE_H = 36
HEADER_ROW_H = 28
CELL_H = 36

# Signal cell base color matching Qt cabana (greyish-blue, dark theme .lighter(135))
SIGNAL_BASE_COLOR = rl.Color(138, 116, 228, 255)
# Signal border color (drawn around signal groups)
SIGNAL_BORDER_ALPHA = 180


class BinaryView(Widget):
  """Binary/hex grid with bit-level heatmap and signal overlays.

  Layout matches Qt cabana: 8 bit columns + 1 hex column per row, one row per byte.
  Clicking a signal selects it. Dragging empty bits creates a new signal.
  Dragging a signal boundary resizes it.
  """

  def __init__(self, stream: CanStream, dbc: DBCManager, undo_stack: UndoStack,
               on_signal_created: Callable[[], None] | None = None,
               on_signal_selected: Callable[[Signal], None] | None = None):
    super().__init__()
    self._stream = stream
    self._dbc = dbc
    self._undo_stack = undo_stack
    self._on_signal_created = on_signal_created
    self._on_signal_selected = on_signal_selected
    self._selected_mid: MessageId | None = None
    self._current_data: MessageData | None = None

    # Drag state
    self._drag_start: tuple[int, int] | None = None  # (byte, bit_col)
    self._drag_end: tuple[int, int] | None = None
    self._dragging = False
    self._drag_mode: str = ""  # "create", "resize", or ""
    self._resize_sig: Signal | None = None

    # Selection / hover
    self._hovered_cell: tuple[int, int] | None = None
    self._hovered_signal: Signal | None = None
    self._selected_signal: Signal | None = None

  def set_message(self, mid: MessageId | None, data: MessageData | None) -> None:
    self._selected_mid = mid
    self._current_data = data

  def _hit_test(self, rect: rl.Rectangle, pos, n_bytes: int,
                cell_w: float, cell_h: float, label_w: float) -> tuple[int, int] | None:
    grid_x = rect.x + styles.PAD + label_w
    grid_y = rect.y + TITLE_H + HEADER_ROW_H
    if cell_w <= 0 or cell_h <= 0:
      return None
    if pos.x < grid_x or pos.y < grid_y:
      return None
    col = int((pos.x - grid_x) / cell_w)
    row = int((pos.y - grid_y) / cell_h)
    if 0 <= row < n_bytes and 0 <= col <= 8:
      return (row, col)
    return None

  def _get_signal_at_cell(self, byte_idx: int, bit_col: int) -> Signal | None:
    if self._selected_mid is None or bit_col >= 8:
      return None
    signals = self._dbc.signals(self._selected_mid[1])
    bit_pos = byte_idx * 8 + (7 - bit_col)
    for sig in signals:
      bits = self._signal_bit_set(sig, len(self._current_data.dat) if self._current_data else 8)
      if bit_pos in bits:
        return sig
    return None

  def _signal_bit_set(self, sig: Signal, n_bytes: int) -> set[int]:
    bits: set[int] = set()
    for j in range(sig.size):
      if sig.is_little_endian:
        pos = sig.lsb + j
      else:
        pos = _flip_bit_pos(sig.start_bit) + j
        pos = _flip_bit_pos(pos)
      if 0 <= pos < n_bytes * 8:
        bits.add(pos)
    return bits

  def _is_signal_boundary(self, sig: Signal, byte_idx: int, bit_col: int, n_bytes: int) -> bool:
    bit_pos = byte_idx * 8 + (7 - bit_col)
    bits = sorted(self._signal_bit_set(sig, n_bytes))
    if not bits:
      return False
    return bit_pos == bits[0] or bit_pos == bits[-1]

  def _render(self, rect: rl.Rectangle):
    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height), styles.BG)

    font = gui_app.font(FontWeight.NORMAL)

    if self._selected_mid is None or self._current_data is None:
      rl.draw_text_ex(font, "Select a message",
                      rl.Vector2(rect.x + styles.PAD, rect.y + rect.height / 2 - 12),
                      styles.FONT_SIZE, 0, styles.TEXT_MUTED)
      return

    data = self._current_data
    dat = data.dat
    n_bytes = len(dat)
    mid = self._selected_mid

    # Title
    name = self._dbc.msg_name(mid[1]) or f"0x{mid[1]:03X}"
    title = f"{name}  Bus:{mid[0]}  0x{mid[1]:03X}  [{n_bytes}]"
    rl.draw_text_ex(font, title, rl.Vector2(rect.x + styles.PAD, rect.y + 8), 20, 0, rl.WHITE)

    # Cell sizes
    label_w = 28
    grid_w = rect.width - styles.PAD * 2 - label_w
    cell_w = grid_w / 9
    cell_h = CELL_H

    grid_x = rect.x + styles.PAD + label_w
    grid_y = rect.y + TITLE_H

    # Column headers
    rl.draw_rectangle(int(rect.x), int(grid_y), int(rect.width), HEADER_ROW_H, styles.HEADER_BG)
    hdr_sz = 16
    for bit in range(8):
      hx = grid_x + bit * cell_w + cell_w / 2
      rl.draw_text_ex(font, str(7 - bit), rl.Vector2(hx - 4, grid_y + 6), hdr_sz, 0, styles.TEXT_DIM)
    hx = grid_x + 8 * cell_w
    rl.draw_text_ex(font, "Hex", rl.Vector2(hx + cell_w / 2 - 12, grid_y + 6), hdr_sz, 0, styles.TEXT_DIM)

    body_y = grid_y + HEADER_ROW_H

    # Heatmap
    flip_counts = self._stream.get_bit_flip_counts(mid)
    max_flips = max(flip_counts) if flip_counts else 1
    if max_flips == 0:
      max_flips = 1
    log_scaler = 255.0 / math.log2(1.2 * max_flips) if max_flips > 0 else 1.0

    # Build signal bit map: bit_pos -> signal_color_index
    # Also track MSB/LSB endpoints for label drawing
    signals = self._dbc.signals(mid[1])
    sig_bit_map: dict[int, int] = {}
    sig_endpoints: dict[int, str] = {}  # bit_pos -> "M" or "L"
    for si, sig in enumerate(signals):
      bits = sorted(self._signal_bit_set(sig, n_bytes))
      for flat in bits:
        sig_bit_map[flat] = si % len(styles.SIGNAL_COLORS)
      if bits:
        if sig.is_little_endian:
          sig_endpoints[bits[0]] = "L"
          sig_endpoints[bits[-1]] = "M"
        else:
          sig_endpoints[bits[0]] = "M"
          sig_endpoints[bits[-1]] = "L"

    # Scissor
    rl.begin_scissor_mode(int(rect.x), int(body_y),
                          int(rect.width), int(rect.height - TITLE_H - HEADER_ROW_H))

    # Hover
    mouse_pos = gui_app.last_mouse_event.pos
    self._hovered_cell = self._hit_test(rect, mouse_pos, n_bytes, cell_w, cell_h, label_w)
    self._hovered_signal = None
    hovered_signal_bits: set[int] = set()
    selected_signal_bits: set[int] = set()
    if self._hovered_cell and self._hovered_cell[1] < 8:
      self._hovered_signal = self._get_signal_at_cell(*self._hovered_cell)
      if self._hovered_signal:
        hovered_signal_bits = self._signal_bit_set(self._hovered_signal, n_bytes)
    if self._selected_signal:
      selected_signal_bits = self._signal_bit_set(self._selected_signal, n_bytes)

    bit_font_sz = 18

    for byte_idx in range(n_bytes):
      ry = body_y + byte_idx * cell_h

      # Row label
      rl.draw_text_ex(font, str(byte_idx),
                      rl.Vector2(rect.x + styles.PAD, ry + (cell_h - bit_font_sz) / 2),
                      hdr_sz, 0, styles.TEXT_DIM)

      for bit in range(8):
        cx = grid_x + bit * cell_w
        bit_idx = byte_idx * 8 + (7 - bit)
        has_signal = bit_idx in sig_bit_map

        # --- Cell background ---
        if has_signal:
          # Signal color with solid alpha so signals are clearly visible
          sc = styles.SIGNAL_COLORS[sig_bit_map[bit_idx]]
          # Base: solid signal color at ~35% opacity
          base_alpha = 90
          # Brighten based on heatmap
          if bit_idx < len(flip_counts) and flip_counts[bit_idx] > 0:
            normalized = math.log2(1.0 + flip_counts[bit_idx] * 1.2) * log_scaler
            base_alpha = int(max(90, min(220, normalized)))
          rl.draw_rectangle(int(cx), int(ry), int(cell_w), int(cell_h),
                            rl.Color(sc.r, sc.g, sc.b, base_alpha))
        else:
          # Non-signal bits: subtle greyish-blue heatmap
          alpha = 0.0
          if bit_idx < len(flip_counts) and flip_counts[bit_idx] > 0:
            normalized = math.log2(1.0 + flip_counts[bit_idx] * 1.2) * log_scaler
            alpha = max(10.0, min(255.0, normalized))
          if alpha > 0:
            rl.draw_rectangle(int(cx), int(ry), int(cell_w), int(cell_h),
                              rl.Color(SIGNAL_BASE_COLOR.r, SIGNAL_BASE_COLOR.g,
                                       SIGNAL_BASE_COLOR.b, int(alpha * 0.4)))

        # Drag highlight
        if self._dragging and self._drag_start and self._drag_end:
          if self._in_drag_range(byte_idx, 7 - bit):
            rl.draw_rectangle(int(cx), int(ry), int(cell_w), int(cell_h), styles.DRAG_HIGHLIGHT)

        # Selected signal highlight
        if bit_idx in selected_signal_bits:
          rl.draw_rectangle(int(cx), int(ry), int(cell_w), int(cell_h),
                            rl.Color(255, 255, 255, 30))

        # Hover highlight (entire hovered signal)
        if bit_idx in hovered_signal_bits and bit_idx not in selected_signal_bits:
          rl.draw_rectangle(int(cx), int(ry), int(cell_w), int(cell_h),
                            rl.Color(255, 255, 255, 20))

        # Grid
        rl.draw_rectangle_lines(int(cx), int(ry), int(cell_w), int(cell_h), styles.GRID)

        # Bit text — 1 = bright white, 0 = very dim
        val = (dat[byte_idx] >> (7 - bit)) & 1
        text = str(val)
        text_color = rl.WHITE if val else rl.Color(60, 62, 70, 255)
        tw = rl.measure_text_ex(font, text, bit_font_sz * FONT_SCALE, 0).x
        rl.draw_text_ex(font, text,
                        rl.Vector2(cx + (cell_w - tw) / 2, ry + (cell_h - bit_font_sz) / 2),
                        bit_font_sz, 0, text_color)

        # MSB/LSB endpoint label (small "M" or "L" at bottom-right, like Qt cabana)
        endpoint = sig_endpoints.get(bit_idx)
        if endpoint:
          ep_sz = 10
          rl.draw_text_ex(font, endpoint,
                          rl.Vector2(cx + cell_w - ep_sz - 1, ry + cell_h - ep_sz - 2),
                          ep_sz, 0, rl.Color(200, 200, 200, 180))

      # Hex cell
      hx = grid_x + 8 * cell_w
      r, g, b = data.byte_colors[byte_idx] if byte_idx < len(data.byte_colors) else (80, 80, 80)
      rl.draw_rectangle(int(hx), int(ry), int(cell_w), int(cell_h), rl.Color(r, g, b, 160))
      rl.draw_rectangle_lines(int(hx), int(ry), int(cell_w), int(cell_h), styles.GRID)

      hex_str = f"{dat[byte_idx]:02X}"
      tw = rl.measure_text_ex(font, hex_str, bit_font_sz * FONT_SCALE, 0).x
      rl.draw_text_ex(font, hex_str,
                      rl.Vector2(hx + (cell_w - tw) / 2, ry + (cell_h - bit_font_sz) / 2),
                      bit_font_sz, 0, rl.WHITE)

    rl.end_scissor_mode()

    # --- Mouse handling ---
    for ev in gui_app.mouse_events:
      if ev.left_pressed and rl.check_collision_point_rec(ev.pos, rect):
        hit = self._hit_test(rect, ev.pos, n_bytes, cell_w, cell_h, label_w)
        if hit and hit[1] < 8:
          sig_at = self._get_signal_at_cell(*hit)
          if sig_at:
            if self._is_signal_boundary(sig_at, hit[0], hit[1], n_bytes):
              self._drag_mode = "resize"
              self._resize_sig = sig_at
              self._drag_start = hit
              self._drag_end = hit
              self._dragging = True
            else:
              self._selected_signal = sig_at
              self._drag_mode = ""
              self._dragging = False
              if self._on_signal_selected:
                self._on_signal_selected(sig_at)
          else:
            self._drag_mode = "create"
            self._resize_sig = None
            self._drag_start = hit
            self._drag_end = hit
            self._dragging = True

      elif ev.left_released:
        if self._dragging and self._drag_start and self._drag_end:
          if self._drag_start != self._drag_end:
            self._complete_drag(n_bytes)
          elif self._drag_mode == "resize" and self._resize_sig:
            self._selected_signal = self._resize_sig
            if self._on_signal_selected:
              self._on_signal_selected(self._resize_sig)
        self._dragging = False
        self._drag_start = None
        self._drag_end = None
        self._drag_mode = ""
        self._resize_sig = None

    # Update drag end from current mouse position
    if self._dragging:
      hit = self._hit_test(rect, mouse_pos, n_bytes, cell_w, cell_h, label_w)
      if hit and hit[1] < 8:
        self._drag_end = hit

    self._handle_keyboard(n_bytes)

  def _complete_drag(self, n_bytes: int):
    if not self._drag_start or not self._drag_end or not self._selected_mid:
      return

    s_byte, s_bit = self._drag_start
    e_byte, e_bit = self._drag_end

    s_flat = s_byte * 8 + (7 - s_bit)
    e_flat = e_byte * 8 + (7 - e_bit)
    if s_flat > e_flat:
      s_flat, e_flat = e_flat, s_flat

    size = e_flat - s_flat + 1
    if size <= 0 or size > n_bytes * 8:
      return

    address = self._selected_mid[1]

    if self._drag_mode == "resize" and self._resize_sig:
      old_sig = self._resize_sig
      new_sig = copy.deepcopy(old_sig)
      new_sig.size = size
      new_sig.start_bit = s_flat
      new_sig.lsb = s_flat
      cmd = EditSignalCommand(self._dbc, address, old_sig, new_sig)
      self._undo_stack.push(cmd)
    elif self._drag_mode == "create":
      name = self._dbc.next_signal_name(address)
      sig = Signal(name=name, start_bit=s_flat, msb=s_flat + size - 1, lsb=s_flat,
                   size=size, is_signed=False, factor=1.0, offset=0.0, is_little_endian=True)
      cmd = AddSignalCommand(self._dbc, address, sig)
      self._undo_stack.push(cmd)

    if self._on_signal_created:
      self._on_signal_created()

  def _handle_keyboard(self, n_bytes: int):
    sig = self._hovered_signal or self._selected_signal
    if not sig or not self._selected_mid:
      return

    address = self._selected_mid[1]

    if (rl.is_key_pressed(rl.KeyboardKey.KEY_DELETE) or
        rl.is_key_pressed(rl.KeyboardKey.KEY_BACKSPACE) or
        rl.is_key_pressed(rl.KeyboardKey.KEY_X)):
      cmd = RemoveSignalCommand(self._dbc, address, sig)
      self._undo_stack.push(cmd)
      self._selected_signal = None
      if self._on_signal_created:
        self._on_signal_created()

    elif rl.is_key_pressed(rl.KeyboardKey.KEY_E):
      new_sig = copy.deepcopy(sig)
      new_sig.is_little_endian = not new_sig.is_little_endian
      cmd = EditSignalCommand(self._dbc, address, sig, new_sig)
      self._undo_stack.push(cmd)

    elif rl.is_key_pressed(rl.KeyboardKey.KEY_S):
      new_sig = copy.deepcopy(sig)
      new_sig.is_signed = not new_sig.is_signed
      cmd = EditSignalCommand(self._dbc, address, sig, new_sig)
      self._undo_stack.push(cmd)

  def _in_drag_range(self, byte_idx: int, bit: int) -> bool:
    if not self._drag_start or not self._drag_end:
      return False
    s_byte, s_bit = self._drag_start
    e_byte, e_bit = self._drag_end
    # Convert column index to bit index (col 0 = bit 7, col 7 = bit 0)
    s_flat = s_byte * 8 + (7 - s_bit)
    e_flat = e_byte * 8 + (7 - e_bit)
    if s_flat > e_flat:
      s_flat, e_flat = e_flat, s_flat
    flat = byte_idx * 8 + bit
    return s_flat <= flat <= e_flat


def _flip_bit_pos(pos: int) -> int:
  return (pos // 8) * 8 + (7 - pos % 8)
