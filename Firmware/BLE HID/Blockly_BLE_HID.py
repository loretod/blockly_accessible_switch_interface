"""
Switch Interface for Adafruit Feather ESP32-S3 Rev TFT
Bluetooth HID Version - Wireless Connection
Uses built-in 1.14" 240x135 color TFT display

IMPORTANT: This requires CircuitPython 9.0+ with BLE HID support
You may need to install adafruit_ble library bundle
"""

import time
import board
import digitalio
import displayio
import terminalio
from adafruit_display_text import label
import adafruit_st7789

# Bluetooth imports
import adafruit_ble
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.standard.hid import HIDService
from adafruit_ble.services.standard.device_info import DeviceInfoService
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode

# ===== DISPLAY SETUP =====
displayio.release_displays()

spi = board.SPI()
tft_cs = board.TFT_CS
tft_dc = board.TFT_DC
tft_reset = board.TFT_RESET
tft_backlight = board.TFT_BACKLIGHT

display_bus = displayio.FourWire(
    spi, command=tft_dc, chip_select=tft_cs, reset=tft_reset
)

display = adafruit_st7789.ST7789(
    display_bus,
    width=240,
    height=135,
    rotation=270,
    rowstart=40,
    colstart=53,
)

backlight = digitalio.DigitalInOut(tft_backlight)
backlight.direction = digitalio.Direction.OUTPUT
backlight.value = True

# ===== BLUETOOTH SETUP =====
print("Setting up Bluetooth...")
hid = HIDService()
device_info = DeviceInfoService(
    software_revision=adafruit_ble.__version__,
    manufacturer="Adafruit Industries"
)
advertisement = ProvideServicesAdvertisement(hid)
advertisement.appearance = 961  # Keyboard appearance
ble = adafruit_ble.BLERadio()

# Friendly BLE name
if not ble.connected:
    ble.name = "Switch Interface"
    print(f"BLE Name: {ble.name}")

# Keyboard will be created after connection
kbd = None

# ===== SWITCH SETUP =====
switch_nav = digitalio.DigitalInOut(board.A0)
switch_nav.direction = digitalio.Direction.INPUT
switch_nav.pull = digitalio.Pull.UP

switch_select = digitalio.DigitalInOut(board.A1)
switch_select.digitalio.Direction.INPUT
switch_select.pull = digitalio.Pull.UP

# ===== KEYCODE ARRAY =====
KEYCODES = [
    # Most common
    ("SPACE", Keycode.SPACE),
    ("ENTER", Keycode.ENTER),

    # Navigation
    ("UP", Keycode.UP_ARROW),
    ("DOWN", Keycode.DOWN_ARROW),
    ("LEFT", Keycode.LEFT_ARROW),
    ("RIGHT", Keycode.RIGHT_ARROW),

    # Letters
    ("A", Keycode.A),
    ("B", Keycode.B),
    ("C", Keycode.C),
    ("D", Keycode.D),
    ("E", Keycode.E),
    ("S", Keycode.S),
    ("W", Keycode.W),
    ("Y", Keycode.Y),
    ("N", Keycode.N),

    # Numbers
    ("1", Keycode.ONE),
    ("2", Keycode.TWO),
    ("3", Keycode.THREE),
    ("4", Keycode.FOUR),
    ("5", Keycode.FIVE),

    # Editing
    ("BKSP", Keycode.BACKSPACE),
    ("DEL", Keycode.DELETE),
    ("TAB", Keycode.TAB),
    ("ESC", Keycode.ESCAPE),
]

# ===== STATE VARIABLES =====
current_index = 0
last_nav_state = True
last_select_state = True
debounce_time = 0.2
connection_status = "SEARCHING"

# ===== DISPLAY FUNCTIONS =====
def create_display_group(index, status_text="", status_color=0xFFFFFF):
    """Create a display group with current selection"""
    splash = displayio.Group()

    # Background
    color_bitmap = displayio.Bitmap(240, 135, 1)
    color_palette = displayio.Palette(1)
    color_palette[0] = 0x1a1a2e
    bg_sprite = displayio.TileGrid(color_bitmap, pixel_shader=color_palette, x=0, y=0)
    splash.append(bg_sprite)

    # Title bar
    title_bg = displayio.Bitmap(240, 25, 1)
    title_palette = displayio.Palette(1)
    title_palette[0] = 0x16213e
    title_sprite = displayio.TileGrid(title_bg, pixel_shader=title_palette, x=0, y=0)
    splash.append(title_sprite)

    title = label.Label(
        terminalio.FONT,
        text="SWITCH INTERFACE",
        color=0x00d4ff,
        x=10,
        y=12
    )
    splash.append(title)

    # Bluetooth status indicator
    bt_color = 0x00ff88 if connection_status == "CONNECTED" else 0xff6b6b
    bt_text = "BT" if connection_status == "CONNECTED" else "..."
    bt_status = label.Label(
        terminalio.FONT,
        text=bt_text,
        color=bt_color,
        x=200,
        y=12
    )
    splash.append(bt_status)

    # If not connected, show pairing message
    if connection_status != "CONNECTED":
        pairing_msg = label.Label(
            terminalio.FONT,
            text="Waiting for",
            color=0xffaa00,
            scale=2,
            x=120,
            y=50
        )
        pairing_msg.anchor_point = (0.5, 0.5)
        pairing_msg.anchored_position = (120, 50)
        splash.append(pairing_msg)

        pairing_msg2 = label.Label(
            terminalio.FONT,
            text="Bluetooth pairing...",
            color=0xffaa00,
            x=120,
            y=75
        )
        pairing_msg2.anchor_point = (0.5, 0.5)
        pairing_msg2.anchored_position = (120, 75)
        splash.append(pairing_msg2)

        return splash

    # Current key name (large)
    key_name = KEYCODES[index][0]
    key_label = label.Label(
        terminalio.FONT,
        text=key_name,
        color=0xffffff,
        scale=3,
        x=120,
        y=60
    )
    key_label.anchor_point = (0.5, 0.5)
    key_label.anchored_position = (120, 60)
    splash.append(key_label)

    # Counter
    counter = label.Label(
        terminalio.FONT,
        text=f"{index + 1} / {len(KEYCODES)}",
        color=0x888888,
        x=10,
        y=100
    )
    splash.append(counter)

    # Navigation hint
    hint = label.Label(
        terminalio.FONT,
        text="NAV: Next  SEL: Send",
        color=0x666666,
        x=10,
        y=120
    )
    splash.append(hint)

    # Status message
    if status_text:
        status = label.Label(
            terminalio.FONT,
            text=status_text,
            color=status_color,
            scale=2,
            x=120,
            y=100
        )
        status.anchor_point = (0.5, 0.5)
        status.anchored_position = (120, 100)
        splash.append(status)

    return splash

def update_display(index, status_text="", status_color=0xFFFFFF):
    """Update the display"""
    display.root_group = create_display_group(index, status_text, status_color)

def send_keycode(keycode):
    """Send keycode via Bluetooth"""
    if kbd and ble.connected:
        kbd.press(keycode)
        kbd.release_all()
        return True
    return False

# ===== STARTUP =====
print("=" * 40)
print("Switch Interface - Bluetooth HID Mode")
print("Feather ESP32-S3 Rev TFT")
print("=" * 40)
print(f"Loaded {len(KEYCODES)} keycodes")
print("Starting Bluetooth advertising...")
print(f"Device name: {ble.name}")
print("Waiting for connection...")
print()

update_display(current_index)

# ===== MAIN LOOP =====
while True:
    # Check Bluetooth connection
    if not ble.connected:
        if connection_status == "CONNECTED":
            print("Bluetooth disconnected")
            connection_status = "SEARCHING"
            kbd = None
            update_display(current_index)

        # Advertise
        ble.start_advertising(advertisement)

        # Wait for connection with timeout
        connection_timeout = time.monotonic() + 0.5
        while not ble.connected and time.monotonic() < connection_timeout:
            time.sleep(0.1)

        if ble.connected:
            print("Bluetooth connected!")
            connection_status = "CONNECTED"
            ble.stop_advertising()
            kbd = Keyboard(hid.devices)
            update_display(current_index)

        continue

    # Read switch states
    nav_state = switch_nav.value
    select_state = switch_select.value

    # Navigate switch pressed
    if nav_state == False and last_nav_state == True:
        current_index = (current_index + 1) % len(KEYCODES)
        update_display(current_index)
        print(f"Navigate → {KEYCODES[current_index][0]}")
        time.sleep(debounce_time)

    # Select switch pressed
    if select_state == False and last_select_state == True:
        key_name, keycode = KEYCODES[current_index]
        if send_keycode(keycode):
            update_display(current_index, "SENT!", 0x00ff88)
            print(f"Sent: {key_name}")
            time.sleep(debounce_time)
            update_display(current_index)
        else:
            update_display(current_index, "ERROR", 0xff6b6b)
            print("Error: Not connected")
            time.sleep(0.3)
            update_display(current_index)

    # Update last states
    last_nav_state = nav_state
    last_select_state = select_state

    time.sleep(0.01)
