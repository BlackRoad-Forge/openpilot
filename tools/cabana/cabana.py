#!/usr/bin/env python3
"""
Cabana - CAN bus analysis tool (Python/Raylib port)

Usage:
  python tools/cabana/cabana.py --demo              # load demo route
  python tools/cabana/cabana.py <route_id>          # load specific route
"""
from __future__ import annotations

import argparse
import os
import pyray as rl

# Set dimensions before gui_app singleton is created
os.environ["BIG"] = "0"
os.environ.setdefault("SCALE", "1.0")

from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.split_panel import SplitPanel
from openpilot.tools.cabana.can_stream import CanStream, MessageId, DEMO_ROUTE
from openpilot.tools.cabana.dbc_manager import DBCManager
from openpilot.tools.cabana.commands import UndoStack
from openpilot.tools.cabana.views.messages_view import MessagesView
from openpilot.tools.cabana.views.binary_view import BinaryView
from openpilot.tools.cabana.views.signal_view import SignalView
from openpilot.tools.cabana.views.charts_view import ChartsView
from openpilot.tools.cabana.views.video_view import VideoView
from openpilot.tools.cabana.views.history_log_view import HistoryLogView
from openpilot.tools.cabana.views.toolbar_view import ToolbarView
from openpilot.tools.cabana.views.menu_bar import MenuBar, MenuItem, separator
from openpilot.tools.cabana import styles
from opendbc.can.dbc import Signal


class DetailPanel(Widget):
  """Center panel: tab bar + binary view (top) + signal view (bottom) in vertical split.
  Supports multiple open message tabs and Binary/Log tab toggle."""

  def __init__(self, stream: CanStream, dbc: DBCManager, undo_stack: UndoStack,
               on_signal_select: callable = None):
    super().__init__()
    self._stream = stream
    self._dbc = dbc
    self._undo_stack = undo_stack

    self._binary_view = BinaryView(stream, dbc, undo_stack,
                                     on_signal_created=self._on_views_changed,
                                     on_signal_selected=self._on_signal_select)
    self._signal_view = SignalView(stream, dbc, undo_stack, on_select_signal=self._on_signal_select)
    self._history_view = HistoryLogView(stream, dbc)

    self._split = self._child(SplitPanel(self._binary_view, self._signal_view,
                                          ratio=0.55, horizontal=False, divider_width=5,
                                          min_first_px=150, min_second_px=100))

    # Tabs: list of open message IDs
    self._tabs: list[MessageId] = []
    self._active_tab: int = -1
    self._show_log: bool = False  # Binary vs Log toggle
    self._on_signal_select_cb = on_signal_select

  def set_message(self, mid: MessageId) -> None:
    # Add tab if not already open
    if mid not in self._tabs:
      if len(self._tabs) >= 10:
        self._tabs.pop(0)
      self._tabs.append(mid)
    self._active_tab = self._tabs.index(mid)

  def _on_views_changed(self):
    """Called when signals are created/removed to refresh views."""
    pass

  def _on_signal_select(self, sig: Signal) -> None:
    if self._on_signal_select_cb and self._active_tab >= 0:
      mid = self._tabs[self._active_tab]
      self._on_signal_select_cb(mid, sig)

  def update_data(self, current_msgs) -> None:
    if self._active_tab < 0 or self._active_tab >= len(self._tabs):
      return
    mid = self._tabs[self._active_tab]
    if mid in current_msgs:
      data = current_msgs[mid]
      self._binary_view.set_message(mid, data)
      self._signal_view.set_message(mid, data)
      self._history_view.set_message(mid)

  def _render(self, rect: rl.Rectangle):
    font = gui_app.font(FontWeight.NORMAL)

    # Tab bar
    tab_y = rect.y
    rl.draw_rectangle(int(rect.x), int(tab_y), int(rect.width), styles.TAB_BAR_H, styles.PANEL_BG)

    # Message tabs
    tx = rect.x + 2
    for i, mid in enumerate(self._tabs):
      name = self._dbc.msg_name(mid[1]) or f"0x{mid[1]:03X}"
      tw = rl.measure_text_ex(font, name, styles.SMALL_FONT * 1.242, 0).x
      tab_w = tw + 28  # room for close button
      tab_rect = rl.Rectangle(tx, tab_y + 2, tab_w, styles.TAB_BAR_H - 4)

      is_active = i == self._active_tab
      hovered = rl.check_collision_point_rec(gui_app.last_mouse_event.pos, tab_rect)

      bg = styles.SELECTED_BG if is_active else (styles.HOVER_BG if hovered else styles.PANEL_BG)
      rl.draw_rectangle_rounded(tab_rect, 0.2, 4, bg)
      rl.draw_text_ex(font, name,
                      rl.Vector2(tx + 4, tab_y + (styles.TAB_BAR_H - styles.SMALL_FONT) / 2),
                      styles.SMALL_FONT, 0, styles.TEXT if is_active else styles.TEXT_DIM)

      # Close button
      close_x = tx + tab_w - 18
      close_rect = rl.Rectangle(close_x, tab_y + 4, 14, styles.TAB_BAR_H - 8)
      close_hovered = rl.check_collision_point_rec(gui_app.last_mouse_event.pos, close_rect)
      if is_active or hovered:
        rl.draw_text_ex(font, "x", rl.Vector2(close_x + 2, tab_y + 5),
                        styles.SMALL_FONT - 4, 0,
                        styles.ACCENT if close_hovered else styles.TEXT_DIM)

      for ev in gui_app.mouse_events:
        if ev.left_released:
          if rl.check_collision_point_rec(ev.pos, close_rect):
            self._tabs.pop(i)
            if self._active_tab >= len(self._tabs):
              self._active_tab = len(self._tabs) - 1
            break
          elif rl.check_collision_point_rec(ev.pos, tab_rect):
            self._active_tab = i

      tx += tab_w + 2

    # Binary/Log toggle (right side of tab bar)
    toggle_labels = ["Binary", "Log"]
    toggle_x = rect.x + rect.width - 110
    for ti, label in enumerate(toggle_labels):
      is_log = ti == 1
      is_selected = self._show_log == is_log
      tw = 50
      tr = rl.Rectangle(toggle_x, tab_y + 3, tw, styles.TAB_BAR_H - 6)
      hovered = rl.check_collision_point_rec(gui_app.last_mouse_event.pos, tr)
      bg = styles.SELECTED_BG if is_selected else (styles.HOVER_BG if hovered else styles.PANEL_BG)
      rl.draw_rectangle_rounded(tr, 0.2, 4, bg)
      rl.draw_text_ex(font, label,
                      rl.Vector2(toggle_x + 6, tab_y + (styles.TAB_BAR_H - styles.SMALL_FONT + 2) / 2),
                      styles.SMALL_FONT - 2, 0, styles.TEXT if is_selected else styles.TEXT_DIM)
      for ev in gui_app.mouse_events:
        if ev.left_released and rl.check_collision_point_rec(ev.pos, tr):
          self._show_log = is_log
      toggle_x += tw + 2

    rl.draw_line(int(rect.x), int(tab_y + styles.TAB_BAR_H),
                 int(rect.x + rect.width), int(tab_y + styles.TAB_BAR_H), styles.BORDER)

    # Body
    body_rect = rl.Rectangle(rect.x, rect.y + styles.TAB_BAR_H,
                              rect.width, rect.height - styles.TAB_BAR_H)

    if self._active_tab < 0 or not self._tabs:
      rl.draw_rectangle(int(body_rect.x), int(body_rect.y),
                        int(body_rect.width), int(body_rect.height), styles.BG)
      rl.draw_text_ex(font, "Select a message",
                      rl.Vector2(body_rect.x + styles.PAD, body_rect.y + body_rect.height / 2 - 12),
                      styles.FONT_SIZE, 0, styles.TEXT_MUTED)
      return

    if self._show_log:
      self._history_view.render(body_rect)
    else:
      self._split.render(body_rect)


class CabanaWindow(Widget):
  """Main cabana window with menu bar, split panels, and toolbar."""

  def __init__(self, stream: CanStream, dbc: DBCManager):
    super().__init__()
    self._stream = stream
    self._dbc = dbc
    self._undo_stack = UndoStack()

    # Build panels
    self._messages_view = MessagesView(stream, dbc, on_select=self._on_message_select)
    self._detail_panel = DetailPanel(stream, dbc, self._undo_stack,
                                      on_signal_select=self._on_signal_select)
    self._charts_view = ChartsView(stream, dbc)
    self._video_view = VideoView(stream)
    self._toolbar = self._child(ToolbarView(stream))

    # Menu bar
    self._menu_bar = self._child(MenuBar())
    self._build_menus()

    # Modal overlays
    self._settings_dialog = None
    self._find_dialog = None

    # Layout matches Qt cabana:
    #   Left dock: messages table
    #   Center: detail panel (binary + signals)
    #   Right dock: video (top) + charts (bottom)
    self._video_charts_split = SplitPanel(self._video_view, self._charts_view,
                                           ratio=0.35, horizontal=False, divider_width=5,
                                           min_first_px=80, min_second_px=80)
    self._center_right_split = SplitPanel(self._detail_panel, self._video_charts_split,
                                           ratio=0.55, horizontal=True, divider_width=5,
                                           min_first_px=200, min_second_px=150)
    self._main_split = self._child(SplitPanel(self._messages_view, self._center_right_split,
                                               ratio=0.30, horizontal=True, divider_width=5,
                                               min_first_px=350))

  def _build_menus(self):
    self._menu_bar.set_menus([
      ("File", [
        MenuItem("New DBC", "Ctrl+N", self._new_dbc),
        MenuItem("Open DBC...", "Ctrl+O", self._open_dbc),
        MenuItem("Save DBC", "Ctrl+S", self._save_dbc),
        MenuItem("Save DBC As...", "Ctrl+Shift+S", self._save_dbc_as),
        separator(),
        MenuItem("Export CSV...", "", self._export_csv),
        separator(),
        MenuItem("Settings...", "Ctrl+,", self._show_settings),
        separator(),
        MenuItem("Exit", "Ctrl+Q", self._exit),
      ]),
      ("Edit", [
        MenuItem("Undo", "Ctrl+Z", self._undo_stack.undo, enabled=lambda: self._undo_stack.can_undo),
        MenuItem("Redo", "Ctrl+Y", self._undo_stack.redo, enabled=lambda: self._undo_stack.can_redo),
      ]),
      ("View", [
        MenuItem("Full Screen", "F11", self._toggle_fullscreen),
        separator(),
        MenuItem("Reset Layout", "", self._reset_layout),
      ]),
      ("Tools", [
        MenuItem("Find Similar Bits", "", self._find_similar_bits),
        MenuItem("Find Signal", "", self._find_signal),
      ]),
      ("Help", [
        MenuItem("About", "", self._show_about),
      ]),
    ])

  def set_dbc(self, dbc: DBCManager) -> None:
    self._dbc = dbc
    self._messages_view._dbc = dbc
    self._detail_panel._dbc = dbc
    self._detail_panel._binary_view._dbc = dbc
    self._detail_panel._signal_view._dbc = dbc
    self._charts_view._dbc = dbc
    self._undo_stack.clear()

  def _on_message_select(self, mid: MessageId) -> None:
    self._detail_panel.set_message(mid)

  def _on_signal_select(self, mid: MessageId, sig: Signal) -> None:
    self._charts_view.add_signal(mid, sig)

  _last_update: float = 0.0

  def _update_state(self):
    dt = rl.get_frame_time()
    self._stream.tick(dt)

    # Status bar (cheap — no lock needed for these)
    dbc_name = self._dbc.dbc_name or "No DBC"
    fp = self._stream.fingerprint
    status = dbc_name
    if fp:
      status += f" | {fp}"
    if self._dbc.modified:
      status += " *"
    self._toolbar.set_status(status)

    if not self._stream.loaded and not self._stream.loading:
      return

    # Throttle data updates to max ~6/sec during loading, full speed when loaded
    now = rl.get_time()
    if self._stream.loading:
      if now - self._last_update < 0.16:
        return
    self._last_update = now

    current_msgs = self._stream.current_messages()
    for mid, data in current_msgs.items():
      data.name = self._dbc.msg_name(mid[1]) or f"0x{mid[1]:03X}"

    self._messages_view.update_data(current_msgs)
    self._detail_panel.update_data(current_msgs)

  def _render(self, rect: rl.Rectangle):
    # Menu bar at top
    menu_rect = rl.Rectangle(rect.x, rect.y, rect.width, styles.MENU_BAR_H)

    # Toolbar at bottom
    toolbar_rect = rl.Rectangle(rect.x, rect.y + rect.height - styles.TOOLBAR_H,
                                rect.width, styles.TOOLBAR_H)

    # Body between menu and toolbar
    body_rect = rl.Rectangle(rect.x, rect.y + styles.MENU_BAR_H,
                              rect.width, rect.height - styles.MENU_BAR_H - styles.TOOLBAR_H)

    self._main_split.render(body_rect)
    self._toolbar.render(toolbar_rect)

    # Menu bar rendered last (dropdowns overlay body)
    self._menu_bar.render(menu_rect)

    # Modal dialogs
    if self._settings_dialog:
      self._settings_dialog.render(rect)
    if self._find_dialog:
      self._find_dialog.render(rect)

  # --- Menu callbacks ---

  def _new_dbc(self):
    self._dbc.new_dbc()
    self._undo_stack.clear()

  def _open_dbc(self):
    try:
      import tkinter as tk
      from tkinter import filedialog
      root = tk.Tk()
      root.withdraw()
      path = filedialog.askopenfilename(
        title="Open DBC",
        filetypes=[("DBC files", "*.dbc"), ("All files", "*.*")]
      )
      root.destroy()
      if path:
        self._dbc.load(path)
        self._undo_stack.clear()
    except Exception as e:
      print(f"Open DBC error: {e}")

  def _save_dbc(self):
    if self._dbc.save_path:
      self._dbc.save(self._dbc.save_path)
    else:
      self._save_dbc_as()

  def _save_dbc_as(self):
    try:
      import tkinter as tk
      from tkinter import filedialog
      root = tk.Tk()
      root.withdraw()
      path = filedialog.asksaveasfilename(
        title="Save DBC As",
        defaultextension=".dbc",
        filetypes=[("DBC files", "*.dbc"), ("All files", "*.*")]
      )
      root.destroy()
      if path:
        self._dbc.save(path)
    except Exception as e:
      print(f"Save DBC error: {e}")

  def _export_csv(self):
    try:
      import tkinter as tk
      from tkinter import filedialog
      root = tk.Tk()
      root.withdraw()
      path = filedialog.asksaveasfilename(
        title="Export CSV",
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
      )
      root.destroy()
      if path:
        self._dbc.export_csv(path, self._stream)
    except Exception as e:
      print(f"Export CSV error: {e}")

  def _show_settings(self):
    from openpilot.tools.cabana.views.settings_dialog import SettingsDialog
    self._settings_dialog = SettingsDialog(on_close=lambda: setattr(self, '_settings_dialog', None))

  def _toggle_fullscreen(self):
    rl.toggle_fullscreen()

  def _reset_layout(self):
    self._main_split._ratio = 0.25
    self._center_right_split._ratio = 0.55
    self._video_charts_split._ratio = 0.35

  def _find_similar_bits(self):
    from openpilot.tools.cabana.views.find_similar_bits import FindSimilarBits
    self._find_dialog = FindSimilarBits(self._stream, self._dbc,
                                         on_close=lambda: setattr(self, '_find_dialog', None))

  def _find_signal(self):
    from openpilot.tools.cabana.views.find_signal import FindSignal
    self._find_dialog = FindSignal(self._stream, self._dbc,
                                    on_close=lambda: setattr(self, '_find_dialog', None))

  def _show_about(self):
    print("Cabana - CAN bus analysis tool (Python/Raylib port)")

  def _exit(self):
    rl.close_window()


def main():
  parser = argparse.ArgumentParser(description="Cabana - CAN bus analysis tool")
  parser.add_argument("route", nargs="?", help="Route ID to load")
  parser.add_argument("--demo", action="store_true", help="Load demo route")
  args = parser.parse_args()

  route = DEMO_ROUTE if args.demo else args.route
  if not route:
    parser.error("Provide a route ID or use --demo")

  # Override singleton dimensions for desktop tool
  gui_app._width = 1600
  gui_app._height = 900
  gui_app._scale = 1.0
  gui_app._scaled_width = 1600
  gui_app._scaled_height = 900
  gui_app.init_window("Cabana", fps=60)

  # Create stream (loads in background) and window immediately
  stream = CanStream(route)
  dbc = DBCManager("")  # loaded once stream has fingerprint

  window = CabanaWindow(stream, dbc)
  gui_app.push_widget(window)

  for _ in gui_app.render():
    # Load DBC as soon as fingerprint is available (don't wait for full load)
    if not dbc.loaded and stream.dbc_name:
      dbc = DBCManager(stream.dbc_name)
      window.set_dbc(dbc)


if __name__ == "__main__":
  main()
