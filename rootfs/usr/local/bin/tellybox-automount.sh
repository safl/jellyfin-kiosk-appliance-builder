#!/bin/bash
# Auto-mount removable USB/SD media under /media/<label>.
#
# Sanitizes the filesystem label and avoids collisions with the indexer's
# virtual category names (Movies, Shows) or with already-mounted drives by
# appending a numeric suffix.
set -eu

DEVICE="/dev/$1"
RAW_LABEL=$(blkid -s LABEL -o value "$DEVICE" 2>/dev/null || true)
[ -n "$RAW_LABEL" ] || RAW_LABEL="$1"

# Sanitize: strip path separators and whitespace, fall back to device name
SAFE_LABEL=$(printf '%s' "$RAW_LABEL" | tr -c '[:alnum:]._-' '_' | sed 's/^_*//;s/_*$//')
[ -n "$SAFE_LABEL" ] || SAFE_LABEL="$1"

reserved() {
    case "${1,,}" in
        movies|shows) return 0 ;;
        *) return 1 ;;
    esac
}

TARGET="$SAFE_LABEL"
if reserved "$TARGET" || [ -e "/media/$TARGET" ]; then
    i=1
    while [ -e "/media/${SAFE_LABEL}_${i}" ]; do
        i=$((i+1))
    done
    TARGET="${SAFE_LABEL}_${i}"
fi

MOUNT="/media/${TARGET}"
mkdir -p "$MOUNT"
systemd-mount --no-block --collect "$DEVICE" "$MOUNT"
