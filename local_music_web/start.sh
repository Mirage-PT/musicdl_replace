#!/usr/bin/env bash
# 一键启动：后端 (8000) + 前端 (5173)，脚本保持前台，Ctrl+C 优雅关闭前后端

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

# 避免重复启动
if lsof -ti :8000 >/dev/null 2>&1; then
  echo "端口 8000 已被占用，后端可能已在运行。如需重启请先执行: bash $SCRIPT_DIR/stop.sh"
  exit 1
fi
if lsof -ti :5173 >/dev/null 2>&1; then
  echo "端口 5173 已被占用，前端可能已在运行。如需重启请先执行: bash $SCRIPT_DIR/stop.sh"
  exit 1
fi

BACKEND_PID=""
FRONTEND_PID=""
cleanup() {
  echo ""
  echo ">>> 正在关闭前后端..."

  # 用 SIGTERM 关闭（避免触发 Python wrapper 的 KeyboardInterrupt 堆栈）
  if [ -n "${FRONTEND_PID:-}" ] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    kill -TERM "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [ -n "${BACKEND_PID:-}" ] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill -TERM "$BACKEND_PID" 2>/dev/null || true
  fi

  # 等待最多 2 秒，仍未退出则强制杀掉
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    alive=0
    if [ -n "${FRONTEND_PID:-}" ] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then alive=1; fi
    if [ -n "${BACKEND_PID:-}" ] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then alive=1; fi
    [ "$alive" = 0 ] && break
    sleep 0.2
  done

  if [ -n "${FRONTEND_PID:-}" ] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    kill -KILL "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [ -n "${BACKEND_PID:-}" ] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill -KILL "$BACKEND_PID" 2>/dev/null || true
  fi

  [ -n "${FRONTEND_PID:-}" ] && echo ">>> 已关闭前端 (PID $FRONTEND_PID)" || true
  [ -n "${BACKEND_PID:-}" ] && echo ">>> 已关闭后端 (PID $BACKEND_PID)" || true
  exit 0
}
trap cleanup INT TERM

# 优先使用项目 .venv 中的 uvicorn（避免 Homebrew Python 的 externally-managed-environment）
UVICORN="uvicorn"
if [ -f "$ROOT/.venv/bin/uvicorn" ]; then
  UVICORN="$ROOT/.venv/bin/uvicorn"
fi

echo ">>> 启动后端 (uvicorn :8000)..."
"$UVICORN" local_music_web.backend.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
sleep 2

echo ">>> 启动前端 (Vite :5173)，按 Ctrl+C 关闭前后端"
echo ""
cd local_music_web/frontend
npm run dev &
FRONTEND_PID=$!

echo ">>> 前端: http://127.0.0.1:5173"
echo ">>> 后端: http://127.0.0.1:8000"
echo ">>> 按 Ctrl+C 退出"

# 等待前端退出；前端退出后也顺便关掉后端
wait "$FRONTEND_PID" 2>/dev/null || true
cleanup
