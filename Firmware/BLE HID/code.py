"""
Switch Interface for Adafruit Feather ESP32-S3 Rev TFT
Bluetooth HID Version — Dual Mode with Onboard Mode Selection
Uses built-in 1.14" 240x135 color TFT display
Compatible with CircuitPython

EXTERNAL SWITCHES (3.5mm jacks, wired to GND, Pull.UP active LOW):
  A1 → Navigate switch
  A2 → Select / Single switch

ONBOARD BUTTONS (mode selection only):
  D1 → Enter Single-Switch Scanning Mode  (A2 is the switch)
  D2 → Enter Two-Switch Mode              (A1 = Navigate, A2 = Select)
  D0 → Return to Mode Select from any active mode

─── BLUETOOTH ──────────────────────────────────────────────
  On startup the device advertises as "Switch Interface".
  Pair it from your computer's Bluetooth settings.
  The display shows ADVERTISING (yellow) while waiting,
  CONNECTED (green) when paired, and DISCONNECTED (red)
  if the connection drops — it will re-advertise automatically.

─── SINGLE-SWITCH MODE ─────────────────────────────────────
  A2 SHORT PRESS  (≤ MAX_SHORT_PRESS_SECS)  : Select & send current item
  A2 HOLD         (≥ HOLD_TO_SCAN_SECS)     : Start auto-scanning
  A2 PRESS during scan                      : Select & send, stop scanning
  D0                                        : Back to Mode Select

─── TWO-SWITCH MODE ────────────────────────────────────────
  A1  : Advance to next item
  A2  : Select & send current item
  D0  : Back to Mode Select
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

# ── Bluetooth HID imports ────────────────────────────────────────────────────
import adafruit_ble
from adafruit_ble import BLERadio
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.standard.hid import HIDService
from adafruit_ble.services.standard.device_info import DeviceInfoService
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode

print("Starting Switch Interface (Bluetooth HID)...")

# ===============================================
# ===== USER CONFIGURABLE VARIABLES =====
# ===============================================

# Bluetooth device name shown during pairing
BLE_DEVICE_NAME = "Switch Interface"

# --- Single-Switch Mode ---
# How long (seconds) A2 must be held to begin auto-scanning
HOLD_TO_SCAN_SECS = 2.0

# How fast (seconds) the scanner advances to the next item
SCAN_INTERVAL_SECS = 1.0

# Maximum press duration (seconds) considered a "short press"
MAX_SHORT_PRESS_SECS = 0.5

# --- Two-Switch Mode ---
# Debounce delay (seconds) after a nav or select press
DEBOUNCE_TIME = 0.1

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
# ===== BLUETOOTH HID SETUP =====
# ===============================================

print("Setting up Bluetooth HID...")

ble = BLERadio()
ble.name = BLE_DEVICE_NAME

hid_service = HIDService()
device_info = DeviceInfoService(
    software_revision=adafruit_ble.__version__,
    manufacturer="Adafruit Industries"
)

advertisement = ProvideServicesAdvertisement(hid_service)
advertisement.appearance = 961  # Bluetooth HID Keyboard appearance code

keyboard = Keyboard(hid_service.devices)

print(f"BLE name: {BLE_DEVICE_NAME}")
print("Bluetooth HID ready.")

# ===============================================
# ===== KEYCODES AND SYMBOL DEFINITIONS =====
# ===============================================

KEYCODES = [
    ("arrow right", [Keycode.RIGHT_ARROW]),
    ("arrow down",  [Keycode.DOWN_ARROW]),
    ("enter",       [Keycode.ENTER]),
    ("arrow left",  [Keycode.LEFT_ARROW]),
    ("arrow up",    [Keycode.UP_ARROW]),
    ("delete",      [Keycode.DELETE]),
    ("w",           [Keycode.W]),
    ("t",           [Keycode.T]),
]

KEY_SYMBOLS = {
    "arrow right": "R",
    "arrow down":  "D",
    "enter":       "e",
    "arrow left":  "L",
    "arrow up":    "U",
    "delete":      "x",
    "w":           "W",
    "t":           "T",
}

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
LIGHT_GRAY = 0xAAAAAA
WHITE      = 0xFFFFFF
GREEN      = 0x00CC00
RED        = 0xFF0000
YELLOW     = 0xCCCC00
ORANGE     = 0xCC5500

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

def draw_ble_status_bar(status):
    """
    Draws a thin status bar at the top of the screen.
      status: "advertising" | "connected" | "disconnected"
    """
    BAR_HEIGHT = 14
    if status == "connected":
        bar_color = GREEN
        bar_text  = "BT CONNECTED"
        txt_color = WHITE
    elif status == "advertising":
        bar_color = YELLOW
        bar_text  = "BT PAIRING..."
        txt_color = 0x000000   # Black on yellow
    else:  # disconnected
        bar_color = RED
        bar_text  = "BT DISCONNECTED"
        txt_color = WHITE

    splash.append(create_background(bar_color, 0, 0, SCREEN_WIDTH, BAR_HEIGHT))
    splash.append(label.Label(
        terminalio.FONT, text=bar_text, color=txt_color, scale=1,
        anchor_point=(0.5, 0.5),
        anchored_position=(SCREEN_WIDTH // 2, BAR_HEIGHT // 2)
    ))

def draw_keycode_screen(index, flash_color=None, scanning=False, ble_status="connected"):
    """Standard two-pane keycode display with BLE status bar at top."""
    clear_display()

    BAR_HEIGHT = 14   # Reserved for the status bar
    pane_y     = BAR_HEIGHT
    pane_h     = SCREEN_HEIGHT - BAR_HEIGHT

    current_symbol = KEY_SYMBOLS.get(KEYCODES[index][0], "?")
    next_index     = (index + 1) % len(KEYCODES)
    next_symbol    = KEY_SYMBOLS.get(KEYCODES[next_index][0], "?")

    right_color = SCAN_COLOR if scanning else PURPLE
    splash.append(create_background(right_color, LEFT_WIDTH, pane_y, RIGHT_WIDTH, pane_h))
    splash.append(label.Label(
        terminalio.FONT, text=current_symbol, color=WHITE, scale=8,
        anchor_point=(0.5, 0.5),
        anchored_position=(LEFT_WIDTH + RIGHT_WIDTH // 2, pane_y + pane_h // 2)
    ))

    splash.append(create_background(LIGHT_GRAY, 0, pane_y, LEFT_WIDTH, pane_h))
    splash.append(label.Label(
        terminalio.FONT, text=next_symbol, color=PURPLE, scale=3,
        anchor_point=(0.5, 0.5),
        anchored_position=(LEFT_WIDTH // 2, pane_y + pane_h // 2)
    ))

    if flash_color is not None:
        splash.append(create_background(flash_color, 0, pane_y, SCREEN_WIDTH, pane_h))
        splash.append(label.Label(
            terminalio.FONT, text="SENT!", color=WHITE, scale=5,
            anchor_point=(0.5, 0.5),
            anchored_position=(SCREEN_WIDTH // 2, pane_y + pane_h // 2)
        ))

    # Status bar drawn last so it sits on top
    draw_ble_status_bar(ble_status)

def draw_advertising_screen():
    """Full-screen advertising/pairing prompt."""
    clear_display()
    splash.append(create_background(DARK_BLUE, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT))
    splash.append(label.Label(
        terminalio.FONT, text="BLUETOOTH", color=YELLOW, scale=3,
        anchor_point=(0.5, 0.5),
        anchored_position=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 28)
    ))
    splash.append(label.Label(
        terminalio.FONT, text="PAIRING...", color=WHITE, scale=2,
        anchor_point=(0.5, 0.5),
        anchored_position=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 4)
    ))
    splash.append(label.Label(
        terminalio.FONT, text=BLE_DEVICE_NAME, color=LIGHT_GRAY, scale=1,
        anchor_point=(0.5, 0.5),
        anchored_position=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 28)
    ))

def draw_menu_screen(ble_status="advertising"):
    """Mode-select screen with BLE status bar."""
    clear_display()

    BAR_HEIGHT = 14
    pane_y     = BAR_HEIGHT
    pane_h     = SCREEN_HEIGHT - BAR_HEIGHT

    splash.append(create_background(DARK_BLUE, 0, pane_y, SCREEN_WIDTH, pane_h))
    # Centre divider
    splash.append(create_background(WHITE, SCREEN_WIDTH // 2 - 1, pane_y, 2, pane_h))

    # Left half — D1 / Single Switch
    splash.append(label.Label(
        terminalio.FONT, text="D1", color=WHITE, scale=4,
        anchor_point=(0.5, 0.5),
        anchored_position=(SCREEN_WIDTH // 4, pane_y + pane_h // 2 - 10)
    ))
    splash.append(label.Label(
        terminalio.FONT, text="1-SW", color=LIGHT_GRAY, scale=2,
        anchor_point=(0.5, 0.5),
        anchored_position=(SCREEN_WIDTH // 4, pane_y + pane_h // 2 + 18)
    ))

    # Right half — D2 / Two Switch
    splash.append(label.Label(
        terminalio.FONT, text="D2", color=WHITE, scale=4,
        anchor_point=(0.5, 0.5),
        anchored_position=(3 * SCREEN_WIDTH // 4, pane_y + pane_h // 2 - 10)
    ))
    splash.append(label.Label(
        terminalio.FONT, text="2-SW", color=LIGHT_GRAY, scale=2,
        anchor_point=(0.5, 0.5),
        anchored_position=(3 * SCREEN_WIDTH // 4, pane_y + pane_h // 2 + 18)
    ))

    draw_ble_status_bar(ble_status)

# ===============================================
# ===== BLUETOOTH CONNECTION MANAGEMENT =====
# ===============================================

def ble_connected():
    """Returns True if a BLE host is currently connected."""
    return ble.connected

def ensure_advertising():
    """Start advertising if not already advertising and not connected."""
    if not ble.connected and not ble.advertising:
        print("BLE: Starting advertising...")
        ble.start_advertising(advertisement)

def stop_advertising():
    """Stop advertising once connected."""
    if ble.advertising:
        ble.stop_advertising()

def wait_for_connection():
    """
    Block until a BLE host connects, updating the display.
    Also watches D1/D2 to allow mode pre-selection; returns
    immediately once connected regardless of button state.
    """
    draw_advertising_screen()
    ensure_advertising()
    print("BLE: Waiting for connection...")

    while not ble_connected():
        time.sleep(0.05)
        led.value = not led.value   # Blink LED while advertising

    stop_advertising()
    led.value = True
    print("BLE: Connected!")

# ===============================================
# ===== SHARED KEYCODE SENDER =====
# ===============================================

def send_keycode(index, ble_status="connected"):
    """Send keycode at index over BLE, flash the screen. Returns True on success."""
    if not ble_connected():
        print("BLE: Not connected — skipping send")
        draw_keycode_screen(index, flash_color=ORANGE, ble_status="disconnected")
        time.sleep(0.2)
        return False

    key_name, keycode = KEYCODES[index]
    try:
        keyboard.press(*keycode)
        time.sleep(0.05)
        keyboard.release_all()
        draw_keycode_screen(index, flash_color=GREEN, ble_status=ble_status)
        print(f"EVENT: Sent: {key_name}")
        time.sleep(0.1)
        return True
    except Exception as e:
        draw_keycode_screen(index, flash_color=RED, ble_status=ble_status)
        print(f"ERROR: Failed to send {key_name}: {e}")
        time.sleep(0.1)
        return False

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
    Handles BLE disconnection gracefully — pauses scanning
    and re-advertises until the host reconnects.
    """
    print("\n--- Single-Switch Mode (A2) ---")
    print(f"  Hold to scan:    {HOLD_TO_SCAN_SECS}s")
    print(f"  Scan interval:   {SCAN_INTERVAL_SECS}s")
    print(f"  Max short press: {MAX_SHORT_PRESS_SECS}s")
    print("  D0 = back to menu\n")

    current_index  = 0
    state          = "IDLE"
    press_start    = None
    last_scan_time = None

    draw_keycode_screen(current_index, ble_status="connected")

    while True:
        try:
            now = time.monotonic()

            # ── Onboard D0 → back to menu ──────────────────────────
            if d0_pressed():
                print("EVENT: D0 → back to menu")
                while d0_pressed():
                    time.sleep(0.01)
                return

            # ── BLE disconnection handling ─────────────────────────
            if not ble_connected():
                print("BLE: Disconnected — pausing, re-advertising...")
                state = "IDLE"   # Reset state so we don't misfire on reconnect
                draw_keycode_screen(current_index, ble_status="disconnected")
                ensure_advertising()
                while not ble_connected():
                    if d0_pressed():
                        while d0_pressed():
                            time.sleep(0.01)
                        return
                    led.value = not led.value
                    time.sleep(0.1)
                stop_advertising()
                led.value = True
                print("BLE: Reconnected!")
                draw_keycode_screen(current_index, ble_status="connected")

            sw = select_pressed()   # A2
            led.value = sw

            # ── IDLE ───────────────────────────────────────────────
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
                        send_keycode(current_index, ble_status="connected")
                        draw_keycode_screen(current_index, ble_status="connected")
                    else:
                        print(f"DEBUG: Ambiguous release ({hold:.2f}s) — ignored")
                    state = "IDLE"

                elif hold >= HOLD_TO_SCAN_SECS:
                    print("EVENT: Hold threshold → start scanning")
                    last_scan_time = now
                    state = "SCANNING"
                    draw_keycode_screen(current_index, scanning=True, ble_status="connected")

            # ── SCANNING ──────────────────────────────────────────
            elif state == "SCANNING":
                if sw:
                    print("EVENT: Press during scan → select")
                    send_keycode(current_index, ble_status="connected")
                    while select_pressed():
                        time.sleep(0.01)
                    state = "IDLE"
                    draw_keycode_screen(current_index, scanning=False, ble_status="connected")

                elif now - last_scan_time >= SCAN_INTERVAL_SECS:
                    current_index = (current_index + 1) % len(KEYCODES)
                    last_scan_time = now
                    draw_keycode_screen(current_index, scanning=True, ble_status="connected")
                    print(f"SCAN: → {KEYCODES[current_index][0]}")

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
    Handles BLE disconnection gracefully.
    """
    print("\n--- Two-Switch Mode (A1=Nav, A2=Select) ---")
    print("  D0 = back to menu\n")

    current_index  = 0
    last_nav_state = nav_pressed()
    last_sel_state = select_pressed()

    draw_keycode_screen(current_index, ble_status="connected")

    while True:
        try:
            # ── Onboard D0 → back to menu ──────────────────────────
            if d0_pressed():
                print("EVENT: D0 → back to menu")
                while d0_pressed():
                    time.sleep(0.01)
                return

            # ── BLE disconnection handling ─────────────────────────
            if not ble_connected():
                print("BLE: Disconnected — pausing, re-advertising...")
                draw_keycode_screen(current_index, ble_status="disconnected")
                ensure_advertising()
                while not ble_connected():
                    if d0_pressed():
                        while d0_pressed():
                            time.sleep(0.01)
                        return
                    led.value = not led.value
                    time.sleep(0.1)
                stop_advertising()
                led.value = True
                print("BLE: Reconnected!")
                # Re-seed edge detection so held switches don't misfire
                last_nav_state = nav_pressed()
                last_sel_state = select_pressed()
                draw_keycode_screen(current_index, ble_status="connected")

            nav_state = nav_pressed()
            sel_state = select_pressed()
            led.value = nav_state or sel_state

            # A1 rising edge → navigate
            if nav_state and not last_nav_state:
                current_index = (current_index + 1) % len(KEYCODES)
                draw_keycode_screen(current_index, ble_status="connected")
                print(f"EVENT: Navigate → {KEYCODES[current_index][0]}")
                time.sleep(DEBOUNCE_TIME)

            # A2 rising edge → select
            if sel_state and not last_sel_state:
                send_keycode(current_index, ble_status="connected")
                draw_keycode_screen(current_index, ble_status="connected")
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
# ===== STARTUP =====
# ===============================================

print("=" * 40)
print("Switch Interface — Bluetooth HID Dual Mode")
print("Feather ESP32-S3 Rev TFT")
print("=" * 40)
print(f"Loaded {len(KEYCODES)} keycodes")
print(f"BLE name: {BLE_DEVICE_NAME}")
print("External switches: A1 = Navigate, A2 = Select/Single")
print("D1 (onboard) = Single-Switch Scanning Mode")
print("D2 (onboard) = Two-Switch Mode")
print("D0 (onboard) = Return to Mode Select")
print()

# ── Initial BLE connection ───────────────────────────────────────────────────
wait_for_connection()

# ===============================================
# ===== MAIN LOOP — MODE SELECT =====
# ===============================================

while True:
    try:
        # If BLE dropped while in the menu, re-advertise and wait
        if not ble_connected():
            print("BLE: Disconnected at menu — re-advertising...")
            draw_menu_screen(ble_status="disconnected")
            ensure_advertising()
            while not ble_connected():
                led.value = not led.value
                time.sleep(0.1)
            stop_advertising()
            led.value = True
            print("BLE: Reconnected!")

        draw_menu_screen(ble_status="connected")
        print("MODE SELECT: Press D1 (single-switch) or D2 (two-switch)")

        # Drain any buttons still held from a previous mode
        while d1_pressed() or d2_pressed():
            time.sleep(0.01)

        # Wait for a fresh mode selection press
        while True:
            # Keep watching for BLE drop even in the menu wait loop
            if not ble_connected():
                break   # Re-enter outer loop to handle reconnection

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
            time.sleep(0.01)

    except Exception as e:
        print(f"Menu error: {e}")
        time.sleep(1.0)