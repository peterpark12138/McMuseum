# DEMO_GUIDE · 麦麦复活赛评审复现指南

本指南的**每一条命令都在 macOS / Linux / Windows(Git Bash) 上实测通过**。
Windows 若没有 `python3`，把命令里的 `python3` 换成 `python` 即可（下文统一写 `python3`）。

核心原则先说清楚，避免误读：

| 数据类型 | 来源 | 在哪里能看到 | 会不会进 GitHub 正式榜 |
|---|---|---|---|
| **真实会员数据** | 你本机 `MCD_MCP_TOKEN` 调 `query-my-account` | CLI / Skill 的投票回执 | — |
| **真实共享榜** | GitHub Issue 里机器人匿名评论的聚合 | `ranking --from-github` / `LEADERBOARD_SOURCE=github` | 已是榜本身 |
| **演示数据** | `data/demo_votes.json`（仓库内置示例值） | 仅 `MCMUSEUM_DEMO=1` 启动的页面 | **永远不会**（该模式不提供投票入口） |
| **本地账本** | `data/votes.json`（已被 .gitignore 排除） | `ranking` 默认视图 | 成功回流后是（可用 `MCMUSEUM_SHARED_BOARD=0` 关闭） |

---

## 0. 环境与依赖

- **Python 3.8+**（本项目零第三方依赖，只用标准库；不需要 pip install 任何东西）
- 可选：`.env` 放凭证（已被 gitignore，**不要提交**）

```bash
git clone https://github.com/peterpark12138/McMuseum.git
cd McMuseum
python3 -V                     # 要求 3.8+
```

`.env` 只放你自己的凭证（键名如下，**值不要发给任何人**）：

```
MCD_MCP_TOKEN=你的麦当劳会员Token      # 模式 B 需要
GITHUB_REPO=owner/repo                # 共享榜读写需要
GITHUB_TOKEN=你的GitHubToken          # 只有作者/机器人需要；只读看榜不需要
```

---

## 1. 模式 A · 公开演示模式（无需任何 Token）

```bash
MCMUSEUM_DEMO=1 python3 web/serve.py      # 默认 8000 端口；改端口加 PORT=xxxx
# 浏览器打开 http://127.0.0.1:8000
```

启动日志会明确告诉你现在是什么模式：

```
🍟 麦麦复活赛前端已启动: http://127.0.0.1:8000  (bind 0.0.0.0, 数据源=演示数据(DEMO))
   🧪 公开演示模式：票数为示例数据（页面已标注「演示数据」），不提供在线投票，也不会回流正式共享榜。
   在线投票：❌ 不可用（demo_mode_vote_disabled）——浏览与看榜照常……
```

页面表现（都是**真实可验证**的，不是文案承诺）：

- 页面**顶部常驻黄色斜纹横幅**「演示数据」，任何滚动位置都看得到；
- 榜单来源显示为「⚠️ 演示数据 · 示例票数，非真实投票结果」；
- 投票按钮是灰色不可用的「🔒 演示模式」，点它弹出的是本机投票指引，而不是"投票成功"；
- `POST /api/vote` 返回 **HTTP 501 `demo_mode_vote_disabled`**。

```bash
# 不看页面也能验证（另开一个终端）
curl -s http://127.0.0.1:8000/api/vote-capabilities   # voting_available=false, mode=demo-browse-only
curl -s http://127.0.0.1:8000/api/leaderboard         # source="demo", 带 demo_note
curl -s http://127.0.0.1:8000/api/product?id=sakura_mcfloat   # 单品详情
curl -s -X POST -H "Content-Type: application/json" \
     -d '{"product":"sakura_mcfloat"}' \
     -w "\nHTTP %{http_code}\n" http://127.0.0.1:8000/api/vote   # HTTP 501
```

> **演示数据为什么不可能污染正式榜**：演示模式读的是 `data/demo_votes.json`（只读），
> 写路径始终是 `data/votes.json`；而该模式下 `/api/vote` 直接 501，压根没有写票的入口。
> 这条已被自动化测试覆盖（`scripts/test_scenarios.py` 场景 13）。

---

## 2. 模式 B · 真实投票（本机 CLI / WorkBuddy Skill）

前置：本机已配置 `MCD_MCP_TOKEN`（你自己的麦当劳会员 Token）。

```bash
# 2.1 看有哪些单品
python3 scripts/revival.py museum | head -20

# 2.2 投一票（真实调用 query-my-account 认证 + 读积分，仅读取不扣减）
python3 scripts/revival.py vote --product sakura_mcfloat --from-mcp
# 想带省份维度（34 个省级行政区受控枚举）：
python3 scripts/revival.py vote --product taro_pie --from-mcp --province 上海

# 2.3 成功后会长这样（真实回执，含共享榜同步结果）
# ✅ 麦当劳会员投票成功！《樱花麦旋风》
#    基础票 1（登录确认）+ 积分票 2（250 积分 ÷ 100） = 共 3 票。
#    （仅读取积分，未扣减；按会员号强身份去重）
#    共享榜：已匿名回流 GitHub ✅        ← 同步成功
# 或
#    共享榜：未回流（……原因……）         ← 本地票已算，共享榜没同步，会明确说
```

**"本地成功" 与 "共享榜同步失败" 是分开报的**，不会把前者说成后者。
回执里 `共享榜：未回流（…）` 就表示：本地这一票算数了，但 GitHub 没写进去。

在 WorkBuddy 里直接说「我想给樱花麦旋风投票」即可，Skill 走的是同一套 `revival.py`。

> ⚠️ **本机测试时想避免污染正式榜单**，加沙箱开关，本地照常计票但不往 GitHub 写：
> ```bash
> MCMUSEUM_SHARED_BOARD=0 python3 scripts/revival.py vote --product taro_pie --from-mcp
> # 回执会写明：共享榜：已按 MCMUSEUM_SHARED_BOARD=0 跳过共享榜提交（本机测试模式，不污染正式榜）
> ```

---

## 3. 投票前后看榜

```bash
# 本地账本（data/votes.json）
python3 scripts/revival.py ranking --top 10

# 真实共享榜（GitHub Issue 聚合，跨用户；只读公开 Issue，可无 GITHUB_TOKEN）
python3 scripts/revival.py ranking --from-github --top 10

# 按省份看（投票时传了 --province 才会有分省数据）
python3 scripts/revival.py ranking --top 10 --province 上海
```

本机实测的真实共享榜输出（API 真实返回，非构造）：

```
🏆 真实复活榜 Top 5（GitHub Issue 聚合 · 跨用户）
================================================
1. 摇摇薯条 — 9 票
2. 香芋派 — 9 票
3. 樱花麦旋风 — 4 票
```

想让网页也显示真实共享榜（而不是本地账本）：

```bash
LEADERBOARD_SOURCE=github GITHUB_BOT_LOGIN=你的GitHub用户名 python3 web/serve.py
```

---

## 4. 验证重复投票被拦截（现在就能复现，不需要任何凭证以外的东西）

同一会员对同一单品投第二次，会被强身份去重拦下：

```bash
python3 scripts/revival.py vote --product sakura_mcfloat --from-mcp
python3 scripts/revival.py vote --product sakura_mcfloat --from-mcp
```

本机实测的第二次输出：

```
该麦当劳会员已为《樱花麦旋风》投过票（每会员每单品仅一次），不能重复刷票。
```

HTTP 接口侧对应 **409 Conflict**（不是 200 假成功）。

> 边界说清楚：去重作用域是**单个 `revival.py` 运行实例的本地账本**。
> **跨设备 / 跨实例的全局去重没有实现**——共享榜是匿名聚合（刻意不含会员标识），
> 无法在榜层面判断两票是否同一个人。本作品选择保护用户隐私并如实声明，不宣称全局去重。

---

## 5. 怎么一眼分辨真实数据与演示数据

| 观察点 | 真实数据 | 演示数据 |
|---|---|---|
| 页面顶部 | 无横幅 | 黄色斜纹「演示数据」横幅 |
| 榜单来源文字 | 「GitHub 共享榜 · 匿名票数聚合」或「本地榜」 | 「⚠️ 演示数据 · 示例票数，非真实投票结果」 |
| `/api/leaderboard` 的 `source` | `github` / `local` / `local(fallback)` | `demo`（并带 `demo_note`） |
| `/api/vote-capabilities` | `demo` 字段为 `false` | `demo: true`、`mode: demo-browse-only` |
| 投票按钮 | 「投一票」（仅可信本机） | 灰色「🔒 演示模式」，点了给指引 |
| GitHub 上能否查到 | 能，机器人匿名评论 `vote mcp +N <省份> <日期> rid=…` | 查不到，演示票从不提交 |

GitHub 上真实票长这样（可在仓库 Issue 里直接核对）：

```
vote mcp +3 上海 2026-10-13 rid=9f2c1a4b77e1
```

聚合时**只认机器人账号**发的、票种为 `mcp`/`backfill` 的这类评论；其他人手写 `vote ... +9999` 一律不计。

---

## 6. 缺少凭证时，哪些功能不可用

| 缺失项 | 仍然可用 | 不可用 |
|---|---|---|
| 无 `MCD_MCP_TOKEN` | 浏览 81 款单品、单品详情、看本地榜 / 演示榜 / 真实共享榜（只读公开 Issue）、公开演示模式 | **真实投票**（CLI/Skill 与网页都不行，会明确提示先连接账号，不降级、不匿名兜底） |
| 无 `GITHUB_REPO` | 本地投票、本地看榜 | 共享榜读写（`ranking --from-github` 会提示未配置，而不是假装 0 票） |
| 无 `GITHUB_TOKEN` | 读真实共享榜（公开 Issue 只读即可，需 `GITHUB_BOT_LOGIN` 锚定信任） | 写共享榜（本地票照算，回执如实写"未回流"） |
| 两者都无 | 完整浏览 + 演示模式 | 一切真实投票与共享榜写入 |

网络故障时同样不撒谎：GitHub 返回 403 / 429 / 500 / 超时，聚合会标记失败并**回退本地榜**，
不会把"读不到"显示成"0 票"。

---

## 7. 清理测试数据（避免污染正式榜）

```bash
# 7.1 只清本地账本（votes.json 已被 gitignore，不入库；删掉即可重来）
rm -f data/votes.json data/.votes.lock
python3 scripts/revival.py ranking --top 5      # 回到空榜

# 7.2 清缓存的 MCP 只读数据
rm -rf data/cache

# 7.3 只清前端生成的榜单快照
rm -f web/leaderboard.json

# 7.4 已经写进 GitHub 共享榜的票**：评论一旦发出就无法"撤销计票"**（聚合只读评论）。
#     正确做法是别让它发生：测试时始终加 MCMUSEUM_SHARED_BOARD=0；
#     如需人工修正，在对应 Issue 删除机器人误发的评论后重新聚合即可。
```

绝对不要做的三件事：

1. 不要把 `.env`、`data/votes.json` 提交到仓库（已在 `.gitignore` 里，别强推）；
2. 不要把 Token 贴到聊天、Issue、截图或录屏里；
3. 不要为了"让演示好看"去手改 `data/votes.json` 冒充真实票。

---

## 8. 跑自动化测试（评审可直接复现）

```bash
python3 scripts/test_scenarios.py       # 15 个场景，全 mock，离线可跑（不需要任何凭证）
python3 scripts/smoke_http.py           # 端到端：真起 4 种部署形态的服务做 HTTP 断言
python3 scripts/selfcheck.py            # 全项目自检（含内容充分性、只读红线、能力边界）
```

`test_scenarios.py` 的每个用例都标了性质：

- `[MOCK]` —— mock 隔离麦当劳 MCP 与 GitHub API，在临时目录操作副本账本，
  **不写 `data/votes.json`、不碰 GitHub**，任何环境结果一致。
- `[REAL]` —— 真实集成，默认**跳过**并显示 ⏭️；需加 `--real` 才执行。
  **跳过不算通过**，汇总里单列。

```bash
# 想跑真实集成（需你本机凭证，脚本不会打印会员标识与 Token；只读，不会提交任何票）
python3 scripts/test_scenarios.py --real
# 等价写法
MCMUSEUM_REAL_INTEGRATION=1 python3 scripts/test_scenarios.py
```

本机实测（2026-10-13，Python 3.13.14 / Windows）：

| 命令 | 结果 |
|---|---|
| `test_scenarios.py` | ✅15 / ❌0 / ⏭️2（默认，REAL 未执行） |
| `test_scenarios.py --real` | ✅17 / ❌0 / ⏭️0（真实 MCP 认证成功；真实 GitHub 榜读取成功，46 款已绑定） |
| `smoke_http.py` | ✅13 / ❌0 |
| `selfcheck.py` | ✅61 / ❌0 / ⚠️1（提醒项为 8 款单品 `verified=false` 待核实） |

> `--real` 只做**只读**验证：调 `query-my-account` 确认能解析出会员标识、读一次共享榜，
> 不会投票、不会发评论、不会改动 `data/votes.json`。

---

## 9. 已知未实现 / 待办（如实列出）

- **跨实例全局去重未实现**（原因见第 4 节边界说明）。
- 名录扩充到 81 款后，其中 **35 款尚未在 GitHub 建投票 Issue**，
  作者需执行 `python3 scripts/report_github.py setup` 补建并更新 `data/issue_map.json`；
  未绑定的单品在共享榜上没有对应条目（本地榜不受影响）。
- 8 款单品 `verified=false`（待用官方历史菜单核实），赛前需确认或从名录移除。
