#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦麦复活赛 · 图片档案采集与校验工具（一期）

一期范围（按评审确认）：
  plan       生成缺图/待核实产品的检索清单（CSV + JSON），供人工检索
  bootstrap  把 web/app.js 里硬编码的 HALL_IMG 迁入产品数据（状态一律 unverified）
  verify     静态校验图片档案的完整性与自洽性
  report     输出覆盖率、缺失清单、待核实清单

**一期不做任何下载** —— 下载与 WebP 转换安排在二期，且只有人工在候选里显式标记
`rights=allowed` 后才允许。理由：获得授权前把外部图片打包进公开仓库存在版权风险。

硬性诚实约束：
  1. 脚本绝不自动把某张图标记成 `verified`；`bootstrap` 迁入的历史图一律 `unverified`。
  2. `status=verified` 但缺少出处（`image_source_url` / `image_source_name`）会被 verify 判为错误
     —— 自称"已核实"就必须能拿出出处。
  3. `status=reconstruction` 必须写 `image_note` 说明是 AI 复原，不允许无说明。
  4. 当前环境没有可用的图片搜索 API，因此 `plan` **只生成检索词，不伪造"已搜到 N 张"**。

用法：
  python3 scripts/image_research.py plan
  python3 scripts/image_research.py bootstrap
  python3 scripts/image_research.py verify
  python3 scripts/image_research.py report
退出码：0 = 正常；1 = verify 发现档案不自洽。
"""
import csv
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
WEB = os.path.join(BASE, "web")
PRODUCTS = os.path.join(DATA, "nostalgic_products.json")
PLAN_CSV = os.path.join(DATA, "image_plan.csv")
PLAN_JSON = os.path.join(DATA, "image_plan.json")
APP_JS = os.path.join(WEB, "app.js")

# 七字段（顺序固定，便于 diff 稳定）
IMAGE_FIELDS = [
    "image", "image_status", "image_source_url",
    "image_source_name", "image_rights", "image_confidence", "image_note",
]
STATUS_ALLOWED = ("verified", "unverified", "reconstruction", "missing")
SOURCE_ALLOWED = ("官方", "媒体", "消费者", "AI 复原", "未知")
CONF_ALLOWED = ("high", "medium", "low", "")

# 中文品类 -> 英文检索词（只能给到品类级，产品名没有可靠英译，不臆造）
CAT_EN = {
    "甜品": "dessert McFlurry pie sundae",
    "蘸酱": "dipping sauce",
    "主食": "burger",
    "小食": "snack side",
    "早餐": "breakfast",
    "饮品": "drink beverage",
}
NO_STATUS = {  # 尚未纳入档案时的默认占位
    "image": "", "image_status": "missing", "image_source_url": "",
    "image_source_name": "", "image_rights": "", "image_confidence": "", "image_note": "",
}
BOOTSTRAP_NOTE = ("本图随仓库早期开发保存，原始出处与授权未留存；"
                  "已从 web/app.js 的 HALL_IMG 迁移，待人工补录 provenance 后再评估是否升为 verified。")


def load_doc():
    with open(PRODUCTS, encoding="utf-8") as f:
        return json.load(f)


def save_doc(doc):
    with open(PRODUCTS, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")


def year_of(p):
    """从 era / first_seen / story 里抽一个年份，用于检索词（抽不到就返回空串）。"""
    for key in ("era", "first_seen", "last_confirmed_sale"):
        m = re.search(r"(19|20)\d{2}", str(p.get(key) or ""))
        if m:
            return m.group(0)
    return ""


def build_terms(p):
    name = (p.get("name") or p.get("official_name") or p.get("id") or "").strip()
    official = (p.get("official_name") or name).strip()
    cat = (p.get("category") or "").strip()
    yr = year_of(p)
    zh = [
        f"麦当劳 {name}",
        f"麦当劳 {official}" + (f" {yr}" if yr else ""),
        f"麦当劳 {cat} 下架" if cat else f"麦当劳 {name} 下架",
        f"麦当劳 {name} 限定 包装",
    ]
    en_base = CAT_EN.get(cat, "")
    en = [
        f"McDonald's China {en_base}" if en_base else f"McDonald's China {name}",
        f"McDonald's {en_base} discontinued" if en_base else f"McDonald's {name} discontinued",
    ]
    # 去重保序
    def uniq(seq):
        seen, out = set(), []
        for s in seq:
            s = " ".join(str(s).split())
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out
    return uniq(zh), uniq(en)


# ---------------- plan ----------------
def cmd_plan(args):
    doc = load_doc()
    ps = doc.get("products", [])
    targets = [p for p in ps
               if args.all or p.get("image_status", "missing") in ("missing", "unverified")]
    rows = []
    for p in targets:
        zh, en = build_terms(p)
        rows.append({
            "id": p.get("id"), "name": p.get("name"), "category": p.get("category"),
            "era": p.get("era"), "first_seen": p.get("first_seen"),
            "current_status": p.get("image_status", "missing"),
            "search_zh": " | ".join(zh), "search_en": " | ".join(en),
            "sources_hint": " ; ".join(list(p.get("sources") or [])[:2]),
        })
    with open(PLAN_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else
                           ["id", "name", "category", "era", "first_seen",
                            "current_status", "search_zh", "search_en", "sources_hint"])
        w.writeheader()
        w.writerows(rows)
    with open(PLAN_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "note": "人工检索清单。脚本未联网搜索，也未产出任何候选图 —— 候选需人工录入。",
            "term_caveat": "search_zh 是「麦当劳 + 产品名 + 年份/限定」的产品级关键词；"
                           "search_en 只能给到**品类级**（产品名没有可靠的官方英译，不臆造），"
                           "英文检索请以 search_en 作为起始词再人工补充。",
            "count": len(rows), "items": rows}, f, ensure_ascii=False, indent=2)
    print(f"📋 检索清单已生成：{len(rows)} 款（{'全部' if args.all else '缺图/待核实'}）")
    print(f"   CSV  {PLAN_CSV}")
    print(f"   JSON {PLAN_JSON}")
    print("⚠️ 本环境无图片搜索 API，脚本未做任何搜索；清单仅供你人工检索后录入候选。")
    return 0


# ---------------- bootstrap ----------------
def cmd_bootstrap(args):
    src = open(APP_JS, encoding="utf-8").read()
    pairs = re.findall(r'^\s*(\w+):\s*"(assets/products/[^"]+)"', src, re.M)
    mapping = dict(pairs)
    if not mapping:
        print("❌ 未能从 web/app.js 解析出 HALL_IMG 映射，放弃迁移。", file=sys.stderr)
        return 1
    doc = load_doc()
    ps = doc.get("products", [])
    filled = skipped = 0
    unknown_ids = []
    for p in ps:
        pid = p.get("id")
        if pid not in mapping:
            for k, v in NO_STATUS.items():
                p.setdefault(k, v)
            continue
        if p.get("image") and not args.force:
            skipped += 1
            continue
        p["image"] = mapping[pid]
        if not p.get("image_status") or args.force:
            p["image_status"] = "unverified"   # 绝不自动 verified
        p["image_source_url"] = ""
        p["image_source_name"] = "未知"
        p["image_rights"] = "未知（未留存出处，复用前需人工确认）"
        p["image_confidence"] = "low"
        p["image_note"] = BOOTSTRAP_NOTE
        # 字段顺序归一：先删后插，保证七字段连续且顺序稳定
        vals = {k: p.pop(k) for k in IMAGE_FIELDS if k in p}
        p.update(vals)
        filled += 1
    product_ids = {p.get("id") for p in ps}
    unknown_ids = sorted(set(mapping) - product_ids)
    save_doc(doc)
    print(f"🔄 HALL_IMG 迁移完成：写入 {filled} 款，跳过已有图 {skipped} 款。")
    print("   状态一律 unverified（出处未知，不冒充已核实）；missing 款补默认占位。")
    if unknown_ids:
        print(f"⚠️ 映射里存在名录之外的 id（未写入）：{unknown_ids}")
    print("👉 下一步：跑 `python3 scripts/image_research.py verify` 确认档案自洽。")
    return 0


# ---------------- verify ----------------
def collect_problems(ps):
    """返回图片档案的所有不自洽项（空列表 = 自洽）。
    selfcheck.py 与 cmd_verify 共用本函数，保证校验规则只有一处实现、不会漂移。"""
    errs = []
    seen_path = {}
    for p in ps:
        pid = p.get("id", "?")
        for k in IMAGE_FIELDS:
            if k not in p:
                errs.append(f"[{pid}] 缺少字段 {k}")
        st = p.get("image_status", "")
        if st not in STATUS_ALLOWED:
            errs.append(f"[{pid}] image_status 非法：{st!r}（允许 {STATUS_ALLOWED}）")
        img = (p.get("image") or "").strip()
        if st == "missing":
            if img:
                errs.append(f"[{pid}] status=missing 却有图片路径 {img}")
        else:
            if not img:
                errs.append(f"[{pid}] status={st} 却没有图片路径")
            else:
                fp = os.path.join(WEB, img.replace("/", os.sep))
                if not os.path.isfile(fp):
                    errs.append(f"[{pid}] 图片文件不存在：{img}")
                if img in seen_path:
                    errs.append(f"[{pid}] 图片路径与 [{seen_path[img]}] 重复：{img}")
                else:
                    seen_path[img] = pid
        if st == "verified":
            if not (p.get("image_source_url") or "").strip():
                errs.append(f"[{pid}] 自称 verified 却无 image_source_url（拿不出出处就不能算已核实）")
            if not (p.get("image_source_name") or "").strip():
                errs.append(f"[{pid}] 自称 verified 却无 image_source_name")
        if st == "reconstruction" and not (p.get("image_note") or "").strip():
            errs.append(f"[{pid}] reconstruction 必须写 image_note 说明是 AI 复原图")
        sn = (p.get("image_source_name") or "").strip()
        if sn and sn not in SOURCE_ALLOWED:
            errs.append(f"[{pid}] image_source_name 非法：{sn!r}（允许 {SOURCE_ALLOWED}）")
        conf = p.get("image_confidence", "")
        if conf not in CONF_ALLOWED:
            errs.append(f"[{pid}] image_confidence 非法：{conf!r}（允许 {CONF_ALLOWED}）")

    pdir = os.path.join(WEB, "assets", "products")
    if os.path.isdir(pdir):
        used = {os.path.basename((p.get("image") or "").replace("/", os.sep)) for p in ps}
        for s in sorted(set(os.listdir(pdir)) - used):
            errs.append(f"[assets] 目录里有图片未被任何单品引用：{s}")
    return errs, seen_path


def cmd_verify(args):
    doc = load_doc()
    ps = doc.get("products", [])
    errs, seen_path = collect_problems(ps)
    if errs:
        print(f"❌ 图片档案不自洽，共 {len(errs)} 处：")
        for e in errs[:50]:
            print("   -", e)
        if len(errs) > 50:
            print(f"   ...（其余 {len(errs)-50} 处省略）")
        return 1
    print(f"✅ 图片档案自洽：{len(ps)} 款单品、{len(seen_path)} 张引用图，无缺失/重复/非法枚举。")
    return 0


# ---------------- report ----------------
def cmd_report(args):
    doc = load_doc()
    ps = doc.get("products", [])
    import collections
    cnt = collections.Counter((p.get("image_status") or "missing") for p in ps)
    total = len(ps)
    have = sum(1 for p in ps if (p.get("image") or "").strip())
    print("📊 图片档案覆盖率")
    print(f"   单品总数 {total}｜有图 {have}（{have*100//max(total,1)}%）")
    for s in STATUS_ALLOWED:
        print(f"   {s:<15} {cnt.get(s, 0)}")
    need = [p for p in ps if p.get("image_status") in ("missing", "unverified")]
    print(f"\n📌 待处理 {len(need)} 款：")
    for p in need[:40]:
        print(f"   - {p.get('id'):<28} {p.get('name')} [{p.get('image_status')}]")
    if len(need) > 40:
        print(f"   ...（其余 {len(need)-40} 款见 image_plan.csv）")
    return 0


def main():
    import argparse
    ap = argparse.ArgumentParser(description="图片档案采集与校验（一期：不下载任何图片）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_plan = sub.add_parser("plan", help="生成检索清单")
    p_plan.add_argument("--all", action="store_true", help="包含全部单品（默认只列缺图/待核实）")
    p_boot = sub.add_parser("bootstrap", help="把 app.js 的 HALL_IMG 迁入产品数据")
    p_boot.add_argument("--force", action="store_true", help="覆盖已存在的图片记录")
    sub.add_parser("verify", help="校验档案自洽性")
    sub.add_parser("report", help="输出覆盖率与待处理清单")
    args = ap.parse_args()
    return {"plan": cmd_plan, "bootstrap": cmd_bootstrap,
            "verify": cmd_verify, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
