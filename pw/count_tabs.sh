#!/bin/bash
# 统计 Edge 里残留的 Playwright Welcome(connect.html) 标签页数量。
# 结束后会关掉本次 attach 自己开的那个标签页。
export PATH="/c/Program Files/Git/usr/bin:/c/Program Files/Git/bin:$PATH"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

playwright-cli -s=edge attach --extension=msedge >/dev/null 2>&1 || exit 1
playwright-cli -s=edge tab-list 2>&1 > pw/tablist.txt
TOTAL=$(grep -cE '^ *- *[0-9]+:' pw/tablist.txt)
JUNK=$(grep -cE 'connect\.html' pw/tablist.txt)
echo "总标签页: $TOTAL"
echo "其中 Playwright Welcome 残留: $JUNK"

WIDX=$(grep -E "connect\.html" pw/tablist.txt | head -1 | sed -E 's/^ *- *([0-9]+):.*/\1/')
if [ -n "$WIDX" ]; then playwright-cli -s=edge tab-close "$WIDX" >/dev/null 2>&1; fi
playwright-cli -s=edge detach >/dev/null 2>&1
