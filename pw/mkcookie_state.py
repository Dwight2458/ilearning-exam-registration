"""把 Playwright storageState JSON 里 huawei 相关域的 cookie 抽成请求头字符串。

用法: python pw/mkcookie_state.py pw/state_cdp.json
输出: .ilearning_cookie.txt   （内容为空时不覆盖旧文件）

为什么不用 `playwright-cli cookie-list`：
  storageState 是 Playwright 官方的登录态导出格式，包含 HttpOnly cookie，
  且会带 domain/path，方便按域过滤。cookie-list 的文本输出不好做域过滤。
"""
import json
import sys
import os

STATE = sys.argv[1] if len(sys.argv) > 1 else 'pw/state_cdp.json'
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   '.ilearning_cookie.txt')

try:
    data = json.load(open(STATE, encoding='utf-8'))
except Exception as e:
    print('读取 storageState 失败:', e)
    sys.exit(1)

# 浏览器请求 https://ilearning.huawei.com 时，只会带这两类域名的 cookie。
# 必须严格按此过滤：huawei 各子域有大量同名 cookie（SESSION / _w3Fid / weboffice_cdn ...
# 光 SESSION 就散落在 committer / himeeting / w3 / edm3 / libing 等十几个子域），
# 一旦混进来就会把真正要用的同名 cookie 顶掉。
EXACT_DOMAIN = 'ilearning.huawei.com'   # 精确域，优先级最高
PARENT_DOMAIN = '.huawei.com'           # 父域

exact, parent = {}, {}
for c in data.get('cookies', []):
    dom = (c.get('domain') or '').strip().lstrip('.').lower()
    full = '.' + dom
    name = c.get('name')
    if not name:
        continue
    if dom == EXACT_DOMAIN:
        exact[name] = c.get('value', '')
    elif full == PARENT_DOMAIN:
        parent[name] = c.get('value', '')

# 精确域覆盖父域
pairs = dict(parent)
pairs.update(exact)

if not pairs:
    print('cookies: 0 —— 未写入，保留原 Cookie 文件')
    print('（大概率是 iLearning 登录态已失效，浏览器里重新登录一次再跑）')
    sys.exit(1)

ck = '; '.join(f'{k}={v}' for k, v in pairs.items())
open(OUT, 'w', encoding='utf-8').write(ck)
print('cookies:', len(pairs), 'len:', len(ck), '->', OUT)
