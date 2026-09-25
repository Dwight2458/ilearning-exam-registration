"""诊断工具：验证「用 CDP 打开 iLearning 页面能否自动登录」。

做法：借 playwright-cli 的 tab-new 开一个标签页访问 https://ilearning.huawei.com/，
观察它最终落地的 URL，然后关掉。

判断依据：
  落地 URL 仍是 ilearning.huawei.com（如 /edx/next/） → 自动登录成功
  落地 URL 跳到 login. / uniportal / sso 等            → 需要人工登录

用法: python pw/check_sso.py
"""
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = 'https://ilearning.huawei.com/'
SESSION = 'ssocheck'
PORTS = (9222, 9223, 9333)


def env():
    e = dict(os.environ)
    e['PATH'] = r'C:\Program Files\Git\usr\bin;C:\Program Files\Git\bin;' + e.get('PATH', '')
    return e


def pw(*args, timeout=60):
    # playwright-cli 实际是 npm 生成的 bash shim，Windows 上不能直接 CreateProcess，
    # 必须交给 bash 执行（并且 PATH 里要有 Git 的 coreutils，否则 sed/dirname 找不到）
    cmd = ' '.join(['playwright-cli', f'-s={SESSION}'] + [f'"{a}"' if ' ' in a else a for a in args])
    r = subprocess.run(['bash', '-c', cmd],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', env=env(), timeout=timeout, cwd=ROOT)
    return (r.stdout or '') + (r.stderr or '')


def find_port():
    import urllib.request
    for p in PORTS:
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{p}/json/version', timeout=2)
            return p
        except Exception:
            continue
    return 0


def main():
    port = find_port()
    if not port:
        print('未检测到 CDP 调试端口（9222/9223/9333）。'
              '请先完全退出 Edge 再运行 pw/start_edge_debug.cmd')
        return 1

    pw('detach')
    out = pw('attach', '--cdp', f'http://127.0.0.1:{port}')
    if 'created' not in out:
        print('CDP attach 失败：', out.strip()[:300])
        return 1
    print(f'已连接 CDP 端口 {port}')

    listing = pw('tab-new', URL)
    idx = None
    for line in listing.splitlines():
        if '(current)' in line:
            m = re.match(r'^\s*-?\s*(\d+):', line.strip())
            if m:
                idx = m.group(1)
            break

    time.sleep(7)
    after = pw('tab-list')
    landed = ''
    for line in after.splitlines():
        if idx is not None and re.match(r'^\s*-?\s*%s:' % idx, line.strip()):
            landed = line.strip()
            break
    print(f'落地：{landed[:160]}')

    if idx is not None and 'ilearning.huawei.com' in landed:
        pw('tab-close', idx)
        print('已关闭预热标签页')
    else:
        print('⚠️ 未确认是 iLearning 页，跳过关闭以免误关其他标签页（请手动检查）')
    pw('detach')

    if 'ilearning.huawei.com' in landed:
        print('\n结论：自动登录成功 —— 无人值守可成立')
        return 0
    print('\n结论：没落在 iLearning 上，自动登录未生效，需要人工登录一次')
    return 2


if __name__ == '__main__':
    sys.exit(main())
