# McMuseum 提交前终检清单（2026-10-13）

> 用途：截止前（约 2026-10-26）最后一次自检，逐条确认"官方清单齐备 / 文档诚实 / 演示无破绽 / 真实链路 / 部署在线 / 图片自洽 / 安全无泄露"。
> 结论速览：**代码与文档已就绪、诚实、自检全绿；唯一阻断性风险是线上部署陈旧，必须在截止前重发。**

---

## 一、官方提交清单齐备性 ✅

| 官方要求文件 | 状态 | 备注 |
|---|---|---|
| `CONTEST_DECLARATION.md` | ✅ | SHA256=`cd28101bcb29cc8fb24b372fe91ce6b42c4a1487a54e01f7ade0c8c6a84241b7`，与官方基准逐字一致（1522 bytes） |
| `README.md` | ✅ | 产品数表述为 81 款 / 68 款在投票池，准确 |
| `MCP_INTEGRATION.md` | ✅ | 存在 |
| `mcp-config.example.json` | ✅ | `type:"streamablehttp"`，Authorization 仅 `${MCD_MCP_TOKEN}` 占位，无真实 token |
| `workbuddy.md` | ✅ | 存在 |
| `SKILL.md` | ✅ | 存在 |
| 源码 | ✅ | 全部在仓库内 |

---

## 二、文档诚实性（零越界措辞）✅

- **禁用词扫描**（"从机制上杜绝 / 跨用户真实聚合 / 数据闭环 / 自动匿名回流 / 强身份防刷 / 全网共同 / 全民聚合"）：`README.md` / `SKILL.md` / `docs/DEMO_GUIDE.md` / `MCP_INTEGRATION.md` 全部 **0 处** ✅
- **三条能力边界速览** 已置于 README 文首（第 8 行）✅
- **未实现边界逐条列出**：跨实例全局去重未实现、共享榜输入源仅限信任锚点账号自身评论 ✅
- **自检 9.19 文档诚实性防回归**：`selfcheck.py` → 63 通过 / 0 失败 / 1 提醒 ✅

---

## 三、演示模式无破绽 ✅

- 常驻斜纹「演示数据」横幅（`web/app.js` L99-107、`web/index.html` L542-544）✅
- 演示模式 `POST /api/vote` = **501** `demo_mode_vote_disabled`（`web/serve.py` L101-105）✅
- `data/demo_votes.json` 带 `_demo:true`，与正式账本 `votes.json` 物理隔离 ✅
- 自检确认"演示票无入口进正式榜" ✅

---

## 四、真实链路 + 安全性 ✅ / ⚠️

- **自检 63 项**覆盖：MCP 只读红线、投票能力三态、账本并发锁、GitHub 故障诚实降级 ✅
- **Token 安全**：本地 `.env` 含真实 `GITHUB_TOKEN`，但 `.gitignore` 第 7 行已忽略，且 `git ls-files` 确认**未跟踪** → 公开仓库无泄露 ✅
  - `scripts/test_scenarios.py:428` 的 `ghp_SUPERSECRET_...` 仅为测试夹具假串，非真 token。
  - 🔎 提醒：该 `.env` token 仅存在于本机磁盘且未被提交；如曾粘贴给第三方工具，建议轮换。

---

## 五、部署入口 ⚠️🔴 最高优先级（阻断性）

线上站点 `https://mcmuseum-revival.app.workbuddy.host/` 经核查为**旧版本构建**，与当前代码不一致：

| 核查项 | 线上实际 | 当前代码应得 | 结论 |
|---|---|---|---|
| `GET /api/vote-capabilities` | `{"error":"not found"}` | 返回三态能力声明（`serve.py` L369-371，自检已覆盖） | ❌ 线上缺该路由 |
| `GET /api/leaderboard` 条目数 | **51** | **81**（数据 `nostalgic_products.json`：81 款、68 款在投票池） | ❌ 线上仍是扩库前计数 |

→ 说明线上跑的是「数据大扩库 `88884cb` + 投票能力对齐 `8ac53c5`」**之前**的构建，可能还早于设计重构。
**动作**：用当前代码重新发布。部署描述符已存在：
- `appId = wbapp_BvqPGWuQ6kAFqhVAXh1FE4`
- `localDir = D:\WorkbuddyTemp\2026-10-10-21-21-06\McMuseum`
- 发布后复验：`/`=200、`/api/vote-capabilities` 返回三态、`/api/leaderboard` 返回 81 条目、`/api/account`=200、演示横幅在位。

---

## 六、GitHub 仓库 About 描述 ⚠️ 次要

- 当前 `description`：`"...51 款下架产品的怀旧博物馆..."`
- 实际数据：**81 款怀旧单品**（含 7 款仍在售），README 已写 81/68。
- 建议：把 About 改为"81 款怀旧单品"（或"81 款 McDonald's 历史产品"），与 README/站点一致，避免评审看到 51 vs 81 矛盾。

---

## 七、赛事榜单状态 ⚠️ 需主动冲

- 当前 **1 Star**；官方 `RANKING.md`（2026-10-13 11:00 刷新）可见最低 **6 Star**，McMuseum **未进榜**。
- 排名唯一依据 = 公开 Star 数；截止约 2026-10-26。
- 报名 Issue #488 官方已回"参赛成功"，但 Star 榜尚未收录 1 星 → 需拉 Star 才能进榜/提升名次。

---

## 八、线上复验结果（2026-10-13 ~13:25 重新发布后）

重新发布：`shareLink` 不变（`https://mcmuseum-revival.app.workbuddy.host/`），`verified=true`，`sandboxId=9d78aa16e12e4735ab33027c3bfe4ddd`，部署源 = 仓库 `main` HEAD `658cedc`。

| 验收项 | 结果 |
|---|---|
| `GET /` | HTTP **200** ✅ |
| `GET /api/vote-capabilities` | 返回三态（`voting_available=False`、`code=vote_not_supported_here`、`demo=False`）✅ **修复 not found** |
| `GET /api/leaderboard` | `source=github`（真实共享榜恢复），**46 条**真实会员票；无本地测试票混入 ✅ **修复 local 回落** |
| `GET /api/account` | HTTP **200** ✅ |
| `POST /api/vote` | HTTP **501**（公开站点不创建正式票）✅ 安全 |
| 演示横幅 | `demo=False` → 公开站点非演示模式，不显示「演示数据」横幅（属正确状态）✅ |

**修复说明（重要）**：第一次重新发布后，榜单 `source=local` 且只剩 1 条本地测试票（樱花麦旋风=1），原因是重发时丢失了发布环境的 `LEADERBOARD_SOURCE=github` 环境变量（`serve.py` 的 `_use_github()` 只读该变量）。已在本地 `.env` 补回 `LEADERBOARD_SOURCE=github`（`.env` 已被 gitignore，仅本地/部署用，不会进公开仓库）。**建议同时在 WorkBuddy 平台「设置—数据管理—应用」里把 `LEADERBOARD_SOURCE=github` 固化为应用环境变量**，以免下次重发再次丢失。

**预期修正**：清单原写"leaderboard 返回 81 条"是对接口的误解——`/api/leaderboard` 列的是**得票产品**（当前 46 款有真实 GitHub 票），并非全部 81 款。如需榜单列出全部 81 款（未得票显示 0），需改 `web/serve.py` 的 leaderboard 路由（待定，见下）。

## 九、待用户定夺

1. **榜单是否列出全部 81 款**：当前列"得票产品"（46 款真实票）。若希望展示完整博物馆排名（81 款含 0 票），需小幅改代码；否则保持现状（更诚实体现"复活意愿"）。
2. **GitHub About 描述**：发布验证已通过，请把仓库 About 的「51 款下架产品」改为 `81 款 McDonald's 历史产品｜McRevival 怀旧复活赛`（在面板/仓库设置改，因含在售品不写"下架"）。

---

## 终检结论

- 代码、文档、诚实性、演示隔离、安全：✅ 全部通过。
- **原阻断性风险（线上部署陈旧）已修复并复验通过**：`/api/vote-capabilities` 恢复、榜单切回真实 GitHub 共享榜（46 款真实票，无测试票混入）、投票仍 501 不可伪造。
- 次要：GitHub About 51→81 对齐（用户改）；榜单"81 款全列"为可选增强；赛事端需冲 Star 进榜。
