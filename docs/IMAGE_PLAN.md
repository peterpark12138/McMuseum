# 图片档案建设：现状盘点与实施方案

> 本文按「先看现状 → 再给方案 → 确认后动手」产出；所有数字均来自对当前仓库的实测。
> **你的四个决策已确认（迁到 JSON / 旧图降级 unverified / 关闭孤儿 Issue / 一期不下载），
> 一期已于 2026-10-13 实施完成**，结果见文末「六、一期交付结果」。

---

## 一、现状盘点（实测）

| 项目 | 实测结果 |
|---|---|
| 产品总数 | **81** 款（`data/nostalgic_products.json`） |
| 数据里的图片字段 | **完全没有** —— 单品字段仅 `category / era / evidence_level / first_seen / id / last_confirmed_sale / market / name / official_name / sources / status / story / tags / verified / vote_eligible` |
| 图片文件 | `web/assets/products/` 下 **26** 个（10 张 .jpg / 8 张 .png / 8 张 .gif） |
| 图片与产品的关联方式 | **硬编码在 `web/app.js` 的 `HALL_IMG` 常量里**（26 条 `id -> 路径`） |
| 图片覆盖率 | **26 / 81 = 32.1%** |
| 映射一致性 | 映射 26 条 ↔ 文件 26 个，**0 缺失、0 孤儿**（这点很干净） |
| 图片元数据 | **0** —— 无来源 URL、无来源类型、无授权、无匹配置信度、无状态 |
| 无图兜底 | emoji（`iconFor(p)`），已有统一占位样式 |
| 加载失败兜底 | **缺失** —— `<img>` 没挂 `onerror`，文件 404 时会显示浏览器破图 |
| 历史中间产物 | `data/_img_reject/`（已被 `.gitignore` 的 `data/_*` 忽略） |

### 现有注释与实际可证明性

`HALL_IMG` 上方写着「官方菜单图 + 网络搜集实物照，**均已人工核对**」。

但仓库内**没有任何逐张的来源记录**来支撑这句话 —— 无法回答"第 7 张图来自哪个网页、什么时候下的、许可如何"。
按你给的七字段标准，这 26 张在补齐 provenance 之前**只能落在 `unverified`**，不能沿用"已核对"的旧口径。

---

## 二、与你给的任务书的三处差异（需先确认）

1. **任务书假设数据里已有 `image` 字段**，实际没有 —— 图片关系是前端 JS 常量。
   这是当前最大的技术债：元数据无处安放、无法追溯、也无法被脚本校验。
2. **任务书要求"不要仅在 `nostalgic_products.json` 加 `image` 字段"** —— 这里正好相反：
   目前是**只在 JS 里、数据里一点没有**。所以本次的方向是"把 JS 里的事实搬进数据并补全元数据"，而不是"给已经有字段的数据加元数据"。
3. **26 张现有图处于"图有、出处无"的状态**，需要先做一轮 provenance 补录（或老实降级标记），
   否则新加的 `image_source_url` 等字段对它们全是空值，等于把旧的技术债原样搬进新结构。

---

## 三、实施方案

### 3.1 数据结构（每款产品新增 7 字段）

```json
"image":              "assets/products/sakura_mcfloat.jpg",
"image_status":       "verified | unverified | reconstruction | missing",
"image_source_url":   "https://...",
"image_source_name":  "官方 / 媒体 / 消费者 / AI 复原",
"image_rights":       "授权情况或使用限制",
"image_confidence":   "high | medium | low",
"image_note":         "年份、包装差异、复原说明"
```

兼容约束（红线）：不删不改任何现有字段；投票 / 榜单 / `vote_eligible` / `verified` 逻辑一律不动；
旧版 `HALL_IMG` 在迁移期内保留作为回退，确保一次迁移中断也不会白屏。

### 3.2 新脚本 `scripts/image_research.py`（子命令）

| 子命令 | 作用 |
|---|---|
| `plan` | 为每款**缺图**产品生成中文 + 英文搜索词，输出 CSV/JSON 审核清单 |
| `review` | 录入候选：URL / 出处网页 / 来源名称 / 匹配理由 / 授权状态 → `data/image_candidates.json` |
| `adopt` | 人工批准后写回产品 JSON；**`image_status` 默认落 `unverified`，脚本绝不自动标 `verified`** |
| `download` | **仅在候选显式标记 `rights=allowed` 后**才下载；校验 magic bytes / 尺寸 / SHA256 去重 / 稳定文件名 |
| `verify` | 静态校验（见 3.5） |
| `report` | 输出覆盖率、缺失清单、待核实清单、新增/变更文件清单 |

**诚实性硬约束**：当前环境没有可用的图片搜索 API，因此 `plan` **只生成检索清单**，不伪造"已搜到 N 张"。

### 3.3 明令禁止（写进脚本与文档）

- 不把搜索引擎缩略图当原图；不绕登录 / 付费墙 / 反爬；不批量抓取社交平台图片。
- 无明确许可不把外部图片打包进公开仓库；AI 生成图一律标 `reconstruction`，绝不冒充历史实拍。
- 缺图时用统一占位卡，**不拿其他产品的图顶替**。

### 3.4 网站体验

- 缺失图片 + `onerror` 失败 → 走同一套占位卡（顺带补上当前缺失的加载失败兜底）。
- 详情页显示来源链接与类型徽章（历史实拍 / AI 复原 / 待核实）。
- 图片区块独立渲染，加载失败不影响投票与榜单（当前已是 `card-img` 独立容器，改造面很小）。
- WebP 优先：**但现有 26 张里有 8 张是动图 GIF**，不能一刀切转 WebP，需按是否会动分流处理。

### 3.5 测试与校验

新增静态校验：ID 与图片记录一一对应、路径存在、重复路径、空字符串、`image_status` 枚举合法性、
`image_source_url` 为空却标 `verified` 的矛盾组合。
回归现有三套：`selfcheck`（现 62/0）、`smoke_http`（现 13/0）、`test_scenarios`（现 15/0）。

---

## 四、需要你拍板的四个问题

1. **是否允许把图片关系从 `app.js` 迁到 JSON**（一次迁移，换来可追溯 + 可脚本校验）？
   还是保守起见只在 JSON 加元数据、继续以 `HALL_IMG` 为唯一真源？
2. **现有 26 张无出处的图**：默认降级标 `unverified` 并限期补证，还是允许按"官方菜单图"口径保留较高信任？
3. **GitHub 上 5 个孤儿 Issue**（51 个 Issue vs `issue_map` 只绑 46 个）：关闭并注明"产品已移出名录"、保持 open、还是补回产品？
4. **是否允许本轮下载外部图片入库**（涉及版权），还是这一轮只做"清单 + 占位 + 展示层"，图源由你人工提供？

---

## 五、分期建议（风险从低到高）

- **一期（低风险、推荐先做）**：`image_research.py` 的 plan/review/verify/report + 七字段落地 +
  统一占位卡与 `onerror` 兜底 + 静态校验。**全程不下载任何图片、不改任何现有业务字段。**
- **二期**：你审核通过后按 `rights=allowed` 逐张下载 + WebP（动图分流）。
- **三期**：展示层特色化 —— 历史实拍 / 记忆碎片 / 复原档案 / 寻图悬赏四个分区。

---

## 六、一期交付结果（2026-10-13 实测）

| 交付项 | 状态 |
|---|---|
| `scripts/image_research.py`（plan / bootstrap / verify / report） | ✅ 已实现，**不含下载** |
| 七字段写入 81 款产品 | ✅ 26 款带图、55 款 `missing` |
| `HALL_IMG` → JSON 迁移 | ✅ 已迁移；前端改为**数据优先**，`HALL_IMG` 降为迁移期兜底 |
| 前端加载失败兜底 | ✅ 新增 `__mcImgFail`（原先只有 emoji 兜底，404 会出破图） |
| `/api/leaderboard` 下发 `image` | ✅ 领奖台也走数据驱动 |
| 静态校验接入 `selfcheck` | ✅ 共用 `image_research.collect_problems`（规则只有一处实现） |
| 测试能抓出违规 | ✅ 场景 16 注入 5 类违规全部被抓、合规条目无误报 |

实测（2026-10-13）：

- `image_research.py verify` → ✅ 81 款、26 张引用图，无缺失/重复/非法枚举
- `selfcheck.py` → ✅63 / ❌0
- `smoke_http.py` → ✅15 / ❌0（含"七字段透传""榜单 image 不空过"两条新断言）
- `test_scenarios.py` → ✅16 / ❌0；`--real` → ✅18 / ❌0

**诚实边界**：图片覆盖率仍是 **26 / 81 = 32%**，且这 26 张**全部 `unverified`**（无出处记录）。
下载二期做 —— 只有你在候选里显式标 `rights=allowed` 后才会执行，脚本本身不会自动抓图。
