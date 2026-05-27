#!/bin/bash
# 停校对女孩前后端(8000 / 5173 / 5174)

echo "🛑 停校对女孩..."

# 按进程名杀(包括 uvicorn reload 的 spawn 子进程)
pkill -9 -f "uvicorn app.main:app" 2>/dev/null && echo "  ✓ 已杀后端 uvicorn"
pkill -9 -f "frontend/node_modules/.bin/vite" 2>/dev/null && echo "  ✓ 已杀前端 vite"
pkill -9 -f "spawn_main" 2>/dev/null

# 按端口兜底
for port in 8000 5173 5174; do
  pids=$(lsof -ti :$port 2>/dev/null)
  if [ -n "$pids" ]; then
    kill -9 $pids 2>/dev/null
    echo "  ✓ 释放端口 $port (PID $pids)"
  fi
done

sleep 1
remain=$(lsof -ti :8000 :5173 :5174 2>/dev/null)
if [ -z "$remain" ]; then
  echo "✓ 端口都空了"
else
  echo "⚠ 还有残留 PID: $remain"
fi
