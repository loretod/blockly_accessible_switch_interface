"""
Switch Interface for Adafruit Feather ESP32-S3 Rev TFT
USB HID Version - Single Switch (A2) with Scanning
Uses built-in 1.14" 240x135 color TFT display
Compatible with CircuitPython

Single-Switch Operation:
  - SHORT PRESS: Sends the currently selected keycode
  - HOLD (>= HOLD_TO_SCAN_SECS): Starts auto-scanning through the list
  - PRESS during scan: Selects & sends the current item, stops scanning
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

print("Starting Switch Interface...")

# ===============================================
# ===== USER CONFIGURABLE VARIABLES =====
# ===============================================

# How long (in seconds) the switch must be held to begin auto-scanning
HOLD_TO_SCAN_SECS = 2.0

# How fast (in seconds) the scanner advances to the next item during scanning
SCAN_INTERVAL_SECS = 1.0

# Maximum duration (in seconds) a press can be to be considered a "short press".
# Presses held longer than this will trigger scanning instead.
MAX_SHORT_PRESS_SECS = 0.5

# ===============================================
# ===== FIXED PIN & DISPLAY INITIALIZATION =====
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
# LED setup
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT

# ===== SINGLE SWITCH PIN (A2 for SEL/SCAN) =====
# Pin uses PULL_UP. Switch must be wired between A2 and GND.
# Pressed state is False (LOW).

switch = digitalio.DigitalInOut(board.A2)
switch.direction = digitalio.Direction.INPUT
switch.pull = digitalio.Pull.UP

# ===== USB HID SETUP =====
time.sleep(1)
keyboard = Keyboard(usb_hid.devices)

# ===============================================
# ===== KEYCODES AND SYMBOL DEFINITIONS =====
# ===============================================

# [Key Name (for internal use), [Keycode(s)]]
KEYCODES = [
    ("arrow right", [Keycode.RIGHT_ARROW]),
    ("arrow down", [Keycode.DOWN_ARROW]),
    ("enter", [Keycode.ENTER]),
    ("arrow left", [Keycode.LEFT_ARROW]),
    ("arrow up", [Keycode.UP_ARROW]),
    ("delete", [Keycode.DELETE]),
    ("w", [Keycode.W]),
    ("t", [Keycode.T]),
]

# Map Key Name to single-character Symbol for display
KEY_SYMBOLS = {
    "arrow right": "R",
    "arrow down": "D",
    "enter": "e",
    "arrow left": "L",
    "arrow up": "U",
    "delete": "x",
    "w": "W",
    "t": "T",
}

current_index = 0

# ===============================================
# ===== SCANNING STATE =====
# ===============================================

# States: "IDLE", "PRESS_PENDING", "SCANNING"
state = "IDLE"
press_start_time = None    # When the current press began
last_scan_time = None      # When the scanner last advanced
is_scanning = False

# ===============================================
# ===== DISPLAY FUNCTIONS =====
# ===============================================

splash = displayio.Group()
display.root_group = splash

def create_background(color, x, y, width, height):
    color_bitmap = displayio.Bitmap(width, height, 1)
    color_palette = displayio.Palette(1)
    color_palette[0] = color
    return displayio.TileGrid(color_bitmap, pixel_shader=color_palette, x=x, y=y)

def update_display(index, flash_color=None, scanning=False):
    global splash

    while splash:
        splash.pop()

    SCREEN_WIDTH = 240
    SCREEN_HEIGHT = 135
    LEFT_WIDTH = SCREEN_WIDTH // 4       # 60px
    RIGHT_WIDTH = SCREEN_WIDTH - LEFT_WIDTH  # 180px

    PURPLE = 0x800080
    SCAN_COLOR = 0x0055FF   # Blue tint during scanning
    LIGHT_GRAY = 0xAAAAAA
    WHITE = 0xFFFFFF

    current_key_name = KEYCODES[index][0]
    current_symbol = KEY_SYMBOLS.get(current_key_name, "?")

    # Right pane background — blue when scanning, purple otherwise
    right_color = SCAN_COLOR if scanning else PURPLE
    right_bg = create_background(right_color, LEFT_WIDTH, 0, RIGHT_WIDTH, SCREEN_HEIGHT)
    splash.append(right_bg)

    current_label = label.Label(
        terminalio.FONT,
        text=current_symbol,
        color=WHITE,
        scale=9,
        anchor_point=(0.5, 0.5),
        anchored_position=(LEFT_WIDTH + RIGHT_WIDTH // 2, SCREEN_HEIGHT // 2)
    )
    splash.append(current_label)

    # Left pane — shows next item
    next_index = (index + 1) % len(KEYCODES)
    next_key_name = KEYCODES[next_index][0]
    next_symbol = KEY_SYMBOLS.get(next_key_name, "?")

    left_bg = create_background(LIGHT_GRAY, 0, 0, LEFT_WIDTH, SCREEN_HEIGHT)
    splash.append(left_bg)

    next_label = label.Label(
        terminalio.FONT,
        text=next_symbol,
        color=PURPLE,
        scale=3,
        anchor_point=(0.5, 0.5),
        anchored_position=(LEFT_WIDTH // 2, SCREEN_HEIGHT // 2)
    )
    splash.append(next_label)

    # Optional flash overlay (SENT! confirmation or error)
    if flash_color is not None:
        flash_bg = create_background(flash_color, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
        splash.append(flash_bg)
        flash_text = label.Label(
            terminalio.FONT,
            text="SENT!",
            color=WHITE,
            scale=5,
            anchor_point=(0.5, 0.5),
            anchored_position=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
        )
        splash.append(flash_text)


def send_keycode(keycode):
    try:
        keyboard.press(*keycode)
        time.sleep(0.05)
        keyboard.release_all()
        return True
    except Exception as e:
        print(f"Error sending keycode: {e}")
        return False


def do_select(index):
    """Send the keycode at index and flash the screen."""
    key_name, keycode = KEYCODES[index]
    if send_keycode(keycode):
        update_display(index, flash_color=0x00FF00)
        print(f"EVENT: Sent: {key_name}")
        time.sleep(0.1)
        update_display(index)
    else:
        update_display(index, flash_color=0xFF0000)
        print(f"EVENT: Failed to send: {key_name}")
        time.sleep(0.1)
        update_display(index)


# ===== STARTUP =====
print("=" * 40)
print("Switch Interface - Single Switch / USB HID Mode")
print("Feather ESP32-S3 Rev TFT")
print("=" * 40)
print(f"Loaded {len(KEYCODES)} keycodes")
print(f"Hold to scan : {HOLD_TO_SCAN_SECS}s")
print(f"Scan interval: {SCAN_INTERVAL_SECS}s")
print(f"Max short press: {MAX_SHORT_PRESS_SECS}s")

update_display(current_index)
print("Ready! Pin A2 (single switch) is active.")
print()

# ===== MAIN LOOP =====
while True:
    try:
        now = time.monotonic()
        sw_pressed = not switch.value  # True when switch is held down (LOW)
        led.value = sw_pressed

        # ----------------------------------------------------------
        # STATE: IDLE — waiting for the switch to be pressed
        # ----------------------------------------------------------
        if state == "IDLE":
            if sw_pressed:
                press_start_time = now
                state = "PRESS_PENDING"
                print("DEBUG: Press started")

        # ----------------------------------------------------------
        # STATE: PRESS_PENDING — switch is down, deciding what to do
        # ----------------------------------------------------------
        elif state == "PRESS_PENDING":
            hold_duration = now - press_start_time

            if not sw_pressed:
                # Switch released — was it a short press?
                if hold_duration <= MAX_SHORT_PRESS_SECS:
                    print(f"EVENT: Short press ({hold_duration:.2f}s) → select")
                    do_select(current_index)
                else:
                    # Released between MAX_SHORT_PRESS and HOLD_TO_SCAN — ignore
                    print(f"DEBUG: Ambiguous release ({hold_duration:.2f}s) — ignored")
                state = "IDLE"

            elif hold_duration >= HOLD_TO_SCAN_SECS:
                # Held long enough — start scanning
                print("EVENT: Hold threshold reached → start scanning")
                is_scanning = True
                last_scan_time = now
                state = "SCANNING"
                update_display(current_index, scanning=True)

        # ----------------------------------------------------------
        # STATE: SCANNING — auto-advancing through items
        # ----------------------------------------------------------
        elif state == "SCANNING":
            # A press while scanning selects the current item
            if sw_pressed:
                print("EVENT: Press during scan → select and stop scanning")
                is_scanning = False
                do_select(current_index)
                # Wait for switch release before returning to IDLE
                while not switch.value:
                    time.sleep(0.01)
                state = "IDLE"
                update_display(current_index, scanning=False)

            else:
                # Advance to next item at SCAN_INTERVAL_SECS
                if now - last_scan_time >= SCAN_INTERVAL_SECS:
                    current_index = (current_index + 1) % len(KEYCODES)
                    last_scan_time = now
                    update_display(current_index, scanning=True)
                    print(f"SCAN: → {KEYCODES[current_index][0]}")

        time.sleep(0.01)

    except RuntimeError as e:
        print(f"RuntimeError: {e}")
        time.sleep(1.0)
    except Exception as e:
        print(f"Unexpected error: {e}")
        time.sleep(1.0)