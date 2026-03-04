#!/usr/bin/env bash
# 一次性执行：在项目根目录创建 .venv 并安装依赖（解决 Homebrew Python 的 externally-managed-environment）

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

if [ -d ".venv" ]; then
  echo ">>> .venv 已存在，正在安装/更新依赖..."
else
  echo ">>> 创建虚拟环境 .venv ..."
  python3 -m venv .venv
fi
echo ">>> 安装项目依赖..."
.venv/bin/pip install -e .
.venv/bin/pip install -r local_music_web/backend/requirements.txt
echo ""
echo ">>> 完成。之后直接运行: bash local_music_web/start.sh"
