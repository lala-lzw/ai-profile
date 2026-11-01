#!/bin/sh
# 用法: ./install.sh [目标技能目录] [技能名...]
# 默认安装到 ~/.claude/skills，安装 ai-profile 与 profile-* 快捷指令。
set -e
SRC="$(cd "$(dirname "$0")/skills" && pwd)"
DEST="${1:-$HOME/.claude/skills}"
[ $# -gt 0 ] && shift
if [ $# -gt 0 ]; then NAMES="$*"; else NAMES="ai-profile profile-start profile-stop profile-mark profile-gui"; fi
mkdir -p "$DEST"
for n in $NAMES; do
  [ -d "$SRC/$n" ] || { echo "未找到技能: $n" >&2; exit 1; }
  rm -rf "$DEST/$n"
  cp -R "$SRC/$n" "$DEST/$n"
  find "$DEST/$n" -name __pycache__ -type d -prune -exec rm -rf {} +
  echo "已安装 $n -> $DEST/$n"
done
