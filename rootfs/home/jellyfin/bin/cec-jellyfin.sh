#!/bin/bash
cec-client -d 1 2>/tmp/cec-bridge.log | while read -r line; do
  case "$line" in
    *"key: up"*) xdotool key Up ;;
    *"key: down"*) xdotool key Down ;;
    *"key: left"*) xdotool key Left ;;
    *"key: right"*) xdotool key Right ;;
    *"key: select"*) xdotool key Return ;;
    *"key: back"*) xdotool key Escape ;;
    *"key: exit"*) xdotool key Escape ;;
    *"key: play"*) xdotool key space ;;
    *"key: pause"*) xdotool key space ;;
    *"key: stop"*) xdotool key s ;;
  esac
done
