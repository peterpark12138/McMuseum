#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦复活赛 · 本地/云端前端服务（展示 + 投票交互 + 看榜）

能力边界（重要，与真实能力保持一致）：
- **浏览/看榜**：公开站点始终可用，无需任何凭证。
- **真实会员投票**：需要访问"访客自己的"麦当劳会员凭证。公开服务不可能拿到，
  也不应持有任何人的个人 Token，因此默认**不提供**在线投票：
    * 默认（mode=public-browse-only）：POST /api/vote 返回 501 + 明确引导，
      前端按钮置灰，绝不返回假的投票成功。
    * 可信本机环境：显式设置 MCMUSEUM_ENABLE_SERVER_VOTE=1 且配置了
      MCD_MCP_TOKEN（你自己的）时，才允许"服务端代你调 query-my-account 投票"，
      此时 POST /api/vote 与 CLI 走完全相同的 revival.record_vote 逻辑。
- **不接受客户端提交的会员标识**：任何 member/account/card/openid 等字段一律 400 拒绝，
  避免把客户端任意字符串当成已认证身份。
- 榜单支持两种数据源：
    * 本地（默认）：读 data/votes.json，单机演示
    * GitHub 共享榜：设 LEADERBOARD_SOURCE=github 后，从 Issue 评论聚合
      跨用户真实榜（仅读取，公开部署可无 token，靠 GITHUB_BOT_LOGIN 锚定信任）
- 纯标准库，无第三方依赖；绑定 0.0.0.0 + $PORT 便于云端部署

运行：
    python web/serve.py                      # 浏览/看榜可用，在线投票不可用（默认安全）
    MCMUSEUM_ENABLE_SERVER_VOTE=1 python web/serve.py   # 本机可信环境：开启在线投票
然后浏览器打开 http://127.0.0.1:8000
"""
import os
import sys
import json
import re
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


# ---- 真实会员投票的能力边界 ----
LOCAL_CLI_HINT = ("在本机执行：python scripts/revival.py vote --product <单品id> --from-mcp "
                  "（或在 WorkBuddy 里让「麦麦复活赛」Skill 代你投票）")

# 客户端提交这些字段 = 试图用客户端字符串冒充会员身份，一律拒绝
_IDENTITY_FIELD_HINTS = ("member", "account", "card", "openid", "unionid", "userid",
                         "phone", "mobile", "token", "credential", "secret", "会员", "账号")


def server_vote_enabled():
    """是否显式开启"服务端代投"（仅可信本机环境）。默认关闭。"""
    return os.environ.get("MCMUSEUM_ENABLE_SERVER_VOTE", "").strip().lower() in ("1", "true", "yes", "on")


# ---- 公开演示模式（模式 A）：与真实投票数据完全隔离 ----
DEMO_VOTES = os.path.join(ROOT, "data", "demo_votes.json")
DEMO_NOTE = ("演示数据：以下票数为示例值，仅用于展示榜单外观，"
             "不代表任何真实投票结果，也不会提交到 GitHub 正式共享榜。")


def demo_mode():
    """是否以「公开演示模式」启动（MCMUSEUM_DEMO=1）。

    演示模式：无需任何 Token；只展示 data/demo_votes.json 里的示例票数；
    在线投票一律不可用，因此演示票不存在流入正式榜的路径。
    """
    return os.environ.get("MCMUSEUM_DEMO", "").strip().lower() in ("1", "true", "yes", "on")


def demo_totals():
    """读取演示票数（只读）。返回 (totals, province_totals)；文件缺失时返回空结构。"""
    try:
        with open(DEMO_VOTES, encoding="utf-8") as f:
            d = json.load(f)
        if not d.get("_demo"):
            return {}, {}      # 不是演示文件就当没有，绝不拿真实数据充数
        return d.get("totals", {}) or {}, d.get("province_totals", {}) or {}
    except Exception:  # noqa: BLE001
        return {}, {}


def vote_capability():
    """当前实例能否在此完成"真实麦当劳会员投票"。返回结构化能力描述（永远不撒谎）。"""
    if demo_mode():
        return {
            "voting_available": False,
            "mode": "demo-browse-only",
            "code": "demo_mode_vote_disabled",
            "http_status": 501,
            "demo": True,
            "msg": ("当前为「公开演示模式」：展示的票数是示例数据，不提供在线投票。"
                    "真实投票请用本机 CLI / WorkBuddy Skill 完成（需麦当劳会员认证）。"),
            "how_to_vote": LOCAL_CLI_HINT,
        }
    if not server_vote_enabled():
        return {
            "voting_available": False,
            "mode": "public-browse-only",
            "code": "vote_not_supported_here",
            "http_status": 501,
            "msg": ("本站点未开启在线投票：公开服务无法安全验证麦当劳会员身份，"
                    "也不会代替访客持有会员凭证。请使用本机 CLI 或 WorkBuddy Skill 投票。"),
            "how_to_vote": LOCAL_CLI_HINT,
        }
    if not mcd_data.token_available():
        return {
            "voting_available": False,
            "mode": "server-vote-enabled-no-token",
            "code": "member_auth_unavailable",
            "http_status": 503,
            "msg": "已开启服务端投票但未配置 MCD_MCP_TOKEN，无法完成会员身份验证；投票未执行。",
            "how_to_vote": LOCAL_CLI_HINT,
        }
    return {
        "voting_available": True,
        "mode": "trusted-local-server",
        "code": "ok",
        "http_status": 200,
        "msg": ("本实例为可信本机环境（已显式开启 MCMUSEUM_ENABLE_SERVER_VOTE 且已配置会员 Token），"
                "可在此投票：与 CLI 走同一套 revival.record_vote 逻辑。"),
        "how_to_vote": "",
    }


def _redact(text):
    """错误信息脱敏：绝不把 Token / 凭证写进响应或日志。"""
    s = str(text)
    for k in ("MCD_MCP_TOKEN", "GITHUB_TOKEN"):
        v = (os.environ.get(k) or "").strip()
        if v and len(v) >= 6:
            s = s.replace(v, "***")
    # Bearer xxx 形式的兜底脱敏
    s = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}", r"\1***", s)
    return s


def _client_identity_fields(data):
    """挑出客户端试图提交的"会员身份类"字段（不接受，仅用于报错提示）。"""
    if not isinstance(data, dict):
        return []
    return [k for k in data.keys()
            if any(h in str(k).lower() for h in _IDENTITY_FIELD_HINTS)]


def _vote_http_status(msg):
    """把 record_vote 的失败原因映射为语义正确的 HTTP 状态码（不做字符串伪造成功）。"""
    s = str(msg or "")
    if "投过票" in s or "不能重复" in s:
        return 409          # 重复投票（该会员该单品已计票）
    if "query-my-account" in s or "会员唯一标识" in s or "无法确认麦当劳会员身份" in s:
        return 401          # 会员身份验证失败（无 token / token 无效 / 读不到会员信息）
    if "省份" in s:
        return 400          # 省份不在受控枚举
    return 400


def _use_github():
    """是否使用 GitHub 共享榜作为数据源（跨用户真实榜）。"""
    return os.environ.get("LEADERBOARD_SOURCE", "").strip().lower() == "github"


_GH_CACHE = {"ts": 0.0, "data": None}
_GH_TTL = 60  # 秒：GitHub 聚合的进程内缓存，保护 API 限流（未认证 60 次/小时）

_ACCT_CACHE = {"ts": 0.0, "data": None}
_ACCT_TTL = 300  # 秒：会员状态缓存（积分变化不敏感，护 MCP 调用）


def _account_status():
    """会员连接状态（只读）。返回 {"connected": bool, "availablePoint": int|None}。

    仅返回积分数字，绝不返回会员唯一标识；无 token 或未解析到积分时
    connected=false（前端据此显示「会员未连接」引导，不伪造数据）。
    """
    now = time.time()
    if _ACCT_CACHE["data"] is not None and now - _ACCT_CACHE["ts"] < _ACCT_TTL:
        return _ACCT_CACHE["data"]
    if not mcd_data.token_available():
        out = {"connected": False, "availablePoint": None}
        _ACCT_CACHE["ts"], _ACCT_CACHE["data"] = now, out
        return out
    try:
        points, member_id = revival.real_account_info()  # 标识只用一次即丢弃，不回传
        # connected 看会员标识是否解析成功（积分可为 0，0 也是合法值）
        out = {"connected": bool(member_id),
               "availablePoint": int(points) if points is not None else None}
    except Exception:  # noqa: BLE001
        out = {"connected": False, "availablePoint": None}
    _ACCT_CACHE["ts"], _ACCT_CACHE["data"] = now, out
    return out


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
        if path == "/app.js":
            self._serve_file(os.path.join(HERE, "app.js"), "application/javascript")
            return
        if path.startswith("/assets/"):
            # 设计稿素材（png/jpg）；防目录穿越
            rel = path[len("/assets/"):].replace("..", "")
            ext = os.path.splitext(rel)[1].lower()
            ctype = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(ext, "application/octet-stream")
            self._serve_file(os.path.join(HERE, "assets", rel), ctype)
            return
        if path == "/api/product":
            # 单品详情（只读）：GET /api/product?id=<单品id>
            qs = urllib.parse.parse_qs(parsed.query)
            pid = (qs.get("id", [None])[0] or "").strip()
            if not pid:
                self._send(*_json({"error": "missing id", "msg": "缺少查询参数 id"}, 400))
                return
            prod = next((p for p in revival.get_products() if p["id"] == pid), None)
            if prod is None:
                self._send(*_json({"error": "product_not_found",
                                   "msg": f"未找到单品「{pid}」，请用 /api/products 查看可用 id"}, 404))
                return
            d = dict(prod)
            if demo_mode():
                dt, _ = demo_totals()
                d["votes"] = dt.get(pid, 0)
                d["demo"] = True
            else:
                d["votes"] = revival.load_votes().get("totals", {}).get(pid, 0)
            self._send(*_json(d))
            return
        if path == "/api/products":
            # 投票大厅单品列表：票数取自当前数据源（演示 / 本地 / GitHub 共享榜）
            if demo_mode():
                # 保持与正式模式一致的数组结构（前端不用改解析逻辑），
                # 演示标记放在每个条目 + /api/vote-capabilities 里。
                totals, _ = demo_totals()
                out = []
                for p in revival.get_products():
                    d = dict(p)
                    d["votes"] = totals.get(p["id"], 0)
                    d["demo"] = True
                    out.append(d)
                self._send(*_json(out))
                return
            if _use_github():
                gt, _ = _github_totals()
                totals = gt if gt is not None else revival.load_votes().get("totals", {})
            else:
                totals = revival.load_votes().get("totals", {})
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
            # 演示模式不触碰 MCP（无 Token，也不该发请求）
            if demo_mode():
                self._send(*_json({"province": "", "demo": True}))
                return
            try:
                p = revival.auto_detect_province()
            except Exception:
                p = ""
            self._send(*_json({"province": p}))
            return
        if path == "/api/leaderboard":
            qs = urllib.parse.parse_qs(parsed.query)
            province = qs.get("province", [None])[0]
            if demo_mode():
                totals, province_totals = demo_totals()
                source = "demo"
            elif _use_github():
                gt, gpt = _github_totals()
                if gt is not None:
                    totals = gt
                    province_totals = gpt or {}
                    source = "github"
                else:
                    votes = revival.load_votes()
                    totals = votes.get("totals", {})
                    province_totals = votes.get("province_totals", {})
                    source = "local(fallback)"
            else:
                votes = revival.load_votes()
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
                               "fallback": used_fallback, "source": source,
                               "demo": demo_mode(),
                               "demo_note": DEMO_NOTE if demo_mode() else ""}))
            return

        # ---- 麦当劳实时只读增强（公开营销类数据支持缓存快照，无 token 也可展示；
        #      用户专属数据（抽奖/附近门店）无 token 时优雅降级，公开部署不影响可用性）----
        if path == "/api/vote-capabilities":
            # 前端据此决定「投一票」按钮可用 / 置灰，并给出本地投票引导（不伪造能力）
            caps = dict(vote_capability())
            caps["demo"] = demo_mode()
            if demo_mode():
                caps["demo_note"] = DEMO_NOTE
            self._send(*_json(caps))
            return
        if path == "/api/account":
            # 会员连接状态 + 可用积分（只读 query-my-account；绝不返回会员标识，300s 缓存）
            self._send(*_json(_account_status()))
            return
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
            # ① 先看这个实例有没有能力做"真实会员投票"（公开站点默认没有）
            caps = vote_capability()
            if not caps["voting_available"]:
                self._send(*_json({"ok": False, "code": caps["code"], "mode": caps["mode"],
                                   "msg": caps["msg"], "how_to_vote": caps["how_to_vote"],
                                   "voting_available": False, "val": 0},
                                  caps["http_status"]))
                return
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                data = {}
            if not isinstance(data, dict):
                data = {}
            # ② 绝不接受客户端提交的"会员标识"冒充已认证身份
            bad = _client_identity_fields(data)
            if bad:
                self._send(*_json({"ok": False, "code": "client_identity_not_accepted",
                                   "msg": ("不接受客户端提交的会员标识字段（" + "、".join(sorted(bad)) +
                                           "）：服务端只信任自己调用 query-my-account 得到的会员身份。"),
                                   "val": 0}, 400))
                return
            product = data.get("product")
            province = data.get("province")
            if not product:
                self._send(*_json({"ok": False, "code": "bad_request", "msg": "缺少 product"}, 400))
                return
            # ③ 真实投票：from_mcp=True 触发真实 query-my-account（不是"当作已认证"，而是真的去认证）
            try:
                msg, ok, val = revival.record_vote(product, province, from_mcp=True)
            except Exception as e:  # noqa: BLE001
                self._send(*_json({"ok": False, "code": "vote_failed",
                                   "msg": _redact(f"投票失败：{e}"), "val": 0}, 500))
                return
            info = getattr(revival, "LAST_VOTE_RESULT", {}) or {}
            payload = {
                "ok": ok,
                "msg": _redact(msg),
                "val": val,
                # 共享榜回流的真实结果（失败时必须如实为 False，前端不得宣称已上榜）
                "shared_board_reported": bool(info.get("github_reported", False)),
                "shared_board_msg": _redact(info.get("github_msg", "")),
            }
            if ok:
                self._send(*_json(payload, 200))
            else:
                payload["code"] = "vote_rejected"
                self._send(*_json(payload, _vote_http_status(msg)))
            return
        self._send(*_json({"error": "not found"}, 404))

    def log_message(self, *a):
        pass


def main():
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    srv = ThreadingHTTPServer((host, port), Handler)
    src = "演示数据(DEMO)" if demo_mode() else ("GitHub 共享榜" if _use_github() else "本地")
    caps = vote_capability()
    print(f"🍟 麦麦复活赛前端已启动: http://127.0.0.1:{port}  (bind {host}, 数据源={src})")
    if demo_mode():
        print("   🧪 公开演示模式：票数为示例数据（页面已标注「演示数据」），不提供在线投票，也不会回流正式共享榜。")
    if caps["voting_available"]:
        print("   在线投票：✅ 已开启（可信本机环境 MCMUSEUM_ENABLE_SERVER_VOTE=1 + 会员 Token 已配置）")
    else:
        print(f"   在线投票：❌ 不可用（{caps['code']}）——浏览与看榜照常，真实投票请用 CLI / Skill：{LOCAL_CLI_HINT}")
        print("   本机想开启在线投票：MCMUSEUM_ENABLE_SERVER_VOTE=1 python web/serve.py")
    print("   Ctrl+C 退出。")
    srv.serve_forever()


if __name__ == "__main__":
    main()
