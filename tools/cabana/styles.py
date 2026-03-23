"""Qt cabana dark theme colors and shared constants."""
from __future__ import annotations

import pyray as rl

# Background colors (from Qt cabana dark theme)
BG = rl.Color(27, 29, 35, 255)            # #1B1D23 - main background
PANEL_BG = rl.Color(37, 40, 48, 255)      # #252830 - panel/header background
HEADER_BG = rl.Color(37, 40, 48, 255)     # #252830
SELECTED_BG = rl.Color(49, 66, 105, 255)  # #314269 - selected row
HOVER_BG = rl.Color(40, 43, 55, 255)      # row hover
ROW_BG = rl.Color(27, 29, 35, 255)        # same as BG
ROW_ALT_BG = rl.Color(30, 32, 40, 255)    # alternating row

# Text colors
TEXT = rl.Color(220, 220, 220, 255)
TEXT_DIM = rl.Color(140, 140, 140, 255)
TEXT_MUTED = rl.Color(100, 100, 100, 255)
ACCENT = rl.Color(100, 160, 255, 255)     # blue accent

# Border / grid
BORDER = rl.Color(55, 58, 68, 255)
GRID = rl.Color(45, 48, 58, 255)

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
TOOLBAR_H = 60
TAB_BAR_H = 28
FONT_SIZE = 22
SMALL_FONT = 18
PAD = 10
