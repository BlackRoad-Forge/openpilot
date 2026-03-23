"""UI rendering smoke tests for cabana views."""
import unittest

import pyray as rl
rl.set_config_flags(rl.ConfigFlags.FLAG_WINDOW_HIDDEN)

from openpilot.system.ui.lib.application import gui_app
from openpilot.tools.cabana.can_stream import CanStream, CanEvent, MessageState, MessageData, MessageId
from openpilot.tools.cabana.dbc_manager import DBCManager
from openpilot.tools.cabana.commands import UndoStack


class MockStream:
  """Minimal mock of CanStream for UI tests (no background thread)."""

  def __init__(self):
    self.route = "mock/route"
    self.fingerprint = "MOCK_CAR"
    self.dbc_name = ""
    self._loaded = True
    self._loading = False
    self._load_progress = ""
    self._playing = False
    self._speed = 1.0
    self._current_sec = 0.0
    self._time_range = (0.0, 10.0)
    self._messages = {
      (0, 0x100): MessageState(events=[
        CanEvent(mono_time=int(i * 1e8), src=0, address=0x100, dat=bytes([i % 256] * 8))
        for i in range(100)
      ]),
    }

  @property
  def loaded(self): return self._loaded
  @property
  def loading(self): return self._loading
  @property
  def load_progress(self): return self._load_progress
  @property
  def duration(self): return self._time_range[1] - self._time_range[0]
  @property
  def current_sec(self): return self._current_sec
  @current_sec.setter
  def current_sec(self, v): self._current_sec = v
  @property
  def playing(self): return self._playing
  @playing.setter
  def playing(self, v): self._playing = v
  @property
  def speed(self): return self._speed
  @speed.setter
  def speed(self, v): self._speed = v
  @property
  def time_range(self): return self._time_range
  @property
  def message_ids(self): return list(self._messages.keys())

  def tick(self, dt): pass

  def current_messages(self):
    return {
      (0, 0x100): MessageData(
        address=0x100, src=0, dat=b'\x42' * 8, count=50, freq=100.0,
        byte_colors=[(80, 80, 80)] * 8, name="TEST_MSG"
      )
    }

  def get_events(self, mid):
    ms = self._messages.get(mid)
    return ms.events if ms else []

  def get_bit_flip_counts(self, mid):
    ms = self._messages.get(mid)
    return ms.bit_flip_counts if ms else []


class TestCabanaUISmoke(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    gui_app._width = 800
    gui_app._height = 600
    gui_app._scale = 1.0
    gui_app._scaled_width = 800
    gui_app._scaled_height = 600
    gui_app.init_window("test-cabana-ui", fps=60)

  @classmethod
  def tearDownClass(cls):
    rl.close_window()

  def _render_frames(self, widget, n=5):
    rect = rl.Rectangle(0, 0, 800, 600)
    for _ in range(n):
      rl.begin_drawing()
      rl.clear_background(rl.BLACK)
      widget.render(rect)
      rl.end_drawing()

  def test_messages_view_renders(self):
    from openpilot.tools.cabana.views.messages_view import MessagesView
    stream = MockStream()
    dbc = DBCManager("")
    view = MessagesView(stream, dbc)
    view.update_data(stream.current_messages())
    self._render_frames(view)

  def test_binary_view_renders(self):
    from openpilot.tools.cabana.views.binary_view import BinaryView
    stream = MockStream()
    dbc = DBCManager("")
    undo = UndoStack()
    view = BinaryView(stream, dbc, undo)
    view.set_message((0, 0x100), stream.current_messages()[(0, 0x100)])
    self._render_frames(view)

  def test_signal_view_renders(self):
    from openpilot.tools.cabana.views.signal_view import SignalView
    stream = MockStream()
    dbc = DBCManager("")
    undo = UndoStack()
    view = SignalView(stream, dbc, undo)
    self._render_frames(view)

  def test_toolbar_renders(self):
    from openpilot.tools.cabana.views.toolbar_view import ToolbarView
    stream = MockStream()
    view = ToolbarView(stream)
    self._render_frames(view)

  def test_charts_view_renders(self):
    from openpilot.tools.cabana.views.charts_view import ChartsView
    stream = MockStream()
    dbc = DBCManager("")
    view = ChartsView(stream, dbc)
    self._render_frames(view)

  def test_history_log_renders(self):
    from openpilot.tools.cabana.views.history_log_view import HistoryLogView
    stream = MockStream()
    dbc = DBCManager("")
    view = HistoryLogView(stream, dbc)
    view.set_message((0, 0x100))
    self._render_frames(view)


if __name__ == '__main__':
  unittest.main()
