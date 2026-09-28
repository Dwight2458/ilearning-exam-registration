# ilearning-exam-registration

iLearning 考试场次「抢名额」工具。

用途：高频轮询考试场次列表，检测到目标场次出现余额时自动提交报名。
当前盯的科目：`examId=54085` 上机编程认证科目-iLearning（专业级，Python），关键词 `上研青浦`。

> ⚠️ **合规提醒**：这是公司内部认证系统。自动化只用于「抢自己本来就要报的名额」，
> 不要用来批量占座。报名会占用次数额度（本科目：每年 4 次 / 每月 1 次），
> 且报名截止后不可取消或变更。

## 文件说明

| 文件 | 说明 |
|---|---|
| `ilearning_sniper.py` | 主程序：轮询 + 自动报名，默认 dry-run |
| `iLearning报名接口探测报告.md` | 接口清单、字段说明、实测记录、踩坑记录 |
| `pw/getcookie_cdp.sh` | 通过 CDP 取 Cookie，**含 SSO 自动重登录**（推荐） |
| `pw/check_sso.py` | 诊断：验证「开页面能否自动登录」 |
| `pw/getcookie.sh` | 通过 Playwright 扩展导出 Cookie（备用，会临时开标签页） |
| `pw/mkcookie_state.py` | 把 storageState JSON 过滤成请求头字符串 |
| `pw/mkcookie.py` | 把 cookie-list 文本过滤成请求头字符串 |
| `pw/start_edge_debug.cmd` | 以调试端口启动 Edge（Edge 需先完全退出） |
| `pw/restart_edge_debug.cmd` | 关闭 Edge 再带调试端口重启（优雅关闭优先） |
| `pw/count_tabs.sh` | 统计残留的 Playwright Welcome 标签页 |
| `recon/` | 接口侦察留档（场次列表响应、请求头等） |

## 快速开始

```bash
# 1) 确认 Cookie 有效
python ilearning_sniper.py --my-bookings

# 2) 看一眼目标场次现状
python ilearning_sniper.py --city 上研青浦 --once

# 3) 盯守（推荐参数：CDP 通道 + 每 10 分钟主动保鲜）
#    已报名的场次用 --exclude-id 排除，避免重复报名多占考试次数额度
python ilearning_sniper.py --city 上研青浦 --interval 30 --execute --yes \
    --cookie-refresh cdp --cookie-source cdp --refresh-every 600 \
    --exclude-id 2094339437273288706
```

`--execute` 才会真正报名，不加就是 dry-run 只打印。

### 排除已报名的场次

```bash
--exclude-id 2094339437273288706            # 场次 ID，可重复
--exclude-name 20261223                     # 按场次名关键词，可重复
```

报名成功后会**自动退出**（`while not booked`），所以重启盯守时如果不想再抢已有场次，
务必带上排除参数——否则一有名额就会再报一场，白占一次额度（每年 4 次 / 每月 1 次）。

场次 ID 可以用 `--city 上研青浦 --once` 看到，或在「我的考试 → 预约考试」里核对场次名。

## Cookie 怎么来

轮询本身**只需要 Cookie，不需要浏览器**。两种自动通道：

**CDP（推荐）** —— 不弹授权、不开新标签页：

1. 完全退出 Edge（后台进程也要退，见 `pw/restart_edge_debug.cmd`）
2. 双击 `pw/start_edge_debug.cmd`
3. 验证：浏览器打开 `http://127.0.0.1:9222/json/version`，看到 JSON 就成功

**手动** —— 浏览器 F12 → Network → 点任一 `ilearning.huawei.com` 请求 →
复制 Request Headers 里的 `cookie:` 整行 → 存进 `.ilearning_cookie.txt`。
四种格式都认（Header 字符串 / JSON 数组 / JSON 对象 / Netscape）。

**Cookie 会老化**（实测十几分钟到一小时），所以加了 `--refresh-every 600` 主动保鲜；
即使不用保鲜，脚本也会每轮读一次 Cookie 文件，手动改了立刻生效、不用重启进程。

### SSO 自动重登录（关键，实现无人值守）

取 Cookie 时会先用 CDP **开一个标签页访问 `https://ilearning.huawei.com/`**，
页面会自动走 SSO 重新登录（实测落地 `/edx/next/`），等 6 秒后再导出，最后按索引把
这个临时标签页关掉。所以即使浏览器登录态失效了，也不需要人工介入。

```
失效 → 开页面触发 SSO 自动登录 → 等 6s → 导出并验证 → 恢复轮询
```

已验证：手动写一份失效 Cookie 模拟过期 → 走上述流程 → 接口恢复正常。

开关（环境变量）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `SSO_WAIT` | `6` | 预热等待秒数 |
| `SKIP_SSO` | `0` | 设为 `1` 跳过预热（只导出） |
| `SSO_URL` | `https://ilearning.huawei.com/` | 预热页面 |

> 注意：开标签页用的是 playwright 的 `tab-new`，不是 CDP 的 `/json/new?url=`——
> 这台 Edge 上后者只会开出 `about:blank`，URL 参数不生效。
> 关闭前会校验该索引上确实是 iLearning 页，不匹配就跳过，宁可留一个多余标签页也不误关你的标签页。

## 几个已经踩过的坑

- `playwright-cli attach --extension` **每调用一次就在浏览器开一个 Welcome 标签页**——
  放进循环会一夜堆出上万个标签页。已在 `playwright-extension-tabs` skill 里记为反模式。
- **强杀 Edge 会清掉 SSO 会话 Cookie**（它们是会话级、无过期时间，只有正常退出才落盘）。
  之后需要重新登录 iLearning。
- `cookie-list` 读不到 HttpOnly cookie，CDP 通道必须用 `state-save`。
- storageState 里 `SESSION` 等名字在 huawei 十几个子域重复，必须按域名（精确域 +
  `.huawei.com` 父域）过滤，否则会被别的子域的同名 cookie 顶掉。
- 接口的场次 ID 字段名是 **`id`**，不是 `sessionId`；取消预约接口传的也是场次 ID，不是 bookId。

## 前置依赖

- Python 3（标准库，无第三方依赖）
- Windows + Git Bash（脚本里用 `/c/...` 路径）
- `curl` 用于探测 CDP 端口
- `playwright-cli`（可选，但推荐安装）—— Cookie 自动刷新依赖它从 Edge 导出 Cookie。
  不装的话 Cookie 失效后无法自动恢复，需手动从浏览器 F12 复制 Cookie 写入 `.ilearning_cookie.txt`
