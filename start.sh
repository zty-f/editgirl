#!/bin/bash
# 一键启动校对女孩(前后端)
# - 启动前反复杀掉 8000 / 5173 上的旧进程,直到端口空
# - 后端单进程模式(不 reload,避免 spawn 孤儿子进程)
# - Ctrl+C 一起关
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

free_port() {
  local port=$1
  for i in 1 2 3 4 5; do
    local pids
    pids=$(lsof -ti :$port 2>/dev/null || true)
    if [ -z "$pids" ]; then return 0; fi
    echo "  端口 $port 被 PID $pids 占用,kill..."
    kill -9 $pids 2>/dev/null || true
    sleep 0.5
  done
  echo "  ⚠ 端口 $port 还是没释放,可能有问题"
  return 1
}

echo "🧹 清旧进程..."
# 先按命令名杀(主进程)
pkill -9 -f "uvicorn app.main:app" 2>/dev/null || true
pkill -9 -f "frontend/node_modules/.bin/vite" 2>/dev/null || true
# 再按端口反复杀(抓 spawn 子进程等)
free_port 8000
free_port 5173
free_port 5174

echo "🚀 启动校对女孩"
echo "  Backend (FastAPI):  http://localhost:8000  ($ROOT/backend)"
echo "  Frontend (Vite):    http://localhost:5173  ($ROOT/frontend)"
echo "  💡 改了后端代码记得 Ctrl+C 重启(本脚本不开 reload 避免端口冲突)"
echo ""

cleanup() {
  echo ""
  echo "🛑 关闭..."
  kill $BE_PID $FE_PID 2>/dev/null || true
  # 兜底再清一次端口
  pkill -9 -f "uvicorn app.main:app" 2>/dev/null || true
  pkill -9 -f "frontend/node_modules/.bin/vite" 2>/dev/null || true
  wait 2>/dev/null
  echo "done"
}
trap cleanup EXIT INT TERM

cd "$ROOT/backend"
"$ROOT/.venv/bin/uvicorn" app.main:app --port 8000 --log-level warning &
BE_PID=$!

cd "$ROOT/frontend"
npm run dev -- --strictPort &
FE_PID=$!

wait
