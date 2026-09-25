#!/bin/bash
# 通过 CDP 从已开启调试端口的 Edge 导出 ilearning Cookie。
# 前提：Edge 是用 --remote-debugging-port=9222 启动的（见 start_edge_debug.cmd）。
#
# 优点：不弹授权、不开新标签页、不需要手动同意，适合无人值守自动刷新。
# 用 state-save（storageState JSON）而不是 cookie-list：
#   它是 Playwright 官方登录态格式，含 HttpOnly cookie，且带 domain 便于按域过滤。
export PATH="/c/Program Files/Git/usr/bin:/c/Program Files/Git/bin:$PATH"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

PORT=""
for p in 9222 9223 9333; do
  if curl -s -m 2 "http://127.0.0.1:$p/json/version" >/dev/null 2>&1; then
    PORT=$p
    break
  fi
done

if [ -z "$PORT" ]; then
  echo "NO_CDP_PORT"
  exit 1
fi

playwright-cli -s=cdpcookie attach --cdp "http://127.0.0.1:$PORT" >/dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "CDP_ATTACH_FAILED"
  exit 1
fi

playwright-cli -s=cdpcookie state-save pw/state_cdp.json >/dev/null 2>&1
playwright-cli -s=cdpcookie detach >/dev/null 2>&1

"/c/Users/b00934843/.workbuddy/binaries/python/versions/3.13.12/python.exe" pw/mkcookie_state.py pw/state_cdp.json
