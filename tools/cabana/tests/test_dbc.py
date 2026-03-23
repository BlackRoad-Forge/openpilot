"""Tests for DBC parsing and generation."""
import unittest

from opendbc.can.dbc import DBC, Signal
from openpilot.tools.cabana.dbc_manager import DBCManager


def _make_signal(name="TEST", start_bit=0, size=8, le=True) -> Signal:
  return Signal(name=name, start_bit=start_bit, msb=start_bit + size - 1, lsb=start_bit,
                size=size, is_signed=False, factor=1.0, offset=0.0, is_little_endian=le)


class TestDBCManager(unittest.TestCase):
  def test_add_and_retrieve_signal(self):
    dbc = DBCManager("")
    dbc.add_signal(0x100, _make_signal("MY_SIG"))

    sigs = dbc.signals(0x100)
    self.assertEqual(len(sigs), 1)
    self.assertEqual(sigs[0].name, "MY_SIG")

  def test_remove_signal(self):
    dbc = DBCManager("")
    dbc.add_signal(0x200, _make_signal("TO_REMOVE"))
    dbc.remove_signal(0x200, "TO_REMOVE")
    self.assertEqual(len(dbc.signals(0x200)), 0)

  def test_update_signal(self):
    dbc = DBCManager("")
    dbc.add_signal(0x300, _make_signal("OLD_NAME", size=4))
    dbc.update_signal(0x300, "OLD_NAME", _make_signal("NEW_NAME", size=16))

    sigs = dbc.signals(0x300)
    self.assertEqual(len(sigs), 1)
    self.assertEqual(sigs[0].name, "NEW_NAME")
    self.assertEqual(sigs[0].size, 16)

  def test_next_signal_name(self):
    dbc = DBCManager("")
    self.assertEqual(dbc.next_signal_name(0x100), "SIG_100_0")

    dbc.add_signal(0x100, _make_signal("SIG_100_0"))
    self.assertEqual(dbc.next_signal_name(0x100), "SIG_100_1")

  def test_generate_dbc_string(self):
    dbc = DBCManager("")
    dbc.add_signal(0x123, _make_signal("SPEED", start_bit=8, size=16))

    content = dbc.to_dbc_string()
    self.assertIn("BO_ 291", content)  # 0x123 = 291
    self.assertIn("SG_ SPEED", content)
    self.assertIn("8|16", content)

  def test_new_dbc_clears(self):
    dbc = DBCManager("")
    dbc.add_signal(0x100, _make_signal())
    dbc.new_dbc()
    self.assertEqual(len(dbc.signals(0x100)), 0)
    self.assertFalse(dbc.modified)

  def test_modified_flag(self):
    dbc = DBCManager("")
    self.assertFalse(dbc.modified)
    dbc.add_signal(0x100, _make_signal())
    self.assertTrue(dbc.modified)

  def test_decode_signal(self):
    dbc = DBCManager("")
    sig = _make_signal("VAL", start_bit=0, size=8)
    sig = Signal(name="VAL", start_bit=0, msb=7, lsb=0, size=8,
                 is_signed=False, factor=0.5, offset=10.0, is_little_endian=True)
    dbc.add_signal(0x100, sig)

    # dat[0] = 100, raw = 100, physical = 100 * 0.5 + 10 = 60
    val = dbc.decode_signal(b'\x64\x00\x00\x00\x00\x00\x00\x00', sig)
    self.assertAlmostEqual(val, 60.0)


class TestParseOpendbc(unittest.TestCase):
  def test_load_known_dbc(self):
    """Test that at least one known DBC loads without error."""
    try:
      dbc = DBC("toyota_new_mc_pt_generated")
      self.assertGreater(len(dbc.msgs), 0)
    except FileNotFoundError:
      self.skipTest("opendbc DBC files not available")


if __name__ == '__main__':
  unittest.main()
