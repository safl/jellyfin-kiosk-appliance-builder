#!/bin/bash
# Auto-mount removable media
DEVICE="/dev/$1"
LABEL=$(blkid -s LABEL -o value "$DEVICE" 2>/dev/null || echo "$1")
MOUNT="/media/${LABEL}"

mkdir -p "$MOUNT"
mount "$DEVICE" "$MOUNT"
