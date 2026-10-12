#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦复活赛 · 场景化端到端测试（评审可复现）

覆盖任务书要求的 15 个场景。每个用例都明确标注测试性质：

  [MOCK] = 用 mock 隔离外部依赖（麦当劳 MCP / GitHub API），不触网、不需要任何凭证，
           任何环境都能跑，结果确定可复现。
  [REAL] = 真实集成测试：会真的访问麦当劳 MCP / GitHub。默认**不执行**，
           需显式 MCMUSEUM_REAL_INTEGRATION=1 才运行；环境不满足时标记 ⏭️跳过，
           **绝不**把跳过或未执行写成通过。

不得把模拟数据冒充真实数据：所有 [MOCK] 用例只在临时目录里操作副本账本，
不写 data/votes.json，也不向 GitHub 提交任何东西。

用法：
  python3 scripts/test_scenarios.py                                  # 只跑 mock（离线可跑）
  python3 scripts/test_scenarios.py --real                           # 追加真实集成用例
  MCMUSEUM_REAL_INTEGRATION=1 python3 scripts/test_scenarios.py      # 等价的环境变量写法
退出码：0 = 全部通过；1 = 有用例失败。
"""
import os
import re
import sys
import json
import time
import shutil
import tempfile
import threading

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(BASE, "scripts")
WEB = os.path.join(BASE, "web")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, WEB)

import revival  # noqa: E402
import report_github as rg  # noqa: E402
import serve as sv  # noqa: E402

# --real：等价于 MCMUSEUM_REAL_INTEGRATION=1，显式开启 [REAL] 真实集成用例
if any(a in ("--real", "-r", "--with-real") for a in sys.argv[1:]):
    os.environ["MCMUSEUM_REAL_INTEGRATION"] = "1"

RESULTS = []


def check(name, ok, note, kind="MOCK"):
    state = "✅" if ok is True else "❌"
    RESULTS.append((bool(ok), name))
    print(f"  {state} [{kind}] {name}\n       └ {note}")


def skip(name, note, kind="REAL"):
    RESULTS.append((None, name))
    print(f"  ⏭️ [{kind}] {name}\n       └ {note}")


def with_tmp_votes(fn, content=None):
    """在临时账本副本上运行 fn()，绝不碰 data/votes.json。"""
    d = tempfile.mkdtemp(prefix="mcmuseum-test-")
    p = os.path.join(d, "votes.json")
    if content is not None:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False)
    old = revival.VOTES
    revival.VOTES = p
    try:
        return fn(p)
    finally:
        revival.VOTES = old
        shutil.rmtree(d, ignore_errors=True)


def fake_member(points=250, mid="test-member-0001"):
    """模拟一个「已通过认证的会员」——仅用于隔离 MCP，不代表真实会员数据。"""
    return lambda: (points, mid)


class _Handler(sv.Handler):
    """极简 handler：只走路由逻辑，不建立 socket。"""
    def __init__(self):
        self.sent = None

    def _send(self, status, headers, body):
        self.sent = (status, body.decode("utf-8"))

    def log_message(self, *a):
        pass


def get(path):
    h = _Handler()
    h.path = path
    h.headers = {}
    h.do_GET()
    return h.sent[0], json.loads(h.sent[1])


def swap_env(key, value):
    """临时设置/清除环境变量，返回还原函数。"""
    old = os.environ.get(key)
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value

    def restore():
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old
    return restore


print("🧪 McMuseum 场景测试（[MOCK]=离线可复现  [REAL]=真实集成，默认跳过）\n")

# ========== 场景 1：正常读取产品列表 ==========
try:
    prods = revival.get_products()
    ids = [p["id"] for p in prods]
    ok = (len(prods) > 0
          and all(p.get("id") and p.get("name") for p in prods)
          and len(set(ids)) == len(ids))
    check("1. 正常读取产品列表", ok,
          f"共 {len(prods)} 款，id 唯一且均含 id/name；"
          f"投票池 {sum(1 for p in prods if p.get('vote_eligible', True))} 款")
except Exception as e:  # noqa: BLE001
    check("1. 正常读取产品列表", False, f"读取失败: {e}")

# ========== 场景 2：产品详情查询失败时的错误处理 ==========
try:
    st, b = get("/api/product?id=__not_exist__")
    ok404 = (st == 404 and b.get("error") == "product_not_found" and bool(b.get("msg")))
    st2, b2 = get("/api/product")
    ok400 = (st2 == 400 and bool(b2.get("error")))
    st3, b3 = get("/api/product?id=sakura_mcfloat")
    ok200 = (st3 == 200 and b3.get("id") == "sakura_mcfloat")
    check("2. 产品详情查询失败的错误处理", ok404 and ok400 and ok200,
          f"未知 id→404 {b.get('error')}（带 JSON 说明，不是 200 空响应）；"
          f"缺 id 参数→400；正常 id→200 {b3.get('name')}")
except Exception as e:  # noqa: BLE001
    check("2. 产品详情查询失败的错误处理", False, f"检查失败: {e}")

# ========== 场景 3：未配置 Token 时，公开演示仍可浏览 ==========
try:
    r = swap_env("MCD_MCP_TOKEN", "")
    try:
        import mcd_data  # noqa: E402
        nut = mcd_data.get_nutrition()
        camp = mcd_data.get_campaigns()
        mall = mcd_data.get_points_mall()
        meals = mcd_data.get_current_meals()
        st_p, prods = get("/api/products")
        demo_t, demo_pt = sv.demo_totals()
    finally:
        r()
    ok = (st_p == 200 and len(prods) > 0
          and isinstance(nut, list) and isinstance(camp, list)
          and isinstance(mall, list) and isinstance(meals, list)
          and len(demo_t) > 0)
    check("3. 无 Token 时公开演示仍可浏览", ok,
          f"/api/products=200（{len(prods)} 款）；演示票 {len(demo_t)} 款可读；"
          f"麦当劳只读增强全部优雅降级为空容器（不崩溃、不报错）")
except Exception as e:  # noqa: BLE001
    check("3. 无 Token 时公开演示仍可浏览", False, f"检查失败: {e}")

# ========== 场景 4：未配置 Token 时，真实投票不能返回成功 ==========
try:
    def _no_token(p):
        return revival.record_vote("sakura_mcfloat", None, from_mcp=True)
    r = swap_env("MCD_MCP_TOKEN", "")
    try:
        msg, ok_r, val = with_tmp_votes(_no_token)
    finally:
        r()
    check("4. 无 Token 时真实投票不返回成功", ok_r is False and val == 0,
          f"ok={ok_r}, val={val}；msg={(msg or '')[:56]}…")
except Exception as e:  # noqa: BLE001
    check("4. 无 Token 时真实投票不返回成功", False, f"检查失败: {e}")

# ========== 场景 5：无效 Token 不产生有效票数 ==========
try:
    def _boom():
        raise RuntimeError("调用 query-my-account 失败：401 Unauthorized（无效 Token）")

    def _invalid(p):
        old = revival.real_account_info
        revival.real_account_info = _boom
        try:
            return revival.record_vote("sakura_mcfloat", None, from_mcp=True), os.path.exists(p)
        finally:
            revival.real_account_info = old
    (msg, ok_r, val), wrote = with_tmp_votes(_invalid)
    check("5. 无效 Token 不产生有效票数", ok_r is False and val == 0 and wrote is False,
          f"认证失败→ok={ok_r}, val={val}；账本未被创建/写入={not wrote}（零票、零副作用）")
except Exception as e:  # noqa: BLE001
    check("5. 无效 Token 不产生有效票数", False, f"检查失败: {e}")

# ========== 场景 6：同一会员对同一产品重复投票 ==========
try:
    def _dup(p):
        old = revival.real_account_info
        revival.real_account_info = fake_member()
        try:
            m1, o1, v1 = revival.record_vote("taro_pie", "上海", from_mcp=True)
            m2, o2, v2 = revival.record_vote("taro_pie", "上海", from_mcp=True)
            m3, o3, v3 = revival.record_vote("shake_fries", None, from_mcp=True)
            return (o1, v1, o2, v2, o3, v3), json.load(open(p, encoding="utf-8"))
        finally:
            revival.real_account_info = old
    (o1, v1, o2, v2, o3, v3), book = with_tmp_votes(_dup)
    ok = (o1 is True and o2 is False and v2 == 0 and o3 is True
          and book["totals"]["taro_pie"] == v1)
    check("6. 同一会员对同一产品重复投票被拦截", ok,
          f"首次 ok={o1}（{v1} 票）；重复 ok={o2}, val={v2}（文档口径：每会员每单品仅一次）；"
          f"换个单品仍可投 ok={o3}（{v3} 票）；账本 totals={book['totals']['taro_pie']}")
except Exception as e:  # noqa: BLE001
    check("6. 同一会员对同一产品重复投票被拦截", False, f"检查失败: {e}")

# ========== 场景 7：两个并发请求同会员同单品不重复计票 ==========
try:
    def _conc(p):
        old = revival.real_account_info
        revival.real_account_info = fake_member(points=0)  # 0 积分 → 每人 1 票，计数最直观
        out = {}
        barrier = threading.Barrier(2)

        def worker(i):
            barrier.wait()                       # 尽量让两个请求同时进入临界区
            m, o, v = revival.record_vote("sakura_mcfloat", None, from_mcp=True)
            out[i] = (o, v)
        try:
            ts = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(timeout=30)
            return out, json.load(open(p, encoding="utf-8"))
        finally:
            revival.real_account_info = old
    out, book = with_tmp_votes(_conc)
    succ = [v for (o, v) in out.values() if o]
    ok = (len(out) == 2 and len(succ) == 1 and book["totals"]["sakura_mcfloat"] == 1)
    check("7. 并发两请求同会员同单品不重复计票", ok,
          f"两个并发请求结果={out}；成功数={len(succ)}，账本 totals={book['totals']['sakura_mcfloat']}（预期 1）")
except Exception as e:  # noqa: BLE001
    check("7. 并发两请求同会员同单品不重复计票", False, f"检查失败: {e}")

# ========== 场景 8：本地持久化失败时不报告已成功保存 ==========
try:
    def _persist_fail(p):
        old_rai, old_save = revival.real_account_info, revival.save_json
        revival.real_account_info = fake_member()
        revival.save_json = lambda path, data: (_ for _ in ()).throw(OSError("磁盘不可写（模拟）"))
        try:
            res = revival.record_vote("sakura_mcfloat", None, from_mcp=True)
            return res, revival.LAST_VOTE_RESULT.get("saved"), os.path.exists(p)
        finally:
            revival.real_account_info, revival.save_json = old_rai, old_save
    (msg, ok_r, val), saved_flag, wrote = with_tmp_votes(_persist_fail)
    ok = (ok_r is False and val == 0 and saved_flag is False and wrote is False
          and "未能保存" in (msg or ""))
    check("8. 本地持久化失败不报告保存成功", ok,
          f"ok={ok_r}, val={val}, saved={saved_flag}；msg={(msg or '')[:44]}…")
except Exception as e:  # noqa: BLE001
    check("8. 本地持久化失败不报告保存成功", False, f"检查失败: {e}")

# ========== 场景 9：GitHub 写入失败时区分本地成功与共享榜同步失败 ==========
try:
    def _gh_fail(p):
        old_rai, old_rv = revival.real_account_info, rg.report_vote
        revival.real_account_info = fake_member()
        rg.report_vote = lambda *a, **k: (False, "模拟：GitHub 提交失败(500)")
        try:
            res = revival.record_vote("sakura_mcfloat", "广东", from_mcp=True)
            return res, dict(revival.LAST_VOTE_RESULT), json.load(open(p, encoding="utf-8"))
        finally:
            revival.real_account_info, rg.report_vote = old_rai, old_rv
    (msg, ok_r, val), rec, book = with_tmp_votes(_gh_fail)
    ok = (ok_r is True and val > 0 and book["totals"]["sakura_mcfloat"] == val
          and rec.get("github_reported") is False
          and bool(rec.get("github_msg"))          # 必须带上失败原因，不能静默
          and "未回流" in msg and "投票成功" in msg)
    check("9. GitHub 写入失败区分本地成功/共享榜失败", ok,
          f"本地 ok={ok_r}（{val} 票）且已落盘={book['totals']['sakura_mcfloat']}；"
          f"shared_board_reported={rec.get('github_reported')}，文案含「未回流」")
except Exception as e:  # noqa: BLE001
    check("9. GitHub 写入失败区分本地成功/共享榜失败", False, f"检查失败: {e}")

# ========== 场景 10：评论超 100 条仍能完整聚合 ==========
try:
    old_req, old_map = rg._req, rg._load_map
    rg._load_map = lambda: {"a": 1, "b": 2}
    page_re = re.compile(r"[?&]page=(\d+)(&|$)")

    def fake_req(url, method="GET", data=None, token=None):
        m = page_re.search(url)
        pg = int(m.group(1)) if m else 1
        n = {1: 100, 2: 57}.get(pg, 0)
        base = 0 if pg == 1 else 100
        return [{"issue_url": "https://api.github.com/repos/o/r/issues/1",
                 "user": {"login": "bot"},
                 "body": f"vote mcp +1 全国 2026-10-13 rid={base+i:012x}"} for i in range(n)]
    rg._req = fake_req
    r = swap_env("GITHUB_BOT_LOGIN", "bot")
    try:
        agg = rg.aggregate()
    finally:
        r()
        rg._req, rg._load_map = old_req, old_map
    ok = agg.get("totals", {}).get("a") == 157 and agg.get("_github_ok") is True
    check("10. GitHub 评论超 100 条完整聚合", ok,
          f"两页共 157 条 → totals['a']={agg.get('totals', {}).get('a')}（预期 157，未丢票）")
except Exception as e:  # noqa: BLE001
    check("10. GitHub 评论超 100 条完整聚合", False, f"检查失败: {e}")

# ========== 场景 11：403/429/500/超时/网络错误不当零票 ==========
try:
    old_req, old_map = rg._req, rg._load_map
    rg._load_map = lambda: {"a": 1}
    cases = {
        "403": RuntimeError("GitHub API 403: rate limit exceeded"),
        "429": RuntimeError("GitHub API 429: too many requests"),
        "500": RuntimeError("GitHub API 500: server error"),
        "超时": RuntimeError("GitHub API 网络错误: timed out"),
    }
    good, detail = True, []
    for label, err in cases.items():
        def boom(url, method="GET", data=None, token=None, _e=err):
            raise _e
        rg._req = boom
        r = swap_env("GITHUB_BOT_LOGIN", "bot")
        try:
            agg = rg.aggregate()
            sv._GH_CACHE.update({"ts": 0.0, "data": None})
            gt, gpt = sv._github_totals()      # 上层必须降级，而不是把 0 当真实榜
            ok_case = (agg.get("_github_ok") is False and gt is None and gpt is None)
            detail.append(f"{label}→_github_ok=False/降级=True")
            good = good and ok_case
        finally:
            r()
    rg._req, rg._load_map = old_req, old_map
    check("11. GitHub 403/429/500/超时不当零票", good,
          "故障一律标记 _github_ok=False 并让上层回退本地榜（不缓存全 0）：" + "；".join(detail))
except Exception as e:  # noqa: BLE001
    check("11. GitHub 403/429/500/超时不当零票", False, f"检查失败: {e}")

# ========== 场景 12：不可信作者 / 格式异常评论不影响榜单 ==========
try:
    comments = [
        {"user": {"login": "attacker"}, "body": "vote mcp +9999 全国 2026-10-13"},  # 伪造作者
        {"user": {"login": "bot"}, "body": "vote guest +500 全国 2026-10-13"},       # 非白名单票种
        {"user": {"login": "bot"}, "body": "vote mcp +abc 全国 2026-10-13"},         # 票数非数字
        {"user": {"login": "bot"}, "body": "vote mcp -5 全国 2026-10-13"},           # 负票
        {"user": {"login": "bot"}, "body": ""},                                      # 空评论
        {"user": {"login": "bot"}, "body": "这是一条普通留言"},                       # 无关内容
        {"user": {"login": "bot"}, "body": "vote mcp +3 上海 2026-10-13 rid=abc"},   # 有效
        {"user": {"login": "bot"}, "body": "vote mcp +2 全国 2026-10-13 rid=def"},   # 有效
    ]
    t, pt = rg._tally_comments(comments, "bot")
    t_none, _ = rg._tally_comments(comments, None)      # 无信任锚点 → 一条都不认
    ok = (t == 5 and pt.get("上海") == 3 and t_none == 0)
    check("12. 不可信作者/格式异常评论不影响榜单", ok,
          f"有效合计 {t} 票（上海 3 + 全国 2）；伪造 9999 / guest 500 / +abc / -5 / 空 / 无关 全部丢弃；"
          f"无信任锚点时 {t_none} 票")
except Exception as e:  # noqa: BLE001
    check("12. 不可信作者/格式异常评论不影响榜单", False, f"检查失败: {e}")

# ========== 场景 13：演示/模拟数据不会进入正式共享榜 ==========
try:
    demo_path = os.path.join(BASE, "data", "demo_votes.json")
    demo = json.load(open(demo_path, encoding="utf-8"))
    ok_flag = demo.get("_demo") is True and bool(demo.get("_note"))
    r = swap_env("MCMUSEUM_DEMO", "1")
    try:
        caps = sv.vote_capability()
        dt, _ = sv.demo_totals()
    finally:
        r()
    # 沙箱开关 MCMUSEUM_SHARED_BOARD=0：本地照常计票，但绝不调用 GitHub
    calls = []
    old_rv = rg.report_vote

    def spy(*a, **k):
        calls.append(a)
        return True, "ok"
    rg.report_vote = spy
    r2 = swap_env("MCMUSEUM_SHARED_BOARD", "0")

    def _sandbox(p):
        old_rai = revival.real_account_info
        revival.real_account_info = fake_member()
        try:
            return revival.record_vote("sakura_mcfloat", None, from_mcp=True), dict(revival.LAST_VOTE_RESULT)
        finally:
            revival.real_account_info = old_rai
    try:
        (m, o, v), rec = with_tmp_votes(_sandbox)
    finally:
        r2()
        rg.report_vote = old_rv
    ok = (ok_flag and caps.get("voting_available") is False
          and caps.get("mode") == "demo-browse-only" and len(dt) > 0
          and len(calls) == 0 and rec.get("shared_board_skipped") is True and o is True)
    check("13. 演示/模拟数据不进入正式共享榜", ok,
          f"演示文件带 _demo 标记与说明；演示模式投票不可用（mode={caps.get('mode')}）；"
          f"沙箱开关下 GitHub 调用次数={len(calls)}（预期 0），本地仍计 {v} 票")
except Exception as e:  # noqa: BLE001
    check("13. 演示/模拟数据不进入正式共享榜", False, f"检查失败: {e}")

# ========== 场景 14：网页不能通过伪造会员 ID 绕过认证 ==========
try:
    clean = sv._client_identity_fields({"product": "sakura_mcfloat", "province": "上海"})
    dirty = sv._client_identity_fields({"product": "x", "member_id": "1", "cardNo": "2",
                                        "openid": "3", "token": "4", "会员号": "5"})
    ok = (not clean) and set(dirty) == {"member_id", "cardNo", "openid", "token", "会员号"}
    check("14. 网页无法用伪造会员 ID 绕过认证", ok,
          f"正常字段放行；身份类字段全部拦截={sorted(dirty)}"
          f"（服务端只信任自己调用 query-my-account 得到的身份）")
except Exception as e:  # noqa: BLE001
    check("14. 网页无法用伪造会员 ID 绕过认证", False, f"检查失败: {e}")

# ========== 场景 15：公开浏览接口不泄露 Token / 会员凭证 ==========
try:
    secret = "SUPERSECRET_MCP_TOKEN_123456"
    gh_secret = "ghp_SUPERSECRET_GITHUB_TOKEN_789"
    member_secret = "SENSITIVE-MEMBER-ID-999"
    r1 = swap_env("MCD_MCP_TOKEN", secret)
    r2 = swap_env("GITHUB_TOKEN", gh_secret)
    old_rai = revival.real_account_info
    revival.real_account_info = lambda: (123, member_secret)   # 制造"含敏感标识"的返回
    try:
        sv._ACCT_CACHE.update({"ts": 0.0, "data": None})
        bodies = {}
        for path in ("/api/products", "/api/leaderboard", "/api/vote-capabilities",
                     "/api/account", "/api/provinces", "/api/product?id=sakura_mcfloat"):
            st, b = get(path)
            bodies[path] = json.dumps(b, ensure_ascii=False)
        red = sv._redact(f"Bearer {secret} / GITHUB_TOKEN={gh_secret}")
    finally:
        revival.real_account_info = old_rai
        r2()
        r1()
        sv._ACCT_CACHE.update({"ts": 0.0, "data": None})
    leaked = [p for p, b in bodies.items() if secret in b or gh_secret in b]
    member_leaked = [p for p, b in bodies.items() if member_secret in b]
    ok = (not leaked and not member_leaked
          and secret not in red and gh_secret not in red
          and all("member_voted" not in b for b in bodies.values()))
    check("15. 公开浏览接口不泄露凭证", ok,
          f"检查 {len(bodies)} 个公开接口：Token 泄露={leaked or '无'}；"
          f"会员标识泄露={member_leaked or '无'}；账本 member_voted 不下发；错误信息已脱敏")
except Exception as e:  # noqa: BLE001
    check("15. 公开浏览接口不泄露凭证", False, f"检查失败: {e}")

# ========== 真实集成测试（默认跳过） ==========
print("\n🔌 真实集成测试")
if os.environ.get("MCMUSEUM_REAL_INTEGRATION", "").strip().lower() not in ("1", "true", "yes", "on"):
    skip("R1. 真实 MCP query-my-account",
         "默认跳过。运行时不打印会员标识；需你本机已配置 MCD_MCP_TOKEN（请勿把 Token 发给任何人）")
    skip("R2. 真实 GitHub 共享榜读取",
         "默认跳过。需 GITHUB_REPO（可无 GITHUB_TOKEN，只读公开 Issue）")
else:
    t0 = time.time()
    try:
        points, mid = revival.real_account_info()
        check("R1. 真实 MCP query-my-account", bool(mid),
              f"耗时 {time.time()-t0:.1f}s；解析到会员标识={bool(mid)}，积分={points}"
              f"（此处不打印会员标识本身）", kind="REAL")
    except Exception as e:  # noqa: BLE001
        check("R1. 真实 MCP query-my-account", False,
              f"真实调用失败（网络不可达或 Token 无效）：{str(e)[:80]}", kind="REAL")
    try:
        if not os.environ.get("GITHUB_REPO"):
            skip("R2. 真实 GitHub 共享榜读取", "缺少 GITHUB_REPO，跳过", kind="REAL")
        else:
            agg = rg.aggregate()
            check("R2. 真实 GitHub 共享榜读取", agg.get("_github_ok") is True,
                  f"_github_ok={agg.get('_github_ok')}；已绑定单品 {len(agg.get('totals', {}))} 款",
                  kind="REAL")
    except Exception as e:  # noqa: BLE001
        check("R2. 真实 GitHub 共享榜读取", False, f"读取失败: {str(e)[:80]}", kind="REAL")

print("-" * 62)
fails = [n for ok_, n in RESULTS if ok_ is False]
skips = [n for ok_, n in RESULTS if ok_ is None]
passed = [n for ok_, n in RESULTS if ok_ is True]
print(f"结论：✅通过 {len(passed)} 项 | ❌失败 {len(fails)} 项 | ⏭️跳过 {len(skips)} 项")
if fails:
    print("失败项：" + "；".join(fails))
_ran_real = any(n.startswith("R") and ok_ is not None for ok_, n in RESULTS)
print("说明：[MOCK] 全部离线可复现（临时账本 + mock 外部依赖，不写真实账本、不碰 GitHub）；")
if _ran_real:
    print("      [REAL] 本次已真实执行（访问了真实 MCP / GitHub，结果见上）。")
else:
    print("      [REAL] 本次默认跳过，未执行既不算通过也不算失败；"
          "需加 --real 才运行。")
sys.exit(1 if fails else 0)
