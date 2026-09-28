#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iLearning 考试场次「抢名额」脚本
================================

用途：高频轮询 iLearning 考试场次列表，检测到目标场次有余额时自动完成报名。

核心接口（通过浏览器实测确认，examId=54085）：
  1) 场次列表  POST /sxz/api/iexam/api/iexam/userexam/v2/exams/sessions
     body: {"examId","sessionName","onlyShowCanReservation","beginTimeStart","endTimeEnd","id"}
  2) 报名校验  POST /sxz/api/iexam/api/iexam/userexam/v1/exams/checkReservation
     body: {"examId","id"}        # 注意字段名是 id，不是 sessionId
  3) 提交报名  POST /sxz/api/iexam/api/iexam/userexam/v1/exams/reservationExam
     body: {"examId","id"}        # 2026-09-24 用真实场次实测成功
  4) 我的预约  GET  /sxz/api/iexam/api/iexam/userexam/v1/personalService/getInitUnderwayBookExamtionX/1/20
  5) 取消预约  PUT  /sxz/api/iexam/api/iexam/userexam/v1/exams/cancelReservationExam/{场次ID}
     body: {}                     # ⚠️ 传的是场次 ID！传 bookId 会报「用户没有预约记录或已失效」

轮询只需要 Cookie，**不需要浏览器**。`--cookie-refresh` 默认 `off`：401 时只做退避重试
（实测 iLearning 的 401 多数是平台维护抖动，同一份 Cookie 过一会儿就能自己恢复）。
只有显式 `--cookie-refresh auto` 才会碰浏览器，且有冷却（30 分钟）和总次数上限（3 次）。

> ⚠️ **事故记录 2026-09-25**：早期版本在 401 时每次都调 `playwright-cli attach --extension`，
> 而该命令**每调用一次就在 Edge 开一个新的 Welcome 标签页**且旧脚本没有 detach。
> 挂一晚上累积了上万个标签页把浏览器打满。已修复：默认不动浏览器；
> `pw/getcookie.sh` 结尾会 detach（detach 会关掉自己开的 connect 页）。

⚠️ 安全设计
  - 默认 dry-run：只监控、只打印，绝不提交报名。
  - 真正报名必须显式加 --execute，且会要求二次确认（或用 --yes 跳过确认）。
  - 报名会占用考试次数（本科目：每年4次 / 每月1次），且报名截止后不可取消/变更。

Cookie 获取（任一方式）：
  1) 浏览器 F12 → Network → 任选一个 ilearning.huawei.com 请求 → 复制 Request Headers 里的 cookie 值
  2) 写入文件（默认 .ilearning_cookie.txt）或 --cookie "xxx" 或环境变量 ILEARNING_COOKIE

用法示例：
  # 只看一次当前所有场次（深圳）
  python ilearning_sniper.py --cookie-file .ilearning_cookie.txt --city 深圳 --once

  # 盯深圳 11 月的场次，每 20 秒刷一次，有货就报（先跑 dry-run 观察）
  python ilearning_sniper.py --city 深圳 --date-start 2026-11-01 --date-end 2026-11-30 --interval 20

  # 确认无误后真报名
  python ilearning_sniper.py --city 深圳 --interval 20 --execute --yes
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sniper.log")


def log(msg: str):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def beep():
    try:
        import winsound
        for f, d in ((880, 300), (1170, 300), (880, 300)):
            winsound.Beep(f, d)
    except Exception:
        print("\a", end="", flush=True)

BASE = "https://ilearning.huawei.com/sxz/api/iexam/api/iexam"
URL_SESSIONS = BASE + "/userexam/v2/exams/sessions"
URL_CHECK = BASE + "/userexam/v1/exams/checkReservation"
URL_BOOK = BASE + "/userexam/v1/exams/reservationExam"
URL_MY_BOOKINGS = BASE + "/userexam/v1/personalService/getInitUnderwayBookExamtionX/1/20"
URL_CANCEL = BASE + "/userexam/v1/exams/cancelReservationExam"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0")


def build_headers(cookie: str, referer: str = "") -> dict:
    h = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "sxz-lang": "zh_CN",
        "user-agent": UA,
        "cookie": cookie,
    }
    if referer:
        h["referer"] = referer
    return h


class AuthError(Exception):
    pass


REFRESH_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pw", "getcookie.sh")
REFRESH_CDP_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pw", "getcookie_cdp.sh")

# CDP 端口可用性探测（ playlist 只需 http://127.0.0.1:<port>/json/version 能返回）
CDP_PORTS = (9222, 9223, 9333)


def cdp_port_open() -> int:
    """返回第一个可用的 CDP 调试端口，没有则 0。"""
    import urllib.request
    for p in CDP_PORTS:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{p}/json/version", timeout=1) as r:
                if r.status == 200:
                    return p
        except Exception:
            continue
    return 0


def run_refresh_script(script: str, timeout: int) -> bool:
    import subprocess
    env = dict(os.environ)
    env["PATH"] = r"C:\Program Files\Git\usr\bin;C:\Program Files\Git\bin;" + env.get("PATH", "")
    try:
        r = subprocess.run(["bash", script], capture_output=True, timeout=timeout,
                           text=True, encoding="utf-8", errors="replace", env=env)
        out = (r.stdout or "").strip()
        if out:
            # 把脚本所有输出都记下来，否则「SSO 预热中」这类过程信息会被吞掉
            for ln in out.splitlines():
                if ln.strip():
                    log("  [取Cookie] " + ln.strip())
        return r.returncode == 0
    except Exception as e:
        log(f"刷新脚本异常：{e}")
        return False

# ⚠️ 血的教训：playwright-cli attach --extension 每调用一次就会在 Edge 里开一个新的
# Welcome(connect.html) 标签页。放进轮询循环里 = 一夜之间几万个标签页把浏览器打满。
# 所以：默认【绝不】自动调用；只有显式 --cookie-refresh auto 且达到冷却时间才会尝试，
# 并且整轮运行最多尝试 MAX_AUTO_REFRESH 次。
MIN_REFRESH_INTERVAL = 1800   # 两次自动刷新之间的最小间隔（秒，扩展通道）
MIN_REFRESH_INTERVAL_CDP = 600  # CDP 通道没有开标签页的代价，可以勤快一点
MAX_AUTO_REFRESH = 3          # 单轮运行内最多自动刷新次数


def refresh_cookie_from_browser(source: str = "auto", timeout: int = 300) -> bool:
    """从已登录的 Edge 重新导出 Cookie。

    source:
      cdp     —— 通过 127.0.0.1:9222 的 CDP 调试端口。
                 需要 Edge 以 --remote-debugging-port=9222 启动（见 pw/start_edge_debug.cmd）。
                 ✅ 无需人工授权、不会新开标签页，是无人值守自动刷新的首选。
      browser —— 走 Playwright 浏览器扩展。⚠️ 每次会临时开一个 Welcome 标签页。
      auto    —— 有 CDP 端口就用 CDP，否则退回扩展方式。
    """
    if source in ("auto", "cdp"):
        if cdp_port_open():
            log("走 CDP 通道取 Cookie（会临时开 1 个标签页触发 SSO 自动登录，用完即关）…")
            if run_refresh_script(REFRESH_CDP_SCRIPT, timeout):
                return True
            if source == "cdp":
                return False
        elif source == "cdp":
            log("未检测到 CDP 调试端口（9222/9223/9333）。"
                "请先完全退出 Edge，再双击 pw/start_edge_debug.cmd 启动。")
            return False

    if source in ("auto", "browser"):
        if not os.path.exists(REFRESH_SCRIPT):
            return False
        log("走 Playwright 扩展取 Cookie（会临时开 1 个 Welcome 标签页，随后自动关闭）…")
        return run_refresh_script(REFRESH_SCRIPT, timeout)
    return False


def load_cookie_file(path: str) -> str:
    """读取并规范化 Cookie 文件；不存在或为空返回空串。"""
    try:
        return normalize_cookie(open(path, encoding="utf-8").read())
    except Exception:
        return ""


def reload_cookie(path: str) -> str:
    return load_cookie_file(path)


HELP_COOKIE = """缺少 Cookie。三种给法任选其一：

  1) 写进文件（默认 .ilearning_cookie.txt）——最省事，直接把内容粘进去保存
  2) --cookie "SESSION=xxx; ilearning-session=yyy; ..."
  3) 环境变量 ILEARNING_COOKIE

接受四种格式，会自动识别：
  A. Header 字符串（推荐）   SESSION=xxx; ilearning-session=yyy; hwssot=...
  B. JSON 数组（DevTools Application → Cookies → 选中多行复制 / EditThisCookie 导出）
     [{{"name":"SESSION","value":"xxx","domain":".huawei.com"}}, ...]
  C. JSON 对象               {{"SESSION":"xxx","ilearning-session":"yyy"}}
  D. Netscape cookies.txt（7 个 Tab 分隔字段）

怎么拿（Edge/Chrome）：
  打开 https://ilearning.huawei.com/... 任意一个页面 → F12 → Network →
  刷新 → 点任一 ilearning.huawei.com 请求 → Request Headers 里复制 cookie 那一整行。
  只复制「发给 ilearning.huawei.com 的」即可，不要包含别的域。
"""

def normalize_cookie(raw: str) -> str:
    """把各种格式的 Cookie 统一成 `a=1; b=2` 的请求头字符串。

    支持四种输入，自动识别：
      1) Header 字符串（推荐）  `SESSION=xxx; ilearning-session=yyy; ...`
      2) JSON 数组（DevTools / EditThisCookie 导出）
         `[{"name":"SESSION","value":"xxx","domain":".huawei.com"}, ...]`
      3) JSON 对象  `{"SESSION":"xxx","ilearning-session":"yyy"}`
         （也兼容 `{"cookies":[...]}` 这种外层包一层的）
      4) Netscape cookies.txt（每行 7 个 Tab 分隔字段）
    """
    raw = (raw or "").strip()
    if not raw:
        return ""

    # 2) / 3) JSON
    if raw[0] in "[{":
        try:
            obj = json.loads(raw)
        except Exception:
            return raw
        items = None
        if isinstance(obj, list):
            items = obj
        elif isinstance(obj, dict) and isinstance(obj.get("cookies"), list):
            items = obj["cookies"]
        elif isinstance(obj, dict) and all(isinstance(v, (str, int, float)) for v in obj.values()):
            return "; ".join(f"{k}={v}" for k, v in obj.items())
        if items is not None:
            pairs = []
            for c in items:
                if not isinstance(c, dict):
                    continue
                name = c.get("name") or c.get("Name") or c.get("key")
                val = c.get("value", c.get("Value", c.get("val", "")))
                if name:
                    pairs.append(f"{name}={val}")
            return "; ".join(pairs)
        return raw

    # 4) Netscape cookies.txt
    lines = [l for l in raw.splitlines() if l.strip() and not l.strip().startswith("#")]
    if lines and all("\t" in l and len(l.split("\t")) >= 7 for l in lines[:3]):
        return "; ".join(f"{p[5]}={p[6]}" for p in (l.split("\t") for l in lines))

    # 1) Header 字符串
    return " ".join(raw.split())  # 折叠多行/多余空白


def post(url: str, payload: dict, cookie: str, timeout: int = 15):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=build_headers(cookie), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise AuthError("Cookie 已失效（HTTP %d），请重新从浏览器导出 Cookie" % e.code)
        raise
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 平台维护 / 网关页会返回 HTML，按瞬时故障处理，继续重试
        return {"code": -1, "message": "非 JSON 响应（维护中？）: %s" % raw[:120], "data": None}


def fetch_sessions(exam_id: str, cookie: str, keyword: str = "",
                   only_available: bool = False,
                   date_start: str = "", date_end: str = "",
                   exclude_ids=None, exclude_keywords=None):
    body = {
        "examId": exam_id,
        "sessionName": keyword,
        "onlyShowCanReservation": 1 if only_available else 0,
        "beginTimeStart": date_start,
        "endTimeEnd": date_end,
        "id": "",
    }
    r = post(URL_SESSIONS, body, cookie)
    if r.get("code") != 200:
        raise RuntimeError(f"场次列表接口异常: {r.get('code')} {r.get('message')}")
    rows = r.get("data") or []

    # 本地排除：已经报过名的场次不该再抢（抢了会多占一次考试次数额度）
    ex_ids = {str(x) for x in (exclude_ids or []) if str(x).strip()}
    ex_kw = [k for k in (exclude_keywords or []) if str(k).strip()]
    if ex_ids or ex_kw:
        kept = []
        for s in rows:
            sid = str(s.get("id"))
            name = str(s.get("roomName") or "") + str(s.get("sessionName") or "")
            if sid in ex_ids or any(k in name for k in ex_kw):
                continue
            kept.append(s)
        return kept
    return rows


def verify_cookie(cookie: str, exam_id: str = "54085") -> bool:
    """真打一次接口，确认 Cookie 到底能不能用。

    为什么要单独做这步：导出脚本只要写出非空文件就返回成功，它不知道 Cookie 是否有效。
    浏览器登录态失效时，CDP 会把浏览器里那堆已经死掉的 Cookie 原样搬出来，
    看起来「导出成功」，实际一用就 401。
    """
    try:
        fetch_sessions(exam_id, cookie, keyword="", only_available=False)
        return True
    except AuthError:
        return False
    except Exception:
        return False


def refresh_and_verify(exam_id: str, args) -> tuple:
    """重导 Cookie 并验证。返回 (是否成功刷到文件, 验证是否通过)。"""
    if not refresh_cookie_from_browser(args.cookie_source):
        return False, False
    fresh = load_cookie_file(args.cookie_file)
    if not fresh:
        return False, False
    return True, verify_cookie(fresh, exam_id)


def fmt_session(s: dict) -> str:
    return (f"{s.get('roomName','')[:26]:<28} | {s.get('beginTime','')} | "
            f"剩余 {str(s.get('remainingQuota')):>4} | 座位 {s.get('seatLimit')} | "
            f"已报 {s.get('sessionUserNum')} | id={s.get('id')}")


def my_bookings(cookie: str):
    """我的考试 → 预约中的考试列表。"""
    req = urllib.request.Request(URL_MY_BOOKINGS,
                                 headers=build_headers(cookie, referer=URL_MY_BOOKINGS),
                                 method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        j = json.loads(resp.read().decode("utf-8", errors="replace"))
    if j.get("code") != 200:
        raise RuntimeError(f"预约列表接口异常: {j.get('code')} {j.get('message')}")
    data = j.get("data") or {}
    rows = data.get("records") or data.get("list") or (data if isinstance(data, list) else [])
    return rows


def cancel_booking(session_id: str, cookie: str):
    """取消预约。实测：这里传的是「场次 ID」，不是 bookId（传 bookId 会报
    「用户没有预约记录或已失效」）。"""
    req = urllib.request.Request(f"{URL_CANCEL}/{session_id}", data=b"{}",
                                 headers=build_headers(cookie), method="PUT")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def try_book(exam_id: str, session: dict, cookie: str, execute: bool) -> bool:
    sid = session.get("id")
    # 一律走 log()，否则「命中 / 报名成功」这类最关键的记录只会进 stdout，
    # 不会落到 sniper.log —— 排查时最想看的就是它们。
    log(f"🎯 命中 {fmt_session(session)}")

    # 1) 报名前校验（只读，不会占名额）
    chk = post(URL_CHECK, {"examId": exam_id, "id": sid}, cookie)
    if chk.get("code") != 200:
        log(f"  校验失败 {chk.get('code')} {chk.get('message')} —— 跳过")
        return False
    d = chk.get("data") or {}
    log(f"  校验通过 剩余名额={d.get('remainingQuota')} 我已报名={d.get('userBooking')} "
        f"预约窗口 {d.get('appointmentOpenBeginTime')} ~ {d.get('appointmentOpenEndTime')}")
    if d.get("userBooking"):
        log("  已经报过这个场次了，跳过。")
        return True

    if not execute:
        log("  [dry-run] 到此为止；加 --execute 才会真正提交报名。")
        return False

    # 2) 真正报名
    res = post(URL_BOOK, {"examId": exam_id, "id": sid}, cookie)
    ok = res.get("code") == 200
    if ok:
        log(f"  ✅ 报名成功：{res.get('message')}  （场次 {session.get('roomName')} "
            f"{session.get('beginTime')}）")
    else:
        log(f"  ❌ 报名失败：{res.get('code')} {res.get('message')}")
    return ok


def main():
    ap = argparse.ArgumentParser(description="iLearning 考试场次自动报名（默认 dry-run）")
    ap.add_argument("--exam-id", default="54085", help="考试 ID，默认 54085")
    ap.add_argument("--city", default="", help="场次名关键词，如 深圳 / 广州 / 西研")
    ap.add_argument("--date-start", default="", help="考试开始时间下界，如 2026-11-01")
    ap.add_argument("--date-end", default="", help="考试开始时间上界，如 2026-11-30")
    ap.add_argument("--session-id", default="", help="只盯这一个场次 ID（最高优先级）")
    ap.add_argument("--exclude-id", action="append", default=[], metavar="SESSION_ID",
                    help="排除某场次 ID，可重复。用于『已经报上名的不再抢』"
                         "（抢了会多占一次考试次数：每年4次/每月1次）")
    ap.add_argument("--exclude-name", action="append", default=[], metavar="KEYWORD",
                    help="按场次名关键词排除，可重复，如 --exclude-name 20261223")
    ap.add_argument("--only-available", action="store_true", help="只请求『可预约』场次（服务端过滤）")
    ap.add_argument("--interval", type=int, default=30, help="轮询间隔秒数，默认 30")
    ap.add_argument("--once", action="store_true", help="只跑一轮就退出")
    ap.add_argument("--execute", action="store_true", help="真正提交报名（默认只监控不报名）")
    ap.add_argument("--yes", action="store_true", help="跳过交互确认（配合 --execute）")
    ap.add_argument("--cookie-refresh", choices=["off", "auto", "cdp"], default="off",
                    help="401 时是否自动从浏览器重导 Cookie。默认 off。"
                         "cdp=走 9222 调试端口（推荐，无感）；auto=有 CDP 用 CDP，否则退回扩展")
    ap.add_argument("--refresh-cookie", action="store_true",
                    help="手动从浏览器导出一次 Cookie 后退出（不轮询）")
    ap.add_argument("--cookie-source", choices=["auto", "cdp", "browser"], default="auto",
                    help="--refresh-cookie / --cookie-refresh 的取 Cookie 通道")
    ap.add_argument("--refresh-every", type=int, default=0, metavar="SECONDS",
                    help="主动保鲜：每隔 N 秒重导一次 Cookie（0=关闭）。"
                         "配 CDP 用，比如 600。Cookie 快照放久会失效，主动换比等 401 更省事")
    ap.add_argument("--my-bookings", action="store_true", help="列出我已预约的考试（含 bookId）")
    ap.add_argument("--cancel", default="", metavar="SESSION_ID", help="取消指定场次 ID 的预约")
    ap.add_argument("--cookie", default="", help="Cookie 字符串")
    ap.add_argument("--cookie-file",
                    default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         ".ilearning_cookie.txt"),
                    help="Cookie 文件路径")
    args = ap.parse_args()

    cookie = normalize_cookie(args.cookie or os.environ.get("ILEARNING_COOKIE", ""))
    if not cookie:
        cookie = load_cookie_file(args.cookie_file)
    if not cookie:
        print(HELP_COOKIE)
        sys.exit(2)
    if "=" not in cookie or ";" not in cookie and cookie.count("=") < 1:
        print("Cookie 格式看起来不对（解析后没有 name=value）。\n")
        print(HELP_COOKIE)
        sys.exit(2)

    if args.refresh_cookie:
        log(f"手动从浏览器导出 Cookie（通道：{args.cookie_source}）…")
        got, ok = refresh_and_verify(args.exam_id, args)
        if not got:
            log("❌ 导出失败（CDP 端口未开 / Edge 未运行 / 扩展未授权）")
            sys.exit(1)
        if ok:
            log("✅ 导出成功，且已实际调用接口验证通过。")
            sys.exit(0)
        log("❌ 导出成功，但调接口仍返回 401 —— 说明浏览器里的登录态已经失效。")
        log("   光刷 Cookie 没用，请打开考试页面重新登录一次再试。")
        sys.exit(2)

    if args.my_bookings:
        for b in my_bookings(cookie):
            print(f"bookId={b.get('bookId')} | {b.get('examinationName','')[:24]:<26} | "
                  f"{b.get('examinationRoomName','')[:22]:<24} | {b.get('examStartTime','')} | "
                  f"取消截止 {b.get('cancelResEndTime','')} | 座位 {b.get('seat')}")
        sys.exit(0)

    if args.cancel:
        if not args.yes:
            print(f"⚠️  即将取消场次 {args.cancel} 的预约")
            if input("确认请输入 yes：").strip().lower() != "yes":
                print("已取消操作。")
                sys.exit(0)
        print(cancel_booking(args.cancel, cookie))
        sys.exit(0)

    if args.execute and not args.yes:
        print("⚠️  即将以【真实报名】模式运行。报名会占用考试次数（每年4次/每月1次），"
              "且报名截止后不可取消或变更。")
        if input("确认继续请输入 yes：").strip().lower() != "yes":
            print("已取消。")
            sys.exit(0)

    referer = f"https://ilearning.huawei.com/iexam/100000/examInfo?examId={args.exam_id}"
    excl = ", ".join([f"id:{x}" for x in args.exclude_id]
                     + [f"name~{x}" for x in args.exclude_name]) or "无"
    print(f"目标 examId={args.exam_id} 关键词='{args.city or '(全部)'}' "
          f"时间={args.date_start or '-'}~{args.date_end or '-'} "
          f"间隔={args.interval}s 模式={'真实报名' if args.execute else 'DRY-RUN'} "
          f"排除={excl}\n")
    log(f"启动：examId={args.exam_id} city={args.city or '全部'} interval={args.interval}s "
        f"mode={'execute' if args.execute else 'dry-run'} 排除={excl}")

    round_no = 0
    booked = False
    auth_fail = 0
    refresh_count = 0
    last_refresh = 0.0
    seen_booked = {}   # 场次ID -> 上次看到的已报人数，用来记录「有人取消」这类变化
    dead_streak = 0    # 连续「刷新后仍 401」的次数
    browser_dead = False  # 判定浏览器登录态已死，暂停自动刷新，等人工登录
    while not booked:
        # 每轮先检查 Cookie 文件是否被人工更新过（换 Cookie 不用重启进程）
        new_ck = load_cookie_file(args.cookie_file)
        if new_ck and new_ck != cookie:
            cookie = new_ck
            auth_fail = 0
            # 人工换过 Cookie 就重置「浏览器已死」判定，自动刷新重新上线
            if browser_dead:
                browser_dead = False
                dead_streak = 0
                log("Cookie 文件已人工更新，自动刷新重新启用。")
            log("检测到 Cookie 文件已更新，已重新加载。")

        # 主动保鲜：CDP 导出很便宜（~10s、无副作用），定期重导一份，
        # 免得快照放陈旧了才开始 401 退避，白等一轮。
        if (args.refresh_every > 0 and not browser_dead
                and time.time() - last_refresh > args.refresh_every):
            last_refresh = time.time()
            got, ok = refresh_and_verify(args.exam_id, args)
            if got and ok:
                fresh = load_cookie_file(args.cookie_file)
                if fresh and fresh != cookie:
                    cookie = fresh
                auth_fail = 0
                log(f"Cookie 已定期保鲜（每 {args.refresh_every}s）并验证通过")
            elif got:
                dead_streak += 1
                log("⚠️  重导出的 Cookie 仍然无效 —— 浏览器里的登录态已经失效，"
                    "光刷 Cookie 没用。请打开考试页面重新登录一次。")
                if dead_streak >= 2:
                    browser_dead = True
                    log("🛑 已连续 2 次刷新后仍无效，暂停自动刷新（不再白白调 CDP）。"
                        "你手动登录并更新 .ilearning_cookie.txt 后，脚本会自动恢复。")

        round_no += 1
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            sessions = fetch_sessions(args.exam_id, cookie, args.city,
                                      args.only_available, args.date_start, args.date_end,
                                      exclude_ids=args.exclude_id,
                                      exclude_keywords=args.exclude_name)
        except AuthError as e:
            if args.once:
                print(f"\n❌ {e}")
                print("   —— 浏览器里的 iLearning 登录态已失效，请打开考试页面重新登录，"
                      "然后重跑（或直接更新 Cookie 文件）。")
                sys.exit(1)
            # 401 多数是 Cookie 过期或平台维护抖动。先看 Cookie 文件有没有被更新过，
            # 更新过就立刻重试，不用重启进程。
            new_ck = load_cookie_file(args.cookie_file)
            if new_ck and new_ck != cookie:
                cookie = new_ck
                auth_fail = 0
                log("检测到 Cookie 文件已更新，已重新加载，立即重试。")
                time.sleep(3)
                continue
            auth_fail += 1
            # 有自动刷新通道时退避别拉太长：Cookie 寿命只有半小时量级，
            # 等 15 分钟才重试会白白错过行情。上限 300s。
            cap = 300 if args.cookie_refresh in ("auto", "cdp") else 900
            backoff = min(120 * (2 ** (auth_fail - 1)), cap)
            log(f"⚠️  {e}（第 {auth_fail} 次）→ {backoff}s 后退避重试，不碰浏览器")
            # 第 1、4、7… 次失败就尝试刷新（配合下面的冷却时间做限流）。
            # 之前是第 3、6、9… 次，考虑到 Cookie 寿命只有半小时量级，等 6 分钟太久了。
            if (not browser_dead and args.cookie_refresh in ("auto", "cdp")
                    and auth_fail % 3 == 1
                    and refresh_count < MAX_AUTO_REFRESH
                    and time.time() - last_refresh > (
                        MIN_REFRESH_INTERVAL_CDP if cdp_port_open() else MIN_REFRESH_INTERVAL)):
                log("尝试从浏览器重导 Cookie 并验证…")
                refresh_count += 1
                last_refresh = time.time()
                got, ok = refresh_and_verify(args.exam_id, args)
                if got and ok:
                    cookie = load_cookie_file(args.cookie_file) or cookie
                    auth_fail = 0
                    log("Cookie 已刷新并验证通过，继续盯守。")
                else:
                    dead_streak += 1
                    log("⚠️  重导出的 Cookie 仍然无效 —— 浏览器里的登录态已经失效，"
                        "光刷 Cookie 没用。请打开考试页面重新登录一次。")
                    if dead_streak >= 2:
                        browser_dead = True
                        log("🛑 已连续 2 次刷新后仍无效，暂停自动刷新（不再白白调 CDP）。"
                            "你手动登录并更新 .ilearning_cookie.txt 后，脚本会自动恢复。")
            if auth_fail % 10 == 0:
                log(f"🚨 已连续 {auth_fail} 次鉴权失败。跑一次 "
                    f"`python ilearning_sniper.py --refresh-cookie` 手动更新 Cookie，"
                    f"或直接覆盖 {args.cookie_file}")
            time.sleep(backoff)
            continue
        except Exception as e:
            log(f"第 {round_no} 轮拉取失败: {e}")
            if args.once:
                sys.exit(1)
            time.sleep(args.interval)
            continue

        if args.session_id:
            sessions = [s for s in sessions if str(s.get("id")) == args.session_id]

        # 有余额 = remainingQuota > 0
        avail = [s for s in sessions if (s.get("remainingQuota") or 0) > 0]

        # 记录「已报人数」变化。如果已报人数掉了（有人取消）而剩余名额仍为 0，
        # 就说明取消并不会释放名额 —— 这是判断「等取消到底有没有用」的关键证据。
        for s in sessions:
            sid = str(s.get("id"))
            n = s.get("sessionUserNum")
            if sid in seen_booked and seen_booked[sid] != n:
                log(f"★ {s.get('roomName')} 已报人数 {seen_booked[sid]} -> {n}"
                    f"（同期剩余名额 {s.get('remainingQuota')}）")
            seen_booked[sid] = n

        line = f"第 {round_no} 轮：共 {len(sessions)} 场，有余额 {len(avail)} 场"
        log(line)
        for s in sorted(sessions, key=lambda x: str(x.get("beginTime")))[:10]:
            log("   " + fmt_session(s))

        if avail:
            beep()
            # 优先选时间最近的
            target = sorted(avail, key=lambda x: str(x.get("beginTime")))[0]
            if args.once:
                print("\n--once 模式：只展示，不报名。")
                break
            booked = try_book(args.exam_id, target, cookie, args.execute)
            if booked and args.execute:
                break
            if booked:  # 已报过
                break

        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已停止。")
