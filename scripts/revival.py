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
- 复活榜聚合（支持城市维度）
- 拉票分享卡生成

用法示例：
  python3 scripts/revival.py museum
  python3 scripts/revival.py vote --product sakura_mcfloat --from-mcp                # 麦当劳会员投票（需 MCD_MCP_TOKEN）
  python3 scripts/revival.py vote --product sakura_mcfloat --from-mcp --city 上海
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
]
POINTS_KEYS = [
    "积分", "可用积分", "会员积分", "积分余额", "积分值",
    "points", "point", "pointbalance", "availablepoints", "balance", "score",
]


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


def extract_member_id(raw):
    """从 query-my-account 返回（可能是 JSON 文本）中稳健解析会员唯一标识。"""
    obj = None
    try:
        obj = json.loads(raw)
    except Exception:
        obj = None
    candidates = _walk_find(obj, MEMBER_ID_KEYS) if obj else []
    # 文本兜底正则（JSON 解析失败或字段名未命中时）
    if not candidates:
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
    """稳健解析积分余额（仅读取），解析不到返回 0，绝不臆造。"""
    obj = None
    try:
        obj = json.loads(raw)
    except Exception:
        obj = None
    nums = [int(v) for v in _walk_find(obj, POINTS_KEYS) if isinstance(v, (int, float)) and v >= 0] if obj else []
    if not nums:
        for m in re.finditer(r"(?:积分|points?)\D{0,8}?(\d+)", raw, re.I):
            nums.append(int(m.group(1)))
    return max(nums) if nums else 0


def real_account_info():
    """真实调用麦当劳 MCP query-my-account，返回 (积分, 会员唯一标识)。仅读取不扣减。"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from mcp_client import McDonaldMCPClient
        c = McDonaldMCPClient()
        c.initialize()
        text = c.get_my_points()
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"调用 query-my-account 失败：{e}")
    raw = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
    return extract_points(raw), extract_member_id(raw)


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


def record_vote(product, city=None, from_mcp=False):
    """记录一票。仅麦当劳会员账号可投票（已取消降级）。

    返回 (msg, ok, val)。
    票数 = 1（确认会员身份的基础票） + 积分票（积分 // POINTS_RATE）。
    去重主键 = 麦当劳会员唯一标识（强身份），每会员每单品仅一次。
    """
    votes = load_json(VOTES, {"totals": {}, "city_totals": {}, "member_voted": {}})
    pid = product
    name = next((p["name"] for p in get_products() if p["id"] == pid), pid)

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
    if city:
        votes["city_totals"].setdefault(city, {})
        votes["city_totals"][city][pid] = votes["city_totals"][city].get(pid, 0) + val
    save_json(VOTES, votes)
    return (f"✅ 麦当劳会员投票成功！《{name}》\n"
            f"   基础票 1（登录确认）+ 积分票 {extra}（{points} 积分 ÷ {POINTS_RATE}） = 共 {total} 票。\n"
            f"   （仅读取积分，未扣减；按会员号强身份去重）"), True, val


def show_github_ranking(top=10):
    """从 GitHub Issue 聚合真实复活榜（跨用户、真实可信，需作者侧 GITHUB_TOKEN）。"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from report_github import aggregate
        data = aggregate()
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


def ranking(top=10, city=None):
    votes = load_json(VOTES, {"totals": {}, "city_totals": {}, "member_voted": {}})
    name = {p["id"]: p["name"] for p in get_products()}
    if city and city in votes.get("city_totals", {}):
        totals = votes["city_totals"][city]
        title = f"🏆 {city} · 复活榜 Top {top}"
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
    p_v.add_argument("--city", default=None)
    p_v.add_argument("--from-mcp", action="store_true",
                     help="仅麦当劳会员可投票：真实读取 query-my-account 积分换算（需 MCD_MCP_TOKEN）")

    p_r = sub.add_parser("ranking")
    p_r.add_argument("--top", type=int, default=10)
    p_r.add_argument("--city", default=None)
    p_r.add_argument("--from-github", action="store_true", help="从 GitHub Issue 聚合真实复活榜（跨用户）")

    p_s = sub.add_parser("share")
    p_s.add_argument("--product", required=True)

    args = ap.parse_args()
    if args.cmd == "museum":
        list_museum()
    elif args.cmd == "meals":
        show_meals_vs_museum()
    elif args.cmd == "vote":
        msg, ok, val = record_vote(args.product, args.city, args.from_mcp)
        print(msg)
        if ok:
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from report_github import report_vote as rpt
                ok2, m2 = rpt(args.product, "mcp", val, args.city)
                if ok2:
                    print(f"[后台统计] {m2}")
            except Exception:  # noqa: BLE001
                pass
    elif args.cmd == "ranking":
        if args.from_github:
            show_github_ranking(args.top)
        else:
            ranking(args.top, args.city)
    elif args.cmd == "share":
        print(share_card(args.product))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
