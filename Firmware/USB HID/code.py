"""
Switch Interface for Adafruit Feather ESP32-S3 Rev TFT
USB HID Version — Triple Mode with Onboard Mode Selection
Uses built-in 1.14" 240x135 color TFT display
Compatible with CircuitPython

EXTERNAL SWITCHES (3.5mm jacks, wired to GND, Pull.UP active LOW):
  A1 → Navigate switch
  A2 → Select / Single switch

ONBOARD BUTTONS / EXTERNAL SWITCHES (mode selection):
  D0 (onboard)             → Direct Switch Mode (Mode 0)
  D1 (onboard) or A2       → Enter Single-Switch Scanning Mode
  D2 (onboard) or A1       → Enter Two-Switch Mode

  EXTERNAL SWITCHES at the mode-select screen:
    Single-click A2 (select) → Single-Switch Scanning Mode
    Single-click A1 (nav)    → Two-Switch Mode
    Double-click A1 or A2    → Direct Switch Mode (Mode 0)
  (Note: a single external-switch click waits one DOUBLE_CLICK_WINDOW before
   committing, so a second click can be detected for Mode 0.)

─── DIRECT SWITCH MODE (Mode 0) ───────────────────────
  A1 TAP    : Send Switch 1 action (default: Enter)
  A2 TAP    : Send Switch 2 action (default: Tab)
  A1/A2 HOLD (≥ SWITCH_HOLD_EXIT_SECS) : Back to Mode Select
  D0        : Back to Mode Select
  (Customisable via config.py — supports keyboard, mouse & media)

─── SINGLE-SWITCH MODE ─────────────────────────────────────
  A2 SHORT PRESS  (≤ MAX_SHORT_PRESS_SECS)  : Select & send current item
  A2 HOLD         (≥ HOLD_TO_SCAN_SECS)     : Start auto-scanning
  A2 PRESS during scan                      : Select & send, stop scanning
  D0                                        : Back to Mode Select

─── TWO-SWITCH MODE ────────────────────────────────────────
  A1  : Advance to next item
  A2  : Select & send current item
  D0  : Back to Mode Select

(D0 is dual-purpose: at the mode-select screen it jumps straight into
 Mode 0; from inside ANY active mode it returns to the mode-select screen.)

─── SUBMENUS (Modes 1 & 2 only) ─────────────────────────────
  Any KEYCODES entry can be a SUBMENU ENTRY POINT (it has a
  "submenu" list). Selecting it sends its own keycode first
  (e.g. to open an on-screen menu on the host) — unless "kc"
  is empty, which marks a pure organisational folder with no
  keystroke of its own — then the scan/nav list switches to
  just that entry's child items. If the entry's "auto_exit"
  is True, picking a child item automatically returns to the
  parent list afterwards. If False, a synthetic "◂ back" item
  is added to the child list so several child items can be
  picked in a row before manually returning.
"""

import time
import board
import digitalio
import displayio
import terminalio
try:
    from fourwire import FourWire
except ImportError:
    from displayio import FourWire
import adafruit_st7789
from adafruit_display_text import label
import usb_hid
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode

# Optional mouse / consumer control — only used by Mode 0 (Direct Switch).
# Imported here (not lazily) so config.py can reference Mouse /
# ConsumerControlCode directly when defining SWITCH1_ACTION / SWITCH2_ACTION.
try:
    from adafruit_hid.mouse import Mouse
    _mouse_available = True
except ImportError:
    _mouse_available = False

try:
    from adafruit_hid.consumer_control import ConsumerControl
    from adafruit_hid.consumer_control_code import ConsumerControlCode
    _consumer_available = True
except ImportError:
    _consumer_available = False

print("Starting Switch Interface...")

# ===============================================
# ===== USER CONFIGURABLE VARIABLES =====
# ===============================================

# --- Single-Switch Mode ---
# How long (seconds) A2 must be held to begin auto-scanning
HOLD_TO_SCAN_SECS = 2.0

# How fast (seconds) the scanner advances to the next item
SCAN_INTERVAL_SECS = 1

# Maximum press duration (seconds) considered a "short press"
MAX_SHORT_PRESS_SECS = 0.5

# --- Two-Switch Mode ---
# Debounce delay (seconds) after a nav or select press
DEBOUNCE_TIME = 0.1

# --- Double-click to enter Mode 0 ---
# Maximum gap (seconds) between two clicks to count as a double-click
DOUBLE_CLICK_WINDOW = 0.4

# --- External switch hold to exit Mode 0 ---
# How long (seconds) an external switch (A1 or A2) must be held in Mode 0
# to return to the mode-select menu.
SWITCH_HOLD_EXIT_SECS = 1.5

# ─── MODE 0: DIRECT SWITCH ACTIONS ─────────────────────────────────────────
#
# Each action is a dict with the key "type" and type-specific fields:
#
#   Keyboard key press:
#     {"type": "key", "keys": [Keycode.ENTER]}
#     {"type": "key", "keys": [Keycode.LEFT_CONTROL, Keycode.C]}
#
#   Mouse button click:
#     {"type": "mouse_click", "button": Mouse.LEFT_BUTTON}   (requires adafruit_hid.mouse)
#
#   Mouse scroll:
#     {"type": "mouse_scroll", "x": 0, "y": 1}   (positive y = scroll up)
#
#   Mouse move:
#     {"type": "mouse_move", "x": 10, "y": 0}
#
#   Media / consumer control:
#     {"type": "media", "code": ConsumerControlCode.PLAY_PAUSE}
#     {"type": "media", "code": ConsumerControlCode.VOLUME_INCREMENT}
#     {"type": "media", "code": ConsumerControlCode.VOLUME_DECREMENT}
#     {"type": "media", "code": ConsumerControlCode.MUTE}
#     {"type": "media", "code": ConsumerControlCode.SCAN_NEXT_TRACK}
#     {"type": "media", "code": ConsumerControlCode.SCAN_PREVIOUS_TRACK}

SWITCH1_ACTION = {"type": "key", "keys": [Keycode.ENTER]}   # A1 press
SWITCH2_ACTION = {"type": "key", "keys": [Keycode.TAB]}     # A2 press

SWITCH1_LABEL  = "Enter"   # Shown on TFT
SWITCH2_LABEL  = "Tab"     # Shown on TFT
SWITCH1_SYMBOL = "ENT"     # Short TFT symbol (1-3 ASCII chars)
SWITCH2_SYMBOL = "TAB"     # Short TFT symbol (1-3 ASCII chars)
# NOTE: the onboard TFT uses terminalio.FONT (a built-in bitmap font) which
# only renders basic ASCII / Latin-1 characters. Emoji and most symbol glyphs
# (e.g. ⏎ ⇥ → ▶) will appear blank. Stick to plain letters/numbers/punctuation.

# ===============================================
# ===== DISPLAY INITIALIZATION =====
# ===============================================

print("\nInitializing display...")
displayio.release_displays()

spi = board.SPI()
tft_cs = board.TFT_CS
tft_dc = board.TFT_DC
tft_reset = board.TFT_RESET
tft_backlight = board.TFT_BACKLIGHT

display_bus = FourWire(
    spi,
    command=tft_dc,
    chip_select=tft_cs,
    reset=tft_reset,
    baudrate=24000000
)

display = adafruit_st7789.ST7789(
    display_bus,
    width=240,
    height=135,
    rowstart=40,
    colstart=52,
    rotation=270,
    bgr=True
)

backlight = digitalio.DigitalInOut(tft_backlight)
backlight.direction = digitalio.Direction.OUTPUT
backlight.value = True

print("Display initialized!")

# ===============================================
# ===== LED SETUP =====
# ===============================================

led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT

# ===============================================
# ===== EXTERNAL SWITCH PINS (A1, A2) =====
# Pull.UP — switch wired between pin and GND.
# Pressed = False (LOW).
# ===============================================

switch_nav = digitalio.DigitalInOut(board.A1)
switch_nav.direction = digitalio.Direction.INPUT
switch_nav.pull = digitalio.Pull.UP

switch_select = digitalio.DigitalInOut(board.A2)
switch_select.direction = digitalio.Direction.INPUT
switch_select.pull = digitalio.Pull.UP

def nav_pressed():
    return not switch_nav.value       # Active LOW

def select_pressed():
    return not switch_select.value    # Active LOW

# ===============================================
# ===== ONBOARD BUTTONS (D0, D1, D2) =====
# D0: Pull.UP  → active LOW
# D1: Pull.DOWN → active HIGH
# D2: Pull.DOWN → active HIGH
# ===============================================

button0 = digitalio.DigitalInOut(board.D0)
button0.switch_to_input(pull=digitalio.Pull.UP)

button1 = digitalio.DigitalInOut(board.D1)
button1.switch_to_input(pull=digitalio.Pull.DOWN)

button2 = digitalio.DigitalInOut(board.D2)
button2.switch_to_input(pull=digitalio.Pull.DOWN)

def d0_pressed():
    return not button0.value   # Active LOW

def d1_pressed():
    return button1.value       # Active HIGH

def d2_pressed():
    return button2.value       # Active HIGH

# ===============================================
# ===== USB HID SETUP =====
# ===============================================

time.sleep(1)
keyboard = Keyboard(usb_hid.devices)

_mouse = None
_consumer = None

def get_mouse():
    global _mouse
    if _mouse is None and _mouse_available:
        try:
            _mouse = Mouse(usb_hid.devices)
        except Exception as e:
            print(f"Mouse init failed: {e}")
    return _mouse

def get_consumer():
    global _consumer
    if _consumer is None and _consumer_available:
        try:
            _consumer = ConsumerControl(usb_hid.devices)
        except Exception as e:
            print(f"ConsumerControl init failed: {e}")
    return _consumer

# ===============================================
# ===== KEYCODES AND SYMBOL DEFINITIONS =====
# ===============================================
#
# Each entry in KEYCODES is normally a dict:
#   {
#       "label":  str             human-readable name (shown in serial log)
#       "kc":     [Keycode, ...]   keys sent together when selected
#       "symbol": str              1-4 char glyph shown on the TFT
#
#       "submenu": [ ... ]         OPTIONAL. Present only on a SUBMENU ENTRY
#                                  POINT. A list of child entries (same
#                                  shape as this one, minus "submenu").
#       "auto_exit": bool          OPTIONAL, only meaningful alongside
#                                  "submenu". True = return to the parent
#                                  list right after a child is picked.
#                                  False = stay in the submenu (a "◂ back"
#                                  item is added automatically) so several
#                                  child items can be picked in a row.
#   }
#
# Legacy format is still accepted for old config.py files: a plain
# (label, [Keycode, ...]) tuple, with its symbol looked up from the
# KEY_SYMBOLS dict below. New config.py files generated by the Shortcut
# Configurator always use the dict format above.

KEYCODES = [
    {"label": "tab",         "kc": [Keycode.TAB],         "symbol": ">"},
    {"label": "arrow right", "kc": [Keycode.RIGHT_ARROW], "symbol": "R"},
    {"label": "arrow down",  "kc": [Keycode.DOWN_ARROW],  "symbol": "D"},
    {"label": "enter",       "kc": [Keycode.ENTER],       "symbol": "e"},
    {"label": "arrow left",  "kc": [Keycode.LEFT_ARROW],  "symbol": "L"},
    {"label": "arrow up",    "kc": [Keycode.UP_ARROW],    "symbol": "U"},
    {"label": "delete",      "kc": [Keycode.DELETE],      "symbol": "x"},
    {"label": "escape",      "kc": [Keycode.ESCAPE],      "symbol": "ESC"},
    {"label": "w",           "kc": [Keycode.W],           "symbol": "W"},
    {"label": "t",           "kc": [Keycode.T],           "symbol": "T"},
    {
        "label": "ctrl+b", "kc": [Keycode.LEFT_CONTROL, Keycode.B], "symbol": "B",
        "auto_exit": True,
        "submenu": [
            {"label": "0", "kc": [Keycode.ZERO],  "symbol": "0"},
            {"label": "1", "kc": [Keycode.ONE],   "symbol": "1"},
            {"label": "2", "kc": [Keycode.TWO],   "symbol": "2"},
            {"label": "3", "kc": [Keycode.THREE], "symbol": "3"},
            {"label": "4", "kc": [Keycode.FOUR],  "symbol": "4"},
            {"label": "5", "kc": [Keycode.FIVE],  "symbol": "5"},
        ],
    },
    {
        # The on-screen menu ctrl+enter opens does not respond to direct
        # letter/ctrl-combo shortcuts — it must be navigated with the arrow
        # keys and confirmed with Enter. No auto_exit: arrow down/up as many
        # times as needed, then Enter to confirm, then "back" to return.
        "label": "ctrl+enter", "kc": [Keycode.LEFT_CONTROL, Keycode.ENTER], "symbol": "ENT",
        "auto_exit": False,
        "submenu": [
            {"label": "arrow down", "kc": [Keycode.DOWN_ARROW], "symbol": "D"},
            {"label": "enter",      "kc": [Keycode.ENTER],      "symbol": "e"},
            {"label": "arrow up",   "kc": [Keycode.UP_ARROW],   "symbol": "U"},
        ],
    },
    {
        # A pure organisational folder: "kc" is empty, so selecting the
        # entry point sends no keystroke of its own — it just opens the
        # submenu below. Each child still sends its own real shortcut.
        "label": "Block Actions", "kc": [], "symbol": "BLK",
        "auto_exit": True,
        "submenu": [
            {"label": "cut",       "kc": [Keycode.LEFT_CONTROL, Keycode.X],                    "symbol": "X"},
            {"label": "copy",      "kc": [Keycode.LEFT_CONTROL, Keycode.C],                    "symbol": "C"},
            {"label": "paste",     "kc": [Keycode.LEFT_CONTROL, Keycode.V],                    "symbol": "V"},
            {"label": "duplicate", "kc": [Keycode.D],                                          "symbol": "D"},
            {"label": "delete",    "kc": [Keycode.BACKSPACE],                                  "symbol": "BS"},
            {"label": "undo",      "kc": [Keycode.LEFT_CONTROL, Keycode.Z],                    "symbol": "U"},
            {"label": "redo",      "kc": [Keycode.LEFT_CONTROL, Keycode.LEFT_SHIFT, Keycode.Z], "symbol": "R"},
        ],
    },
]

# Only consulted for legacy tuple-style KEYCODES entries.
KEY_SYMBOLS = {}

# Load user overrides from config.py (if present on CIRCUITPY drive)
try:
    from config import *
except ImportError:
    pass  # config.py missing — use defaults above

# ===============================================
# ===== MENU NORMALIZATION =====
# ===============================================
# Accepts both the new dict format and the legacy tuple format (using
# KEY_SYMBOLS for the latter) and produces a uniform tree of dicts.

def normalize_item(raw, symbols_table):
    if isinstance(raw, dict):
        item = dict(raw)
    else:
        label, kc = raw[0], raw[1]
        item = {"label": label, "kc": kc, "symbol": symbols_table.get(label, "?")}
    item.setdefault("symbol", "?")
    if item.get("submenu"):
        item["submenu"] = [normalize_item(c, symbols_table) for c in item["submenu"]]
        item.setdefault("auto_exit", False)
    return item

def normalize_menu(raw_list, symbols_table):
    return [normalize_item(r, symbols_table) for r in raw_list]

MENU = normalize_menu(KEYCODES, KEY_SYMBOLS)

# ===============================================
# ===== MENU / SUBMENU NAVIGATION STATE =====
# ===============================================

def _back_item():
    """Synthetic item appended to every submenu's child list so the user
    can return to the parent list without sending any keystroke."""
    return {"label": "back", "kc": None, "symbol": "<", "is_back": True}

class MenuFrame:
    """One level of the menu stack: the items currently being scanned or
    navigated, the active index within them, and whether picking a plain
    (non-submenu) item here should automatically pop back to the parent."""
    def __init__(self, items, auto_exit=False):
        self.items = items
        self.index = 0
        self.auto_exit = auto_exit

menu_stack = [MenuFrame(MENU, auto_exit=False)]

def current_frame():
    return menu_stack[-1]

def current_item():
    f = current_frame()
    return f.items[f.index]

def in_submenu():
    return len(menu_stack) > 1

def enter_submenu(item):
    children = list(item["submenu"]) + [_back_item()]
    menu_stack.append(MenuFrame(children, auto_exit=item.get("auto_exit", False)))

def exit_submenu():
    if len(menu_stack) > 1:
        menu_stack.pop()

def advance_index():
    f = current_frame()
    f.index = (f.index + 1) % len(f.items)

def reset_menu():
    """Called whenever a mode is (re)entered — always start at the top."""
    while len(menu_stack) > 1:
        menu_stack.pop()
    menu_stack[0].index = 0

# ===============================================
# ===== DISPLAY HELPERS =====
# ===============================================

SCREEN_WIDTH  = 240
SCREEN_HEIGHT = 135
LEFT_WIDTH    = SCREEN_WIDTH // 4
RIGHT_WIDTH   = SCREEN_WIDTH - LEFT_WIDTH

PURPLE     = 0x800080
SCAN_COLOR = 0x0055FF
DARK_BLUE  = 0x003399
TEAL       = 0x007060   # Mode 0 accent colour
LIGHT_GRAY = 0xAAAAAA
WHITE      = 0xFFFFFF
GREEN      = 0x00CC00
RED        = 0xFF0000
ORANGE     = 0xFF8C00   # submenu entry-point / in-submenu visual cue
SUBMENU_BORDER_PX = 10  # thickness (px) of the submenu-entry outline cue

splash = displayio.Group()
display.root_group = splash

def create_background(color, x, y, width, height):
    bmp = displayio.Bitmap(width, height, 1)
    pal = displayio.Palette(1)
    pal[0] = color
    return displayio.TileGrid(bmp, pixel_shader=pal, x=x, y=y)

def clear_display():
    while splash:
        splash.pop()

def draw_current_screen(flash_color=None, scanning=False):
    """Standard two-pane display, aware of the current submenu context.

    Visual cues (mirroring the color + outline cue used on the configurator
    website for submenu entries):
      - An item that OPENS a submenu gets a thicker ORANGE outline drawn
        behind its normal panel color.
      - While INSIDE a submenu, a small "SUB" badge is shown top-left.
    """
    clear_display()

    f          = current_frame()
    item       = f.items[f.index]
    next_item  = f.items[(f.index + 1) % len(f.items)]

    current_symbol = item.get("symbol", "?")
    next_symbol    = next_item.get("symbol", "?")
    is_entry_point = bool(item.get("submenu"))

    right_color = SCAN_COLOR if scanning else PURPLE

    if is_entry_point:
        # Thicker colored outline behind the normal panel = "opens a submenu"
        border = SUBMENU_BORDER_PX
        splash.append(create_background(ORANGE, LEFT_WIDTH, 0, RIGHT_WIDTH, SCREEN_HEIGHT))
        splash.append(create_background(
            right_color,
            LEFT_WIDTH + border, border,
            RIGHT_WIDTH - 2 * border, SCREEN_HEIGHT - 2 * border
        ))
    else:
        splash.append(create_background(right_color, LEFT_WIDTH, 0, RIGHT_WIDTH, SCREEN_HEIGHT))

    splash.append(label.Label(
        terminalio.FONT, text=current_symbol, color=WHITE, scale=9,
        anchor_point=(0.5, 0.5),
        anchored_position=(LEFT_WIDTH + RIGHT_WIDTH // 2, SCREEN_HEIGHT // 2)
    ))

    splash.append(create_background(LIGHT_GRAY, 0, 0, LEFT_WIDTH, SCREEN_HEIGHT))
    splash.append(label.Label(
        terminalio.FONT, text=next_symbol, color=PURPLE, scale=3,
        anchor_point=(0.5, 0.5),
        anchored_position=(LEFT_WIDTH // 2, SCREEN_HEIGHT // 2)
    ))

    if in_submenu():
        splash.append(label.Label(
            terminalio.FONT, text="SUB", color=ORANGE, scale=1,
            anchor_point=(0.0, 0.0), anchored_position=(2, 2)
        ))

    if flash_color is not None:
        splash.append(create_background(flash_color, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT))
        splash.append(label.Label(
            terminalio.FONT, text="SENT!", color=WHITE, scale=5,
            anchor_point=(0.5, 0.5),
            anchored_position=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
        ))

def draw_direct_switch_screen(active=None, flash_color=None):
    """
    Two-pane display for Mode 0.
    active = None | 1 | 2   (which switch was just pressed)
    """
    clear_display()

    half = SCREEN_WIDTH // 2

    # Left pane — Switch 1 (A1)
    left_bg = flash_color if (active == 1 and flash_color) else TEAL
    right_bg = flash_color if (active == 2 and flash_color) else DARK_BLUE

    splash.append(create_background(left_bg,  0,    0, half,                SCREEN_HEIGHT))
    splash.append(create_background(right_bg, half, 0, SCREEN_WIDTH - half, SCREEN_HEIGHT))

    # Vertical divider
    splash.append(create_background(WHITE, half - 1, 0, 2, SCREEN_HEIGHT))

    # Switch 1 label
    splash.append(label.Label(
        terminalio.FONT, text="SW1", color=WHITE, scale=1,
        anchor_point=(0.5, 0.2),
        anchored_position=(half // 2, SCREEN_HEIGHT // 2 - 22)
    ))
    sym1 = SWITCH1_SYMBOL[:3]
    splash.append(label.Label(
        terminalio.FONT, text=sym1, color=WHITE, scale=4,
        anchor_point=(0.5, 0.5),
        anchored_position=(half // 2, SCREEN_HEIGHT // 2 + 4)
    ))

    # Switch 2 label
    splash.append(label.Label(
        terminalio.FONT, text="SW2", color=WHITE, scale=1,
        anchor_point=(0.5, 0.2),
        anchored_position=(half + (SCREEN_WIDTH - half) // 2, SCREEN_HEIGHT // 2 - 22)
    ))
    sym2 = SWITCH2_SYMBOL[:3]
    splash.append(label.Label(
        terminalio.FONT, text=sym2, color=WHITE, scale=4,
        anchor_point=(0.5, 0.5),
        anchored_position=(half + (SCREEN_WIDTH - half) // 2, SCREEN_HEIGHT // 2 + 4)
    ))

def draw_menu_screen():
    """Mode-select screen shown on startup and on return from any mode."""
    clear_display()

    third = SCREEN_WIDTH // 3

    splash.append(create_background(DARK_BLUE, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT))

    # Dividers
    splash.append(create_background(WHITE, third - 1,     0, 2, SCREEN_HEIGHT))
    splash.append(create_background(WHITE, 2 * third - 1, 0, 2, SCREEN_HEIGHT))

    # Left — D0 (or double-click A1/A2) → Mode 0 Direct Switch
    splash.append(label.Label(
        terminalio.FONT, text="D0", color=WHITE, scale=2,
        anchor_point=(0.5, 0.5),
        anchored_position=(third // 2, SCREEN_HEIGHT // 2 - 20)
    ))
    splash.append(label.Label(
        terminalio.FONT, text="DIR", color=LIGHT_GRAY, scale=2,
        anchor_point=(0.5, 0.5),
        anchored_position=(third // 2, SCREEN_HEIGHT // 2 + 10)
    ))
    splash.append(label.Label(
        terminalio.FONT, text="direct", color=LIGHT_GRAY, scale=1,
        anchor_point=(0.5, 0.5),
        anchored_position=(third // 2, SCREEN_HEIGHT // 2 + 28)
    ))

    # Centre — D1 or A2 (select switch) → Single-Switch mode
    splash.append(label.Label(
        terminalio.FONT, text="D1/A2", color=WHITE, scale=2,
        anchor_point=(0.5, 0.5),
        anchored_position=(third + third // 2, SCREEN_HEIGHT // 2 - 20)
    ))
    splash.append(label.Label(
        terminalio.FONT, text="1-SW", color=LIGHT_GRAY, scale=2,
        anchor_point=(0.5, 0.5),
        anchored_position=(third + third // 2, SCREEN_HEIGHT // 2 + 10)
    ))
    splash.append(label.Label(
        terminalio.FONT, text="select", color=LIGHT_GRAY, scale=1,
        anchor_point=(0.5, 0.5),
        anchored_position=(third + third // 2, SCREEN_HEIGHT // 2 + 28)
    ))

    # Right — D2 or A1 (nav switch) → Two-Switch mode
    splash.append(label.Label(
        terminalio.FONT, text="D2/A1", color=WHITE, scale=2,
        anchor_point=(0.5, 0.5),
        anchored_position=(2 * third + third // 2, SCREEN_HEIGHT // 2 - 20)
    ))
    splash.append(label.Label(
        terminalio.FONT, text="2-SW", color=LIGHT_GRAY, scale=2,
        anchor_point=(0.5, 0.5),
        anchored_position=(2 * third + third // 2, SCREEN_HEIGHT // 2 + 10)
    ))
    splash.append(label.Label(
        terminalio.FONT, text="nav", color=LIGHT_GRAY, scale=1,
        anchor_point=(0.5, 0.5),
        anchored_position=(2 * third + third // 2, SCREEN_HEIGHT // 2 + 28)
    ))

# ===============================================
# ===== SHARED ACTION DISPATCHER (Mode 0) =====
# ===============================================

def dispatch_action(action, label_str="action"):
    """
    Execute a Mode 0 switch action dict.
    Supported types: key, mouse_click, mouse_scroll, mouse_move, media
    """
    try:
        t = action.get("type", "key")

        if t == "key":
            keys = action.get("keys", [Keycode.ENTER])
            press_keys(keys)
            print(f"EVENT: Sent key: {label_str}")

        elif t == "mouse_click":
            m = get_mouse()
            if m:
                btn = action.get("button", Mouse.LEFT_BUTTON)
                m.click(btn)
                print(f"EVENT: Mouse click: {label_str}")
            else:
                print("ERROR: Mouse HID not available")

        elif t == "mouse_scroll":
            m = get_mouse()
            if m:
                m.move(wheel=action.get("y", 0))
                print(f"EVENT: Mouse scroll: {label_str}")
            else:
                print("ERROR: Mouse HID not available")

        elif t == "mouse_move":
            m = get_mouse()
            if m:
                m.move(x=action.get("x", 0), y=action.get("y", 0))
                print(f"EVENT: Mouse move: {label_str}")
            else:
                print("ERROR: Mouse HID not available")

        elif t == "media":
            cc = get_consumer()
            if cc:
                cc.send(action.get("code", ConsumerControlCode.PLAY_PAUSE))
                print(f"EVENT: Media: {label_str}")
            else:
                print("ERROR: ConsumerControl HID not available")

        else:
            print(f"WARN: Unknown action type: {t}")

        return True
    except Exception as e:
        print(f"ERROR: dispatch_action failed ({label_str}): {e}")
        return False

# ===============================================
# ===== SHARED KEYCODE SENDER (Modes 1 & 2) =====
# ===============================================

# Modifiers get pressed and given a moment to register on the host BEFORE
# the "main" key goes down. Sending everything in one press(*keys) call
# usually works, but some apps only recognise a modifier+key combo if the
# modifier's key-down arrives in its own HID report slightly ahead of the
# main key — sending them all at once can look, to that app, like the main
# key was pressed with no modifier yet. This staggering costs ~20ms and is
# harmless for everything else.
MODIFIER_KEYCODES = {
    Keycode.LEFT_CONTROL, Keycode.RIGHT_CONTROL,
    Keycode.LEFT_SHIFT,   Keycode.RIGHT_SHIFT,
    Keycode.LEFT_ALT,     Keycode.RIGHT_ALT,
    Keycode.LEFT_GUI,     Keycode.RIGHT_GUI,
}

def press_keys(keycode_list):
    """Press modifiers first (with a brief settle delay), then the
    remaining key(s), hold briefly, then release everything."""
    mods  = [k for k in keycode_list if k in MODIFIER_KEYCODES]
    mains = [k for k in keycode_list if k not in MODIFIER_KEYCODES]
    if mods:
        keyboard.press(*mods)
        time.sleep(0.03)
    if mains:
        keyboard.press(*mains)
    time.sleep(0.05)
    keyboard.release_all()

def send_keycode(item):
    """Press/release item's keycode combo, flash the screen. Returns True on success."""
    key_name, keycode = item["label"], item["kc"]
    try:
        press_keys(keycode)
        draw_current_screen(flash_color=GREEN)
        print(f"EVENT: Sent: {key_name}")
        time.sleep(0.1)
        return True
    except Exception as e:
        draw_current_screen(flash_color=RED)
        print(f"ERROR: Failed to send {key_name}: {e}")
        time.sleep(0.1)
        return False

def select_current_item():
    """Handle picking whatever item is currently active:
       - the synthetic "back" item exits the submenu with no keystroke
       - an entry with no "kc" (a pure organisational folder) sends nothing,
         just gives a quick visual acknowledgement
       - a submenu entry point sends its own keycode (if any), then enters
         its submenu
       - a plain item sends its keycode, then auto-exits the submenu if
         the enclosing entry point was configured with auto_exit
    """
    f    = current_frame()
    item = f.items[f.index]

    if item.get("is_back"):
        print("EVENT: Back -> parent menu")
        exit_submenu()
        draw_current_screen()
        return True

    if item.get("kc"):
        ok = send_keycode(item)
    else:
        # No keystroke defined (e.g. an organisational-only submenu folder)
        draw_current_screen(flash_color=GREEN)
        print(f"EVENT: Selected: {item['label']} (no keystroke)")
        time.sleep(0.1)
        ok = True

    if item.get("submenu"):
        print(f"EVENT: Enter submenu -> {item['label']}")
        enter_submenu(item)
    elif in_submenu() and f.auto_exit:
        print("EVENT: Auto-exit submenu")
        exit_submenu()

    draw_current_screen()
    return ok

# ===============================================
# ===== MODE 0: DIRECT SWITCH (A1=SW1, A2=SW2) =====
# ===============================================

def run_direct_switch_mode():
    """
    Mode 0 — Direct Switch Interface
    A1 → Switch 1 action  (default: Enter)
    A2 → Switch 2 action  (default: Tab)

    Exit to mode select by holding A1 or A2 for SWITCH_HOLD_EXIT_SECS, or by
    pressing D0. A short tap (released before the hold threshold) fires that
    switch's action; a long hold returns to the menu without firing it.

    Actions are defined by SWITCH1_ACTION / SWITCH2_ACTION dicts and may be
    keyboard keys, mouse clicks/moves/scrolls, or media controls. See config.py.
    """
    print("\n--- Direct Switch Mode (Mode 0) ---")
    print(f"  SW1 (A1): {SWITCH1_LABEL}")
    print(f"  SW2 (A2): {SWITCH2_LABEL}")
    print(f"  Hold a switch {SWITCH_HOLD_EXIT_SECS}s, or press D0, = back to menu\n")

    last_sw1 = nav_pressed()
    last_sw2 = select_pressed()

    draw_direct_switch_screen()

    while True:
        try:
            # Onboard D0 exits to menu
            if d0_pressed():
                print("EVENT: D0 → back to menu")
                while d0_pressed():
                    time.sleep(0.01)
                return

            sw1 = nav_pressed()
            sw2 = select_pressed()
            led.value = sw1 or sw2

            # Fresh press on either switch → decide tap vs hold
            pressed_now = None
            if sw1 and not last_sw1:
                pressed_now = 1
            elif sw2 and not last_sw2:
                pressed_now = 2

            if pressed_now is not None:
                press_start = time.monotonic()

                # Watch the press: short release → fire action; long hold → exit
                while nav_pressed() or select_pressed():
                    held = time.monotonic() - press_start
                    if held >= SWITCH_HOLD_EXIT_SECS:
                        print("EVENT: Switch held → back to menu")
                        # Wait for full release before leaving
                        while nav_pressed() or select_pressed():
                            time.sleep(0.01)
                        return
                    time.sleep(0.01)

                # Released before hold threshold → fire the action for that switch
                if pressed_now == 1:
                    draw_direct_switch_screen(active=1, flash_color=GREEN)
                    dispatch_action(SWITCH1_ACTION, SWITCH1_LABEL)
                else:
                    draw_direct_switch_screen(active=2, flash_color=GREEN)
                    dispatch_action(SWITCH2_ACTION, SWITCH2_LABEL)

                time.sleep(0.05)
                draw_direct_switch_screen()
                time.sleep(DEBOUNCE_TIME)

            last_sw1 = nav_pressed()
            last_sw2 = select_pressed()

            time.sleep(0.01)

        except RuntimeError as e:
            print(f"RuntimeError: {e}")
            time.sleep(1.0)
        except Exception as e:
            print(f"Unexpected error: {e}")
            time.sleep(1.0)

# ===============================================
# ===== MODE 1: SINGLE SWITCH (A2) =====
# ===============================================

def run_single_switch_mode():
    """
    A2 is the single external switch (Pull.UP, active LOW).
      Short press  → select & send current item.
      Hold         → start auto-scanning.
      Press during scan → select & send, stop scanning.
      D0 (onboard) → return to mode select.
    """
    print("\n--- Single-Switch Mode (A2) ---")
    print(f"  Hold to scan:    {HOLD_TO_SCAN_SECS}s")
    print(f"  Scan interval:   {SCAN_INTERVAL_SECS}s")
    print(f"  Max short press: {MAX_SHORT_PRESS_SECS}s")
    print("  D0 = back to menu\n")

    reset_menu()
    state          = "IDLE"   # IDLE | PRESS_PENDING | SCANNING
    press_start    = None
    last_scan_time = None

    draw_current_screen()

    while True:
        try:
            now = time.monotonic()

            # Onboard D0 exits to menu (from any submenu depth)
            if d0_pressed():
                print("EVENT: D0 → back to menu")
                while d0_pressed():
                    time.sleep(0.01)
                return

            sw = select_pressed()   # A2
            led.value = sw

            # ── IDLE ──────────────────────────────────────────────
            if state == "IDLE":
                if sw:
                    press_start = now
                    state = "PRESS_PENDING"

            # ── PRESS_PENDING ──────────────────────────────────────
            elif state == "PRESS_PENDING":
                hold = now - press_start

                if not sw:
                    if hold <= MAX_SHORT_PRESS_SECS:
                        print(f"EVENT: Short press ({hold:.2f}s) → select")
                        select_current_item()
                    else:
                        print(f"DEBUG: Ambiguous release ({hold:.2f}s) — ignored")
                    state = "IDLE"

                elif hold >= HOLD_TO_SCAN_SECS:
                    print("EVENT: Hold threshold → start scanning")
                    last_scan_time = now
                    state = "SCANNING"
                    draw_current_screen(scanning=True)

            # ── SCANNING ──────────────────────────────────────────
            elif state == "SCANNING":
                if sw:
                    print("EVENT: Press during scan → select")
                    select_current_item()
                    while select_pressed():
                        time.sleep(0.01)
                    state = "IDLE"
                    draw_current_screen(scanning=False)

                elif now - last_scan_time >= SCAN_INTERVAL_SECS:
                    advance_index()
                    last_scan_time = now
                    draw_current_screen(scanning=True)
                    print(f"SCAN: → {current_item()['label']}")

            time.sleep(0.01)

        except RuntimeError as e:
            print(f"RuntimeError: {e}")
            time.sleep(1.0)
        except Exception as e:
            print(f"Unexpected error: {e}")
            time.sleep(1.0)

# ===============================================
# ===== MODE 2: TWO SWITCH (A1 = NAV, A2 = SELECT) =====
# ===============================================

def run_two_switch_mode():
    """
    A1 = Navigate  (advance to next item, Pull.UP active LOW).
    A2 = Select    (send current item,    Pull.UP active LOW).
    D0 (onboard)   = Return to mode select.
    """
    print("\n--- Two-Switch Mode (A1=Nav, A2=Select) ---")
    print("  D0 = back to menu\n")

    reset_menu()
    last_nav_state = nav_pressed()
    last_sel_state = select_pressed()

    draw_current_screen()

    while True:
        try:
            # Onboard D0 exits to menu (from any submenu depth)
            if d0_pressed():
                print("EVENT: D0 → back to menu")
                while d0_pressed():
                    time.sleep(0.01)
                return

            nav_state = nav_pressed()
            sel_state = select_pressed()
            led.value = nav_state or sel_state

            # A1 rising edge → navigate
            if nav_state and not last_nav_state:
                advance_index()
                draw_current_screen()
                print(f"EVENT: Navigate → {current_item()['label']}")
                time.sleep(DEBOUNCE_TIME)

            # A2 rising edge → select
            if sel_state and not last_sel_state:
                select_current_item()
                time.sleep(DEBOUNCE_TIME)

            last_nav_state = nav_state
            last_sel_state = sel_state

            time.sleep(0.01)

        except RuntimeError as e:
            print(f"RuntimeError: {e}")
            time.sleep(1.0)
        except Exception as e:
            print(f"Unexpected error: {e}")
            time.sleep(1.0)

# ===============================================
# ===== EXTERNAL-SWITCH GESTURE HELPER =====
# ===============================================

def resolve_external_switch_gesture(first_switch):
    """
    Called the moment an external switch press is first detected at the
    mode-select screen. `first_switch` is "A1" or "A2".

    Waits for the first press to release, then watches for a SECOND press
    within DOUBLE_CLICK_WINDOW seconds.

    Returns:
      "mode0"   if a second press arrives in time (double-click)
      "single"  if no second press and the first switch was A2
      "two"     if no second press and the first switch was A1
    """
    # Wait for the first press to be released
    while nav_pressed() or select_pressed():
        time.sleep(0.005)

    # Watch for a second press within the window
    window_start = time.monotonic()
    while time.monotonic() - window_start < DOUBLE_CLICK_WINDOW:
        if nav_pressed() or select_pressed():
            # Second press → double-click → Mode 0
            while nav_pressed() or select_pressed():
                time.sleep(0.005)
            return "mode0"
        time.sleep(0.005)

    # No second press → single click maps to a mode by which switch was used
    return "single" if first_switch == "A2" else "two"

# ===============================================
# ===== STARTUP =====
# ===============================================

print("=" * 40)
print("Switch Interface — Triple Mode")
print("Feather ESP32-S3 Rev TFT")
print("=" * 40)
_submenu_count = sum(1 for i in MENU if i.get("submenu"))
_child_count   = sum(len(i["submenu"]) for i in MENU if i.get("submenu"))
print(f"Loaded {len(MENU)} top-level items "
      f"({_submenu_count} submenu{'s' if _submenu_count != 1 else ''}, "
      f"{_child_count} nested item{'s' if _child_count != 1 else ''})")
print("External switches: A1 = Navigate/SW1, A2 = Select/SW2")
print("D0 (onboard)             = Direct Switch Mode (Mode 0)")
print("D1 (onboard) or single-click A2 = Single-Switch Scanning Mode")
print("D2 (onboard) or single-click A1 = Two-Switch Mode")
print("Double-click A1 or A2    = Direct Switch Mode (Mode 0)")
print()

# ===============================================
# ===== MAIN LOOP — MODE SELECT =====
# ===============================================

while True:
    try:
        draw_menu_screen()
        print("MODE SELECT:")
        print("  D0 (onboard)          → Direct Switch (Mode 0)")
        print("  D1 (onboard)          → Single-Switch")
        print("  D2 (onboard)          → Two-Switch")
        print("  Single-click A2       → Single-Switch")
        print("  Single-click A1       → Two-Switch")
        print("  Double-click A1 / A2  → Direct Switch (Mode 0)")

        # Drain any buttons/switches still held from a previous mode before listening
        while d0_pressed() or d1_pressed() or d2_pressed() or select_pressed() or nav_pressed():
            time.sleep(0.01)

        # Wait for a fresh activation.
        # Onboard buttons act instantly (unambiguous).
        # An external-switch press is DEFERRED: we wait to see whether a second
        # press follows (double-click → Mode 0) before committing to a mode.
        while True:
            # ── Onboard buttons — instant ──────────────────────────
            if d0_pressed():
                while d0_pressed():
                    time.sleep(0.01)
                run_direct_switch_mode()
                break

            if d1_pressed():
                while d1_pressed():
                    time.sleep(0.01)
                run_single_switch_mode()
                break

            if d2_pressed():
                while d2_pressed():
                    time.sleep(0.01)
                run_two_switch_mode()
                break

            # ── External switch — single vs double click ───────────
            if nav_pressed() or select_pressed():
                first = "A1" if nav_pressed() else "A2"
                gesture = resolve_external_switch_gesture(first)
                if gesture == "mode0":
                    print("EVENT: Double-click → Direct Switch Mode (Mode 0)")
                    run_direct_switch_mode()
                elif gesture == "single":
                    print("EVENT: Single-click A2 → Single-Switch Mode")
                    run_single_switch_mode()
                else:  # "two"
                    print("EVENT: Single-click A1 → Two-Switch Mode")
                    run_two_switch_mode()
                break

            time.sleep(0.01)

    except Exception as e:
        print(f"Menu error: {e}")
        time.sleep(1.0)
