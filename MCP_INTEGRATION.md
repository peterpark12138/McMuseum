# MCP_INTEGRATION.md · 麦当劳 MCP 真实集成说明

本作品通过官方 **麦当劳 MCP**（`https://mcp.mcd.cn`，Streamable HTTP + Bearer Token）完成全部会员与数据能力。**仅读取，绝不扣减、绝不下单。**

## 1. 连接方式

- 客户端：`scripts/mcp_client.py`（纯标准库实现 `initialize` 握手 / `tools/list` / `tools/call`）。
- 鉴权：`Authorization: Bearer <MCD_MCP_TOKEN>`，Token 仅经环境变量或 `.env`（已被 `.gitignore` 排除）注入，**禁止明文入库**。
- 服务端共 35 个工具；本作品按「只读白名单」受控使用。

## 2. 只读红线（调用层强制）

所有 MCP 调用必须经过 `scripts/mcd_data.py` 的 `safe_call()`：

- `READ_ONLY_TOOLS`：27 个只读工具白名单，不在名单内直接抛 `ValueError` 拒绝。
- `WRITE_TOOLS`：8 个写/交易类工具（`create-order` / `mall-create-order` / `party-order-create` /
  `cancel-order` / `draw-lottery` / `auto-bind-coupons` / `calculate-price` / `delivery-create-address`）
  **在调用层被硬性拦截**，任何代码路径都无法触达。
- `scripts/selfcheck.py` 含防回归测试：逐一验证 8 个写工具被拒绝、只读工具放行。

补充说明：白名单校验**同时存在于客户端 `scripts/mcp_client.py` 的 `call_tool()` 入口**（不在
`READ_ONLY_TOOLS` 内一律抛 `ValueError`），即校验下沉到了最底层调用点，任何绕过
`mcd_data.safe_call()` 的新增代码路径同样被拦截。`selfcheck.py` 对客户端层有独立
拒绝测试（8 写工具逐一验证 + `mcp_client.py` 源码白名单断言 + 只读放行验证）。

## 3. 实际使用的工具与业务映射

| 工具 | 业务价值 | 调用位置 |
|------|---------|---------|
| `query-my-account` | 会员身份确认（`accountId` 强身份去重）+ 积分换算投票（`availablePoint // 100`），仅读余额 | `revival.py real_account_info()` |
| `query-meals`（需 `storeCode`） | 「在售 vs 怀旧」对比：将 MCP 实时返回的在售餐品与本地怀旧单品库（47 款，供应状态按证据分级标注）做交集对照，展示哪些怀旧单品当前仍在售 | `mcd_data.get_current_meals()` |
| `delivery-query-addresses` → `delivery-query-stores` | 省份自动识别（仅取省级，不读取/不落盘地址原文）+ 附近门店展示 | `mcd_data._get_address_and_stores()` |
| `list-nutrition-foods` | 160 款餐品实时营养库（前端可搜索） | `mcd_data.get_nutrition()` |
| `campaign-calendar` | 营销活动日历（「麦麦现在」页） | `mcd_data.get_campaigns()` |
| `mall-points-products` | 积分商城速览（仅展示，不兑换） | `mcd_data.get_points_mall()` |
| `query-lottery-info` | 积分抽奖活动速览（仅展示，不抽奖） | `mcd_data.get_lottery_info()` |

## 4. 缓存与频控

- 所有抓取结果按 TTL 落盘 `data/cache/`（6 小时；已被 `.gitignore` 排除，不入库），避免高频打扰麦当劳接口（限 600 次/分钟）。
- 无 `MCD_MCP_TOKEN` 时所有数据源优雅降级为空值 + 前端「连接账号后查看」占位，公开部署不持有任何 token。

## 5. 会员身份的作用域（公开站点为什么不能帮你投票）

`query-my-account` 返回的是**当前 Token 持有人**的会员信息。这意味着：

- 服务端拿到的永远是「服务器自己那份 Token 的会员」，**不是访客的会员**；
- 因此公开站点调用它去投票，等于「用作者/部署者的会员身份替所有人投票」，属于伪造票数；
- 把访客的个人 Token 交给公开服务器保存，又会带来泄露与越权风险。

本作品的结论是**公开站点默认不提供在线投票**，并把这条做成可验证的硬约束：

| 部署形态 | `POST /api/vote` |
|---|---|
| 公开站点（默认） | **501** `vote_not_supported_here`（按钮置灰 + 本机 CLI 引导） |
| 显式开启但无 Token | **503** `member_auth_unavailable` |
| 可信本机（`MCMUSEUM_ENABLE_SERVER_VOTE=1` + 本人 Token） | 真实调用 `query-my-account` 认证后计票 |

另有两条不可绕过：请求体携带任何 `member*` / `card*` / `openid` / `token` 字段一律 **400**
`client_identity_not_accepted`；`from_mcp=True` 只表示"允许去认证"，**不等于已认证**，
解析不出会员唯一标识即拒绝投票。验证方式：`python3 scripts/selfcheck.py` 与 `python3 scripts/smoke_http.py`。
