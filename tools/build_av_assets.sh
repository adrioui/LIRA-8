#!/usr/bin/env bash
# Build the A/V assets for the LIRA-8 glitch patch.
#
# Produces, into the output directory:
#   video_audio.wav  48kHz mono, for the RAVE water model (which is mono at 48k)
#   clean.mp4        h264 intermediate, single I-frame per GOP, no B-frames
#   mosh.mp4         the same stream with its I-frames dropped (datamoshed)
#
# Why the extra hop: a datamosh lives in the compressed bitstream, so the stream
# has to be MPEG-4 Part 2 with B-frames disabled before frames can be removed.
# Gem's AVFoundation film plugin cannot be relied on for MPEG-4 Part 2 in AVI,
# so the moshed stream is re-encoded to h264 afterwards. The melt is in the
# decoded pixels, so it survives that transcode.
set -euo pipefail

SRC="${1:?usage: build_av_assets.sh <source-video> [out-dir]}"
OUT="${2:-$(cd "$(dirname "$0")/.." && pwd)/LIRA-8_Pd_Standalone/av}"
# Optional trim, in seconds. START=8 DUR=22 keeps the 00:08-00:30 section.
# Empty means the whole file.
START="${START:-}"
DUR="${DUR:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$OUT"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

say() { printf '\n== %s\n' "$*"; }

say "source"
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,nb_frames,codec_name \
  -of default=noprint_wrappers=1 "$SRC"

TRIM_ARGS=()
if [ -n "$START" ]; then TRIM_ARGS+=( -ss "$START" ); fi
if [ -n "$DUR" ]; then TRIM_ARGS+=( -t "$DUR" ); fi
[ ${#TRIM_ARGS[@]} -gt 0 ] && printf 'trim: %s\n' "${TRIM_ARGS[*]}"

say "audio -> 48kHz mono (the RAVE model is mono at 48kHz)"
ffmpeg -y -v error "${TRIM_ARGS[@]}" -i "$SRC" -vn -ac 1 -ar 48000 -c:a pcm_s16le "$OUT/video_audio.wav"
ffprobe -v error -show_entries stream=sample_rate,channels,duration \
  -of default=noprint_wrappers=1 "$OUT/video_audio.wav"

say "encode MPEG-4 Part 2, no B-frames, forced I-frame interval"
# GOP sets the melt density: the encoder emits an I-frame every GOP frames and
# datamosh.py drops all but the first, so smaller GOP means more melt. 30
# gives a melt roughly every second. 100000 leaves only scene-cut keyframes.
GOP="${GOP:-30}"
printf 'gop: %s\n' "$GOP"
ffmpeg -y -v error "${TRIM_ARGS[@]}" -i "$SRC" -an -c:v mpeg4 -bf 0 -g "$GOP" -q:v 3 -f avi "$tmp/step1.avi"

say "extract raw elementary stream"
ffmpeg -y -v error -i "$tmp/step1.avi" -c:v copy -f m4v "$tmp/step1.m4v"

say "drop I-frames"
python3 "$HERE/datamosh.py" "$tmp/step1.m4v" "$tmp/step2.m4v" --keep-first

say "remux and transcode to h264 for Gem"
# Transcode from the AVI, not the raw elementary stream: a bare .m4v carries no
# container timestamps and ffmpeg stops after the first GOP.
ffmpeg -y -v error -i "$tmp/step2.m4v" -c:v copy "$tmp/mosh.avi"
ffmpeg -y -v error -i "$tmp/mosh.avi" -an -c:v libx264 -preset medium -crf 18 \
  -pix_fmt yuv420p -movflags +faststart "$OUT/mosh.mp4"
ffmpeg -y -v error -i "$tmp/step1.avi" -an -c:v libx264 -preset medium -crf 18 \
  -pix_fmt yuv420p -movflags +faststart "$OUT/clean.mp4"

say "verify"
for f in clean mosh; do
  n=$(ffprobe -v error -select_streams v:0 -count_frames \
        -show_entries stream=nb_read_frames -of csv=p=0 "$OUT/$f.mp4")
  printf '  %-6s %s frames\n' "$f" "$n"
done

# The melt is the whole point, so assert the two clips actually differ.
# Sample past dropped I-frames. One sample can miss a short melt, so probe
# three points across the clip and keep the strongest difference.
if [ -n "$DUR" ]; then
  SAMPLE_TS=$(awk -v d="$DUR" 'BEGIN { printf "%g %g %g", d/4, d/2, 3*d/4 }')
else
  SAMPLE_TS="20 25 30"
fi
best=0
for SAMPLE_T in $SAMPLE_TS; do
  diff_px=$(ffmpeg -v error -ss "$SAMPLE_T" -i "$OUT/clean.mp4" -ss "$SAMPLE_T" -i "$OUT/mosh.mp4" \
    -filter_complex "blend=all_mode=difference,signalstats,metadata=print:file=-" \
    -frames:v 1 -f null - 2>/dev/null | grep -m1 YAVG | sed 's/.*YAVG=//')
  printf '  t=%ss  mean abs diff=%s\n' "$SAMPLE_T" "$diff_px"
  best=$(awk -v b="$best" -v d="$diff_px" 'BEGIN { print (d > b) ? d : b }')
done
printf '  strongest diff=%s\n' "$best"
awk -v d="$best" 'BEGIN { exit (d > 0.5) ? 0 : 1 }' \
  || { echo "FAIL: moshed clip is indistinguishable from clean" >&2; exit 1; }

say "done"
ls -la "$OUT"