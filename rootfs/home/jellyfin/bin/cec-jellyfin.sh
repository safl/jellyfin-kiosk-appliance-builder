#!/bin/bash
cec-client -d 1 2>/tmp/cec-bridge.log | while read -r line; do
  case "$line" in
    *"key pressed: up"*) xdotool key Up ;;
    *"key pressed: down"*) xdotool key Down ;;
    *"key pressed: left"*) xdotool key Left ;;
    *"key pressed: right"*) xdotool key Right ;;
    *"key pressed: select"*) xdotool key Return ;;
    *"key pressed: exit"*) xdotool key Escape ;;
    *"key pressed: play"*) xdotool key space ;;
    *"key pressed: pause"*) xdotool key space ;;
    *"key pressed: stop"*) xdotool key s ;;
  esac
done
