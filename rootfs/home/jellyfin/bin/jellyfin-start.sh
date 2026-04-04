#!/bin/bash
# Wait for the local Jellyfin server, complete initial setup, then launch client
SERVER="http://localhost:8096"
AUTH_HEADER='MediaBrowser Client="JKAB", Device="JKAB", DeviceId="jkab", Version="1.0"'

LIBRARY_OPTS='{"SaveLocalMetadata":true,"SaveSubtitlesWithMedia":true,"SaveLyricsWithMedia":true,"SaveTrickplayWithMedia":true}'

# Show splash screen while waiting for the server
yad --fullscreen --no-buttons --no-escape --undecorated \
    --text-align=center --justify=center \
    --text="\n\n\n\n\nStarting Jellyfin..." \
    --text-info --fore="#ffffff" --back="#101010" \
    --fontname="Sans 24" &
SPLASH_PID=$!

# Wait for server to be ready
for i in $(seq 1 30); do
    curl -sf "$SERVER/System/Ping" >/dev/null 2>&1 && break
    sleep 2
done

# Complete setup wizard if not already done
if curl -sf "$SERVER/Startup/Configuration" >/dev/null 2>&1; then
    curl -sf -X POST "$SERVER/Startup/Configuration" \
        -H "Content-Type: application/json" \
        -d '{"UICulture":"en-US","MetadataCountryCode":"US","PreferredMetadataLanguage":"en"}' >/dev/null 2>&1

    curl -sf -X POST "$SERVER/Startup/User" \
        -H "Content-Type: application/json" \
        -d '{"Name":"Jellyfin","Password":"jellyfin"}' >/dev/null 2>&1

    curl -sf -X POST "$SERVER/Startup/RemoteAccess" \
        -H "Content-Type: application/json" \
        -d '{"EnableRemoteAccess":true,"EnableAutomaticPortMapping":false}' >/dev/null 2>&1

    curl -sf -X POST "$SERVER/Startup/Complete" >/dev/null 2>&1

    # Save metadata alongside media files (survives image reflash)
    curl -sf -X POST "$SERVER/System/Configuration" \
        -H "Content-Type: application/json" \
        -d '{"ImageSavingConvention":"Compatible"}' >/dev/null 2>&1

    # Authenticate to get a token for library setup
    TOKEN=$(curl -sf -X POST "$SERVER/Users/AuthenticateByName" \
        -H "Content-Type: application/json" \
        -H "Authorization: $AUTH_HEADER" \
        -d '{"Username":"Jellyfin","Pw":"jellyfin"}' | \
        python3 -c "import sys,json; print(json.load(sys.stdin)['AccessToken'])" 2>/dev/null)

    if [ -n "$TOKEN" ]; then
        AUTH="$AUTH_HEADER, Token=\"$TOKEN\""

        # Add default media libraries — both scan /media/ so USB/SD content appears automatically
        curl -sf -X POST "$SERVER/Library/VirtualFolders?name=Movies&collectionType=movies&paths=%2Fmedia&refreshLibrary=false" \
            -H "Authorization: $AUTH" \
            -H "Content-Type: application/json" \
            -d "$LIBRARY_OPTS" >/dev/null 2>&1

        curl -sf -X POST "$SERVER/Library/VirtualFolders?name=Shows&collectionType=tvshows&paths=%2Fmedia&refreshLibrary=true" \
            -H "Authorization: $AUTH" \
            -H "Content-Type: application/json" \
            -d "$LIBRARY_OPTS" >/dev/null 2>&1
    fi
fi

# Kill splash
kill "$SPLASH_PID" 2>/dev/null
wait "$SPLASH_PID" 2>/dev/null

# Auto-detect scale factor based on resolution
SCALE=1
RES=$(xrandr 2>/dev/null | grep '\*' | head -1 | awk '{print $1}' | cut -d'x' -f1)
if [ "${RES:-0}" -ge 3840 ]; then
    SCALE=2
fi

exec jellyfinmediaplayer --fullscreen --scale-factor="$SCALE"
