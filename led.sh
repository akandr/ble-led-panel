#!/usr/bin/env bash
# Control the B.K.Light / iPixel Color 64x16 BLE panel (advertises as LED_BLE_xxxx).
# Usage:
#   ./led.sh scan
#   ./led.sh text "Hello" [animation=scroll_left] [speed=70] [color=00ff88]
#   ./led.sh image photo.png            # any image, fit to 64x16
#   ./led.sh gif anim.gif [slot]        # upload gif, optionally store in slot 1-9
#   ./led.sh video clip.mp4 [seconds] [fps]   # ffmpeg -> 64x16 GIF -> upload (default 10 s, 12 fps)
#   ./led.sh clock | bright 1-100 | off | on | info | clear
set -euo pipefail
ADDR="${LED_ADDR:?set LED_ADDR to the panel address from ./led.sh scan (MAC on Linux, UUID on macOS)}"
PX="${PYPIXEL:-$(dirname "$0")/venv/bin/pypixelcolor}"
[ -x "$PX" ] || PX=pypixelcolor
W=64; H=16
cmd="${1:-}"; shift || true
case "$cmd" in
  scan)   "$PX" --scan ;;
  info)   "$PX" -a "$ADDR" -c get_device_info ;;
  text)   "$PX" -a "$ADDR" -c send_text "$@" ;;
  image)  "$PX" -a "$ADDR" -c send_image "$1" resize_method=fit ;;
  gif)    "$PX" -a "$ADDR" -c send_image "$1" ${2:+save_slot=$2} ;;
  video)
    in="$1"; secs="${2:-10}"; fps="${3:-12}"; out="${TMPDIR:-/tmp}/led_$(basename "${in%.*}").gif"
    ffmpeg -hide_banner -loglevel error -y -t "$secs" -i "$in" \
      -vf "fps=$fps,scale=$W:$H:force_original_aspect_ratio=increase,crop=$W:$H,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=bayer" \
      "$out"
    echo "GIF: $out ($(du -k "$out" | cut -f1) KB) -- keep under ~50 KB" >&2
    "$PX" -a "$ADDR" -c send_image "$out" ;;
  clock)  "$PX" -a "$ADDR" -c set_clock_mode ;;
  bright) "$PX" -a "$ADDR" -c set_brightness "$1" ;;
  off)    "$PX" -a "$ADDR" -c set_power false ;;
  on)     "$PX" -a "$ADDR" -c set_power true ;;
  clear)  "$PX" -a "$ADDR" -c clear ;;
  *) sed -n 2,10p "$0"; exit 1 ;;
esac
