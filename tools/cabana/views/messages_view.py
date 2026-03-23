from __future__ import annotations

import pyray as rl
from collections.abc import Callable

from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.table import Table, TableColumn
from openpilot.tools.cabana.can_stream import CanStream, MessageId, MessageData
from openpilot.tools.cabana.dbc_manager import DBCManager
from openpilot.tools.cabana.desktop_scroll import DesktopScrollPanel


class MessageRow:
  """One row in the messages table."""
  __slots__ = ('mid', 'name', 'address_str', 'src', 'freq', 'count', 'dat_hex', 'data')

  def __init__(self, mid: MessageId, data: MessageData, name: str):
    self.mid = mid
    self.name = name
    self.address_str = f"0x{mid[1]:03X}"
    self.src = str(mid[0])
    self.freq = f"{data.freq:.0f}" if data.freq > 0 else ""
    self.count = str(data.count)
    self.dat_hex = data.dat.hex(' ')
    self.data = data


COL_BUS = 0
COL_ADDR = 1
COL_NAME = 2
COL_FREQ = 3
COL_COUNT = 4
COL_DATA = 5

COLUMNS = [
  TableColumn("Bus", 35, sortable=True),
  TableColumn("Addr", 70, sortable=True),
  TableColumn("Name", 220, sortable=True, filterable=True),
  TableColumn("Freq", 55, sortable=True, align=2),
  TableColumn("Count", 65, sortable=True, align=2),
  TableColumn("Data", 200, sortable=False),
]


def _cell_text(row: MessageRow, col: int) -> str:
  if col == COL_BUS:
    return row.src
  elif col == COL_ADDR:
    return row.address_str
  elif col == COL_NAME:
    return row.name
  elif col == COL_FREQ:
    return row.freq
  elif col == COL_COUNT:
    return row.count
  elif col == COL_DATA:
    return row.dat_hex
  return ""


def _cell_color(row: MessageRow, col: int) -> rl.Color | None:
  if col == COL_DATA:
    colors = row.data.byte_colors
    if colors and colors[0] != (80, 80, 80):
      r, g, b = colors[0]
      return rl.Color(r, g, b, 255)
  return None


class MessagesView(Widget):
  """Messages table showing all CAN messages with live data."""

  def __init__(self, stream: CanStream, dbc: DBCManager,
               on_select: Callable[[MessageId], None] | None = None):
    super().__init__()
    self._stream = stream
    self._dbc = dbc
    self._on_select = on_select
    self._selected_mid: MessageId | None = None

    self._table = self._child(Table(COLUMNS, row_height=26, header_height=32, font_size=20,
                                     scroll_panel=DesktopScrollPanel()))
    self._table.set_cell_text(_cell_text)
    self._table.set_cell_color(_cell_color)
    self._table.set_row_click(self._on_row_click)

    self._rows: list[MessageRow] = []

  def _on_row_click(self, row: MessageRow) -> None:
    self._selected_mid = row.mid
    if self._on_select:
      self._on_select(row.mid)

  def update_data(self, current_msgs: dict[MessageId, MessageData]) -> None:
    rows: list[MessageRow] = []
    for mid, data in current_msgs.items():
      name = self._dbc.msg_name(mid[1]) or f"0x{mid[1]:03X}"
      rows.append(MessageRow(mid, data, name))
    self._rows = rows
    self._table.set_rows(rows)

    if self._selected_mid:
      for row in rows:
        if row.mid == self._selected_mid:
          self._table.set_selected(row)
          break

  def _render(self, rect: rl.Rectangle):
    self._table.render(rect)
