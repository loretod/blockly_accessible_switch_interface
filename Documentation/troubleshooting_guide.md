# Switch Interface Troubleshooting Guide

## Quick Diagnostic Checklist
Before diving into specific issues, verify these basics:
- [ ] CircuitPython 9.0+ or 10.x is installed
- [ ] TinyUF2 Bootloader was updated
- [ ] All required libraries are in the `lib` folder
- [ ] USB cable is a data cable (not charge-only)
- [ ] Switches are normally-open momentary type
- [ ] Board backlight is on (screen should glow)
- [ ] Serial console shows no error messages

---

## Display Issues

### Problem: Display is completely blank/black
**Symptoms:** Screen is dark, no text visible, but device appears powered

**Solutions:**
1. **Check backlight pin**
   - Open serial console and look for "Backlight enabled" message
   - If missing, backlight pin detection failed
   - Manually set backlight: `backlight = digitalio.DigitalInOut(board.D45)`

2. **Verify display initialization**
   - Serial console should show "Display initialized: 240x135"
   - If you see "AttributeError: 'NoneType'", display failed to initialize
   - Check that `adafruit_st7789.mpy` is in the `lib` folder

3. **Test with simple code**
   ```python
   import board
   import displayio
   import terminalio
   from adafruit_display_text import label
   
   displayio.release_displays()
   spi = board.SPI()
   display_bus = displayio.FourWire(spi, command=board.D6, 
                                     chip_select=board.D5, reset=board.D9)
   import adafruit_st7789
   display = adafruit_st7789.ST7789(display_bus, width=240, height=135,
                                     rotation=270, rowstart=40, colstart=53)
   
   splash = displayio.Group()
   text = label.Label(terminalio.FONT, text="TEST", color=0xFFFFFF, x=50, y=50, scale=3)
   splash.append(text)
   display.root_group = splash
   ```

4. **Library version mismatch**
   - CircuitPython 10.x requires 10.x libraries
   - Download matching library bundle from circuitpython.org/libraries
   - Delete old libraries and install fresh ones

### Problem: Display shows garbage/corrupted text
**Symptoms:** Screen shows random pixels, wrong colors, or garbled text

**Solutions:**
1. **Check SPI configuration**
   - Baudrate too high: Lower from 24MHz to 12MHz
   - Change: `spi.configure(baudrate=12000000)`

2. **Verify rotation and offsets**
   - Wrong rotation causes display issues
   - Ensure: `rotation=270, rowstart=40, colstart=53`
   - Try rotation values: 0, 90, 180, 270

3. **Power supply issue**
   - USB port may not provide enough power
   - Try different USB port or powered hub

### Problem: Display works but text is too dim
**Symptoms:** Can barely see text, very faint display

**Solutions:**
1. **Backlight not fully on**
   - Verify backlight pin: `backlight.value = True`
   - Try toggling: `backlight.value = False` then `backlight.value = True`

2. **Check power**
   - Low USB power can dim display
   - Test with different USB cable

---

## Switch Input Issues

### Problem: Switches don't respond at all
**Symptoms:** Pressing switches does nothing, no navigation or selection

**Solutions:**
1. **Test switch continuity**
   - Use multimeter to verify switch closes circuit when pressed
   - Check 3.5mm jack wiring: Tip and Sleeve should connect when pressed
   - Verify jack is fully inserted

2. **Check pin connections**
   - Navigate switch: Jack tip → A0, sleeve → GND
   - Select switch: Jack tip → A1, sleeve → GND
   - Verify solder joints are solid

3. **Test pins in serial console**
   - Add debug code:
   ```python
   print(f"A0 value: {switch_nav.value}")
   print(f"A1 value: {switch_select.value}")
   ```
   - Should show `True` when not pressed, `False` when pressed

4. **Wrong switch type**
   - Device requires **normally-open** switches
   - Normally-closed switches will behave reversed
   - Latching switches won't work (must be momentary)

### Problem: Switches trigger erratically or double-trigger
**Symptoms:** Single press causes multiple actions, unpredictable behavior

**Solutions:**
1. **Increase debounce time**
   - Default is 0.2 seconds
   - Increase: `debounce_time = 0.3` or `0.4`
   - Helps with bouncy mechanical switches

2. **Check for loose connections**
   - Wiggle jack while testing
   - Resolder connections if intermittent
   - Verify jack is firmly mounted

3. **Electrical noise**
   - Add small capacitor (0.1µF) across switch terminals
   - Keep switch wires short and away from power wires
   - Use shielded cable if available

### Problem: Only one switch works
**Symptoms:** One switch navigates/selects correctly, other does nothing

**Solutions:**
1. **Verify both pins configured**
   - Check both `switch_nav` and `switch_select` are defined
   - Ensure both have `pull = digitalio.Pull.UP`

2. **Test individual pins**
   - Swap switch connections to isolate problem
   - If problem follows the switch → bad switch/cable
   - If problem stays with pin → check code/wiring

3. **Pin conflict**
   - Ensure A1 and A2 aren't used elsewhere
   - Check for pin conflicts with display or other features

---

## USB HID / Keyboard Issues

### Problem: Keystrokes not received by computer
**Symptoms:** Display shows "SENT!" but computer doesn't respond

**Solutions:**
1. **Check USB HID initialization**
   - Serial console should show "USB HID Keyboard initialized"
   - If missing, HID failed to initialize
   - Try unplugging and replugging USB

2. **Verify computer recognizes device**
   - **Windows:** Device Manager → Human Interface Devices → "Adafruit Feather ESP32-S3"
   - **Mac:** System Information → USB → Look for keyboard device
   - **Linux:** `lsusb` should show Adafruit device

3. **Test with text editor**
   - Open Notepad/TextEdit
   - Click inside to give it focus
   - If works in editor but not other apps → app-specific issue

4. **Security software blocking**
   - Antivirus may block USB HID devices
   - Temporarily disable to test
   - Add exception for CircuitPython device

### Problem: Wrong keys being sent
**Symptoms:** Press switch, but wrong character appears

**Solutions:**
1. **Verify keycode mapping**
   - Check KEYCODES array matches display
   - Ensure index is correct
   - Common mistake: Display shows one key but sends another

2. **Keyboard layout mismatch**
   - Some keys depend on OS keyboard layout
   - Test with basic keys first (letters, numbers, arrows)
   - Avoid symbols if layout uncertain

3. **Stuck modifier keys**
   - If SHIFT/CTRL/ALT stuck, all keys will be wrong
   - Add to code: `keyboard.release_all()` before every send

---

## CircuitPython Issues

### Problem: Code doesn't auto-reload
**Symptoms:** Changes to code.py don't take effect

**Solutions:**
1. **Manual reload**
   - Press CTRL+D in serial console
   - Or press physical RESET button
   - Or save code.py again

2. **Auto-reload disabled**
   - Check for `supervisor.disable_autoreload()`
   - Remove or comment out

3. **USB connection issue**
   - Unplug and replug USB
   - Try different USB cable/port
   - Check CIRCUITPY drive is mounted

### Problem: "ImportError" for libraries
**Symptoms:** Error says module not found

**Solutions:**
1. **Library not installed**
   - Download CircuitPython library bundle
   - Match version to your CircuitPython version
   - Copy required libraries to `lib` folder

2. **Wrong library version**
   - CircuitPython 10.x needs 10.x libraries
   - Check bundle version number
   - Delete old libraries and reinstall

3. **Library name mismatch**
   - Ensure exact spelling: `adafruit_display_text` (folder)
   - Not `.mpy` files for folders
   - Check capitalization

### Problem: "MemoryError" when running code
**Symptoms:** Code runs then crashes with memory error

**Solutions:**
1. **Too many libraries**
   - Remove unused imports
   - Use `.mpy` compiled libraries instead of `.py`
   - Delete unused libraries from `lib`

2. **Display groups too large**
   - Reduce number of label objects
   - Simplify graphics
   - Reuse groups instead of creating new ones

3. **Firmware issue**
   - Update to latest CircuitPython
   - Try stable vs. beta versions

---

## Common Error Messages

| Error | Meaning | Solution |
|-------|---------|----------|
| `AttributeError: 'module' object has no attribute 'TFT_CS'` | Pin names changed in CP version | Use pin detection code or manual pin assignment |
| `AttributeError: 'NoneType' object has no attribute 'width'` | Display failed to initialize | Check display libraries and initialization code |
| `ImportError: no module named 'adafruit_st7789'` | Missing display driver | Install `adafruit_st7789.mpy` in lib folder |
| `OSError: [Errno 19] No such device` | USB HID not available | Check `usb_hid` is enabled in boot.py |
| `ValueError: Not a valid keycode` | Wrong keycode constant | Use `Keycode.NAME` format, check spelling |
| `MemoryError` | Out of RAM | Remove unused code/libraries, use .mpy files |

---

## Still Having Issues?

### Diagnostic Code
Run this to check your setup:
```python
import board
import supervisor
print(f"CircuitPython version: {supervisor.runtime.version}")
print(f"Board: {board.board_id}")
print("Available pins:", dir(board))
```

### Where to Get Help
1. [**Adafruit Forums**](forums.adafruit.com)
2. [**CircuitPython Discord**](adafru.it/discord)
3. **GitHub Issues:** [Project repository Issues](https://github.com/loretod/blockly_accessible_switch_interface/issues)

### Before Asking for Help
Include this information:
- CircuitPython version
- Board type (Feather ESP32-S3 Rev TFT)
- Libraries installed (and versions)
- Complete error message from serial console
- What you've already tried
- Photo of wiring if relevant

---

## Safety Reminder
If experiencing any of these issues, **stop use immediately**:
- 🔥 Burning smell or smoke
- ⚡ Sparks or short circuits
- 💧 Water damage or moisture inside