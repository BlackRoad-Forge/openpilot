"""Tests for undo/redo command stack."""
import unittest

from opendbc.can.dbc import Signal
from openpilot.tools.cabana.dbc_manager import DBCManager
from openpilot.tools.cabana.commands import UndoStack, AddSignalCommand, RemoveSignalCommand, EditSignalCommand


def _make_signal(name="TEST_SIG", start_bit=0, size=8) -> Signal:
  return Signal(name=name, start_bit=start_bit, msb=start_bit + size - 1, lsb=start_bit,
                size=size, is_signed=False, factor=1.0, offset=0.0, is_little_endian=True)


class TestUndoStack(unittest.TestCase):
  def setUp(self):
    self.dbc = DBCManager("")
    self.stack = UndoStack()

  def test_add_signal_undo_redo(self):
    sig = _make_signal("SIG_A")
    cmd = AddSignalCommand(self.dbc, 0x100, sig)
    self.stack.push(cmd)

    sigs = self.dbc.signals(0x100)
    self.assertEqual(len(sigs), 1)
    self.assertEqual(sigs[0].name, "SIG_A")

    self.stack.undo()
    self.assertEqual(len(self.dbc.signals(0x100)), 0)

    self.stack.redo()
    self.assertEqual(len(self.dbc.signals(0x100)), 1)

  def test_remove_signal_undo(self):
    sig = _make_signal("SIG_B")
    self.dbc.add_signal(0x200, sig)

    cmd = RemoveSignalCommand(self.dbc, 0x200, sig)
    self.stack.push(cmd)
    self.assertEqual(len(self.dbc.signals(0x200)), 0)

    self.stack.undo()
    sigs = self.dbc.signals(0x200)
    self.assertEqual(len(sigs), 1)
    self.assertEqual(sigs[0].name, "SIG_B")

  def test_edit_signal_undo(self):
    sig = _make_signal("SIG_C", size=4)
    self.dbc.add_signal(0x300, sig)

    new_sig = _make_signal("SIG_C", size=16)
    cmd = EditSignalCommand(self.dbc, 0x300, sig, new_sig)
    self.stack.push(cmd)

    sigs = self.dbc.signals(0x300)
    self.assertEqual(sigs[0].size, 16)

    self.stack.undo()
    sigs = self.dbc.signals(0x300)
    self.assertEqual(sigs[0].size, 4)

  def test_can_undo_redo(self):
    self.assertFalse(self.stack.can_undo)
    self.assertFalse(self.stack.can_redo)

    self.stack.push(AddSignalCommand(self.dbc, 0x100, _make_signal()))
    self.assertTrue(self.stack.can_undo)
    self.assertFalse(self.stack.can_redo)

    self.stack.undo()
    self.assertFalse(self.stack.can_undo)
    self.assertTrue(self.stack.can_redo)

  def test_push_clears_redo(self):
    self.stack.push(AddSignalCommand(self.dbc, 0x100, _make_signal("A")))
    self.stack.undo()
    self.assertTrue(self.stack.can_redo)

    self.stack.push(AddSignalCommand(self.dbc, 0x100, _make_signal("B")))
    self.assertFalse(self.stack.can_redo)

  def test_clear(self):
    self.stack.push(AddSignalCommand(self.dbc, 0x100, _make_signal()))
    self.stack.clear()
    self.assertFalse(self.stack.can_undo)
    self.assertFalse(self.stack.can_redo)


if __name__ == '__main__':
  unittest.main()
