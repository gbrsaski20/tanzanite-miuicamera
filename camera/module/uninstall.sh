#!/system/bin/sh
# Clean up runtime state so a re-flash starts from a known state.

PIDFILE=/data/local/tmp/miuicamera_slowmo_watch.pid
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE" 2>/dev/null)
    [ -n "$PID" ] && kill "$PID" 2>/dev/null
    rm -f "$PIDFILE"
fi

rm -rf /data/local/tmp/miuicamera_slowmo_done 2>/dev/null
rm -f /data/local/tmp/micam_status.txt /data/local/tmp/micam_crash.txt 2>/dev/null
rm -f /sdcard/micam_status.txt /sdcard/micam_crash.txt 2>/dev/null

exit 0
