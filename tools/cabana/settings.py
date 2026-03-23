"""Cabana settings with JSON persistence."""
from __future__ import annotations

import json
from pathlib import Path


SETTINGS_PATH = Path.home() / ".config" / "cabana" / "settings.json"
SESSION_PATH = Path.home() / ".config" / "cabana" / "session.json"

DEFAULTS = {
  "drag_direction": "msb_first",     # msb_first, lsb_first, always_le, always_be
  "chart_series_type": "line",       # line, step, scatter
  "chart_range": 3.0,               # seconds visible
  "chart_columns": 1,               # 1-4
  "chart_height": 200,              # pixels per chart
  "fps": 60,
  "sparkline_range": 15.0,          # seconds
  "last_dbc_path": "",
}


class Settings:
  """Singleton settings with JSON persistence."""

  _instance: Settings | None = None

  def __new__(cls) -> Settings:
    if cls._instance is None:
      cls._instance = super().__new__(cls)
      cls._instance._data = dict(DEFAULTS)
      cls._instance._load()
    return cls._instance

  def _load(self) -> None:
    if SETTINGS_PATH.exists():
      try:
        stored = json.loads(SETTINGS_PATH.read_text())
        self._data.update(stored)
      except Exception:
        pass

  def save(self) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(self._data, indent=2))

  def get(self, key: str):
    return self._data.get(key, DEFAULTS.get(key))

  def set(self, key: str, value) -> None:
    self._data[key] = value
    self.save()

  @property
  def drag_direction(self) -> str:
    return self.get("drag_direction")

  @property
  def chart_series_type(self) -> str:
    return self.get("chart_series_type")

  @property
  def chart_range(self) -> float:
    return self.get("chart_range")

  @property
  def chart_columns(self) -> int:
    return self.get("chart_columns")

  @property
  def chart_height(self) -> int:
    return self.get("chart_height")


class Session:
  """Session state (layout ratios, open tabs, etc.) with persistence."""

  def __init__(self):
    self._data: dict = {}
    self._load()

  def _load(self) -> None:
    if SESSION_PATH.exists():
      try:
        self._data = json.loads(SESSION_PATH.read_text())
      except Exception:
        pass

  def save(self) -> None:
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(json.dumps(self._data, indent=2))

  def get(self, key: str, default=None):
    return self._data.get(key, default)

  def set(self, key: str, value) -> None:
    self._data[key] = value
