#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦复活赛 · 麦当劳 MCP 只读数据中枢（v5，强化只读红线）

本模块是「访问麦当劳 MCP 的唯一受控出口」：
- 任何对麦当劳 MCP 的调用都必须经过 safe_call()，它强制校验工具名
  必须落在 READ_ONLY_TOOLS 白名单内；一旦有人想调用写/交易类工具
  （delivery-create-address / create-order / draw-lottery / auto-bind-coupons /
   calculate-price / party-order-create / mall-create-order / cancel-order），
   立即抛 ValueError —— 把「仅读取」的红线收口到调用层，杜绝误用。
- 所有抓取结果按 TTL 落到 data/cache/（已被 .gitignore 排除，不入库），
  既避免对麦当劳接口高频打扰，也保证公开部署无 token 时优雅降级。

仅用于「博物馆展示增强」：活动日历、积分商城、抽奖信息、营养库、
在售对比、附近门店。绝不执行下单 / 扣减 / 领券 / 创建地址等写操作。
"""
import os
import re
import json
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE, "data", "cache")
TOKEN_ENV = "MCD_MCP_TOKEN"

# ---- 只读白名单（单一事实来源在 mcp_client.py 客户端层；此处引用以保持一致）----
# 写/交易类（严禁调用，双层防御：客户端 call_tool 与本模块 safe_call 均校验）：
WRITE_TOOLS = {
    "draw-lottery",            # 抽奖（扣积分/次数）
    "delivery-create-address", # 创建配送地址
    "create-order",            # 创建订单
    "auto-bind-coupons",       # 自动领券
    "calculate-price",         # 计价（订单前置）
    "party-order-create",      # 派对下单
    "mall-create-order",       # 商城兑换下单
    "cancel-order",            # 取消订单
}
try:
    from mcp_client import READ_ONLY_TOOLS
except Exception:  # noqa: BLE001  # 兜底：直接运行本模块时
    READ_ONLY_TOOLS = frozenset({
        "delivery-query-stores", "query-lottery-info", "query-party-store-date",
        "campaign-calendar", "query-my-coupons", "delivery-query-addresses",
        "query-meal-assistance", "query-promotions", "query-survey-coupon",
        "mall-product-detail", "query-party-city", "order-list",
        "mall-order-detail", "query-party-store", "available-coupons",
        "now-time-info", "query-nearby-stores", "query-my-prizes",
        "mall-order-list", "list-nutrition-foods", "query-store-coupons",
        "query-my-account", "query-meals", "query-meal-detail",
        "mall-points-products", "query-order", "query-party-store-session",
    })


def safe_call(client, name, arguments=None):
    """强制只读的 MCP 调用入口：不在白名单直接拒绝。"""
    if name not in READ_ONLY_TOOLS:
        raise ValueError(
            f"🚫 安全拦截：工具「{name}」不在只读白名单内，本作品禁止任何写/交易操作。"
            f"如需扩展，请先在 READ_ONLY_TOOLS 中明确登记并经审查。"
        )
    return client.call_tool(name, arguments or {})


def token_available():
    try:
        import mcp_client
        mcp_client._load_env_file()
    except Exception:
        pass
    return bool(os.environ.get(TOKEN_ENV))


# ---- 通用缓存 ----
def _cache_path(key):
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{key}.json")


def _cache_get(key, ttl):
    p = _cache_path(key)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if time.time() - obj.get("_ts", 0) > ttl:
            return None
        return obj.get("data")
    except Exception:
        return None


def _cache_set(key, data):
    try:
        with open(_cache_path(key), "w", encoding="utf-8") as f:
            json.dump({"_ts": time.time(), "data": data}, f, ensure_ascii=False)
    except Exception:
        pass


def _client():
    import mcp_client
    mcp_client._load_env_file()
    c = mcp_client.McDonaldMCPClient()
    c.initialize()
    return c


def _text(resp):
    """取 MCP 文本返回（与 mcp_client._extract_text 一致）。"""
    if not resp:
        return ""
    result = resp.get("result")
    if not result:
        return ""
    content = result.get("content", [])
    texts = [c.get("text") for c in content if c.get("type") == "text"]
    return "\n".join(texts) if texts else ""


def _extract_json_object(text):
    """从文本中抓取一个用花括号配平的 JSON 对象（用于解析 Original Response）。

    健壮版：文本里常在 JSON 之前出现说明性 `{` / `}`，若只从第一个 `{` 起算会误判。
    改为从每一个 `{` 位置依次尝试配平解析，返回第一个成功解析的对象。
    """
    s = text or ""
    starts = [i for i, ch in enumerate(s) if ch == "{"]
    for start in starts:
        depth = 0
        in_str = False
        esc = False
        ok = False
        for i in range(start, len(s)):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    ok = True
                    break
        if ok:
            try:
                return json.loads(s[start:i + 1])
            except Exception:
                continue
    return None


# ---- 各只读数据源 ----

def get_nutrition(force=False):
    """营养库（list-nutrition-foods）：返回 [{productName, energyKcal, protein, fat, ...}]。"""
    cached = None if force else _cache_get("nutrition", ttl=6 * 3600)
    if cached is not None:
        return cached
    if not token_available():
        return []
    try:
        c = _client()
        resp = safe_call(c, "list-nutrition-foods", {})
        txt = _text(resp)
        body = txt.split("]:", 1)[-1] if "]:[" not in txt else txt
        # 真实数据在 data 字段（JSON 字符串），尝试解析
        obj = _extract_json_object(txt)
        rows = []
        raw = ""
        if isinstance(obj, dict):
            raw = obj.get("data") or ""
            if isinstance(raw, str):
                raw = raw
            else:
                raw = json.dumps(obj, ensure_ascii=False)
        else:
            raw = txt
        # raw 形如：[160]{productName,nutritionDescription,energyKj,energyKcal,...}:\n 名称,描述,1288,308,16,16,24,781,213
        # 字段固定 9 列：名称, 描述, energyKj,energyKcal,protein,fat,carb,sodium,calcium
        # 描述可能含逗号 -> 取「按逗号切分后的最后 7 列」作为数值（最稳），名称取首列。
        lines = [ln for ln in raw.splitlines() if ln.strip() and not ln.strip().startswith("[")]
        for ln in lines:
            name = ln.split(",", 1)[0].strip()
            if not name or name.startswith("{") or "productName" in name:
                continue
            parts = [p.strip() for p in ln.split(",")]
            if len(parts) < 9:
                continue
            nums = parts[-7:]
            if not all(re.fullmatch(r"\d[\d,]*", n) for n in nums):
                continue
            try:
                rec = {
                    "productName": name,
                    "energyKj": nums[0].replace(",", ""),
                    "energyKcal": nums[1].replace(",", ""),
                    "protein": nums[2].replace(",", ""),
                    "fat": nums[3].replace(",", ""),
                    "carbohydrate": nums[4].replace(",", ""),
                    "sodium": nums[5].replace(",", ""),
                    "calcium": nums[6].replace(",", ""),
                }
                rows.append(rec)
            except Exception:
                continue
        _cache_set("nutrition", rows)
        return rows
    except Exception:
        return []


def get_campaigns(force=False):
    """营销活动日历（campaign-calendar）：返回 [{date, title, image}]。"""
    cached = None if force else _cache_get("campaigns", ttl=6 * 3600)
    if cached is not None:
        return cached
    if not token_available():
        return []
    try:
        c = _client()
        resp = safe_call(c, "campaign-calendar", {})
        txt = _text(resp)
        entries = []
        blocks = re.split(r"\n\s*####\s+", txt)
        for b in blocks[1:]:
            date = b.splitlines()[0].strip() if b.splitlines() else ""
            titles = re.findall(r"\*\*活动标题\*\*[:：]\s*(.+)", b)
            images = re.findall(r'<img src="([^"]+)"', b)
            for i, t in enumerate(titles):
                entries.append({
                    "date": date,
                    "title": t.strip(),
                    "image": images[i] if i < len(images) else "",
                })
        _cache_set("campaigns", entries)
        return entries
    except Exception:
        return []


def get_lottery_info(force=False):
    """积分抽奖活动信息（query-lottery-info，仅读取，不抽奖）。"""
    cached = None if force else _cache_get("lottery", ttl=3600)
    if cached is not None:
        return cached
    if not token_available():
        return {}
    try:
        c = _client()
        resp = safe_call(c, "query-lottery-info", {})
        txt = _text(resp)
        obj = _extract_json_object(txt)
        if not isinstance(obj, dict):
            return {}
        data = obj.get("data") or {}
        out = {
            "statusText": (data.get("status") or {}).get("message", ""),
            "activityCode": data.get("activityCode", ""),
            "activityStatusText": data.get("activityStatusText", ""),
            "cost": "",
            "prizes": [],
        }
        dd = data.get("drawDecision") or {}
        out["cost"] = dd.get("nextConsumption", "")
        prizes = data.get("prizes") or data.get("publicPrizes") or []
        for p in prizes[:8]:
            if isinstance(p, dict):
                out["prizes"].append(p.get("prizeName") or p.get("name") or "")
        _cache_set("lottery", out)
        return out
    except Exception:
        return {}


def get_points_mall(force=False):
    """积分商城可兑换（mall-points-products）：返回 [{spuName, spuId, point, selling, upTime}]。"""
    cached = None if force else _cache_get("mall", ttl=6 * 3600)
    if cached is not None:
        return cached
    if not token_available():
        return []
    try:
        c = _client()
        resp = safe_call(c, "mall-points-products", {})
        txt = _text(resp)
        obj = _extract_json_object(txt)
        items = []
        if isinstance(obj, dict):
            arr = obj.get("data") or []
            for it in arr:
                if isinstance(it, dict):
                    items.append({
                        "spuName": it.get("spuName", ""),
                        "spuId": it.get("spuId", ""),
                        "point": it.get("point", ""),
                        "selling": it.get("selling", ""),
                        "upTime": it.get("upTime", ""),
                        "image": it.get("spuImage", ""),
                    })
        _cache_set("mall", items)
        return items
    except Exception:
        return []


def _get_address_and_stores():
    """只读：取默认配送地址 + 该地址可配送门店列表。返回 (province, address_id, stores)。

    隐私安全：仅取省份名（用 34 枚举匹配），绝不落盘 / 回传任何地址原文。
    """
    if not token_available():
        return "", "", []
    try:
        c = _client()
        aobj = _extract_json_object(_text(safe_call(c, "delivery-query-addresses", {})))
        addrs = ((aobj or {}).get("data") or {}).get("addresses") or []
        if not addrs:
            return "", "", []
        a0 = addrs[0] if isinstance(addrs[0], dict) else {}
        address_id = a0.get("addressId") or a0.get("id") or ""
        province = ""
        try:
            import revival
            blob = json.dumps(a0, ensure_ascii=False)
            for pr in revival.PROVINCES:
                if pr in blob:
                    province = pr
                    break
        except Exception:
            pass
        if not address_id:
            return province, "", []
        sobj = _extract_json_object(_text(safe_call(c, "delivery-query-stores",
                                                   {"addressId": address_id, "beType": "2"})))
        sd = (sobj or {}).get("data")
        if isinstance(sd, list):
            stores = sd
        elif isinstance(sd, dict):
            stores = sd.get("stores") or sd.get("list") or []
        else:
            stores = []
        return province, address_id, [s for s in stores if isinstance(s, dict)]
    except Exception:
        return "", "", []


def _get_default_store():
    """只读：默认配送地址对应的首个门店（storeCode）。返回 {province, store_code, store_name, address} 或 {}。"""
    province, _, stores = _get_address_and_stores()
    if not stores:
        return {}
    s0 = stores[0]
    return {
        "province": province,
        "store_code": s0.get("storeCode") or s0.get("code") or "",
        "store_name": s0.get("storeName") or s0.get("name") or "",
        "address": s0.get("address") or "",
    }


def get_current_meals(force=False, store_code=None):
    """当前在售菜单（query-meals，需门店码）：返回 [{name, code, image}]。

    麦当劳接口要求 storeCode 才能返回菜单；无门店码时自动尝试用默认配送地址解析，
    仍拿不到则优雅返回 []（公开部署 / 未登录均不影响可用性）。
    """
    if store_code is None and token_available():
        store_code = _get_default_store().get("store_code") or None
    key = "meals_" + (store_code or "none")
    cached = None if force else _cache_get(key, ttl=6 * 3600)
    if cached is not None:
        return cached
    if not token_available() or not store_code:
        return []
    try:
        c = _client()
        resp = safe_call(c, "query-meals", {"beType": 1, "orderType": 1, "storeCode": store_code})
        obj = _extract_json_object(_text(resp))
        data = (obj or {}).get("data") or {}
        if not isinstance(data, dict):
            return []
        names = []
        meals_map = data.get("meals") or {}
        if isinstance(meals_map, dict):
            for v in meals_map.values():
                if isinstance(v, dict) and v.get("name"):
                    names.append({"name": v.get("name"), "code": v.get("code", ""),
                                  "image": v.get("image", "")})
        for cat in data.get("categories") or []:
            if isinstance(cat, dict):
                for m in cat.get("meals") or []:
                    if isinstance(m, dict) and m.get("name"):
                        names.append({"name": m.get("name"), "code": m.get("code", ""), "image": ""})
        seen, uniq = set(), []
        for n in names:
            if n["name"] in seen:
                continue
            seen.add(n["name"])
            uniq.append(n)
        if uniq:
            _cache_set(key, uniq)
        return uniq
    except Exception:
        return []


def compare_on_sale(products):
    """在售对比：对本地怀旧单品判断「仍在售 / 已绝版」。

    返回 {product_id: {"available": bool, "matched": str|null}}。
    匹配策略：怀旧单品名与在售餐品名做双向包含（去掉常见后缀前先做原样），
    命中即视为仍在售，并给出在售同名/近似名用于展示。
    """
    meals = get_current_meals()
    meal_names = [m["name"] for m in meals]
    out = {}
    for p in products:
        pid = p.get("id")
        name = p.get("name", "")
        matched = None
        for mn in meal_names:
            if not mn:
                continue
            if name in mn or mn in name:
                matched = mn
                break
        out[pid] = {"available": matched is not None, "matched": matched}
    return out


def get_nearby_stores():
    """附近可配送门店（只读地址 + 只读门店）。仅取省份，不落盘地址原文。"""
    if not token_available():
        return {"province": "", "stores": []}
    try:
        province, _, stores = _get_address_and_stores()
        out = [{
            "name": s.get("storeName") or s.get("name") or "",
            "address": s.get("address") or "",
        } for s in stores[:12]]
        return {"province": province, "stores": out}
    except Exception:
        return {"province": "", "stores": []}


if __name__ == "__main__":
    print("token_available:", token_available())
    print("nutrition:", len(get_nutrition()))
    print("campaigns:", len(get_campaigns()))
    print("lottery:", get_lottery_info())
    print("mall:", len(get_points_mall()))
    print("meals:", len(get_current_meals()))
