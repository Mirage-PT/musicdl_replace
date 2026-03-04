#!/usr/bin/env bash
# 一键关闭：结束 8000 和 5173 端口上的进程（默认优雅关闭，超时再强杀）

cd "$(dirname "$0")"
ROOT="$(dirname "$0")/.."

killed=0

FORCE=0
if [ "${1:-}" = "--force" ] || [ "${1:-}" = "-f" ]; then
  FORCE=1
fi

graceful_kill_pids() {
  local pids="$1"
  if [ -z "$pids" ]; then return 0; fi
  if [ "$FORCE" = 1 ]; then
    echo "$pids" | xargs kill -9 2>/dev/null || true
    return 0
  fi
  # 先 TERM
  echo "$pids" | xargs kill -TERM 2>/dev/null || true
  # 等 1.5s
  sleep 1.5
  # 仍存活则 KILL
  local still=""
  still=$(echo "$pids" | xargs -I{} sh -c 'kill -0 "{}" 2>/dev/null && echo "{}" || true' | tr '\n' ' ' | xargs || true)
  if [ -n "$still" ]; then
    echo "$still" | xargs kill -9 2>/dev/null || true
  fi
}

# 按端口杀进程（更可靠，不依赖 .pid 文件）
for port in 8000 5173; do
  # macOS / Linux: lsof -ti :port 得到监听该端口的进程 PID
  pids=$(lsof -ti :$port 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo ">>> 关闭端口 $port 上的进程: $pids"
    graceful_kill_pids "$pids"
    killed=1
  fi
done

# 清理可能存在的 .pid 文件
rm -f .backend.pid .frontend.pid

if [ "$killed" = 1 ]; then
  if [ "$FORCE" = 1 ]; then
    echo "已强制关闭本地音乐管理前后端。"
  else
    echo "已关闭本地音乐管理前后端。"
  fi
else
  echo "未发现运行中的后端(8000)或前端(5173)进程。"
fi
