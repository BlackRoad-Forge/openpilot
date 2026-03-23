"""Undo/redo command stack for DBC signal editing."""
from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from opendbc.can.dbc import Signal
from openpilot.tools.cabana.dbc_manager import DBCManager


class Command(ABC):
  """Base command for undo/redo."""
  description: str = ""

  @abstractmethod
  def execute(self) -> None: ...

  @abstractmethod
  def undo(self) -> None: ...


class AddSignalCommand(Command):
  def __init__(self, dbc: DBCManager, address: int, signal: Signal):
    self._dbc = dbc
    self._address = address
    self._signal = copy.deepcopy(signal)
    self.description = f"Add signal {signal.name}"

  def execute(self) -> None:
    self._dbc.add_signal(self._address, copy.deepcopy(self._signal))

  def undo(self) -> None:
    self._dbc.remove_signal(self._address, self._signal.name)


class RemoveSignalCommand(Command):
  def __init__(self, dbc: DBCManager, address: int, signal: Signal):
    self._dbc = dbc
    self._address = address
    self._signal = copy.deepcopy(signal)
    self.description = f"Remove signal {signal.name}"

  def execute(self) -> None:
    self._dbc.remove_signal(self._address, self._signal.name)

  def undo(self) -> None:
    self._dbc.add_signal(self._address, copy.deepcopy(self._signal))


class EditSignalCommand(Command):
  def __init__(self, dbc: DBCManager, address: int, old_signal: Signal, new_signal: Signal):
    self._dbc = dbc
    self._address = address
    self._old = copy.deepcopy(old_signal)
    self._new = copy.deepcopy(new_signal)
    self.description = f"Edit signal {old_signal.name}"

  def execute(self) -> None:
    self._dbc.update_signal(self._address, self._old.name, copy.deepcopy(self._new))

  def undo(self) -> None:
    self._dbc.update_signal(self._address, self._new.name, copy.deepcopy(self._old))


class UndoStack:
  """Simple undo/redo stack."""

  def __init__(self):
    self._commands: list[Command] = []
    self._index: int = -1  # points to last executed command
    self._on_change: list[callable] = []

  def push(self, cmd: Command) -> None:
    """Execute command and push onto stack, clearing any redo history."""
    # Truncate redo history
    self._commands = self._commands[:self._index + 1]
    cmd.execute()
    self._commands.append(cmd)
    self._index += 1
    self._notify()

  def undo(self) -> None:
    if not self.can_undo:
      return
    self._commands[self._index].undo()
    self._index -= 1
    self._notify()

  def redo(self) -> None:
    if not self.can_redo:
      return
    self._index += 1
    self._commands[self._index].execute()
    self._notify()

  @property
  def can_undo(self) -> bool:
    return self._index >= 0

  @property
  def can_redo(self) -> bool:
    return self._index < len(self._commands) - 1

  @property
  def undo_text(self) -> str:
    if self.can_undo:
      return self._commands[self._index].description
    return ""

  @property
  def redo_text(self) -> str:
    if self.can_redo:
      return self._commands[self._index + 1].description
    return ""

  def clear(self) -> None:
    self._commands.clear()
    self._index = -1
    self._notify()

  def add_listener(self, cb) -> None:
    self._on_change.append(cb)

  def _notify(self) -> None:
    for cb in self._on_change:
      cb()
