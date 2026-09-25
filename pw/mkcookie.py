import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(HERE, 'raw_cookies.txt')
OUT = os.path.join(ROOT, '.ilearning_cookie.txt')
sys.stdout.reconfigure(encoding='utf-8')
pairs = {}
for line in open(RAW, encoding='utf-8', errors='replace'):
    line = line.strip()
    if '=' not in line or '(domain:' not in line:
        continue
    head, dompart = line.split('(domain:', 1)
    dom = dompart.split(',', 1)[0].strip()
    if 'ilearning.huawei.com' not in dom and dom != '.huawei.com':
        continue
    name, val = head.split('=', 1)
    pairs[name.strip()] = val.strip()
ck = '; '.join(k + '=' + v for k, v in pairs.items())
if not ck:
    print('cookies: 0 —— 未写入，保留原 Cookie 文件（避免被清空）')
    sys.exit(1)
open(OUT, 'w', encoding='utf-8').write(ck)
print('cookies:', len(pairs), 'len:', len(ck))
for k in pairs:
    print(' -', k, '=', pairs[k][:40])
