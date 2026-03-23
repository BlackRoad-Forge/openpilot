from __future__ import annotations

import copy
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

    # Hover
    self._hovered_cell: tuple[int, int] | None = None
    self._hovered_signal: Signal | None = None

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
    return bit_pos == sig.lsb or bit_pos == sig.msb

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
    rl.draw_text_ex(font, title, rl.Vector2(rect.x + styles.PAD, rect.y + 8), 16, 0, rl.WHITE)

    # Cell sizes
    label_w = 28
    grid_w = rect.width - styles.PAD * 2 - label_w
    cell_w = grid_w / 9
    cell_h = CELL_H

    grid_x = rect.x + styles.PAD + label_w
    grid_y = rect.y + TITLE_H

    # Column headers
    rl.draw_rectangle(int(rect.x), int(grid_y), int(rect.width), HEADER_ROW_H, styles.HEADER_BG)
    hdr_sz = 13
    for bit in range(8):
      hx = grid_x + bit * cell_w + cell_w / 2
      rl.draw_text_ex(font, str(7 - bit), rl.Vector2(hx - 3, grid_y + 7), hdr_sz, 0, styles.TEXT_DIM)
    hx = grid_x + 8 * cell_w
    rl.draw_text_ex(font, "Hex", rl.Vector2(hx + cell_w / 2 - 10, grid_y + 7), hdr_sz, 0, styles.TEXT_DIM)

    body_y = grid_y + HEADER_ROW_H

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
        # Use actual lsb/msb from signal, not sorted bit positions
        # For both LE and BE: lsb bit gets "L", msb bit gets "M"
        lsb_bit = sig.lsb
        msb_bit = sig.msb
        if lsb_bit in bits:
          sig_endpoints[lsb_bit] = "L"
        if msb_bit in bits:
          sig_endpoints[msb_bit] = "M"

    # Scissor
    rl.begin_scissor_mode(int(rect.x), int(body_y),
                          int(rect.width), int(rect.height - TITLE_H - HEADER_ROW_H))

    # Hover
    mouse_pos = gui_app.last_mouse_event.pos
    self._hovered_cell = self._hit_test(rect, mouse_pos, n_bytes, cell_w, cell_h, label_w)
    self._hovered_signal = None
    hovered_signal_bits: set[int] = set()
    if self._hovered_cell and self._hovered_cell[1] < 8:
      self._hovered_signal = self._get_signal_at_cell(*self._hovered_cell)
      if self._hovered_signal:
        hovered_signal_bits = self._signal_bit_set(self._hovered_signal, n_bytes)

    # Font sizes matching Qt cabana (~13px for bits, 8px for M/L labels)
    bit_font_sz = 14
    ml_font_sz = 8

    # Build per-cell signal lookup for border drawing: (row, col) -> set of signal indices
    cell_sigs: dict[tuple[int, int], set[int]] = {}
    for si, sig in enumerate(signals):
      for flat in self._signal_bit_set(sig, n_bytes):
        row = flat // 8
        col = 7 - (flat % 8)  # flat bit -> display column
        key = (row, col)
        if key not in cell_sigs:
          cell_sigs[key] = set()
        cell_sigs[key].add(si)

    for byte_idx in range(n_bytes):
      ry = body_y + byte_idx * cell_h

      # Row label
      rl.draw_text_ex(font, str(byte_idx),
                      rl.Vector2(rect.x + styles.PAD, ry + (cell_h - bit_font_sz) / 2),
                      12, 0, styles.TEXT_DIM)

      for bit in range(8):
        cx = grid_x + bit * cell_w
        bit_idx = byte_idx * 8 + (7 - bit)
        has_signal = bit_idx in sig_bit_map

        # --- Cell background ---
        if has_signal:
          sc = styles.SIGNAL_COLORS[sig_bit_map[bit_idx]]
          is_hovered = bit_idx in hovered_signal_bits
          if is_hovered:
            # Hovered: full signal color, darker (like Qt's .darker(125))
            rl.draw_rectangle(int(cx), int(ry), int(cell_w), int(cell_h),
                              rl.Color(sc.r * 4 // 5, sc.g * 4 // 5, sc.b * 4 // 5, 160))
          else:
            # Unselected: very muted fill + inset borders (like Qt cabana)
            my_sigs = cell_sigs.get((byte_idx, bit), set())
            for si_idx in my_sigs:
              draw_left = si_idx not in cell_sigs.get((byte_idx, bit - 1), set())
              draw_right = si_idx not in cell_sigs.get((byte_idx, bit + 1), set())
              draw_top = si_idx not in cell_sigs.get((byte_idx - 1, bit), set())
              draw_bottom = si_idx not in cell_sigs.get((byte_idx + 1, bit), set())

              inset_x = cx + (3 if draw_left else 0)
              inset_y = ry + (2 if draw_top else 0)
              inset_w = cell_w - (3 if draw_left else 0) - (3 if draw_right else 0)
              inset_h = cell_h - (2 if draw_top else 0) - (2 if draw_bottom else 0)

              # Very subtle fill — just enough to see the signal region
              sig_c = styles.SIGNAL_COLORS[si_idx % len(styles.SIGNAL_COLORS)]
              rl.draw_rectangle(int(inset_x), int(inset_y), int(inset_w), int(inset_h),
                                rl.Color(sig_c.r, sig_c.g, sig_c.b, 35))

              # Border lines (signal color at moderate alpha)
              border_c = rl.Color(sig_c.r * 4 // 5, sig_c.g * 4 // 5, sig_c.b * 4 // 5, 180)
              if draw_left:
                rl.draw_line(int(inset_x), int(inset_y), int(inset_x), int(inset_y + inset_h), border_c)
              if draw_right:
                rl.draw_line(int(inset_x + inset_w), int(inset_y), int(inset_x + inset_w), int(inset_y + inset_h), border_c)
              if draw_top:
                rl.draw_line(int(inset_x), int(inset_y), int(inset_x + inset_w), int(inset_y), border_c)
              if draw_bottom:
                rl.draw_line(int(inset_x), int(inset_y + inset_h), int(inset_x + inset_w), int(inset_y + inset_h), border_c)

        # Drag highlight
        if self._dragging and self._drag_start and self._drag_end:
          if self._in_drag_highlight(byte_idx, 7 - bit, n_bytes):
            if self._drag_mode == "resize" and self._resize_sig:
              si = signals.index(self._resize_sig) if self._resize_sig in signals else 0
              sc = styles.SIGNAL_COLORS[si % len(styles.SIGNAL_COLORS)]
              rl.draw_rectangle(int(cx), int(ry), int(cell_w), int(cell_h),
                                rl.Color(sc.r, sc.g, sc.b, 120))
            else:
              rl.draw_rectangle(int(cx), int(ry), int(cell_w), int(cell_h), styles.DRAG_HIGHLIGHT)

        # Bit text — same color for 0 and 1 (like Qt cabana uses QPalette::Text)
        val = (dat[byte_idx] >> (7 - bit)) & 1
        text = str(val)
        text_color = styles.TEXT
        tw = rl.measure_text_ex(font, text, bit_font_sz * FONT_SCALE, 0).x
        rl.draw_text_ex(font, text,
                        rl.Vector2(cx + (cell_w - tw) / 2, ry + (cell_h - bit_font_sz) / 2),
                        bit_font_sz, 0, text_color)

        # MSB/LSB label (8px like Qt cabana's small_font)
        endpoint = sig_endpoints.get(bit_idx)
        if endpoint:
          rl.draw_text_ex(font, endpoint,
                          rl.Vector2(cx + cell_w - ml_font_sz - 2, ry + cell_h - ml_font_sz - 3),
                          ml_font_sz, 0, styles.TEXT_DIM)

      # Hex cell
      hx = grid_x + 8 * cell_w
      r, g, b = data.byte_colors[byte_idx] if byte_idx < len(data.byte_colors) else (80, 80, 80)
      rl.draw_rectangle(int(hx), int(ry), int(cell_w), int(cell_h), rl.Color(r, g, b, 160))

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
              # Click inside signal = fire callback (no drag, no selection state)
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

      # Use sig.lsb/msb directly (correct for both LE and BE)
      drag_start_flat = self._drag_start[0] * 8 + (7 - self._drag_start[1])
      drag_end_flat = self._drag_end[0] * 8 + (7 - self._drag_end[1])

      if drag_start_flat == old_sig.lsb:
        # Dragged the LSB end — keep MSB fixed
        new_lsb = drag_end_flat
        new_msb = old_sig.msb
      else:
        # Dragged the MSB end — keep LSB fixed
        new_lsb = old_sig.lsb
        new_msb = drag_end_flat

      if new_lsb > new_msb:
        new_lsb, new_msb = new_msb, new_lsb

      new_size = new_msb - new_lsb + 1
      if new_size <= 0 or new_size > n_bytes * 8:
        return

      new_sig = copy.deepcopy(old_sig)
      new_sig.size = new_size
      new_sig.lsb = new_lsb
      new_sig.msb = new_msb
      # start_bit convention: LE uses lsb, BE uses msb
      new_sig.start_bit = new_lsb if old_sig.is_little_endian else new_msb
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
    sig = self._hovered_signal
    if not sig or not self._selected_mid:
      return

    address = self._selected_mid[1]

    if (rl.is_key_pressed(rl.KeyboardKey.KEY_DELETE) or
        rl.is_key_pressed(rl.KeyboardKey.KEY_BACKSPACE) or
        rl.is_key_pressed(rl.KeyboardKey.KEY_X)):
      cmd = RemoveSignalCommand(self._dbc, address, sig)
      self._undo_stack.push(cmd)
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

  def _in_drag_highlight(self, byte_idx: int, bit: int, n_bytes: int) -> bool:
    """Check if a bit should be highlighted during drag.
    For create: highlights the drag range.
    For resize: highlights from the signal's fixed end to the drag position."""
    if not self._drag_start or not self._drag_end:
      return False

    flat = byte_idx * 8 + bit
    drag_end_flat = self._drag_end[0] * 8 + (7 - self._drag_end[1])

    if self._drag_mode == "resize" and self._resize_sig:
      sig = self._resize_sig
      drag_start_flat = self._drag_start[0] * 8 + (7 - self._drag_start[1])
      if drag_start_flat == sig.lsb:
        # Dragging LSB — MSB is fixed
        lo, hi = min(drag_end_flat, sig.msb), max(drag_end_flat, sig.msb)
      else:
        # Dragging MSB — LSB is fixed
        lo, hi = min(drag_end_flat, sig.lsb), max(drag_end_flat, sig.lsb)
      return lo <= flat <= hi
    else:
      # Create mode: simple range between start and end
      s_flat = self._drag_start[0] * 8 + (7 - self._drag_start[1])
      lo, hi = min(s_flat, drag_end_flat), max(s_flat, drag_end_flat)
      return lo <= flat <= hi


def _flip_bit_pos(pos: int) -> int:
  return (pos // 8) * 8 + (7 - pos % 8)
