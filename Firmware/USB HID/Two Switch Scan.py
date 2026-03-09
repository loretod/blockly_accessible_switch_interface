"""
Switch Interface for Adafruit Feather ESP32-S3 Rev TFT
USB HID Version - Wired Connection
Uses built-in 1.14" 240x135 color TFT display
Compatible with CircuitPython
"""

import time
import board
import digitalio
import displayio
import terminalio
# Starting in CircuitPython 9.x fourwire will be a seperate internal library
# rather than a component of the displayio library
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
# ===== FIXED PIN & DISPLAY INITIALIZATION =====
# ===============================================

print("\nInitializing display...")
displayio.release_displays()

# Set up the SPI bus and control pins
spi = board.SPI()
tft_cs = board.TFT_CS     # Chip Select
tft_dc = board.TFT_DC     # Data/Command
tft_reset = board.TFT_RESET # Reset pin
tft_backlight = board.TFT_BACKLIGHT # Backlight pin

display_bus = FourWire(
    spi,
    command=tft_dc,
    chip_select=tft_cs,
    reset=tft_reset,
    baudrate=24000000
)

# Initialize the ST7789 display (240x135 with offsets)
display = adafruit_st7789.ST7789(
    display_bus,
    width=240,
    height=135,
    rowstart=40,
    colstart=52,
    rotation=270,
    bgr=True
)

# Manually enable the backlight pin
backlight = digitalio.DigitalInOut(tft_backlight)
backlight.direction = digitalio.Direction.OUTPUT
backlight.value = True

print("Display initialized!")
# ===============================================
# LED setup
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT

# ===== SWITCH PINS (Using A1 for NAV, A2 for SEL) =====

# Both pins use PULL_UP. Button must be wired between the pin (A1/A2) and GND.
# Pressed state is False (LOW).

# Navigation Switch (A1)
switch_nav = digitalio.DigitalInOut(board.A1)
switch_nav.direction = digitalio.Direction.INPUT
switch_nav.pull = digitalio.Pull.UP

# Select Switch (A2)
switch_select = digitalio.DigitalInOut(board.A2)
switch_select.direction = digitalio.Direction.INPUT
switch_select.pull = digitalio.Pull.UP

# Button setup
button0 = digitalio.DigitalInOut(board.D0)
button0.switch_to_input(pull=digitalio.Pull.UP)

button1 = digitalio.DigitalInOut(board.D1)
button1.switch_to_input(pull=digitalio.Pull.DOWN)

button2 = digitalio.DigitalInOut(board.D2)
button2.switch_to_input(pull=digitalio.Pull.DOWN)

last_nav_state = switch_nav.value
last_select_state = switch_select.value

debounce_time = 0.1 # Small debounce for switch presses

# ===== USB HID SETUP =====
time.sleep(1) # Delay for USB to be ready
keyboard = Keyboard(usb_hid.devices)

# ===============================================
# ===== KEYCODES AND SYMBOL DEFINITIONS (New) =====
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
    "enter": "e", # Unicode Enter/Return symbol
    "arrow left": "L",
    "arrow up": "U",
    "delete": "x", # Unicode Delete/Backspace symbol
    "w": "W",
    "t": "T",
}

current_index = 0

# ===============================================
# ===== DISPLAY FUNCTIONS (Updated Layout) =====
# ===============================================

# Define the root display group
splash = displayio.Group()
display.root_group = splash

# Helper to create a solid color background tile
def create_background(color, x, y, width, height):
    color_bitmap = displayio.Bitmap(width, height, 1)
    color_palette = displayio.Palette(1)
    color_palette[0] = color
    return displayio.TileGrid(color_bitmap, pixel_shader=color_palette, x=x, y=y)

def update_display(index, flash_color=None):
    global splash

    # Clear previous content
    while splash:
        splash.pop()

    # Screen dimensions
    SCREEN_WIDTH = 240
    SCREEN_HEIGHT = 135

    # Pane dimensions
    LEFT_WIDTH = SCREEN_WIDTH // 4      # 60px
    RIGHT_WIDTH = SCREEN_WIDTH - LEFT_WIDTH # 180px

    # Colors
    PURPLE = 0x800080
    LIGHT_GRAY = 0xAAAAAA
    WHITE = 0xFFFFFF

    # --- 1. Right Pane (3/4 - Current Value) ---
    current_key_name = KEYCODES[index][0]
    current_symbol = KEY_SYMBOLS.get(current_key_name, "?")

    # Background (3/4 - Purple)
    right_bg = create_background(PURPLE, LEFT_WIDTH, 0, RIGHT_WIDTH, SCREEN_HEIGHT)
    splash.append(right_bg)

    # Symbol Label (Largest size, centered)
    # Using scale=9 for a large, centered character
    current_label = label.Label(
        terminalio.FONT,
        text=current_symbol,
        color=WHITE,
        scale=9,
        anchor_point=(0.5, 0.5), # Anchor at center of text
        anchored_position=(LEFT_WIDTH + RIGHT_WIDTH // 2, SCREEN_HEIGHT // 2)
    )
    splash.append(current_label)

    # --- 2. Left Pane (1/4 - Next Value) ---
    next_index = (index + 1) % len(KEYCODES)
    next_key_name = KEYCODES[next_index][0]
    next_symbol = KEY_SYMBOLS.get(next_key_name, "?")

    # Background (1/4 - Light Gray)
    left_bg = create_background(LIGHT_GRAY, 0, 0, LEFT_WIDTH, SCREEN_HEIGHT)
    splash.append(left_bg)

    # Next Symbol Label (Smaller size, centered)
    # Using scale=3
    next_label = label.Label(
        terminalio.FONT,
        text=next_symbol,
        color=PURPLE,
        scale=3,
        anchor_point=(0.5, 0.5),
        anchored_position=(LEFT_WIDTH // 2, SCREEN_HEIGHT // 2)
    )
    splash.append(next_label)

    # --- 3. Optional Flash (for SENT! confirmation) ---
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


# Function to send the keycode
def send_keycode(keycode):
    try:
        keyboard.press(*keycode)
        time.sleep(0.05)
        keyboard.release_all()
        return True
    except Exception as e:
        print(f"Error sending keycode: {e}")
        return False

# ===== STARTUP =====
print("=" * 40)
print("Switch Interface - USB HID Mode")
print("Feather ESP32-S3 Rev TFT")
print("=" * 40)
print(f"Loaded {len(KEYCODES)} keycodes")

# Test display
print("Initializing display...")
update_display(current_index)
print("Display initialized!")
print("Ready! Pins A1 (NAV) and A2 (SEL) are active.")
print("Check the serial console for real-time pin debugging.")
print()

# ===== MAIN LOOP =====
while True:
    try:
        # Read switch states (True = unpressed, False = pressed when wired to GND)
        nav_state = switch_nav.value
        select_state = switch_select.value

        # Check Button D0
        if not button0.value:  # button0 is active (Pull.UP, active LOW)
            print("Button D0 pressed")
            led.value = True
        # Check Button D1
        elif button1.value:  # button1 is active (Pull.DOWN, active HIGH)
            print("Button D1 pressed")
            led.value = True
        # Check Button D2
        elif button2.value:  # button2 is active (Pull.DOWN, active HIGH)
            print("Button D2 pressed")
            led.value = True
        else:
            led.value = False  # No buttons are pressed, turn off the LED

        # DEBUGGING: Print the current raw state of the switches
        print(f"Pin States: NAV (A1)={nav_state}, SEL (A2)={select_state}")

        # Navigate switch pressed (A1: falling edge/LOW=pressed)
        if nav_state == False and last_nav_state == True:
            current_index = (current_index + 1) % len(KEYCODES)
            update_display(current_index)
            print(f"EVENT: Navigate → {KEYCODES[current_index][0]}")
            time.sleep(debounce_time)

        # Select switch pressed (A2: falling edge/LOW=pressed)
        if select_state == False and last_select_state == True:
            key_name, keycode = KEYCODES[current_index]
            if send_keycode(keycode):
                # Flash the screen green for 100ms on success
                update_display(current_index, flash_color=0x00FF00) # Green
                print(f"EVENT: Sent: {key_name}")
                time.sleep(0.1) # brief delay for flash
                update_display(current_index) # Restore normal display
            else:
                # Flash the screen red on failure
                update_display(current_index, flash_color=0xFF0000) # Red
                print(f"EVENT: Failed to send: {key_name}")
                time.sleep(0.1)
                update_display(current_index)

        # Update last states
        last_nav_state = nav_state
        last_select_state = select_state

        time.sleep(0.01)

    except RuntimeError as e:
        # Handle USB errors if cable is unplugged
        print(f"RuntimeError: {e}")
        time.sleep(1.0)
    except Exception as e:
        # Catch all other exceptions
        print(f"An unexpected error occurred: {e}")
        time.sleep(1.0)
