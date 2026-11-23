#!/system/bin/sh
# Retimet Xiaomi HSR_120 recordings to play 4x slower (120fps -> 30fps).
# tanzanite's vendor does not expose CamSupportedSlowMotion, so MiuiCamera
# writes a 120fps track without SlowMotion_Data and gallery plays it normally.

CAMDIR=${CAMDIR:-/sdcard/DCIM/Camera}
MARKDIR=/data/local/tmp/miuicamera_slowmo_done
PIDFILE=/data/local/tmp/miuicamera_slowmo_watch.pid
mkdir -p "$MARKDIR" 2>/dev/null

u32hex() {
    od -An -tx1 -j "$2" -N4 "$1" 2>/dev/null | tr -d ' \n'
}

put32() {
    _f=$1; _off=$2; _v=$3
    _esc=$(printf '\\x%02x\\x%02x\\x%02x\\x%02x' \
        $((_v >> 24)) $(((_v >> 16) & 255)) \
        $(((_v >> 8) & 255)) $((_v & 255)))
    printf "$_esc" | dd of="$_f" bs=1 seek="$_off" conv=notrunc 2>/dev/null
}

patch_one() {
    _file=$1
    _base=$(basename "$_file")
    _stts=$(grep -abo stts "$_file" 2>/dev/null | head -1 | cut -d: -f1)
    _mvhd=$(grep -abo mvhd "$_file" 2>/dev/null | head -1 | cut -d: -f1)
    [ -n "$_stts" ] && [ -n "$_mvhd" ] || return 1

    _cnt=$((16#$(u32hex "$_file" $((_stts + 8)))))
    _first=$((16#$(u32hex "$_file" $((_stts + 12 + 4)))))
    # already retimed
    [ "$_first" -ge 3000 ] && return 0

    _total=0
    _i=0
    while [ "$_i" -lt "$_cnt" ]; do
        _p=$((_stts + 12 + _i * 8))
        _samples=$((16#$(u32hex "$_file" "$_p")))
        _delta=$((16#$(u32hex "$_file" $((_p + 4)))))
        put32 "$_file" $((_p + 4)) $((_delta * 4))
        _total=$((_total + _samples * _delta * 4))
        _i=$((_i + 1))
    done

    # video mdhd = the one with timescale 90000
    for _m in $(grep -abo mdhd "$_file" 2>/dev/null | cut -d: -f1); do
        _ts=$((16#$(u32hex "$_file" $((_m + 16)))))
        if [ "$_ts" -eq 90000 ]; then
            put32 "$_file" $((_m + 20)) "$_total"
            break
        fi
    done

    _movdur=$((_total / 9))   # 90000 -> 10000 timescale
    put32 "$_file" $((_mvhd + 20)) "$_movdur"
    _tk=$(grep -abo tkhd "$_file" 2>/dev/null | head -1 | cut -d: -f1)
    [ -n "$_tk" ] && put32 "$_file" $((_tk + 28)) "$_movdur"

    # disable the audio track: it would stop after the original duration
    _tk2=$(grep -abo tkhd "$_file" 2>/dev/null | sed -n 2p | cut -d: -f1)
    if [ -n "$_tk2" ]; then
        _fl=$((16#$(u32hex "$_file" $((_tk2 + 4)))))
        put32 "$_file" $((_tk2 + 4)) $((_fl & 0xfffffffe))
    fi

    echo "retimed $_base: $_cnt entries, $((_total / 90000))s" >> "$MARKDIR/log"
    touch "$MARKDIR/$_base"
}

if [ "$1" = "--once" ]; then
    for f in "$CAMDIR"/*_HSR_120.mp4; do
        [ -f "$f" ] || continue
        b=$(basename "$f")
        [ -e "$MARKDIR/$b" ] && continue
        patch_one "$f"
    done
    exit 0
fi

# kill previous watcher if still alive
if [ -f "$PIDFILE" ]; then
    old=$(cat "$PIDFILE" 2>/dev/null)
    if [ -n "$old" ] && [ -d "/proc/$old" ]; then
        kill "$old" 2>/dev/null
    fi
fi
echo $$ > "$PIDFILE"

while true; do
    now=$(date +%s)
    for f in "$CAMDIR"/*_HSR_120.mp4; do
        [ -f "$f" ] || continue
        b=$(basename "$f")
        [ -e "$MARKDIR/$b" ] && continue
        mt=$(stat -c %Y "$f" 2>/dev/null || echo 0)
        [ $((now - mt)) -ge 8 ] || continue
        patch_one "$f"
    done
    sleep 5
done
