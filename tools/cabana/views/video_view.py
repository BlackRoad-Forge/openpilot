"""Video playback view synced to CAN stream time, with timeline scrubber."""
from __future__ import annotations

import threading
import numpy as np
import pyray as rl

from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.lib.application import gui_app, FontWeight, FONT_SCALE
from openpilot.tools.cabana.can_stream import CanStream
from openpilot.tools.cabana import styles

TIMELINE_H = 34
TIME_LABEL_FONT = 14


class VideoView(Widget):
  """Video frame + timeline scrubber bar. Click video = pause/play. Click/drag timeline = seek."""

  SEGMENT_SECS = 60.0
  FPS = 20.0

  def __init__(self, stream: CanStream):
    super().__init__()
    self._stream = stream
    self._texture: rl.Texture | None = None
    self._frame_width = 0
    self._frame_height = 0
    self._rgba_frame: np.ndarray | None = None
    self._frame_lock = threading.Lock()

    self._camera_paths: list[str] = []
    self._readers: dict[int, object] = {}
    self._error: str = ""
    self._route_resolved = False
    self._resolving = False

    self._decode_thread: threading.Thread | None = None
    self._requested_frame: tuple[int, int] = (-1, -1)
    self._last_displayed: tuple[int, int] = (-1, -1)

    self._dragging_timeline = False
    self._timeline_rect = rl.Rectangle(0, 0, 0, 0)
    self._video_rect = rl.Rectangle(0, 0, 0, 0)

  def _resolve_route(self):
    if self._resolving or self._route_resolved:
      return
    self._resolving = True
    def _do():
      try:
        from openpilot.tools.lib.route import Route
        paths = Route(self._stream.route).camera_paths()
        if paths:
          self._camera_paths = paths
          self._route_resolved = True
        else:
          self._error = "No camera data"
      except Exception as e:
        self._error = f"Video: {e}"
      self._resolving = False
    threading.Thread(target=_do, daemon=True).start()

  def _decode_in_background(self, seg_idx: int, frame_idx: int):
    if self._decode_thread and self._decode_thread.is_alive():
      self._requested_frame = (seg_idx, frame_idx)
      return
    if (seg_idx, frame_idx) == self._last_displayed:
      return
    self._requested_frame = (seg_idx, frame_idx)

    def _do():
      s, f = self._requested_frame
      if s not in self._readers:
        if s < 0 or s >= len(self._camera_paths):
          return
        try:
          from openpilot.tools.lib.framereader import FrameReader
          self._readers[s] = FrameReader(self._camera_paths[s], pix_fmt="rgb24")
        except Exception:
          return
      reader = self._readers[s]
      f = min(f, reader.frame_count - 1)
      if f < 0:
        return
      try:
        rgb = reader.get(f)
      except Exception:
        return
      h, w = rgb.shape[:2]
      rgba = np.empty((h, w, 4), dtype=np.uint8)
      rgba[:, :, :3] = rgb
      rgba[:, :, 3] = 255
      with self._frame_lock:
        self._rgba_frame = rgba
        self._frame_width = w
        self._frame_height = h
      self._last_displayed = (s, f)

    self._decode_thread = threading.Thread(target=_do, daemon=True)
    self._decode_thread.start()

  def _render(self, rect: rl.Rectangle):
    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height), styles.BG)
    font = gui_app.font(FontWeight.NORMAL)

    self._timeline_rect = rl.Rectangle(rect.x, rect.y + rect.height - TIMELINE_H, rect.width, TIMELINE_H)
    self._video_rect = rl.Rectangle(rect.x, rect.y, rect.width, rect.height - TIMELINE_H)

    if not self._route_resolved and not self._error and not self._resolving:
      if self._stream.loaded or self._stream.loading:
        self._resolve_route()

    self._render_video(self._video_rect, font)
    self._render_timeline(self._timeline_rect, font)

    # Timeline drag
    for ev in gui_app.mouse_events:
      if ev.left_pressed and rl.check_collision_point_rec(ev.pos, self._timeline_rect):
        self._dragging_timeline = True
        self._seek_to_x(ev.pos.x)
      elif ev.left_released:
        self._dragging_timeline = False
    if self._dragging_timeline:
      self._seek_to_x(gui_app.last_mouse_event.pos.x)

  def _render_video(self, rect: rl.Rectangle, font):
    if self._error:
      rl.draw_text_ex(font, self._error, rl.Vector2(rect.x + 8, rect.y + rect.height / 2 - 10), 16, 0, styles.TEXT_DIM)
      return
    if not self._route_resolved:
      rl.draw_text_ex(font, "Loading video...", rl.Vector2(rect.x + 8, rect.y + rect.height / 2 - 10), 16, 0, styles.TEXT_DIM)
      return

    cur = self._stream.current_sec
    seg = int(cur / self.SEGMENT_SECS)
    fidx = int((cur - seg * self.SEGMENT_SECS) * self.FPS)
    self._decode_in_background(seg, fidx)

    if self._texture is None and self._frame_width > 0:
      img = rl.gen_image_color(self._frame_width, self._frame_height, rl.BLACK)
      self._texture = rl.load_texture_from_image(img)
      rl.unload_image(img)

    with self._frame_lock:
      rgba = self._rgba_frame

    if rgba is not None and self._texture is not None:
      if self._texture.width != self._frame_width or self._texture.height != self._frame_height:
        rl.unload_texture(self._texture)
        img = rl.gen_image_color(self._frame_width, self._frame_height, rl.BLACK)
        self._texture = rl.load_texture_from_image(img)
        rl.unload_image(img)
      rl.update_texture(self._texture, rl.ffi.cast("void *", rgba.ctypes.data))
      va = self._frame_width / self._frame_height
      ra = rect.width / rect.height if rect.height > 0 else 1.0
      if va > ra:
        dh = rect.width / va
        dst = rl.Rectangle(rect.x, rect.y + (rect.height - dh) / 2, rect.width, dh)
      else:
        dw = rect.height * va
        dst = rl.Rectangle(rect.x + (rect.width - dw) / 2, rect.y, dw, rect.height)
      rl.draw_texture_pro(self._texture, rl.Rectangle(0, 0, self._frame_width, self._frame_height),
                          dst, rl.Vector2(0, 0), 0.0, rl.WHITE)
      if not self._stream.playing:
        cx, cy = dst.x + dst.width / 2, dst.y + dst.height / 2
        rl.draw_circle(int(cx), int(cy), 24, rl.Color(0, 0, 0, 100))
        rl.draw_triangle(rl.Vector2(cx - 8, cy - 12), rl.Vector2(cx - 8, cy + 12),
                         rl.Vector2(cx + 12, cy), rl.Color(255, 255, 255, 180))
    else:
      rl.draw_text_ex(font, "Loading video...", rl.Vector2(rect.x + 8, rect.y + rect.height / 2 - 10), 16, 0, styles.TEXT_DIM)

  def _render_timeline(self, rect: rl.Rectangle, font):
    rl.draw_rectangle(int(rect.x), int(rect.y), int(rect.width), int(rect.height), styles.PANEL_BG)
    rl.draw_line(int(rect.x), int(rect.y), int(rect.x + rect.width), int(rect.y), styles.BORDER)
    dur = self._stream.duration
    if dur <= 0:
      return
    pad = 8
    bx, bw, by, bh = rect.x + pad, rect.width - pad * 2, rect.y + 6, 8

    # Background — dim where not loaded, brighter where loaded
    rl.draw_rectangle_rounded(rl.Rectangle(bx, by, bw, bh), 0.5, 4, rl.Color(40, 42, 48, 255))
    if self._stream.loading and self._stream.load_frac < 1.0:
      rl.draw_rectangle_rounded(rl.Rectangle(bx, by, bw * self._stream.load_frac, bh), 0.5, 4, rl.Color(55, 58, 65, 255))
    else:
      rl.draw_rectangle_rounded(rl.Rectangle(bx, by, bw, bh), 0.5, 4, rl.Color(55, 58, 65, 255))

    # Playback position
    p = self._stream.current_sec / dur
    rl.draw_rectangle_rounded(rl.Rectangle(bx, by, bw * p, bh), 0.5, 4, styles.ACCENT)
    hx = bx + bw * p
    rl.draw_line_ex(rl.Vector2(hx, by - 2), rl.Vector2(hx, by + bh + 2), 2, rl.WHITE)
    rl.draw_circle(int(hx), int(by + bh / 2), 5, rl.WHITE)

    # Time labels
    rl.draw_text_ex(font, _fmt(self._stream.current_sec), rl.Vector2(bx, by + bh + 2), TIME_LABEL_FONT, 0, styles.TEXT)
    dt = _fmt(dur)
    tw = rl.measure_text_ex(font, dt, TIME_LABEL_FONT * FONT_SCALE, 0).x
    rl.draw_text_ex(font, dt, rl.Vector2(bx + bw - tw, by + bh + 2), TIME_LABEL_FONT, 0, styles.TEXT_DIM)

  def _seek_to_x(self, x: float):
    pad = 8
    bx = self._timeline_rect.x + pad
    bw = self._timeline_rect.width - pad * 2
    if bw > 0 and self._stream.duration > 0:
      self._stream.current_sec = max(0.0, min(1.0, (x - bx) / bw)) * self._stream.duration

  def _handle_mouse_release(self, mouse_pos) -> None:
    if rl.check_collision_point_rec(mouse_pos, self._video_rect):
      self._stream.playing = not self._stream.playing

  def __del__(self):
    if self._texture is not None:
      rl.unload_texture(self._texture)


def _fmt(s: float) -> str:
  m = int(s) // 60
  return f"{m}:{s - m * 60:05.2f}"
