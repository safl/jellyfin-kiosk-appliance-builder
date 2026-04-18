#!/bin/bash
# Start jkab-server and launch jkab-player

# Wait for jkab-server to be ready (health check)
for i in $(seq 1 30); do
    if curl -sf http://localhost:8080/api/health >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Launch JKAB player
exec python3 /home/jellyfin/bin/jkab-player.py
