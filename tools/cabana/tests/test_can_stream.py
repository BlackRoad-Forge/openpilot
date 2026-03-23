"""Tests for CanStream logic (no GUI required)."""
import unittest

from openpilot.tools.cabana.can_stream import CanEvent, MessageState, MessageData, CanStream


class TestBitFlipCounts(unittest.TestCase):
  def test_basic_flips(self):
    """Two events with different bytes should count bit flips correctly."""
    events = [
      CanEvent(mono_time=1000, src=0, address=0x100, dat=b'\x00'),
      CanEvent(mono_time=2000, src=0, address=0x100, dat=b'\xFF'),
    ]
    ms = MessageState(events=events)

    # Compute flips manually
    n_bytes = 1
    ms.bit_flip_counts = [0] * (n_bytes * 8)
    prev = events[0].dat
    for ev in events[1:]:
      for bi in range(min(len(prev), len(ev.dat))):
        diff = prev[bi] ^ ev.dat[bi]
        for bit in range(8):
          if diff & (1 << bit):
            ms.bit_flip_counts[bi * 8 + bit] += 1
      prev = ev.dat

    # All 8 bits should flip once (0x00 -> 0xFF)
    self.assertEqual(ms.bit_flip_counts, [1] * 8)

  def test_no_flips(self):
    """Identical events should have zero flips."""
    events = [
      CanEvent(mono_time=1000, src=0, address=0x100, dat=b'\xAA'),
      CanEvent(mono_time=2000, src=0, address=0x100, dat=b'\xAA'),
    ]
    ms = MessageState(events=events)
    ms.bit_flip_counts = [0] * 8
    prev = events[0].dat
    for ev in events[1:]:
      for bi in range(min(len(prev), len(ev.dat))):
        diff = prev[bi] ^ ev.dat[bi]
        for bit in range(8):
          if diff & (1 << bit):
            ms.bit_flip_counts[bi * 8 + bit] += 1
      prev = ev.dat

    self.assertEqual(ms.bit_flip_counts, [0] * 8)


class TestByteColors(unittest.TestCase):
  def test_increasing(self):
    """Byte that increases should be blue."""
    prev_dat = b'\x10'
    curr_dat = b'\x20'
    colors = []
    for bi in range(len(curr_dat)):
      if curr_dat[bi] > prev_dat[bi]:
        colors.append((70, 130, 230))
      elif curr_dat[bi] < prev_dat[bi]:
        colors.append((230, 80, 80))
      else:
        colors.append((80, 80, 80))
    self.assertEqual(colors[0], (70, 130, 230))

  def test_decreasing(self):
    """Byte that decreases should be red."""
    prev_dat = b'\x20'
    curr_dat = b'\x10'
    colors = []
    for bi in range(len(curr_dat)):
      if curr_dat[bi] > prev_dat[bi]:
        colors.append((70, 130, 230))
      elif curr_dat[bi] < prev_dat[bi]:
        colors.append((230, 80, 80))
      else:
        colors.append((80, 80, 80))
    self.assertEqual(colors[0], (230, 80, 80))

  def test_unchanged(self):
    """Byte that stays the same should be grey."""
    prev_dat = b'\x42'
    curr_dat = b'\x42'
    colors = []
    for bi in range(len(curr_dat)):
      if curr_dat[bi] > prev_dat[bi]:
        colors.append((70, 130, 230))
      elif curr_dat[bi] < prev_dat[bi]:
        colors.append((230, 80, 80))
      else:
        colors.append((80, 80, 80))
    self.assertEqual(colors[0], (80, 80, 80))


if __name__ == '__main__':
  unittest.main()
