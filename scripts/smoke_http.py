#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""临时 HTTP 冒烟测试：验证公开站投票能力边界（跑完即删）。"""
import os
import sys
import time
import json
import socket
import subprocess
import urllib.request
import urllib.error

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
results = []


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_server(env_extra):
    port = free_port()
    env = dict(os.environ)
    env["PORT"] = str(port)
    env.update(env_extra)
    proc = subprocess.Popen([PY, os.path.join(BASE, "web", "serve.py")],
                            cwd=BASE, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/products", timeout=2)
            return proc, port
        except urllib.error.HTTPError:
            return proc, port
        except Exception:
            time.sleep(0.25)
    proc.kill()
    raise RuntimeError("服务启动超时")


def call(port, path, method="GET", payload=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def check(name, ok, note):
    results.append((ok, name, note))
    print(f"  {'✅' if ok else '❌'} {name}\n       └ {note}")


def main():
    print("🌐 HTTP 冒烟：投票能力边界\n")

    # 场景 A：公开部署（默认）
    p, port = start_server({})
    try:
        st, d = call(port, "/api/products")
        check("公开站可浏览单品", st == 200 and len(d) > 0, f"HTTP {st}, {len(d)} 款")
        st, d = call(port, "/api/leaderboard")
        check("公开站可看榜", st == 200, f"HTTP {st}, source={d.get('source')}")
        st, d = call(port, "/api/vote-capabilities")
        check("公开站投票能力=不可用", st == 200 and d.get("voting_available") is False,
              f"HTTP {st}, mode={d.get('mode')}, http_status={d.get('http_status')}")
        st, d = call(port, "/api/vote", "POST", {"product": "sakura_mcfloat", "province": "上海"})
        check("公开站 POST /api/vote 返回 501 且 ok=false",
              st == 501 and d.get("ok") is False and d.get("val") == 0,
              f"HTTP {st}, code={d.get('code')}")
        st, d = call(port, "/api/vote", "POST", {"product": "x", "member_id": "1"})
        check("公开站不接受客户端会员标识（能力优先拦截）", st == 501 and d.get("val") == 0,
              f"HTTP {st}, code={d.get('code')}")
    finally:
        p.kill()

    # 场景 B：显式开启但无会员 Token
    p, port = start_server({"MCMUSEUM_ENABLE_SERVER_VOTE": "1", "MCD_MCP_TOKEN": ""})
    try:
        st, d = call(port, "/api/vote", "POST", {"product": "sakura_mcfloat"})
        check("开启但无 Token 返回 503 且未计票",
              st == 503 and d.get("ok") is False and d.get("mode") == "server-vote-enabled-no-token",
              f"HTTP {st}, code={d.get('code')}")
        st, d = call(port, "/api/products")
        check("无 Token 仍可浏览", st == 200 and len(d) > 0, f"HTTP {st}, {len(d)} 款")
    finally:
        p.kill()

    # 场景 C：可信本机（有 Token）→ 客户端身份字段必须被拒（不走到真实投票）
    p, port = start_server({"MCMUSEUM_ENABLE_SERVER_VOTE": "1"})
    try:
        st, d = call(port, "/api/vote-capabilities")
        check("可信本机能力=可用", st == 200 and d.get("voting_available") is True,
              f"HTTP {st}, mode={d.get('mode')}")
        st, d = call(port, "/api/vote", "POST",
                     {"product": "sakura_mcfloat", "member_id": "888", "cardNo": "999"})
        check("可信本机也拒绝客户端会员标识（400，绝不采信）",
              st == 400 and d.get("code") == "client_identity_not_accepted" and d.get("val") == 0,
              f"HTTP {st}, code={d.get('code')}")
    finally:
        p.kill()

    print("-" * 60)
    bad = [r for r in results if not r[0]]
    print(f"结论：通过 {len(results) - len(bad)} 项 | ❌失败 {len(bad)} 项")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
