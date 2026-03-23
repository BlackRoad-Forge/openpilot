from __future__ import annotations

import csv
import copy
from pathlib import Path
from typing import TYPE_CHECKING

from opendbc.can.dbc import DBC, Signal, Msg
from opendbc.can.parser import get_raw_value

if TYPE_CHECKING:
  from openpilot.tools.cabana.can_stream import CanStream


class DBCManager:
  """Wraps opendbc DBC with overlay-based mutation for signal editing."""

  def __init__(self, dbc_name: str = ""):
    self._dbc: DBC | None = None
    self._dbc_name = dbc_name
    self._save_path: str = ""
    self._modified = False

    # Overlay: stores added/modified signals per address
    # Key: address, Value: dict of signal_name -> Signal
    self._overlay: dict[int, dict[str, Signal]] = {}
    # Signals removed from base DBC
    self._removed: dict[int, set[str]] = {}

    if dbc_name:
      try:
        self._dbc = DBC(dbc_name)
        print(f"Loaded DBC: {dbc_name} ({len(self._dbc.msgs)} messages)")
      except FileNotFoundError:
        print(f"DBC not found: {dbc_name}")

  @property
  def loaded(self) -> bool:
    return self._dbc is not None or bool(self._overlay)

  @property
  def dbc_name(self) -> str:
    return self._dbc_name

  @property
  def modified(self) -> bool:
    return self._modified

  @property
  def save_path(self) -> str:
    return self._save_path

  def msg(self, address: int) -> Msg | None:
    if self._dbc is None:
      return None
    return self._dbc.msgs.get(address)

  def msg_name(self, address: int) -> str:
    m = self.msg(address)
    return m.name if m else ""

  def signals(self, address: int) -> list[Signal]:
    """Get merged signals: base DBC + overlay - removed."""
    result: dict[str, Signal] = {}

    # Base signals
    if self._dbc:
      m = self._dbc.msgs.get(address)
      if m:
        removed = self._removed.get(address, set())
        for name, sig in m.sigs.items():
          if name not in removed:
            result[name] = sig

    # Overlay signals (override base)
    if address in self._overlay:
      for name, sig in self._overlay[address].items():
        result[name] = sig

    return list(result.values())

  def add_signal(self, address: int, signal: Signal) -> None:
    """Add a signal to the overlay."""
    if address not in self._overlay:
      self._overlay[address] = {}
    self._overlay[address][signal.name] = signal
    self._modified = True

  def remove_signal(self, address: int, name: str) -> None:
    """Remove a signal (from overlay or mark base signal as removed)."""
    # Remove from overlay if present
    if address in self._overlay and name in self._overlay[address]:
      del self._overlay[address][name]
      if not self._overlay[address]:
        del self._overlay[address]
    else:
      # Mark base signal as removed
      if address not in self._removed:
        self._removed[address] = set()
      self._removed[address].add(name)
    self._modified = True

  def update_signal(self, address: int, old_name: str, new_signal: Signal) -> None:
    """Update a signal. If name changed, remove old and add new."""
    if old_name != new_signal.name:
      self.remove_signal(address, old_name)
    self.add_signal(address, new_signal)

  def get_signal(self, address: int, name: str) -> Signal | None:
    """Get a specific signal by name."""
    for sig in self.signals(address):
      if sig.name == name:
        return sig
    return None

  def next_signal_name(self, address: int) -> str:
    """Generate next auto-name for a new signal."""
    existing = {s.name for s in self.signals(address)}
    for i in range(256):
      name = f"SIG_{address:03X}_{i}"
      if name not in existing:
        return name
    return f"SIG_{address:03X}_new"

  def decode_signal(self, dat: bytes, sig: Signal) -> float:
    """Decode a signal from CAN message data, returning physical value."""
    raw = get_raw_value(dat, sig)
    if sig.is_signed:
      raw -= ((raw >> (sig.size - 1)) & 0x1) * (1 << sig.size)
    return raw * sig.factor + sig.offset

  def decode_all(self, address: int, dat: bytes) -> dict[str, float]:
    """Decode all signals for a message, returning {name: value}."""
    result: dict[str, float] = {}
    for sig in self.signals(address):
      result[sig.name] = self.decode_signal(dat, sig)
    return result

  def new_dbc(self) -> None:
    """Reset to empty state."""
    self._dbc = None
    self._dbc_name = ""
    self._overlay.clear()
    self._removed.clear()
    self._modified = False
    self._save_path = ""

  def to_dbc_string(self) -> str:
    """Generate DBC file content from base + overlay."""
    lines = ['VERSION ""', '', 'NS_ :', '', 'BS_:', '', 'BU_:', '', '']

    # Collect all messages with their signals
    all_addresses: set[int] = set()
    if self._dbc:
      all_addresses.update(self._dbc.msgs.keys())
    all_addresses.update(self._overlay.keys())

    for addr in sorted(all_addresses):
      msg = self.msg(addr)
      msg_name = msg.name if msg else f"MSG_{addr:03X}"
      msg_size = msg.size if msg else 8
      signals = self.signals(addr)

      lines.append(f'BO_ {addr} {msg_name}: {msg_size} XXX')
      for sig in signals:
        endian = '1' if sig.is_little_endian else '0'
        signed = '-' if sig.is_signed else '+'
        lines.append(f' SG_ {sig.name} : {sig.start_bit}|{sig.size}@{endian}{signed}'
                      f' ({sig.factor},{sig.offset})'
                      f' [0|0]'
                      f' "" XXX')
      lines.append('')

    return '\n'.join(lines)

  def save(self, path: str) -> None:
    """Save DBC to file."""
    content = self.to_dbc_string()
    Path(path).write_text(content)
    self._save_path = path
    self._modified = False
    print(f"Saved DBC to {path}")

  def load(self, path: str) -> None:
    """Load DBC from file path."""
    self._overlay.clear()
    self._removed.clear()
    self._dbc_name = Path(path).stem
    self._save_path = path
    try:
      self._dbc = DBC(path)
      self._modified = False
      print(f"Loaded DBC: {path} ({len(self._dbc.msgs)} messages)")
    except Exception as e:
      print(f"Error loading DBC: {e}")

  def export_csv(self, path: str, stream: 'CanStream') -> None:
    """Export decoded signal data to CSV."""
    with open(path, 'w', newline='') as f:
      writer = csv.writer(f)

      # Header
      header = ['time_ns', 'bus', 'address', 'address_hex']
      all_signals: list[tuple[int, int, Signal]] = []  # (src, addr, sig)
      for mid in stream.message_ids:
        src, addr = mid
        for sig in self.signals(addr):
          all_signals.append((src, addr, sig))
          header.append(f"{addr:03X}_{sig.name}")
      writer.writerow(header)

      # Data rows - iterate through time
      t0 = stream.time_range[0]
      for mid in stream.message_ids:
        events = stream.get_events(mid)
        src, addr = mid
        sigs = self.signals(addr)
        if not sigs:
          continue
        for ev in events:
          row = [ev.mono_time, ev.src, ev.address, f"0x{ev.address:03X}"]
          for sig in sigs:
            try:
              val = self.decode_signal(ev.dat, sig)
              row.append(f"{val:.6g}")
            except Exception:
              row.append("")
          writer.writerow(row)

    print(f"Exported CSV to {path}")
