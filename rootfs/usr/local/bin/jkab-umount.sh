#!/bin/bash
# Unmount removable media
DEVICE="/dev/$1"
MOUNT=$(findmnt -n -o TARGET "$DEVICE" 2>/dev/null)

if [ -n "$MOUNT" ]; then
    umount "$MOUNT"
    rmdir "$MOUNT" 2>/dev/null
fi
