#!/bin/bash
# 从已登录的 Edge 导出 ilearning Cookie。
# ⚠️ attach --extension 每次都会新开一个 Welcome(connect.html) 标签页，
#    所以结尾必须把它关掉再 detach，否则反复调用会把浏览器标签页堆满。
export PATH="/c/Program Files/Git/usr/bin:/c/Program Files/Git/bin:$PATH"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

playwright-cli -s=edge attach --extension=msedge >/dev/null 2>&1 || exit 1

# 1) 导出 cookie
playwright-cli -s=edge cookie-list 2>&1 | grep -E "ilearning.huawei.com|huawei.com" > pw/raw_cookies.txt

# 2) 关掉本次 attach 打开的 Welcome 标签页
WIDX=$(playwright-cli -s=edge tab-list 2>&1 | grep -E "connect\.html" | head -1 | sed -E 's/^- *([0-9]+):.*/\1/')
if [ -n "$WIDX" ]; then
  playwright-cli -s=edge tab-close "$WIDX" >/dev/null 2>&1
fi

# 3) 断开会话（保留浏览器运行）
playwright-cli -s=edge detach >/dev/null 2>&1

# 4) 生成 cookie 文件（为空时不覆盖旧文件）
python pw/mkcookie.py
