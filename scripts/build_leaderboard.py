#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦复活赛 · 排行榜数据生成
读取本地投票 / GitHub 真实聚合，产出 web/leaderboard.json，供 leaderboard.html 可视化渲染。
用法：
  python3 scripts/build_leaderboard.py            # 本地榜
  python3 scripts/build_leaderboard.py --from-github   # 真实跨用户榜（需 GITHUB_REPO + token）
"""
import os
import sys
import json
import datetime
import argparse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "nostalgic_products.json")
VOTES = os.path.join(BASE, "data", "votes.json")
WEB = os.path.join(BASE, "web")
OUT = os.path.join(WEB, "leaderboard.json")


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_products():
    return load_json(DATA, {"products": []}).get("products", [])


def build(from_github=False):
    products = get_products()
    city_totals = {}
    if from_github:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from report_github import aggregate
            agg = aggregate() or {}
            mode = "github"
        except Exception as e:  # noqa: BLE001
            agg = {}
            mode = f"github(失败:{e})"
        totals = {p["id"]: agg.get(p["id"], 0) for p in products}
    else:
        v = load_json(VOTES, {"totals": {}, "city_totals": {}})
        totals = v.get("totals", {})
        city_totals = v.get("city_totals", {})
        mode = "local"

    national = [
        {
            "id": p["id"],
            "name": p["name"],
            "era": p.get("era", ""),
            "story": p.get("story", ""),
            "tags": p.get("tags", []),
            "verified": p.get("verified", False),
            "votes": totals.get(p["id"], 0),
        }
        for p in products
    ]
    national.sort(key=lambda x: (-x["votes"], x["name"]))

    cities = {}
    for city, d in city_totals.items():
        cl = [
            {"id": p["id"], "name": p["name"], "votes": d.get(p["id"], 0)}
            for p in products
        ]
        cl = [c for c in cl if c["votes"] > 0]
        cl.sort(key=lambda x: (-x["votes"], x["name"]))
        if cl:
            cities[city] = cl

    out = {
        "updated": datetime.datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "national": national,
        "cities": cities,
    }
    os.makedirs(WEB, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"已生成 {OUT}（mode={mode}, 单品 {len(national)}, 有票城市 {len(cities)}）")


def main():
    ap = argparse.ArgumentParser(description="生成排行榜数据")
    ap.add_argument("--from-github", action="store_true", help="使用 GitHub 真实聚合数据")
    args = ap.parse_args()
    build(args.from_github)


if __name__ == "__main__":
    main()
