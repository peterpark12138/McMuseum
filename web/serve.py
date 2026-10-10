#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦复活赛 · 本地前端服务（展示 + 投票交互 + 看榜）

- 包裹 scripts/revival.py，把投票/榜单能力以 JSON API 暴露给网页
- 投票走真实麦当劳 MCP（需 MCD_MCP_TOKEN / .env）
- 纯本地运行，不依赖任何第三方框架（仅标准库）

运行：
    python web/serve.py
然后浏览器打开 http://127.0.0.1:8000
"""
import os
import sys
import json
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


def _json(data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return status, {"Content-Type": "application/json; charset=utf-8"}, body


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
        if path == "/api/leaderboard":
            qs = urllib.parse.parse_qs(parsed.query)
            province = qs.get("province", [None])[0]
            votes = revival.load_json(revival.VOTES, {"totals": {}, "province_totals": {}})
            name = {p["id"]: p["name"] for p in revival.get_products()}
            if province and province in votes.get("province_totals", {}):
                totals = votes["province_totals"][province]
                used_fallback = False
            else:
                totals = votes.get("totals", {})
                used_fallback = bool(province)  # 该省暂无投票 -> 回退全国榜（前端会提示）
            items = sorted(totals.items(), key=lambda x: -x[1])
            out = [{"id": i, "name": name.get(i, i), "votes": v} for i, v in items]
            self._send(*_json({"province": province, "items": out, "fallback": used_fallback}))
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
            # 仅麦当劳会员可投票：from_mcp=True 触发真实 query-my-account 读取
            msg, ok, val = revival.record_vote(product, province, from_mcp=True)
            self._send(*_json({"ok": ok, "msg": msg, "val": val}))
            return
        self._send(*_json({"error": "not found"}, 404))

    def log_message(self, *a):
        pass


def main():
    port = int(os.environ.get("PORT", "8000"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"🍟 麦麦复活赛前端已启动: http://127.0.0.1:{port}")
    print("   投票需已配置 MCD_MCP_TOKEN（或 .env）；Ctrl+C 退出。")
    srv.serve_forever()


if __name__ == "__main__":
    main()
