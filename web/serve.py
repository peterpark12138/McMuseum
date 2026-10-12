#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦复活赛 · 本地/云端前端服务（展示 + 投票交互 + 看榜）

- 包裹 scripts/revival.py，把投票/榜单能力以 JSON API 暴露给网页
- 投票走真实麦当劳 MCP（需 MCD_MCP_TOKEN / .env），仅会员可投
- 榜单支持两种数据源：
    * 本地（默认）：读 data/votes.json，单机演示
    * GitHub 共享榜：设 LEADERBOARD_SOURCE=github 后，从 Issue 评论聚合
      跨用户真实榜（仅读取，公开部署可无 token，靠 GITHUB_BOT_LOGIN 锚定信任）
- 纯标准库，无第三方依赖；绑定 0.0.0.0 + $PORT 便于云端部署

运行：
    python web/serve.py
然后浏览器打开 http://127.0.0.1:8000
"""
import os
import sys
import json
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)            # McMuseum 根目录
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

# 载入 .env（与脚本共用同一份 token 配置）
try:
    import mcp_client
    mcp_client._load_env_file()
except Exception:
    pass

import revival  # noqa: E402
import report_github  # noqa: E402
import mcd_data  # noqa: E402


def _json(data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return status, {"Content-Type": "application/json; charset=utf-8"}, body


def _use_github():
    """是否使用 GitHub 共享榜作为数据源（跨用户真实榜）。"""
    return os.environ.get("LEADERBOARD_SOURCE", "").strip().lower() == "github"


_GH_CACHE = {"ts": 0.0, "data": None}
_GH_TTL = 60  # 秒：GitHub 聚合的进程内缓存，保护 API 限流（未认证 60 次/小时）


def _github_totals():
    """从 GitHub 聚合真实共享榜，返回 (totals, province_totals) 或 (None, None)。

    带 60s 进程内 TTL 缓存：聚合本身已是仓库级单接口（个位数调用），
    叠加缓存后公开站点不会触及 GitHub 未认证限流。
    """
    now = time.time()
    if _GH_CACHE["data"] is not None and now - _GH_CACHE["ts"] < _GH_TTL:
        d = _GH_CACHE["data"]
        return d.get("totals", {}), d.get("province_totals", {})
    try:
        agg = report_github.aggregate()
        if not agg.get("_github_ok", True):
            # GitHub 网络失败：不缓存全 0 结果，降级本地榜，待下次请求重试
            return None, None
        _GH_CACHE["ts"] = now
        _GH_CACHE["data"] = agg
        return agg.get("totals", {}), agg.get("province_totals", {})
    except Exception:  # noqa: BLE001
        return None, None


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, headers, body):
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _serve_file(self, path, ctype):
        if not os.path.exists(path):
            self._send(*_json({"error": "missing file"}, 404))
            return
        with open(path, "rb") as f:
            body = f.read()
        self._send(200, {"Content-Type": ctype + "; charset=utf-8"}, body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self._serve_file(os.path.join(HERE, "index.html"), "text/html")
            return
        if path == "/style.css":
            self._serve_file(os.path.join(HERE, "style.css"), "text/css")
            return
        if path == "/app.js":
            self._serve_file(os.path.join(HERE, "app.js"), "application/javascript")
            return
        if path == "/api/products":
            # 投票大厅单品列表：票数取自当前数据源（本地或 GitHub 共享榜）
            if _use_github():
                gt, _ = _github_totals()
                totals = gt if gt is not None else revival.load_json(revival.VOTES, {"totals": {}}).get("totals", {})
            else:
                totals = revival.load_json(revival.VOTES, {"totals": {}}).get("totals", {})
            out = []
            for p in revival.get_products():
                d = dict(p)
                d["votes"] = totals.get(p["id"], 0)
                out.append(d)
            self._send(*_json(out))
            return
        if path == "/api/provinces":
            self._send(*_json(revival.PROVINCES))
            return
        if path == "/api/detect-province":
            # 自动识别省份（仅取省级，不返回/不存储任何地址原文）；识别不到返回 ""
            try:
                p = revival.auto_detect_province()
            except Exception:
                p = ""
            self._send(*_json({"province": p}))
            return
        if path == "/api/leaderboard":
            qs = urllib.parse.parse_qs(parsed.query)
            province = qs.get("province", [None])[0]
            if _use_github():
                gt, gpt = _github_totals()
                if gt is not None:
                    totals = gt
                    province_totals = gpt or {}
                    source = "github"
                else:
                    votes = revival.load_json(revival.VOTES, {"totals": {}, "province_totals": {}})
                    totals = votes.get("totals", {})
                    province_totals = votes.get("province_totals", {})
                    source = "local(fallback)"
            else:
                votes = revival.load_json(revival.VOTES, {"totals": {}, "province_totals": {}})
                totals = votes.get("totals", {})
                province_totals = votes.get("province_totals", {})
                source = "local"
            name = {p["id"]: p["name"] for p in revival.get_products()}
            if province and province in province_totals:
                totals = province_totals[province]
                used_fallback = False
            else:
                used_fallback = bool(province)  # 该省暂无投票 -> 回退全国榜（前端会提示）
            items = sorted(totals.items(), key=lambda x: -x[1])
            out = [{"id": i, "name": name.get(i, i), "votes": v} for i, v in items]
            self._send(*_json({"province": province, "items": out,
                               "fallback": used_fallback, "source": source}))
            return

        # ---- 麦当劳实时只读增强（公开营销类数据支持缓存快照，无 token 也可展示；
        #      用户专属数据（抽奖/附近门店）无 token 时优雅降级，公开部署不影响可用性）----
        if path == "/api/nutrition":
            qs = urllib.parse.parse_qs(parsed.query)
            name = (qs.get("name", [None])[0] or "").strip()
            items = mcd_data.get_nutrition()
            if name:
                items = [x for x in items if name in (x.get("productName") or "")]
            self._send(*_json({"fallback": not items,
                               "items": items[:200]}))
            return
        if path == "/api/campaigns":
            items = mcd_data.get_campaigns()
            self._send(*_json({"fallback": not items, "items": items}))
            return
        if path == "/api/lottery":
            self._send(*_json({"fallback": not mcd_data.token_available(),
                               "info": mcd_data.get_lottery_info()}))
            return
        if path == "/api/points-mall":
            items = mcd_data.get_points_mall()
            self._send(*_json({"fallback": not items, "items": items}))
            return
        if path == "/api/on-sale":
            products = revival.get_products()
            meals = mcd_data.get_current_meals()
            self._send(*_json({"fallback": not meals,
                               "meals": [m["name"] for m in meals],
                               "comparison": mcd_data.compare_on_sale(products)}))
            return
        if path == "/api/nearby":
            near = mcd_data.get_nearby_stores()
            self._send(*_json({"fallback": not mcd_data.token_available(), **near}))
            return
        self._send(*_json({"error": "not found"}, 404))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/vote":
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                data = {}
            product = data.get("product")
            province = data.get("province")
            if not product:
                self._send(*_json({"ok": False, "msg": "缺少 product"}, 400))
                return
            # 仅麦当劳会员可投票：from_mcp=True 触发真实 query-my-account 读取。
            # record_vote 内部会自动把有效票回流到 GitHub 共享榜（匿名、仅作者可写）。
            msg, ok, val = revival.record_vote(product, province, from_mcp=True)
            self._send(*_json({"ok": ok, "msg": msg, "val": val}))
            return
        self._send(*_json({"error": "not found"}, 404))

    def log_message(self, *a):
        pass


def main():
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    srv = ThreadingHTTPServer((host, port), Handler)
    src = "GitHub 共享榜" if _use_github() else "本地"
    print(f"🍟 麦麦复活赛前端已启动: http://127.0.0.1:{port}  (bind {host}, 数据源={src})")
    print("   投票需已配置 MCD_MCP_TOKEN（或 .env）；Ctrl+C 退出。")
    srv.serve_forever()


if __name__ == "__main__":
    main()
