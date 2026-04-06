#!/usr/bin/env python3
"""CEC-to-keyboard bridge using libcec (like Kodi does internally)"""
import cec
import subprocess
import time

KEY_MAP = {
    0x01: "Up",
    0x02: "Down",
    0x03: "Left",
    0x04: "Right",
    0x00: "Return",    # Select
    0x0D: "Escape",    # Exit/Back
    0x44: "space",     # Play
    0x46: "space",     # Pause
    0x45: "s",         # Stop
    0x48: "BackSpace", # Rewind
    0x49: "BackSpace", # Fast forward
}

LOG = "/tmp/cec-bridge.log"

def log(msg):
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

def on_keypress(event, key, duration):
    if duration > 0:
        return
    name = KEY_MAP.get(key)
    if name:
        log(f"key {key:#04x} -> {name}")
        subprocess.run(["xdotool", "key", name])
    else:
        log(f"key {key:#04x} UNMAPPED")

log("Starting CEC bridge")
cec.init()
log("CEC initialized")
cec.add_callback(on_keypress, cec.EVENT_KEYPRESS)
log("Callback registered")
cec.set_active_source()
log("Active source set — waiting for keys")

count = 0
while True:
    time.sleep(1)
    count += 1
    if count % 30 == 0:
        cec.set_active_source()
        log("Re-asserted active source")
