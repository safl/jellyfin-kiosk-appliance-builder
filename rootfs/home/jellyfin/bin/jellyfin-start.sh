#!/bin/bash
# Wait for the local Jellyfin server, complete first-time setup, then launch client
source /etc/jkab.conf

SERVER="http://localhost:8096"
AUTH_HEADER='MediaBrowser Client="JKAB", Device="JKAB", DeviceId="jkab", Version="1.0"'
LOG=/tmp/jellyfin-setup.log

LIBRARY_OPTS="{\"PreferredMetadataLanguage\":\"$JKAB_METADATA_LANGUAGE\",\"MetadataCountryCode\":\"$JKAB_METADATA_COUNTRY\",\"SaveLocalMetadata\":true,\"SaveSubtitlesWithMedia\":true,\"SaveLyricsWithMedia\":true,\"SaveTrickplayWithMedia\":true}"

# Wait for server API to be fully ready
# The server serves an HTML splash page before the API is functional — check for JSON
WIZARD_PENDING=false
for i in $(seq 1 60); do
    if curl -sf "$SERVER/Startup/Configuration" 2>/dev/null | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
        WIZARD_PENDING=true
        break
    fi
    if curl -sf "$SERVER/System/Info/Public" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['StartupWizardCompleted']" 2>/dev/null; then
        break
    fi
    sleep 2
done

# Complete setup wizard if not already done
if [ "$WIZARD_PENDING" = true ]; then
    echo "$(date) Starting setup wizard..." >> "$LOG"

    curl -f -X POST "$SERVER/Startup/Configuration" \
        -H "Content-Type: application/json" \
        -d "{\"UICulture\":\"$JKAB_UI_CULTURE\",\"MetadataCountryCode\":\"$JKAB_METADATA_COUNTRY\",\"PreferredMetadataLanguage\":\"$JKAB_METADATA_LANGUAGE\"}" >> "$LOG" 2>&1

    # GET triggers default user creation (InitializeAsync), then POST renames it
    curl -sf "$SERVER/Startup/User" >> "$LOG" 2>&1
    curl -f -X POST "$SERVER/Startup/User" \
        -H "Content-Type: application/json" \
        -d '{"Name":"jellyfin","Password":"jellyfin"}' >> "$LOG" 2>&1

    curl -f -X POST "$SERVER/Startup/RemoteAccess" \
        -H "Content-Type: application/json" \
        -d '{"EnableRemoteAccess":true,"EnableAutomaticPortMapping":false}' >> "$LOG" 2>&1

    curl -f -X POST "$SERVER/Startup/Complete" >> "$LOG" 2>&1

    # Authenticate to configure server, user preferences, and libraries
    AUTH_RESULT=$(curl -f -X POST "$SERVER/Users/AuthenticateByName" \
        -H "Content-Type: application/json" \
        -H "Authorization: $AUTH_HEADER" \
        -d '{"Username":"jellyfin","Pw":"jellyfin"}' 2>> "$LOG")

    TOKEN=$(echo "$AUTH_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['AccessToken'])" 2>/dev/null)
    USER_ID=$(echo "$AUTH_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['User']['Id'])" 2>/dev/null)

    if [ -n "$TOKEN" ]; then
        AUTH="$AUTH_HEADER, Token=\"$TOKEN\""
        echo "$(date) Authenticated, configuring..." >> "$LOG"

        # Update server configuration (requires full object — GET, merge, POST)
        SERVER_CONFIG=$(curl -sf "$SERVER/System/Configuration" -H "Authorization: $AUTH")
        SERVER_CONFIG=$(echo "$SERVER_CONFIG" | python3 -c "
import sys, json
c = json.load(sys.stdin)
c['UICulture'] = '$JKAB_UI_CULTURE'
c['MetadataCountryCode'] = '$JKAB_METADATA_COUNTRY'
c['PreferredMetadataLanguage'] = '$JKAB_METADATA_LANGUAGE'
c['ImageSavingConvention'] = 'Compatible'
print(json.dumps(c))
" 2>/dev/null)
        curl -f -X POST "$SERVER/System/Configuration" \
            -H "Authorization: $AUTH" \
            -H "Content-Type: application/json" \
            -d "$SERVER_CONFIG" >> "$LOG" 2>&1

        # Set user preferences (subtitle/audio language)
        curl -f -X POST "$SERVER/Users/$USER_ID/Configuration" \
            -H "Authorization: $AUTH" \
            -H "Content-Type: application/json" \
            -d "{\"AudioLanguagePreference\":\"$JKAB_AUDIO_LANGUAGE\",\"SubtitleLanguagePreference\":\"$JKAB_SUBTITLE_LANGUAGE\",\"SubtitleMode\":\"$JKAB_SUBTITLE_MODE\",\"PlayDefaultAudioTrack\":true,\"RememberAudioSelections\":true,\"RememberSubtitleSelections\":true}" >> "$LOG" 2>&1

        # Create media libraries — both scan /media/ so USB/SD content appears automatically
        curl -f -X POST "$SERVER/Library/VirtualFolders?name=Movies&collectionType=movies&paths=%2Fmedia&refreshLibrary=false" \
            -H "Authorization: $AUTH" \
            -H "Content-Type: application/json" \
            -d "$LIBRARY_OPTS" >> "$LOG" 2>&1

        curl -f -X POST "$SERVER/Library/VirtualFolders?name=Shows&collectionType=tvshows&paths=%2Fmedia&refreshLibrary=true" \
            -H "Authorization: $AUTH" \
            -H "Content-Type: application/json" \
            -d "$LIBRARY_OPTS" >> "$LOG" 2>&1

        echo "$(date) Setup complete" >> "$LOG"
    else
        echo "$(date) Authentication failed" >> "$LOG"
    fi
else
    echo "$(date) Wizard already completed, skipping setup" >> "$LOG"
fi

# Auto-detect scale factor based on display resolution
SCALE=1
RES=$(cat /sys/class/drm/card*-*/modes 2>/dev/null | head -1 | cut -dx -f1)
if [ "${RES:-0}" -ge 3840 ]; then
    SCALE=2
fi

exec jellyfinmediaplayer --fullscreen --scale-factor="$SCALE"
