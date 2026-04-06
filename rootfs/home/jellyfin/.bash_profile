# Auto-start X on tty1 only
if [ "$(tty)" = "/dev/tty1" ]; then
    while true; do
        startx -- -keeptty > /tmp/xorg.log 2>&1
        sleep 2
    done
fi
