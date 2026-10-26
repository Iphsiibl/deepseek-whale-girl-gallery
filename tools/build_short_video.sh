#!/usr/bin/env bash
# 由原片重剪 56 秒导览版，并把 AI 配音按画面段起点对位混音。
#
#   bash tools/build_short_video.sh
#
# 依赖：ffmpeg / ffprobe；配音段由 tools/gen_tts.py 先行生成到 docs/video/vo/
#
# 设计要点
#   · 每段画面长度 = 该句配音的实际长度，所以音画天然对齐，不需要手调时间轴
#   · 视频流直接 copy（不重编码），只在片尾换容器时动一次
#   · 音频统一 loudnorm 到 -16 LUFS + alimiter 防削波，符合平台响度预期

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VIDEO_DIR="$ROOT/docs/video"
VO_DIR="$VIDEO_DIR/vo"
SRC="$VIDEO_DIR/galaxy-tour.mp4"
OUT="$VIDEO_DIR/galaxy-tour-56s.mp4"

[ -f "$SRC" ] || { echo "找不到母版 $SRC" >&2; exit 1; }
[ -d "$VO_DIR" ] || { echo "找不到配音目录 $VO_DIR（先跑 tools/gen_tts.py）" >&2; exit 1; }

# 画面段：从母版取的区间（秒）
CUTS=(
  "0:6.05"        # 首屏
  "6.05:10.95"    # 萌娘百科收录
  "10.95:15.49"   # 换装三视图
  "15.49:22.44"   # 社区二创
  "22.44:29.60"   # 社区二创
  "29.60:38.96"   # 社区二创
  "78:84.90"      # 灯箱 1:1
  "96:99.85"      # 场景壁纸
  "102:108"       # 结尾页
)

# 配音段与其入点（毫秒），顺序与 CUTS 一一对应
VO_FILES=(vo-01 vo-02 vo-03 vo-04 vo-05 vo-06 vo-07b vo-08 vo-09)
VO_DELAYS=(0 6050 10950 15490 22440 29600 38960 45860 49570)

# --- 1) 灯箱段轻微提速 ---------------------------------------------------
# 第 7 句原始生成 7.67s，超出灯箱画面长度（7s），用 atempo 压到 6.91s。
# 轻微提速不改音色，只是让语音不压过画面切换点。
if [ ! -f "$VO_DIR/vo-07b.mp3" ]; then
  ffmpeg -v error -i "$VO_DIR/vo-07.mp3" -filter:a "atempo=1.1116" \
    -c:a libmp3lame -q:a 2 "$VO_DIR/vo-07b.mp3"
fi

# --- 2) 裁剪拼接视频 -------------------------------------------------------
FILTER=""
for i in "${!CUTS[@]}"; do
  start="${CUTS[$i]%%:*}"; end="${CUTS[$i]##*:}"
  FILTER="${FILTER}[0:v]trim=${start}:${end},setpts=PTS-STARTPTS[v${i}];"
done
LABELS=""
for i in "${!CUTS[@]}"; do LABELS="${LABELS}[v${i}]"; done
FILTER="${FILTER}${LABELS}concat=n=${#CUTS[@]}:v=1:a=0[outv]"

TMP_VIDEO="$(mktemp -u -t short_XXXX.mp4)"
ffmpeg -y -v error -i "$SRC" -filter_complex "$FILTER" -map "[outv]" \
  -c:v libx264 -preset slow -crf 19 -pix_fmt yuv420p "$TMP_VIDEO"

# --- 3) 配音对位混音 -------------------------------------------------------
AFILTER=""
INPUTS=()
for i in "${!VO_FILES[@]}"; do
  f="$VO_DIR/${VO_FILES[$i]}.mp3"
  [ -f "$f" ] || { echo "缺少配音段 $f" >&2; exit 1; }
  d="${VO_DELAYS[$i]}"
  AFILTER="${AFILTER}[$((i+1)):a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,adelay=${d}|${d}[a${i}];"
  INPUTS+=(-i "$f")
done
ALABELS=""
for i in "${!VO_FILES[@]}"; do ALABELS="${ALABELS}[a${i}]"; done
AFILTER="${AFILTER}${ALABELS}amix=inputs=${#VO_FILES[@]}:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,alimiter=limit=0.95[outa]"

ffmpeg -y -v error -i "$TMP_VIDEO" "${INPUTS[@]}" -filter_complex "$AFILTER" \
  -map 0:v -map "[outa]" -c:v copy -c:a aac -b:a 192k -movflags +faststart "$OUT"
rm -f "$TMP_VIDEO"

DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT")
SIZE=$(du -h "$OUT" | cut -f1)
echo "生成完成: $OUT  (${DUR}s, ${SIZE})"
[ "${DUR%.*}" -lt 60 ] && echo "✓ 短于 60 秒" || echo "✗ 超过 60 秒"
