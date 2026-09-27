# iLearning 考试报名接口探测报告

> 目标页面：`https://ilearning.huawei.com/iexam/100000/examInfo?examId=54085`
> 上机编程认证科目-iLearning（专业级，Python）
> 探测方式：Playwright 扩展模式接管本机 Edge 已登录 Tab + 前端 JS 反查 + 接口实测
> 日期：2026-09-24

## 🏆 最终结果：抢到了（2026-09-27 17:15:49）

盯守连续运行 **46 小时 48 分 / 5330 轮**，在第 5290 轮命中并成功报名：

```
[2026-09-27 17:15:47] 第 5290 轮：共 4 场，有余额 1 场
    科目一上研青浦20261223 | 2026-12-23 18:30 | 剩余 1 | 已报 159

[命中] 科目一上研青浦20261223 剩余 1
  校验通过 剩余名额=1 我已报名=0 预约窗口 2026-09-02 10:00 ~ 2026-12-21 18:00
  ✅ 报名成功：操作成功            （17:15:49，距命中仅 2 秒）
```

**API 复核**（不只信日志）：

```
bookId=2104137928464953346 | 上机编程认证科目-iLearning（专业级，Python）
                             | 科目一上研青浦20261223 | 2026-12-23 18:30
                             | 取消截止 2026-12-21 18:00
已报人数 159 → 160，剩余名额 1 → 0
```

两天运行健康度：**281 次 Cookie 自动保鲜 + SSO 预热，全部验证通过，零人工介入**。
只有 3 次短暂 401（9/26 15:32、9/27 15:43），都在几分钟内自愈。

### 名额是「管理员放的」，不是「别人退的」

全程 `★ 已报人数变化` 一条都没触发——**两天里已报人数纹丝不动（159）**，
而剩余名额突然从 0 变 1。说明这个名额是**管理员从池子里放出来的**，
不是取消退回的。这也印证了前面的判断：`remainingQuota` 是独立的发放池。

> 所以「盯别人取消来捡漏」这个假设是错的，但**「盯管理员放名额」是对的**——
> 盯守 46 小时后终于等到了一次。

## 结论

**可以自动化，并且不需要爬页面。** 站点是纯前后端分离，报名全链路都是 JSON/XHR 接口，
凭 Cookie 即可直接调用，无 CSRF token、无签名、无验证码。已实测跑通到「报名校验」这一步。

## 一、核心接口（全部实测通过）

统一前缀：`https://ilearning.huawei.com/sxz/api/iexam/api/iexam`
所有请求：`POST` + `Content-Type: application/json` + `sxz-lang: zh_CN` + 浏览器 Cookie（SSO 登录态）

### 1. 场次列表（轮询用这个）

```
POST /userexam/v2/exams/sessions
```

请求体（实测过滤参数有效）：

```json
{
  "examId": "54085",
  "sessionName": "深圳",        // 场次名关键词，空串=全部
  "onlyShowCanReservation": 1,  // 1=只返回可预约场次（服务端已过滤）
  "beginTimeStart": "2026-11-01",  // 考试开始时间下界
  "endTimeEnd": "2026-11-30",      // 考试开始时间上界
  "id": ""                      // 实测传 sessionId 无效，会被忽略
}
```

响应 `data[]` 关键字段：

| 字段 | 含义 |
|---|---|
| `id` | **场次 ID，报名时要用它** |
| `sessionName` / `roomName` | 场次名 / 考场名（如「科目一深圳20261014」） |
| `beginTime` / `endTime` | 考试开始/结束（2026-10-14 18:30） |
| `remainingQuota` | **剩余名额，>0 即可报名** |
| `seatLimit` / `sessionUserNum` | 总座位 / 已报名人数 |
| `userBooking` | 我自己是否已报名（0/1） |
| `appointmentOpenBeginTime` / `EndTime` | 预约开放窗口 |
| `appointmentMax` | 单场预约上限 |
| `countdown` | 距考试开始的秒数 |

实测结果：全量 **60 场**，`onlyShowCanReservation=1` 过滤后 **31 场**，`sessionName=深圳` 过滤后 4 场，
时间范围过滤同样生效。单次响应约 90 KB，60 个场次。

### 2. 报名前校验（只读，不占名额）

```
POST /userexam/v1/exams/checkReservation
body: {"examId": "54085", "id": "<场次ID>"}
```

返回 `code:200` + 该场次完整详情（含 `remainingQuota`、`userBooking`）。
这一步可以在真正提交前再确认一次名额，避免并发抢名额时白跑。

### 3. 提交报名（真正的动作）

```
POST /userexam/v1/exams/reservationExam
body: {"examId": "54085", "id": "<场次ID>"}
```

实测用无效场次 ID 探测的返回：

```json
{"code":500,"message":"session.does.not.exist","data":null}
```

### ✅ 真实报名已实测成功（2026-09-24 15:33）

经授权用真实场次跑了一次完整报名：深圳 20261223（id `2094339437290065922`），返回 `code:200 操作成功`。
报名前后对账，确认真的落库了：

| 字段 | 报名前 | 报名后 |
|---|---|---|
| `userBooking` | 0 | **1** |
| `sessionUserNum`（已报人数） | 7 | **8** |
| `remainingQuota`（剩余名额） | 479 | **478** |
| `userExamStatus` | 40 | **10**（已预约） |

并且在「我的考试 → 预约考试」里能看到这条记录，旁边就是「取消预约」按钮。
**所以接口链路是通的，自动化方案可落地。**

## 二、最大的坑：字段名是 `id`，不是 `sessionId`

后端校验顺序是 `examId is null!` → `sessionId is null!`。
传 `{examId, sessionId}` 会一直报 `sessionId is null!`；把 `sessionId` 换成 **`id`** 立刻 200。
（这个字段命名和列表接口里的 `id` 是同一个，但和直觉相反，容易卡很久。）
另外 `sessionIds` 会触发 500，别用。

### 4. 我的预约列表（查 bookId 用这个）

```
GET /userexam/v1/personalService/getInitUnderwayBookExamtionX/1/20
```

返回 `bookId / examinationName / examinationRoomName / examStartTime / seat /
cancelResEndTime（取消截止时间）`。**`bookId` 是取消预约要用的 ID，和场次 ID 不是一回事。**

### 5. 取消预约（撤销用这个）

```
PUT /userexam/v1/exams/cancelReservationExam/{bookId}
body: {}
```

注意是 **PUT**、参数在 **路径**上、body 是空对象 `{}`。

## 三、其他相关接口（顺带挖到的，本次没用上）

| 接口 | 用途 |
|---|---|
| `GET /userexam/v2/exams/{examId}` | 考试详情（时长/及格分/次数限制/承诺书） |
| `POST /userexam/v1/listCombo` | 场次相关下拉数据 |
| `GET /userexam/v1/examResults/1/30?examId=&lastTwoYear=1` | 我的考试记录（报名后可用来确认） |
| `GET /userexam/v1/getIsRelationCourse/{examId}` | 关联课程 |
| `POST /open/api/iexam/userexam/v1/examCommonVerify/{examId}` | 考试资格校验（开放接口） |

## 四、当前场次余额快照（2026-09-24 15:25）

| 日期 | 有余考场次（剩余名额） |
|---|---|
| 2026-10-14 | 广州 9、深圳 14、成研 1、苏研 8 |
| 2026-11-11 | 济南 20、西研 6、苏研 124、广州 14、深圳 381、成研 152 |
| 2026-12-09 | 西研 399、广州 15、苏研 165、成研 208、深圳 470、松山湖 135、北研 179、济南 24、武研 23 |
| 2026-12-23 | 广州 15、杭研 105、济南 25、松山湖 344、北研 275、苏研 165、南研 146、长沙 2、成研 206、西研 451、武研 154、深圳 479 |

深圳/苏州/成都这类大考场名额充足，真正紧张的是 10-14 批次（多数已满）。

## 五、风险与注意事项

1. **次数限制**：本科目每年 4 次、每月 1 次，当前已用 0 次。报名即占用，脚本误报代价很高 → 默认 dry-run。
2. **报名截止后不可取消/变更**：认证开始前 2 个工作日 18:00 锁定（本次测试场次为 2026-12-21 18:00，时间充裕）。
   另外注意：取消后是否归还「每年4次/每月1次」的次数额度未经验证，别指望取消能无损回滚。
3. **名额是动态的**：10-14 深圳从 17 → 14 只间隔几分钟，说明确实在被抢，轮询有意义。
4. **Cookie 有效期**：SSO 会话过期后脚本会拿到非 200，需要重新导出 Cookie。`.ilearning_cookie.txt` 里是真实登录凭据，别外传。
5. **轮询频率别太高**：建议 ≥15s，60 场全量响应 90 KB，太频繁容易被风控盯上；用 `--city` 关键词过滤可以只返回几条，压力小很多。
6. **合规**：这是公司内部认证系统，自动化只用于「抢自己本来就要报的名额」，不要用来批量占座。

## 五点五、Cookie 怎么更新（重点）

**最重要的是：不用重启盯守进程。** 脚本每一轮都会读一次 Cookie 文件，401 时也会立刻比对，
文件内容一变就自动重载。实测：11:31:04 报 401 → 退避 → 11:33:04 检测到文件更新 → 自动恢复。

### 给程序喂什么格式

**默认是 Header 字符串**（就是 DevTools 里那一整行）。另外三种格式也会自动识别，任选：

| 格式 | 长什么样 |
|---|---|
| **A. Header 字符串**（推荐） | `SESSION=xxx; ilearning-session=yyy; hwssot=...` |
| B. JSON 数组 | `[{"name":"SESSION","value":"xxx","domain":".huawei.com"}, ...]` |
| C. JSON 对象 | `{"SESSION":"xxx","ilearning-session":"yyy"}` |
| D. Netscape cookies.txt | 每行 7 个 Tab 分隔字段 |

四种都已实测通过。

### 三种投喂方式

```bash
# 1) 写进文件（默认）——最省事
#    直接把内容粘进 .ilearning_cookie.txt 保存，盯守下一轮自动生效

# 2) 命令行
python ilearning_sniper.py --cookie "SESSION=xxx; ilearning-session=yyy; ..." --city 上研青浦 --once

# 3) 环境变量
set ILEARNING_COOKIE=SESSION=xxx; ilearning-session=yyy
```

### 手动从浏览器抓（30 秒搞定）

1. 打开 `https://ilearning.huawei.com/...` 任意页面，F12 → Network
2. 刷新，点任一 `ilearning.huawei.com` 的请求
3. Request Headers 里复制 `cookie:` 那一整行
4. 粘进 `.ilearning_cookie.txt` 保存

或者跑 `python ilearning_sniper.py --refresh-cookie`（自动从 Edge 导）。

### 两条自动通道：CDP（推荐）vs 浏览器扩展

| | CDP 调试端口 | Playwright 扩展 |
|---|---|---|
| 人工点授权 | **不需要** | 需要（Tab 授权） |
| 会不会开新标签页 | **不会** | 会（每次 attach 一个 Welcome） |
| 前置条件 | Edge 必须用 `--remote-debugging-port=9222` 启动 | 装了 Playwright 扩展 |
| 适合无人值守 | ✅ | ❌（会把浏览器标签页堆满） |

**启用 CDP（一次性）**：

1. 先在 Edge 里清掉残留标签页（右键标签 → 「关闭其他标签页」），**否则重启后它们会全部恢复**
2. 完全退出 Edge（任务管理器确认没有 `msedge.exe`）
3. 双击 `pw\start_edge_debug.cmd`
4. 浏览器打开 `http://127.0.0.1:9222/json/version`，能看到 JSON 就成功了

之后：

```bash
python ilearning_sniper.py --refresh-cookie --cookie-source cdp   # 手动导一次
python ilearning_sniper.py --city 上研青浦 --interval 20 --execute --yes --cookie-refresh cdp
```

`--cookie-source auto`（默认）会优先用 CDP，检测不到端口才退回扩展通道。
走 CDP 时自动刷新间隔从 30 分钟放宽到 10 分钟（因为不再有开标签页的代价），
且第 1 次 401 就会尝试刷新（扩展通道要等第 3 次）。

**CDP 通道实测（2026-09-25 15:33）**：导出耗时 ~10 秒，拿到 28 条有效 Cookie，
`--my-bookings` 正常返回，**浏览器 page 数量保持 5 不变**（确认不开标签页）。

### 三个坑

1. **`cookie-list` 读不到 HttpOnly cookie** —— CDP 通道必须用 `state-save`
   （Playwright storageState 格式，官方登录态导出，含 HttpOnly）配合 `pw/mkcookie_state.py`。
2. **必须按域过滤，不能全塞**。storageState 有 887 条 cookie，光 `SESSION` 就散落在
   committer / himeeting / w3 / edm3 / libing 等十几个子域，混进来会把真正要用的顶掉。
   浏览器请求 `ilearning.huawei.com` 时只带 `ilearning.huawei.com` 和 `.huawei.com` 两类，
   按同样规则过滤后正好 28 条。
3. **Cookie 快照会老化，别等 401 才补**。实测 15:34 拿的快照用到 16:41 就 401；
   16:54 补的快照到 17:09 又 401。但现场重新导一次立刻就好 —— 说明浏览器登录态没事，
   是**快照冻结**在某一刻，而服务端会话只有十几分钟到一小时。
   所以加了 `--refresh-every 600`：**主动保鲜**，每 10 分钟静默重导一次，不等 401。
   401 退避上限也从 900s 压到 300s。

4. **「导出成功」不等于「Cookie 可用」**（2026-09-25 18:13 定案）。
   现场重新 CDP 导出后**第一个请求就是 401**，响应头里 9 个 `Set-Cookie` 全是
   `Expires=Thu, 01 Jan 1970`（删除指令）：`login_uid` / `idaas_login_token` / `login_sid`。
   即**服务端已判定该会话无效，并主动清登录态**。
   CDP 只是把浏览器里现存的 Cookie 原样搬出来——浏览器自己都掉登录了，搬出来自然没用。
   所以脚本现在会在刷新后**真打一次接口验证**，无效就明确报
   「浏览器登录态已失效，请重新登录」，而不是含糊地说「导出成功」。
   连续 2 次无效就停掉自动刷新，等你人工登录。

5. **CDP 的 `/json/new?url=` 不会跳转**（这台 Edge 140.0.3485.81 上只会开出 `about:blank`）。
   要开页面必须用 playwright 的 `tab-new`，它能正常导航。
   顺带验证：访问 `https://ilearning.huawei.com/` 会**自动完成 SSO 登录**，落地 `/edx/next/`。
   → 因此取 Cookie 流程改成「开页面预热 6s → 导出 → 关标签页」，**浏览器登录态失效也能自愈**，
   彻底不需要人工介入。实测：手动写入失效 Cookie → 预热导出 → 接口恢复。

6. **⚠️ 强杀 Edge 会清掉 SSO 会话 Cookie**。`hwssot` / `SESSION` / `ilearning-session` /
   `SESSIONID` / `hwsso_login` 都是**会话级 Cookie（无过期时间）**，Chromium 只在**正常退出**时
   才落盘；`taskkill /F` 直接丢，之后 iLearning 需要重新登录。
   `restart_edge_debug.cmd` 已改成「先优雅关闭 → 等 6 秒 → 检测残留 → 才强杀」。

> 安全提示：9222 只监听 127.0.0.1，但本机任何程序都能通过该端口完全控制浏览器。
> 不需要时正常重启一次 Edge 即可关闭。

> Cookie 实测寿命约 **25~70 分钟**，所以无人值守过夜的话需要中途补几次，
> 或者显式开 `--cookie-refresh auto`（30 分钟冷却 + 单轮最多 3 次，会碰 Edge）。

## 六、配套脚本

`ilearning_sniper.py`（同目录），Python 3 标准库，无第三方依赖。

```bash
# 1) 先只看一次，确认 Cookie 有效
python ilearning_sniper.py --city 深圳 --once

# 2) 盯某个场次，每 20s 刷一次（dry-run，只打印不报名）
python ilearning_sniper.py --session-id <场次ID> --interval 20

# 3) 确认无误后真报名（会二次确认）
python ilearning_sniper.py --city 深圳 --interval 20 --execute

# 4) 查看我已预约的考试（含 bookId）
python ilearning_sniper.py --my-bookings

# 5) 撤销这次测试报名
python ilearning_sniper.py --cancel 2103025240124702722
```

当前状态：**深圳 20261223 的测试报名已撤销**（用的就是第 5 条，返回「取消预约成功！」）。
你的「我的考试」里只剩原本那条：软件设计与重构认证 科目四上研青浦20261216。

> ⚠️ 踩坑记录：`cancelReservationExam` 后面跟的是**场次 ID**（`2094339437290065922`），
> 不是「我的预约」接口返回的 `bookId`（`2103025240124702722`）。
> 传 bookId 会返回 `500 用户没有预约记录或已失效`。已修正进脚本。

## 七、上研青浦盯守（当前正在跑）

需求：只要「科目一上研青浦」，四场全部名额为 0，靠捡别人取消的漏。

```bash
python ilearning_sniper.py --city 上研青浦 --interval 15 --execute --yes
```

已在后台跑起来（每 15s 一轮），命中即：响三声蜂鸣 → 校验 → 提交报名 → 自动停。
日志实时写在 `sniper.log`。命中的场次默认取**时间最近**的一场；
想锁定某场加 `--session-id <ID>`，想限定日期加 `--date-start/--date-end`。

Cookie 自愈：脚本遇到 401 不再退出，会自动调 `pw/getcookie.sh` 从已登录的 Edge 重新导出
Cookie 并继续；自动刷新失败则每 120s 重试一次，期间手动覆盖 `.ilearning_cookie.txt` 也能被读到。
（`pw/mkcookie.py` 已加保护：导出为空时**不覆盖**原 Cookie 文件。）

> 2026-09-24 19:33 第一轮盯守跑了 143 轮后因 401 中断；19:45 用同一份 Cookie 内容重试即恢复，
> 说明那次 401 多半是平台升级维护导致的瞬时故障，不是真过期。Cookie 实测寿命 40 分钟到 3 小时不等。

上研青浦四场（2026-09-24 18:57 快照）：

| 场次 | 场次 ID | 剩余 | 预约截止 |
|---|---|---|---|
| 20261014 | `2094339417358733313` | 0 | 2026-10-12 18:00 |
| 20261111 | `2094339424270946306` | 0 | 2026-11-09 18:00 |
| 20261209 | `2094339430499487745` | 0 | 2026-12-07 18:00 |
| 20261223 | `2094339437273288706` | 0 | 2026-12-21 18:00 |

**一个反常现象**：这四场 `seatLimit / roomUserNum / appointmentMax` 都是 760，已报才 123~162，
但 `remainingQuota` 就是 0。说明 `remainingQuota` 不是「容量 − 已报」，而是一个独立名额池
（深圳场次也是：容量 510、已报 7，剩余只有 478）。所以别拿容量去推算，只认 `remainingQuota`。
推论：如果管理员压根没给上研青浦放名额，光靠等取消可能等不到 —— 盯一段时间没动静的话，
建议直接找考试管理员（杨金兰 84298454）问放名额的节奏。

Cookie 已导出到 `.ilearning_cookie.txt`；过期后重新从浏览器 F12 → Network → 任一
`ilearning.huawei.com` 请求的 Request Headers 复制 `cookie` 值覆盖即可。
