#!/bin/bash
# 通过 CDP 从 Edge 导出 ilearning Cookie（无人值守，含 SSO 自动重登录）。
# 前提：Edge 是以 --remote-debugging-port=9222 启动的（见 start_edge_debug.cmd）。
#
# 流程：
#   1) 用 playwright 开一个标签页访问 https://ilearning.huawei.com/
#      —— 页面会自动走 SSO 重新登录，把已失效的会话 Cookie 换成新的
#      （实测落地 URL = /edx/next/，说明自动登录生效，不是登录页）
#   2) 等 SSO_WAIT 秒（默认 6）
#   3) 用 storageState 导出 Cookie（含 HttpOnly）
#   4) 关掉刚开的标签页 —— 关闭前会校验该索引上确实是 iLearning 页，
#      不匹配就跳过，宁可留一个多余标签页也不误关用户的标签页
#
# 为什么不用 CDP 的 /json/new?url=：
#   这台 Edge 上它只会开出 about:blank，URL 参数不生效。playwright 的 tab-new 可以正常跳转。
#
# 可用环境变量覆盖：SSO_WAIT / SKIP_SSO / SSO_URL
export PATH="/c/Program Files/Git/usr/bin:/c/Program Files/Git/bin:$PATH"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

PY="/c/Users/b00934843/.workbuddy/binaries/python/versions/3.13.12/python.exe"
SSO_WAIT="${SSO_WAIT:-6}"
SSO_URL="${SSO_URL:-https://ilearning.huawei.com/}"
SKIP_SSO="${SKIP_SSO:-0}"
S="cdpcookie"

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

playwright-cli -s=$S attach --cdp "http://127.0.0.1:$PORT" >/dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "CDP_ATTACH_FAILED"
  exit 1
fi

# --- 1) 开标签页触发 SSO 自动登录（新标签会成为 current） ---
NEWIDX=""
if [ "$SKIP_SSO" != "1" ]; then
  NEWIDX=$(playwright-cli -s=$S tab-new "$SSO_URL" 2>&1 \
            | grep -E '\(current\)' | head -1 | sed -E 's/^ *- *([0-9]+):.*/\1/')
  if [ -n "$NEWIDX" ]; then
    echo "SSO 预热中（等 ${SSO_WAIT}s 自动登录）…"
    sleep "$SSO_WAIT"
  else
    echo "SSO_WARMUP_SKIPPED"
  fi
fi

# --- 2) 导出 Cookie ---
playwright-cli -s=$S state-save pw/state_cdp.json >/dev/null 2>&1

# --- 3) 关标签页（先校验索引内容，避免误关） ---
if [ -n "$NEWIDX" ]; then
  LINE=$(playwright-cli -s=$S tab-list 2>&1 | grep -E "^ *- *${NEWIDX}:")
  case "$LINE" in
    *ilearning.huawei.com*)
      playwright-cli -s=$S tab-close "$NEWIDX" >/dev/null 2>&1
      ;;
    *)
      echo "WARN: 索引 $NEWIDX 不是 iLearning 页，跳过关闭以免误关其他标签页"
      ;;
  esac
fi

playwright-cli -s=$S detach >/dev/null 2>&1

"$PY" pw/mkcookie_state.py pw/state_cdp.json
