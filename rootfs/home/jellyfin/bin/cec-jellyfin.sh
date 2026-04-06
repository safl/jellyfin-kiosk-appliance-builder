#!/bin/bash
# Map HDMI CEC remote keys to keyboard input via xdotool
LOG=/tmp/cec-bridge.log
MAX_LOG_SIZE=1048576  # 1 MB

rotate_log() {
    if [ -f "$LOG" ] && [ "$(stat -c%s "$LOG" 2>/dev/null)" -ge "$MAX_LOG_SIZE" ]; then
        mv "$LOG" "$LOG.old"
    fi
}

cec-client -d 1 2>>"$LOG" | while read -r line; do
  echo "$(date '+%H:%M:%S') $line" >> "$LOG"
  rotate_log
  case "$line" in
    *"key pressed: up"*)     xdotool key Up ;;
    *"key pressed: down"*)   xdotool key Down ;;
    *"key pressed: left"*)   xdotool key Left ;;
    *"key pressed: right"*)  xdotool key Right ;;
    *"key pressed: select"*) xdotool key Return ;;
    *"key pressed: exit"*)   xdotool key Escape ;;
    *"key pressed: play"*)   xdotool key space ;;
    *"key pressed: pause"*)  xdotool key space ;;
    *"key pressed: stop"*)   xdotool key s ;;
    *)                       echo "$(date '+%H:%M:%S') UNMATCHED: $line" >> "$LOG" ;;
  esac
done
