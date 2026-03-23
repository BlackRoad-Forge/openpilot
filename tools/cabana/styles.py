"""Qt cabana dark theme colors and shared constants."""
from __future__ import annotations

import pyray as rl

# Background colors (neutral greys matching Qt dark theme palette)
BG = rl.Color(45, 45, 45, 255)            # QPalette::Window (~#2d2d2d)
PANEL_BG = rl.Color(53, 53, 53, 255)      # QPalette::Base (~#353535)
HEADER_BG = rl.Color(53, 53, 53, 255)
SELECTED_BG = rl.Color(42, 130, 218, 255) # QPalette::Highlight
HOVER_BG = rl.Color(60, 60, 60, 255)      # row hover
ROW_BG = rl.Color(45, 45, 45, 255)        # same as BG
ROW_ALT_BG = rl.Color(50, 50, 50, 255)    # QPalette::AlternateBase

# Text colors
TEXT = rl.Color(208, 208, 208, 255)        # QPalette::Text
TEXT_DIM = rl.Color(128, 128, 128, 255)
TEXT_MUTED = rl.Color(85, 85, 85, 255)
ACCENT = rl.Color(42, 130, 218, 255)      # QPalette::Highlight

# Border / grid
BORDER = rl.Color(60, 60, 60, 255)
GRID = rl.Color(58, 58, 58, 255)

# Binary view heatmap
HEATMAP_RED = rl.Color(200, 60, 60, 255)

# Signal colors (matching Qt cabana)
SIGNAL_COLORS = [
  rl.Color(255, 201, 14, 255),   # yellow
  rl.Color(41, 198, 218, 255),   # cyan
  rl.Color(126, 87, 194, 255),   # purple
  rl.Color(253, 121, 168, 255),  # pink
  rl.Color(76, 175, 80, 255),    # green
  rl.Color(255, 138, 101, 255),  # orange
  rl.Color(100, 181, 246, 255),  # light blue
  rl.Color(255, 238, 88, 255),   # light yellow
]

# Chart colors
CHART_COLORS = [
  rl.Color(255, 100, 100, 255),
  rl.Color(100, 200, 255, 255),
  rl.Color(100, 255, 100, 255),
  rl.Color(255, 255, 100, 255),
  rl.Color(255, 150, 255, 255),
  rl.Color(150, 255, 255, 255),
]

# Byte change colors
BYTE_INCREASING = (70, 130, 230)   # blue
BYTE_DECREASING = (230, 80, 80)    # red
BYTE_UNCHANGED = (80, 80, 80)      # grey

# Drag highlight
DRAG_HIGHLIGHT = rl.Color(100, 160, 255, 100)

# Layout constants
MENU_BAR_H = 26
TOOLBAR_H = 36
TAB_BAR_H = 28
FONT_SIZE = 22
SMALL_FONT = 18
PAD = 10
