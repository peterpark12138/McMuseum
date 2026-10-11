#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦复活赛 · 投票与榜单引擎（Skill 配套脚本）

设计要点（v4）：
- 怀旧单品博物馆展示
- 投票严格绑定「麦当劳会员账号」：仅麦当劳会员可投票（已取消 WorkBuddy 账号降级 / 匿名投票）
- 票数 = 1（确认会员身份的基础票） + 积分票（真实调用 query-my-account 读取积分，每 100 积分 = 1 票）
    · 无积分 → 仅 1 票（登录确认票）
    · 仅读取积分，绝不扣减
- 强身份去重：以麦当劳会员唯一标识（会员号 / openid / 卡号 等）为去重主键，每会员每单品仅可投一次
- 在售 vs 怀旧对比：调用 query-meals（--from-mcp）与本地博物馆对照
- 复活榜聚合（支持省份维度，省份为受控枚举，防脏数据）
- 拉票分享卡生成

用法示例：
  python3 scripts/revival.py museum
  python3 scripts/revival.py vote --product sakura_mcfloat --from-mcp                # 麦当劳会员投票（需 MCD_MCP_TOKEN）
  python3 scripts/revival.py vote --product sakura_mcfloat --from-mcp --province 上海
  python3 scripts/revival.py meals --from-mcp                                      # 在售 vs 怀旧对比
  python3 scripts/revival.py ranking --top 10
  python3 scripts/revival.py share --product sakura_mcfloat
"""
import json
import os
import sys
import argparse
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "nostalgic_products.json")
VOTES = os.path.join(BASE, "data", "votes.json")
POINTS_RATE = 100  # 每 100 积分 = 1 票（额外票）

# 34 个省级行政区（含直辖市 / 自治区 / 特别行政区）。
# 投票地域维度用受控枚举，避免自由文本城市名造成的脏数据 / 榜被拆散。
PROVINCES = [
    "北京", "天津", "上海", "重庆",
    "河北", "山西", "辽宁", "吉林", "黑龙江", "江苏", "浙江", "安徽", "福建", "江西",
    "山东", "河南", "湖北", "湖南", "广东", "海南", "四川", "贵州", "云南", "陕西",
    "甘肃", "青海", "台湾",
    "内蒙古", "广西", "西藏", "宁夏", "新疆",
    "香港", "澳门",
]


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_products():
    return load_json(DATA, {"products": []}).get("products", [])


def list_museum():
    print("🍟 麦麦怀旧单品博物馆")
    print("=" * 48)
    for p in get_products():
        mark = "✅" if p.get("verified") else "⚠️待核实"
        print(f"[{p['id']}] {p['name']}  ({p['era']})  {mark}")
        print(f"    {p['story']}")
        print(f"    标签: {', '.join(p.get('tags', []))}")
        print("-" * 48)


# ---- 稳健的会员身份 / 积分解析（修复"会员号强身份去重脆弱"） ----
# 候选字段名覆盖中英文常见表达；递归搜索整棵 JSON，不依赖固定字段名。
MEMBER_ID_KEYS = [
    "会员号", "会员编号", "会员卡号", "会员id", "会员标识", "会员卡", "卡号",
    "memberno", "member_no", "memberid", "member_id", "membernumber", "member_number",
    "cardno", "card_no", "cardnumber", "loyaltyid", "loyalty_id",
    "openid", "unionid", "userid", "user_id", "customerid", "customer_id", "mid", "mcdmemberid",
    "accountid", "account_id", "accountno", "account_no", "accountcode",
]
POINTS_KEYS = [
    "积分", "可用积分", "会员积分", "积分余额", "积分值",
    "points", "point", "pointbalance", "availablepoints", "balance", "score",
]
# 优先使用的积分字段（可用积分）；accumulative/expired/frozen/used 为历史/过期/冻结/已用，不计入投票
POINTS_PREF_KEYS = ["availablepoint", "available_point", "可用积分", "points", "point", "pointbalance"]


def _walk_find(obj, keys):
    """递归在 dict/list 中按候选 key（不区分大小写、包含匹配）收集非空值。"""
    found = []
    kl = [k.lower() for k in keys]

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(k, str) and any(kk in k.lower() for kk in kl) and v not in (None, ""):
                    found.append(v)
                walk(v)
        elif isinstance(o, list):
            for it in o:
                walk(it)

    walk(obj)
    return found


def _to_obj(raw):
    """若 raw 是 JSON 文本则解析为对象；已是 dict/list 则原样返回；否则 None。"""
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return None
    return None


def _as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def extract_member_id(raw):
    """从 query-my-account 返回（对象或 JSON 文本）中稳健解析会员唯一标识。

    真实返回优先位于 result.structuredContent.data.accountId（UUID 形式），
    此处对对象/文本均兼容，并保留中文文本兜底正则。
    """
    obj = _to_obj(raw)
    candidates = _walk_find(obj, MEMBER_ID_KEYS) if obj else []
    # 文本兜底正则（JSON 解析失败或字段名未命中时）
    if not candidates and isinstance(raw, str):
        for pat in [
            r"会员[号识ID:： ]{0,6}[:：]?\s*([A-Za-z0-9_-]{4,})",
            r"member[ _-]?id\s*[:：]?\s*['\"]?([A-Za-z0-9_-]{4,})",
            r"card[ _-]?no\s*[:：]?\s*['\"]?([A-Za-z0-9_-]{4,})",
            r"openid\s*[:：]?\s*['\"]?([A-Za-z0-9_-]{4,})",
            r"(1\d{10})",
        ]:
            m = re.search(pat, raw, re.I)
            if m:
                candidates.append(m.group(1))
    for c in candidates:
        s = str(c).strip()
        # 稳定标识：长度>=4 且含字母或数字，排除纯短数字（如"1"）、单位、标签
        if len(s) >= 4 and re.search(r"[A-Za-z0-9]", s) and not re.fullmatch(r"\d{1,3}", s):
            return s
    return ""


def extract_points(raw):
    """稳健解析可用于投票的积分余额（优先可用积分），仅读取，解析不到返回 0。"""
    obj = _to_obj(raw)
    if obj:
        # 优先可用积分字段
        for kk in POINTS_PREF_KEYS:
            for v in _walk_find(obj, [kk]):
                iv = _as_int(v)
                if iv is not None and iv >= 0:
                    return iv
        # 兜底：任意积分类字段取最大
        allp = [iv for iv in (_as_int(v) for v in _walk_find(obj, POINTS_KEYS))
                if iv is not None and iv >= 0]
        if allp:
            return max(allp)
    # 文本兜底
    s = raw if isinstance(raw, str) else ""
    for m in re.finditer(r"(?:积分|points?)\D{0,8}?(\d+)", s, re.I):
        return int(m.group(1))
    return 0


def real_account_info():
    """真实调用麦当劳 MCP query-my-account，返回 (积分, 会员唯一标识)。仅读取不扣减。

    真实返回结构：
      result.structuredContent.data.{accountId, availablePoint, ...}
      result.content[].text 为可读文本（兜底解析用）。
    优先读取结构化字段，确保稳定拿到会员唯一标识与可用积分。
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from mcp_client import McDonaldMCPClient
        c = McDonaldMCPClient()
        c.initialize()
        out = c.call_tool("query-my-account", {})
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"调用 query-my-account 失败：{e}")

    result = (out or {}).get("result", {})
    # 结构化数据（首选）
    data = {}
    sc = result.get("structuredContent") if isinstance(result, dict) else None
    if isinstance(sc, dict):
        data = sc.get("data") or {}
    # 文本兜底
    content = result.get("content", []) if isinstance(result, dict) else []
    raw_text = "\n".join(
        x.get("text", "") for x in content
        if isinstance(x, dict) and x.get("type") == "text"
    )

    # 会员唯一标识：优先结构化字段，其次文本兜底
    member_id = extract_member_id(data) or extract_member_id(raw_text)
    # 积分：优先可用积分，其次文本兜底
    points = extract_points(data) or extract_points(raw_text)
    return points, member_id


def show_meals_vs_museum():
    """调用 query-meals 拉在售菜单，与本地怀旧博物馆对照。"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from mcp_client import McDonaldMCPClient
        c = McDonaldMCPClient()
        c.initialize()
        raw = c.get_meals()
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ 调用 query-meals 失败（演示模式）：{e}")
        print("以下为本地怀旧博物馆，真实在售请以麦当劳官方实时结果为准：")
        list_museum()
        return
    print("📋 当前在售菜单（来自 query-meals，实时）：")
    print(str(raw)[:1200])
    print("\n🍟 怀旧博物馆（已下架/限定，本地）：")
    list_museum()
    print("👉 对比可见：你怀念的老麦，回来了吗？")


def find_province_in_text(text):
    """从任意文本中匹配 34 个省级行政区名，返回规范省份名，匹配不到返回 ''。

    子串匹配即可覆盖「广东省深圳市…」这类写法，无需额外别名表。
    """
    s = str(text or "")
    if not s:
        return ""
    for p in PROVINCES:
        if p in s:
            return p
    return ""


# 自动探测省份时**只允许调用只读工具**：绝不能触碰 create/add/update/delete 等写操作工具。
# （麦当劳 MCP 同时暴露了 delivery-query-addresses 与 delivery-create-address，
#   若不过滤，探测逻辑可能会去调用「创建地址」接口，违反本作品「仅读取」的红线。）
ADDR_READ_HINTS = ("query", "get", "list", "read")
ADDR_WRITE_HINTS = ("create", "add", "update", "delete", "remove",
                    "modify", "bind", "cancel", "pay", "submit", "set")


def _tool_tokens(name):
    """把工具名切成单词（kebab/snake 分隔）。

    必须用「整词」而非子串判断：如 write 词 `add` 是 `address` 的子串，
    用子串会把 delivery-query-addresses 自己误判成写操作而排除。
    """
    return [t for t in re.split(r"[-_\s.]+", str(name).lower()) if t]


def address_read_tools(tools):
    """从工具名列表中筛出「只读」的地址类工具。"""
    out = []
    for t in tools or []:
        low = str(t).lower()
        if "address" not in low:
            continue
        toks = _tool_tokens(low)
        if any(tok in ADDR_WRITE_HINTS for tok in toks):
            continue          # 写操作工具一律跳过
        if not any(tok in ADDR_READ_HINTS for tok in toks):
            continue          # 非读取语义，跳过
        out.append(t)
    return out


def auto_detect_province():
    """自动探测用户所在省份（隐私安全：只取省份名，不落盘任何地址原文）。

    策略：调麦当劳 MCP 的**只读**地址类工具解析省份；任何一步失败都静默返回 ''，
    由调用方降级为「全国」，绝不阻塞投票。仅读取，绝不修改/创建任何账号数据。
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from mcp_client import McDonaldMCPClient
        c = McDonaldMCPClient()
        c.initialize()
        prefer = address_read_tools(c.list_tools())
        for name in prefer:
            try:
                resp = c.call_tool(name, {})
                p = find_province_in_text(json.dumps(resp, ensure_ascii=False))
                if p:
                    return p
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    return ""


def record_vote(product, province=None, from_mcp=False, auto_province=True):
    """记录一票。仅麦当劳会员账号可投票（已取消降级）。

    返回 (msg, ok, val)。
    票数 = 1（确认会员身份的基础票） + 积分票（积分 // POINTS_RATE）。
    去重主键 = 麦当劳会员唯一标识（强身份），每会员每单品仅一次。
    province 为可选地域维度，必须是 PROVINCES 受控枚举之一，否则拒绝（防脏数据）。
    province 为 None 且 auto_province=True 时，自动从麦当劳 MCP 地址解析（仅取省份，不存地址）。
    """
    votes = load_json(VOTES, {"totals": {}, "province_totals": {}, "member_voted": {}})
    pid = product
    name = next((p["name"] for p in get_products() if p["id"] == pid), pid)

    # 省份维度：未提供时自动探测（仅麦当劳会员路径，因需 MCP 连接）
    auto_detected = False
    if not province and auto_province and from_mcp:
        province = auto_detect_province() or None
        auto_detected = bool(province)

    # 省份维度：受控枚举校验，避免脏数据
    if province and province not in PROVINCES:
        return (f"⚠️ 省份「{province}」不在可选范围内（应为 34 个省级行政区之一，如 上海 / 广东 / 四川）。"
                f"如无需分省统计，请勿传 --province。"), False, 0

    # 已取消降级：非麦当劳账号一律拒绝
    if not from_mcp:
        return ("⚠️ 仅麦当劳会员账号可投票。请先连接麦当劳账号（配置 MCD_MCP_TOKEN 后使用 --from-mcp）。"
                "本作品已取消 WorkBuddy 账号 / 匿名降级投票。"), False, 0

    try:
        points, member_id = real_account_info()
    except RuntimeError as e:
        return f"{e}\n（无法确认麦当劳会员身份，投票已取消。）", False, 0

    # 强身份去重：解析不到会员唯一标识时，宁可拒绝也不降级
    if not member_id:
        return ("⚠️ 未能从 query-my-account 解析出麦当劳会员唯一标识，无法安全去重，投票被拒绝。"
                "（已取消降级机制，不允许按其他账号投票；请确认 MCD_MCP_TOKEN 有效且返回会员信息）"), False, 0

    base = 1                        # 确认麦当劳账号 = 1 基础票（登录确认）
    extra = points // POINTS_RATE   # 每 100 积分额外 1 票
    total = base + extra

    key = "m:" + member_id
    voted = votes["member_voted"].setdefault(key, [])
    if pid in voted:
        return f"该麦当劳会员已为《{name}》投过票（每会员每单品仅一次），不能重复刷票。", False, 0

    votes["member_voted"][key].append(pid)
    votes["totals"][pid] = votes["totals"].get(pid, 0) + total
    val = total
    if province:
        votes["province_totals"].setdefault(province, {})
        votes["province_totals"][province][pid] = votes["province_totals"][province].get(pid, 0) + val
    save_json(VOTES, votes)

    # 后台上报到 GitHub 共享榜（匿名、仅作者 token 可写；未配置自动跳过）。
    # 放在 record_vote 内，确保命令行与前端 /api/vote 都能回流到共享榜。
    # 上报结果显式告知（诚实原则）：本地票若未回流共享榜，用户应知情。
    report_note = ""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import mcp_client as _mc
        _mc._load_env_file()  # 确保 .env 中的 GITHUB_REPO/GITHUB_TOKEN 被加载
        from report_github import report_vote as _rpt
        ok_r, m_r = _rpt(pid, "mcp", val, province)
        report_note = f"\n   共享榜：{'已匿名回流 GitHub ✅' if ok_r else f'未回流（{m_r}）'}"
    except Exception as e:  # noqa: BLE001
        report_note = f"\n   共享榜：未回流（{e}）"

    region_line = ""
    if province:
        tag = "自动识别" if auto_detected else "手动选择"
        region_line = f"\n   地域：{province}（{tag}，仅统计到省级，不存储地址）"
    return (f"✅ 麦当劳会员投票成功！《{name}》\n"
            f"   基础票 1（登录确认）+ 积分票 {extra}（{points} 积分 ÷ {POINTS_RATE}） = 共 {total} 票。\n"
            f"   （仅读取积分，未扣减；按会员号强身份去重）{region_line}{report_note}"), True, val


def show_github_ranking(top=10):
    """从 GitHub Issue 聚合真实复活榜（跨用户、真实可信，需作者侧 GITHUB_TOKEN）。"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from report_github import aggregate
        data = aggregate().get("totals", {})
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ 无法读取 GitHub 真实榜：{e}")
        return
    if not data:
        print("未配置 GITHUB_REPO / data/issue_map.json，暂无可聚合的真实榜。")
        print("（运行 `python3 scripts/report_github.py setup` 初始化后端，或先本地投票看榜）")
        return
    name = {p["id"]: p["name"] for p in get_products()}
    items = sorted(data.items(), key=lambda x: -x[1])
    print(f"🏆 真实复活榜 Top {top}（GitHub Issue 聚合 · 跨用户）")
    print("=" * 48)
    if all(v == 0 for _, v in items):
        print("（真实榜暂无投票，快去 GitHub 给作品点 Star 并拉朋友来打榜！）")
        return
    for i, (pid, cnt) in enumerate(items[:top], 1):
        print(f"{i}. {name.get(pid, pid)} — {cnt} 票")


def ranking(top=10, province=None):
    votes = load_json(VOTES, {"totals": {}, "province_totals": {}, "member_voted": {}})
    name = {p["id"]: p["name"] for p in get_products()}
    if province and province in votes.get("province_totals", {}):
        totals = votes["province_totals"][province]
        title = f"🏆 {province} · 复活榜 Top {top}"
    else:
        totals = votes.get("totals", {})
        title = f"🏆 复活榜 Top {top}"
    items = sorted(totals.items(), key=lambda x: -x[1])
    print(title)
    print("=" * 48)
    if not items:
        print("（暂无投票，快去为你的青春打call！）")
        return
    for i, (pid, cnt) in enumerate(items[:top], 1):
        print(f"{i}. {name.get(pid, pid)} — {cnt} 票")


def share_card(product):
    p = next((x for x in get_products() if x["id"] == product), None)
    if not p:
        return "未找到该单品，请检查 id。"
    return (
        "【麦麦复活赛 · 拉票卡】\n"
        f"我支持的复活选手：{p['name']}\n"
        f"{p['story']}\n"
        "快来帮我投票，让它打一场复活赛！\n"
        "#麦麦复活赛 #让老麦回来 #麦当劳程序员创意开发大赛"
    )


def main():
    ap = argparse.ArgumentParser(description="麦麦复活赛引擎")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("museum")

    p_m = sub.add_parser("meals")
    p_m.add_argument("--from-mcp", action="store_true", help="真实调用 query-meals 拉在售菜单")

    p_v = sub.add_parser("vote")
    p_v.add_argument("--product", required=True)
    p_v.add_argument("--province", default=None,
                    help="可选省份维度（34 个省级行政区之一，如 上海/广东/四川），受控枚举防脏数据")
    p_v.add_argument("--from-mcp", action="store_true",
                     help="仅麦当劳会员可投票：真实读取 query-my-account 积分换算（需 MCD_MCP_TOKEN）")

    p_r = sub.add_parser("ranking")
    p_r.add_argument("--top", type=int, default=10)
    p_r.add_argument("--province", default=None,
                     help="按省份查看复活榜（需与投票时传入的省份一致）")
    p_r.add_argument("--from-github", action="store_true", help="从 GitHub Issue 聚合真实复活榜（跨用户）")

    p_s = sub.add_parser("share")
    p_s.add_argument("--product", required=True)

    args = ap.parse_args()
    if args.cmd == "museum":
        list_museum()
    elif args.cmd == "meals":
        show_meals_vs_museum()
    elif args.cmd == "vote":
        msg, ok, val = record_vote(args.product, args.province, args.from_mcp)
        print(msg)
    elif args.cmd == "ranking":
        if args.from_github:
            show_github_ranking(args.top)
        else:
            ranking(args.top, args.province)
    elif args.cmd == "share":
        print(share_card(args.product))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
