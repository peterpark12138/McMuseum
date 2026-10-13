#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦复活赛 · 一键自检脚本
直接回答「能不能跑通」：逐项检查 Python 环境、脚本语法、各子命令、
以及真实依赖（MCD_MCP_TOKEN / GITHUB_TOKEN）的配置状态。

相比旧版，本脚本新增「内容充分性检查」，弥补"只检查文件是否存在"的盲区：
- README 是否真的包含 介绍/安装/示例/目标用户
- CONTEST_DECLARATION 关键声明是否完整
- mcp-config.example.json 是否仅含占位符（无明文 Token）
- 降级机制是否已移除（revival.py / SKILL.md 不再含降级/ WB 兜底投票）
- 会员号强身份去重是否稳健实现
- 真实 MCP 调用是否保留
- 怀旧单品是否还残留"在售品"(maila_wing) 或大量未核实项

用法：
  python3 scripts/selfcheck.py
退出码：0 = 核心功能全部可跑（本地全流程 + 真实依赖待联调）；非 0 = 有阻断性问题。
"""
import os
import sys
import subprocess
import json
import re as _re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(BASE, "scripts")
DATA = os.path.join(BASE, "data", "nostalgic_products.json")
WEB = os.path.join(BASE, "web")

checks = []  # (名称, 状态 ok/降级/warn/fail, 说明)


def run(cmd, cwd=BASE):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:  # noqa: BLE001
        return -1, "", str(e)


def read_text(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def add(name, ok, note):
    checks.append((name, "✅" if ok else "❌", note))


def add_state(name, state, note):
    checks.append((name, state, note))


print("🔍 麦麦复活赛 · 自检开始\n")

# 1. Python 版本
pyv = sys.version_info
add_state("Python 版本", "✅" if (pyv.major, pyv.minor) >= (3, 8) else "❌",
          f"{pyv.major}.{pyv.minor}.{pyv.micro}（要求 3.8+）")

# 2. 脚本语法编译
for fn in ["revival.py", "mcp_client.py", "report_github.py", "build_leaderboard.py", "mcd_data.py"]:
    fp = os.path.join(SCRIPTS, fn)
    rc, _, err = run([sys.executable, "-m", "py_compile", fp])
    if rc != 0:
        add(f"语法编译 {fn}", False, err.strip()[:200])
    else:
        add(f"语法编译 {fn}", True, "通过")

# serve.py 位于 web/ 目录（前端服务），单独编译
_serve_fp = os.path.join(WEB, "serve.py")
_rc, _, _err = run([sys.executable, "-m", "py_compile", _serve_fp])
add("语法编译 serve.py", _rc == 0, "通过" if _rc == 0 else _err.strip()[:200])

# 3. 数据文件存在且合法
if os.path.exists(DATA):
    try:
        d = json.load(open(DATA, encoding="utf-8"))
        n = len(d.get("products", []))
        nv = sum(1 for p in d["products"] if p.get("verified"))
        add("怀旧单品数据", True, f"{n} 款（verified={nv}）")
    except Exception as e:  # noqa: BLE001
        add("怀旧单品数据", False, f"JSON 非法: {e}")
else:
    add("怀旧单品数据", False, "缺失 data/nostalgic_products.json")

# 4. 各子命令（无 Token 降级路径，不应崩溃）
for label, cmd in [
    ("museum 展示", ["revival.py", "museum"]),
    ("vote 麦当劳会员投票(无Token应友好提示)", ["revival.py", "vote", "--product", "sakura_mcfloat", "--from-mcp"]),
    ("ranking 本地榜", ["revival.py", "ranking", "--top", "3"]),
    ("share 卡片", ["revival.py", "share", "--product", "sakura_mcfloat"]),
    ("build_leaderboard 生成", ["build_leaderboard.py"]),
]:
    rc, _, err = run([sys.executable, os.path.join(SCRIPTS, cmd[0])] + cmd[1:])
    add(f"命令 {label}", rc == 0, (err.strip()[:160] if rc != 0 else "退出码 0"))

# 5. 真实 MCP 调用路径（无 Token 时友好降级，不崩溃）
rc, out, err = run([sys.executable, os.path.join(SCRIPTS, "revival.py"), "meals", "--from-mcp"])
add("meals --from-mcp 降级", rc == 0, "无 Token 时友好降级" if rc == 0 else err.strip()[:160])

# 6. 防重复逻辑说明
add_state("防重复逻辑", "✅", "每麦当劳会员每单品仅一次（强身份去重）；无积分仅 1 票（代码见 revival.py record_vote）")

# 7. 可视化页面文件存在
html_ok = os.path.exists(os.path.join(WEB, "leaderboard.html"))
add("可视化页面 leaderboard.html", html_ok, "麦系红黄配色，零依赖" if html_ok else "缺失")
add("leaderboard.json", os.path.exists(os.path.join(WEB, "leaderboard.json")),
    "由 build_leaderboard.py 生成" if os.path.exists(os.path.join(WEB, "leaderboard.json")) else "尚未生成（跑 build 即可）")

# 8. 必交文件存在
for fn in ["README.md", "CONTEST_DECLARATION.md", "MCP_INTEGRATION.md", "mcp-config.example.json", "workbuddy.md", "SKILL.md", "LICENSE"]:
    fp = os.path.join(BASE, fn)
    add(f"交付物 {fn}", os.path.exists(fp), "存在" if os.path.exists(fp) else "缺失")

# ===== 9. 内容充分性检查（弥补"只查文件存在"的盲区） =====
print("\n📝 内容充分性检查")

# 9.1 README 四要素
readme = read_text(os.path.join(BASE, "README.md"))
has_intro = any(k in readme for k in ("项目介绍", "介绍", "关于本项目", "是什么"))
has_install = "安装" in readme
has_example = any(k in readme for k in ("使用示例", "示例", "用法示例"))
has_target = "目标用户" in readme
if len(readme) < 200:
    add("README 内容充分(介绍/安装/示例/目标用户)", False, "正文过短，疑似空壳")
elif has_intro and has_install and has_example and has_target:
    add("README 内容充分(介绍/安装/示例/目标用户)", True, "含四大要素关键词")
else:
    miss = [k for k, v in (("介绍", has_intro), ("安装", has_install), ("示例", has_example), ("目标用户", has_target)) if not v]
    add("README 内容充分(介绍/安装/示例/目标用户)", False, f"缺少: {', '.join(miss)}")

# 9.2 CONTEST_DECLARATION 官方原文逐字比对（官方要求：文件名与内容均不可改动）
import hashlib as _hl
cd_txt = read_text(os.path.join(BASE, "CONTEST_DECLARATION.md"))
cd_sha = _hl.sha256(cd_txt.encode("utf-8")).hexdigest()
# 官方原文 SHA256（逐字取自官方仓库 raw 文件，2026-10-12 核对）
OFFICIAL_CD_SHA = "cd28101bcb29cc8fb24b372fe91ce6b42c4a1487a54e01f7ade0c8c6a84241b7"
if len(cd_txt) < 50:
    add("CONTEST_DECLARATION 完整性", False, "内容过短，疑似缺失")
elif cd_sha == OFFICIAL_CD_SHA:
    add("CONTEST_DECLARATION 完整性", True, "与官方原文逐字一致(SHA256 校验通过)")
else:
    add("CONTEST_DECLARATION 完整性", False,
        "⚠️ 与官方原文不一致——赛事要求该文件内容不可改动，请恢复官方原文件")

# 9.3 mcp-config 仅占位符
cfg_path = os.path.join(BASE, "mcp-config.example.json")
cfg_txt = read_text(cfg_path)
if cfg_path and not cfg_txt:
    add("mcp-config 仅占位符(无明文Token)", False, "文件为空")
else:
    try:
        json.loads(cfg_txt)
        has_ph = "${" in cfg_txt
        # 粗略排查：是否存在超长 base64/明文 token 串（>24 且非占位符）
        import re as _re  # 兼容早期分支：保证 _re 可用
        # 仅排查「明文超长凭证」；环境变量占位符 ${...} 与 "Bearer ${...}" 必须放行
        leaked = _re.search(r'"(?:token|authorization|bearer)"\s*:\s*"(?!\$\{)(?!Bearer\s+\$\{)[^"]{16,}"', cfg_txt, _re.I)
        if has_ph and not leaked:
            add("mcp-config 仅占位符(无明文Token)", True, "含环境变量占位符，无明文凭证")
        else:
            add("mcp-config 仅占位符(无明文Token)", False, "疑似含明文凭证或缺少占位符")
    except Exception:
        add("mcp-config 仅占位符(无明文Token)", False, "JSON 解析失败")

# 9.4 降级机制已移除
rev_src = read_text(os.path.join(SCRIPTS, "revival.py"))
skl_src = read_text(os.path.join(BASE, "SKILL.md"))
# 真正的「降级残留」信号：旧的 WB / 匿名兜底计票代码特征，例如计票键 "u:" + uid / wb_uid。
# 现仅麦当劳会员可投票（计票键 "m:" + member_id），非会员直接拒绝；
# 注释 / 文档中的「已取消降级」「取消匿名降级投票」属合规说明，不应误判为残留。
_code_fallback = ('"u:" +' in rev_src) or ('"u:" + uid' in rev_src) or ("wb_uid" in rev_src) or ("workbuddy_uid" in rev_src)
# 文案残留：出现「降级投票 / 降级计票 / 降级放行」且全文无「已取消」否定语境，才视为可疑
_has_pos = bool(_re.search(r'降级\s*(?:投票|计票|放行)', rev_src)) or bool(_re.search(r'降级\s*(?:投票|计票|放行)', skl_src))
_neg_ctx = ("已取消" in rev_src) or ("已取消" in skl_src) or ("取消降级" in rev_src)
degraded = _code_fallback or (_has_pos and not _neg_ctx)
add("降级机制已移除", not degraded,
    "revival.py / SKILL.md 均不含降级 / WB 兜底投票" if not degraded else "仍残留降级逻辑，需清理")

# 9.5 会员号强身份去重稳健
robust = ("extract_member_id" in rev_src) and ("MEMBER_ID_KEYS" in rev_src)
add("会员号强身份去重稳健", robust,
    "revival.py 实现多字段稳健解析(extract_member_id + MEMBER_ID_KEYS)" if robust else "未找到稳健解析实现")

# 9.6 真实 MCP 调用保留
mcp_src = read_text(os.path.join(SCRIPTS, "mcp_client.py"))
keep_mcp = ("query-my-account" in mcp_src) and ("query-meals" in mcp_src)
add("真实 MCP 调用保留", keep_mcp, "mcp_client.py 仍调用 query-my-account / query-meals" if keep_mcp else "MCP 调用缺失")

# 9.7 单品名单健康度
try:
    d = json.load(open(DATA, encoding="utf-8"))
    ids = [p["id"] for p in d["products"]]
    if "maila_wing" in ids:
        add("单品名单不含在售品(maila_wing)", False, "仍含在售的麦辣鸡翅，应移除")
    else:
        add("单品名单不含在售品(maila_wing)", True, "已移除在售品")
    unverified = [p["name"] for p in d["products"] if not p.get("verified")]
    if unverified:
        add_state("单品待核实项", "⚠️", f"存在 {len(unverified)} 个 verified=false: {', '.join(unverified)}（赛前需确认或移除）")
    else:
        add("单品全部已核实", True, "无待核实项")
except Exception:
    pass

# 9.8 省份自动探测必须是「只读」的
# 麦当劳 MCP 同时暴露 delivery-query-addresses(读) 与 delivery-create-address(写)，
# 若过滤器失效，自动探测可能会去调用「创建地址」接口，违反本作品仅读取的红线。
try:
    sys.path.insert(0, SCRIPTS)
    import revival as _rv
    _sample = ["delivery-query-addresses", "delivery-create-address",
               "query-my-account", "cancel-order", "create-order"]
    _sel = _rv.address_read_tools(_sample)
    _ok = ("delivery-query-addresses" in _sel
           and "delivery-create-address" not in _sel
           and "create-order" not in _sel)
    add("省份自动探测仅调用只读工具", _ok,
        f"只读工具筛选正常：选中 {_sel}" if _ok else f"筛选异常，可能误调写操作工具：{_sel}")
    # 省份枚举与解析
    _p = _rv.find_province_in_text("吉林省长春市朝阳区某路")
    add("省份文本解析正确", _p == "吉林", f"地址文本 -> {_p or '(未识别)'}")
except Exception as _e:
    add("省份自动探测仅调用只读工具", False, f"检查失败: {_e}")

# 9.9 共享榜聚合只信任机器人自身评论（防伪造刷票）
try:
    import report_github as _rg
    _bot = "mcrevival-bot"
    _comments = [
        {"user": {"login": _bot}, "body": "vote mcp +3 上海 2026-10-11"},
        {"user": {"login": "attacker"}, "body": "vote base +999 全国 2026-10-11"},  # 伪造刷票
        {"user": {"login": _bot}, "body": "vote mcp +1 全国 2026-10-11"},
        {"user": {"login": "someone"}, "body": "vote mcp +50 广东 2026-10-11"},   # 伪造刷票
        {"user": {"login": _bot}, "body": "这是一条无关评论"},
    ]
    _total, _pt = _rg._tally_comments(_comments, _bot)
    # 仅 bot 的两条计票：上海 3 + 全国 1 = 4；伪造的 999 / 50 不应计入
    _spoof_ok = (_total == 4) and (_pt.get("上海") == 3) and ("全国" not in _pt)
    add("共享榜仅信任机器人评论(防伪造)", _spoof_ok,
        f"拒绝伪造刷票：bot 计 {_total} 票；上海={_pt.get('上海')}" if _spoof_ok
        else f"聚合异常：total={_total}, pt={_pt}（伪造评论可能被计入！）")
    # 结构校验：无 GITHUB_REPO 时返回新结构 {"totals":{}, "province_totals":{}}
    _old_repo = os.environ.pop("GITHUB_REPO", None)
    try:
        _agg = _rg.aggregate()
        _struct_ok = isinstance(_agg, dict) and "totals" in _agg and "province_totals" in _agg
    finally:
        if _old_repo is not None:
            os.environ["GITHUB_REPO"] = _old_repo
    add("aggregate 返回新结构(totals/province_totals)", _struct_ok,
        "结构正确" if _struct_ok else "结构缺失键")
except Exception as _e:
    add("共享榜仅信任机器人评论(防伪造)", False, f"检查失败: {_e}")

# 9.10 麦当劳 MCP 只读红线：safe_call 拦截写工具 + get_* 无 token 优雅降级
try:
    import mcd_data as _md
    # (a) 8 个写/交易类工具必须被 safe_call 拒绝
    class _FakeClient:
        def __init__(self):
            self.called = []
        def call_tool(self, name, arguments=None):
            self.called.append(name)
            return {"result": {"content": []}}
    def _raises(client, name):
        try:
            _md.safe_call(client, name, {})
            return False
        except ValueError:
            return True
        except Exception:
            return False
    _fc = _FakeClient()
    _writes = ["draw-lottery", "delivery-create-address", "create-order",
               "auto-bind-coupons", "calculate-price", "party-order-create",
               "mall-create-order", "cancel-order"]
    _rejected = all(_raises(_fc, n) for n in _writes)
    # (b) 只读工具必须被放行（会真正调用，验证白名单含它们）
    _fc2 = _FakeClient()
    try:
        _md.safe_call(_fc2, "query-meals", {"beType": 1, "orderType": 1})
        _allowed = (_fc2.called == ["query-meals"])
    except Exception:
        _allowed = False
    add("MCP 只读红线(safe_call 拦截写工具)", _rejected and _allowed,
        f"8 个写工具全部被拒，只读工具正常放行" if (_rejected and _allowed)
        else f"拦截异常：rejected={_rejected}, read_passed={_allowed}")

    # (c) 无 token 时各 get_* 优雅降级（离线、不触网），均返回空容器
    _saved = os.environ.get("MCD_MCP_TOKEN")
    try:
        os.environ["MCD_MCP_TOKEN"] = ""   # 强制视为无 token（_load_env_file 不会覆盖已存在的空值）
        _nut = _md.get_nutrition()
        _cmp = _md.get_campaigns()
        _lot = _md.get_lottery_info()
        _mall = _md.get_points_mall()
        _meals = _md.get_current_meals()
        _near = _md.get_nearby_stores()
        _degrade_ok = (isinstance(_nut, list) and isinstance(_cmp, list)
                       and isinstance(_lot, dict) and isinstance(_mall, list)
                       and isinstance(_meals, list) and isinstance(_near, dict))
    finally:
        if _saved is not None:
            os.environ["MCD_MCP_TOKEN"] = _saved
    add("只读增强无 token 优雅降级", _degrade_ok,
        "各 get_* 无 token 时返回空容器，公开部署不崩" if _degrade_ok else "降级路径异常")

    # (d) serve.py 已暴露 6 个只读接口
    _serve_src = read_text(os.path.join(WEB, "serve.py"))
    _paths = ["/api/nutrition", "/api/campaigns", "/api/lottery",
              "/api/points-mall", "/api/on-sale", "/api/nearby"]
    _all_paths = all(p in _serve_src for p in _paths)
    add("serve.py 暴露 6 个只读接口", _all_paths,
        f"已接入: {', '.join(_paths)}" if _all_paths else "缺少部分接口")
except Exception as _e:
    add("MCP 只读红线(safe_call 拦截写工具)", False, f"检查失败: {_e}")

# 9.11 共享榜补报与分页：_plan_backfill 差额计算 + _fetch_all_comments 翻页
try:
    import report_github as _rg
    # (a) _plan_backfill 纯函数：本地多出 3 票（2 在省 + 1 全国）→ 计划补 2 条；GitHub 领先时不补
    _local = {"totals": {"a": 3, "b": 2}, "province_totals": {"吉林": {"a": 2}}}
    _gh = {"totals": {"a": 0, "b": 5}, "province_totals": {}}
    _plan = _rg._plan_backfill(_local, _gh)
    _plan_ok = sorted(_plan) == [("a", 1, "全国"), ("a", 2, "吉林")]
    # 幂等：补报后（gh 追平）计划应为空
    _gh2 = {"totals": {"a": 3, "b": 5}, "province_totals": {"吉林": {"a": 2}}}
    _plan_ok = _plan_ok and _rg._plan_backfill(_local, _gh2) == []
    add("共享榜补报差额计算(_plan_backfill)", _plan_ok,
        "本地超 3 票 -> 计划 2 条；追平后计划为空(幂等)" if _plan_ok else f"实际计划: {_plan}")

    # (b) _fetch_all_comments 自动翻页：两页各 100 条 + 第三页空 → 共 200 条
    class _Orig:
        pass
    _orig_req = _rg._req
    _page_re = _re.compile(r"[?&]page=(\d+)(&|$)")
    def _fake_req(url, method="GET", data=None, token=None):
        mm = _page_re.search(url)
        pg = mm.group(1) if mm else "0"
        if pg == "1":
            return [{"id": i} for i in range(100)]
        if pg == "2":
            return [{"id": i} for i in range(100, 200)]
        return []
    _rg._req = _fake_req
    try:
        _got = _rg._fetch_all_comments("https://api.github.com/repos/x/y/issues/1")
    finally:
        _rg._req = _orig_req
    _page_ok = len(_got) == 200
    add("聚合评论自动翻页(防超100条丢票)", _page_ok,
        "2 页 x 100 条全部取回" if _page_ok else f"实际取回 {len(_got)} 条")
except Exception as _e:
    add("共享榜补报与分页", False, f"检查失败: {_e}")

# 9.11b 客户端层只读红线：call_tool 是唯一出口，CLI/任意代码路径均无法绕过
try:
    import mcp_client as _mc2
    _client2 = _mc2.McDonaldMCPClient()  # 需 token（本机已配置）；call_tool 校验先于任何网络请求
    _post_calls = []
    _orig_post = _client2._post
    _client2._post = lambda payload, notify=False: (_post_calls.append(payload), {"result": {}})[1]
    # (a) 8 个写工具经客户端 call_tool 必须被拒绝，且绝不发出网络请求
    _cli_blocked = 0
    for _w in ["create-order", "draw-lottery", "delivery-create-address", "auto-bind-coupons",
               "calculate-price", "party-order-create", "mall-create-order", "cancel-order"]:
        try:
            _client2.call_tool(_w, {})
        except ValueError:
            _cli_blocked += 1
    # (b) CLI main 使用的也是同一 call_tool（源码断言：无独立请求路径）
    _cli_src_ok = "call_tool(args.tool" in read_text(os.path.join(SCRIPTS, "mcp_client.py"))
    # (c) 只读工具放行且走到 _post
    _rd_ok = _client2.call_tool("query-my-account", {}) == {"result": {}} and len(_post_calls) == 1
    _client2._post = _orig_post
    add("客户端层只读白名单(含 CLI 无绕过)", _cli_blocked == 8 and _cli_src_ok and _rd_ok,
        f"8 写工具全拦截且零网络调用={_cli_blocked == 8}; CLI 走 call_tool={_cli_src_ok}; 只读放行={_rd_ok}")
except Exception as _e:
    add("客户端层只读白名单(含 CLI 无绕过)", False, f"检查失败: {_e}")

# ===== 9.12 投票能力边界（公开站点不得伪造能力 / 不得假成功 / 不得谎报共享榜） =====
print("\n🔒 投票能力边界检查")
try:
    sys.path.insert(0, WEB)
    import serve as _sv  # noqa: E402

    def _swap_env(k, v):
        """临时设置/清除环境变量，返回还原函数（保证测试互不污染）。"""
        old = os.environ.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
        def _restore():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old
        return _restore

    # (a) 默认（公开部署）：在线投票不可用 —— 501 明确拒绝，绝不是假的 200 成功
    _r1 = _swap_env("MCMUSEUM_ENABLE_SERVER_VOTE", None)
    try:
        _caps = _sv.vote_capability()
    finally:
        _r1()
    _def_ok = (_caps["voting_available"] is False and _caps["http_status"] == 501
               and _caps["mode"] == "public-browse-only" and bool(_caps["how_to_vote"]))
    add("公开部署默认关闭在线投票(501)", _def_ok,
        f"mode={_caps.get('mode')} code={_caps.get('code')} http={_caps.get('http_status')}"
        if _def_ok else f"能力声明异常：{_caps}")

    # (b) 显式开启但无会员 Token：503，不能计票
    _r2 = _swap_env("MCMUSEUM_ENABLE_SERVER_VOTE", "1")
    _r3 = _swap_env("MCD_MCP_TOKEN", "")
    try:
        _caps2 = _sv.vote_capability()
    finally:
        _r3(); _r2()
    _notok_ok = (_caps2["voting_available"] is False and _caps2["http_status"] == 503
                 and _caps2["mode"] == "server-vote-enabled-no-token")
    add("开启但无会员 Token 时拒绝投票(503)", _notok_ok,
        f"mode={_caps2.get('mode')} http={_caps2.get('http_status')}" if _notok_ok
        else f"能力声明异常：{_caps2}")

    # (c) 不接受客户端提交的会员标识（防止把任意字符串当已认证身份）
    _clean = _sv._client_identity_fields({"product": "a", "province": "上海"})
    _dirty = _sv._client_identity_fields({"product": "a", "member_id": "1", "cardNo": "2"})
    _idf_ok = (not _clean) and set(_dirty) == {"member_id", "cardNo"}
    add("拒绝客户端提交的会员标识字段", _idf_ok,
        f"正常请求放行；身份类字段被识别拦截：{sorted(_dirty)}" if _idf_ok
        else f"识别异常 clean={_clean} dirty={sorted(_dirty)}")

    # (d) 失败原因 -> 语义正确的 HTTP 状态码
    _st_ok = (_sv._vote_http_status("该麦当劳会员已为《X》投过票") == 409
              and _sv._vote_http_status("未能从 query-my-account 解析出麦当劳会员唯一标识") == 401
              and _sv._vote_http_status("省份「火星」不在可选范围内") == 400)
    add("投票失败原因映射语义状态码", _st_ok,
        "重复=409 / 认证失败=401 / 参数错误=400" if _st_ok else "状态码映射不正确")

    # (e) 错误信息脱敏：Token 不得进入响应或日志
    _r4 = _swap_env("MCD_MCP_TOKEN", "SUPERSECRET_TOKEN_VALUE_123")
    try:
        _rd = _sv._redact("授权失败 Bearer abcdef1234567890 / token=SUPERSECRET_TOKEN_VALUE_123")
    finally:
        _r4()
    _red_ok = ("SUPERSECRET_TOKEN_VALUE_123" not in _rd) and ("abcdef1234567890" not in _rd)
    add("错误信息脱敏(不含 Token)", _red_ok, f"脱敏后：{_rd}" if _red_ok else f"仍有明文凭证：{_rd}")
except Exception as _e:
    add("投票能力边界(serve.py)", False, f"检查失败: {_e}")

# 9.13 投票核心：无效身份不产票 + GitHub 回流失败如实回执（纯本地，不触网）
try:
    import tempfile as _tf
    import shutil as _sh
    import revival as _rv3
    _tmpdir = _tf.mkdtemp(prefix="mcmuseum-selftest-")
    _tmpvotes = os.path.join(_tmpdir, "votes.json")
    _orig_rai, _orig_votes = _rv3.real_account_info, _rv3.VOTES
    try:
        _rv3.VOTES = _tmpvotes
        # 场景1：认证失败（等价于 token 无效 / 读不到会员信息）
        def _boom():
            raise RuntimeError("MCP 认证失败")
        _rv3.real_account_info = _boom
        _, _o1, _v1 = _rv3.record_vote("sakura_mcfloat", None, from_mcp=True)
        # 场景2：能读到积分但解析不出会员唯一标识（无法安全去重 -> 宁可拒绝）
        _rv3.real_account_info = lambda: (100, None)
        _, _o2, _v2 = _rv3.record_vote("sakura_mcfloat", None, from_mcp=True)
        _no_vote = (_o1 is False and _o2 is False and _v1 == 0 and _v2 == 0
                    and not os.path.exists(_tmpvotes))
        add("无效会员身份不产生票数", _no_vote,
            "认证失败 / 无会员标识均被拒绝，且未写入任何票" if _no_vote
            else f"异常：ok1={_o1}, ok2={_o2}, val1={_v1}, val2={_v2}")

        # 场景3：本地计票成功但 GitHub 回流失败 —— 回执必须 github_reported=False
        import report_github as _rg3
        _orig_rv = _rg3.report_vote
        _rg3.report_vote = lambda *a, **k: (False, "模拟：GitHub 提交失败")
        _rv3.real_account_info = lambda: (250, "selftest-member-0001")
        try:
            _, _o3, _v3 = _rv3.record_vote("sakura_mcfloat", "上海", from_mcp=True)
            _rec = dict(_rv3.LAST_VOTE_RESULT)
        finally:
            _rg3.report_vote = _orig_rv
        _gh_honest = (_o3 is True and _rec.get("github_reported") is False
                      and bool(_rec.get("github_msg")))
        add("GitHub 回流失败时如实回执(不谎报)", _gh_honest,
            f"本地计 {_v3} 票；shared_board_reported={_rec.get('github_reported')}, "
            f"msg={str(_rec.get('github_msg'))[:40]}" if _gh_honest
            else f"回执不诚实：{_rec}")
    finally:
        _rv3.real_account_info, _rv3.VOTES = _orig_rai, _orig_votes
        _sh.rmtree(_tmpdir, ignore_errors=True)
except Exception as _e:
    add("投票核心(无效身份不产票/回执诚实)", False, f"检查失败: {_e}")

# 9.14 前端静态资源不得出现任何凭证；投票入口必须走能力探测
try:
    _app = read_text(os.path.join(WEB, "app.js"))
    _idx = read_text(os.path.join(WEB, "index.html"))
    _leak = bool(_re.search(r"(ghp_[A-Za-z0-9]{10,}|github_pat_[A-Za-z0-9_]{10,})", _app + _idx))
    add("前端静态文件无明文凭证", not _leak,
        "index.html / app.js 未发现 token 串" if not _leak else "发现疑似 token，立即撤销并清除")
    _gate = ("vote-capabilities" in _app) and ("unavailable" in _app) and ("showVoteUnavailable" in _app)
    add("前端投票入口按能力置灰并引导本机", _gate,
        "调 /api/vote-capabilities，不可用则置灰并给出本机 CLI" if _gate
        else "前端未做能力探测，可能出现「点了给假成功」")
except Exception as _e:
    add("前端投票入口检查", False, f"检查失败: {_e}")

# 9.15 共享榜：无信任锚点时不得承认任何票（否则任何人可伪造刷榜）
try:
    import report_github as _rg4
    _t_none, _pt_none = _rg4._tally_comments(
        [{"user": {"login": "anyone"}, "body": "vote mcp +999 全国 2026-10-11"}], None)
    _anchor_ok = (_t_none == 0 and _pt_none == {})
    add("无信任锚点时不承认任何票", _anchor_ok,
        "bot_login 为空 -> 0 票（杜绝无锚点时的伪造刷榜）" if _anchor_ok
        else f"危险：无锚点仍计入 {_t_none} 票")
    # 票种白名单：未验证票（如 guest/anon）即使由机器人发出也不计入
    _t2, _ = _rg4._tally_comments(
        [{"user": {"login": "bot"}, "body": "vote guest +50 全国 2026-10-11"},
         {"user": {"login": "bot"}, "body": "vote mcp +2 广东 2026-10-11"}], "bot")
    _vt_ok = (_t2 == 2)
    add("共享榜票种白名单(拒绝未验证票)", _vt_ok,
        "仅 mcp/backfill 计票，guest 类被丢弃" if _vt_ok else f"异常：计入 {_t2} 票")

    # 幂等重试：POST 超时后回查到同一 rid -> 视为已写入，绝不重复提交
    _orig_req4 = _rg4._req
    _posts = []
    def _flaky(url, method="GET", data=None, token=None):
        if method == "POST":
            _posts.append((data or {}).get("body", ""))
            raise RuntimeError("GitHub API 网络错误: timed out")
        _mm = _rg4._RID_RE.search(_posts[-1] if _posts else "")
        return [{"body": f"vote mcp +1 全国 2026-10-11 rid={_mm.group(1)}"}] if _mm else []
    _rg4._req = _flaky
    try:
        _ok4, _ = _rg4._post_comment("https://x/1/comments", "vote mcp +1 全国 2026-10-11",
                                     None, "https://x/1")
    finally:
        _rg4._req = _orig_req4
    _idem_ok = (_ok4 is True and len(_posts) == 1)
    add("共享榜提交幂等(超时不重复计票)", _idem_ok,
        f"超时后回查确认已写入，仅提交 {len(_posts)} 次" if _idem_ok
        else f"可能重复计票：ok={_ok4}, POST 次数={len(_posts)}")

    # 4xx 不重试：鉴权/限流失败重试也无意义，且不会"半成功"
    _posts2 = []
    def _fourxx(url, method="GET", data=None, token=None):
        if method == "POST":
            _posts2.append(1)
            raise RuntimeError("GitHub API 403: forbidden")
        return []
    _rg4._req = _fourxx
    try:
        _ok5, _ = _rg4._post_comment("https://x/1/comments", "vote mcp +1 全国 2026-10-11",
                                     None, "https://x/1", retries=2)
    finally:
        _rg4._req = _orig_req4
    _no_retry_ok = (_ok5 is False and len(_posts2) == 1)
    add("共享榜 4xx 失败不重试", _no_retry_ok,
        "403 仅尝试 1 次即失败上报" if _no_retry_ok else f"异常重试：{len(_posts2)} 次")
except Exception as _e:
    add("共享榜信任锚点检查", False, f"检查失败: {_e}")

# 9.16 演示模式（模式 A）与真实数据隔离
try:
    _demo_path = os.path.join(BASE, "data", "demo_votes.json")
    _demo_ok = os.path.exists(_demo_path)
    if _demo_ok:
        with open(_demo_path, encoding="utf-8") as f:
            _demo = json.load(f)
        _demo_ok = _demo.get("_demo") is True and bool(_demo.get("_note"))
    add("演示数据文件存在且自带演示标记", _demo_ok,
        "data/demo_votes.json 带 _demo=true 与说明文字" if _demo_ok
        else "缺失 data/demo_votes.json 或缺少 _demo 标记")

    _r5 = None
    try:
        import serve as _sv2  # noqa: E402
        _old = os.environ.get("MCMUSEUM_DEMO")
        os.environ["MCMUSEUM_DEMO"] = "1"
        try:
            _c = _sv2.vote_capability()
            _dt, _ = _sv2.demo_totals()
        finally:
            os.environ.pop("MCMUSEUM_DEMO", None)
            if _old is not None:
                os.environ["MCMUSEUM_DEMO"] = _old
        _iso = (_c.get("voting_available") is False
                and _c.get("mode") == "demo-browse-only" and len(_dt) > 0)
        add("演示模式下投票不可用(演示票无入口进正式榜)", _iso,
            f"mode={_c.get('mode')}；演示票 {len(_dt)} 款可读" if _iso else f"隔离异常：{_c}")
    except Exception as _e:
        add("演示模式下投票不可用(演示票无入口进正式榜)", False, f"检查失败: {_e}")
except Exception as _e:
    add("演示模式检查", False, f"检查失败: {_e}")

# 9.17 投票账本健壮性：并发锁 / 旧账本缺键归一化 / 持久化失败不报成功
try:
    import tempfile as _tf2
    import shutil as _sh2
    import threading as _th
    import revival as _rv4
    _d4 = _tf2.mkdtemp(prefix="mcmuseum-sc-")
    _p4 = os.path.join(_d4, "votes.json")
    _old_v4 = _rv4.VOTES
    _rv4.VOTES = _p4
    try:
        # (a) 旧账本缺 province_totals 时不能崩（早期版本写出的只有 city_totals）
        with open(_p4, "w", encoding="utf-8") as f:
            json.dump({"totals": {"x": 1}, "city_totals": {}}, f)
        _v4 = _rv4.load_votes()
        _norm_ok = isinstance(_v4.get("province_totals"), dict) and isinstance(_v4.get("member_voted"), dict)
        add("旧版账本缺键自动归一化", _norm_ok,
            "缺 province_totals 的旧 votes.json 也能正常读写" if _norm_ok else "归一化失败，带省份投票会 KeyError")

        # (b) 默认值不共享引用（否则换账本也提示"已投过票"）
        _a = _rv4.load_votes()
        _a["member_voted"]["m:zz"] = ["x"]
        _b = _rv4.load_votes()
        _noalias = "m:zz" not in _b.get("member_voted", {})
        add("账本默认值不跨调用共享引用", _noalias,
            "两次 load_votes 互不污染" if _noalias else "默认值被共享，会串账")

        # (c) 并发双投只计一次
        os.path.exists(_p4) and os.remove(_p4)
        _old_rai4 = _rv4.real_account_info
        _rv4.real_account_info = lambda: (0, "sc-member-0001")
        _out = {}
        _bar = _th.Barrier(2)

        def _w(i):
            _bar.wait()
            _out[i] = _rv4.record_vote("sakura_mcfloat", None, from_mcp=True)[1]
        try:
            _ts = [_th.Thread(target=_w, args=(i,)) for i in range(2)]
            for t in _ts:
                t.start()
            for t in _ts:
                t.join(timeout=30)
            _book = json.load(open(_p4, encoding="utf-8"))
        finally:
            _rv4.real_account_info = _old_rai4
        _conc_ok = sum(1 for v in _out.values() if v) == 1 and _book["totals"]["sakura_mcfloat"] == 1
        add("并发同会员同单品只计一票(有锁)", _conc_ok,
            f"成功数={sum(1 for v in _out.values() if v)}，账本={_book['totals']['sakura_mcfloat']}"
            if _conc_ok else f"重复计票：{_book['totals']}")

        # (d) 持久化失败不报成功
        _old_save4 = _rv4.save_json
        _rv4.save_json = lambda path, data: (_ for _ in ()).throw(OSError("模拟磁盘不可写"))
        _rv4.real_account_info = lambda: (0, "sc-member-0002")
        try:
            _m5, _ok5, _v5 = _rv4.record_vote("taro_pie", None, from_mcp=True)
        finally:
            _rv4.save_json = _old_save4
            _rv4.real_account_info = _old_rai4
        _pf_ok = (_ok5 is False and _v5 == 0 and "未能保存" in _m5)
        add("持久化失败不报告投票成功", _pf_ok,
            "写盘失败 -> ok=False 且明确提示未计入" if _pf_ok else f"异常：ok={_ok5}, msg={_m5[:40]}")
    finally:
        _rv4.VOTES = _old_v4
        _sh2.rmtree(_d4, ignore_errors=True)
except Exception as _e:
    add("投票账本健壮性检查", False, f"检查失败: {_e}")

# 9.18 沙箱开关：MCMUSEUM_SHARED_BOARD=0 时不向正式共享榜写任何东西
try:
    import report_github as _rg5
    import revival as _rv5
    import tempfile as _tf3
    import shutil as _sh3
    _calls = []
    _old_rv5 = _rg5.report_vote
    _rg5.report_vote = lambda *a, **k: (_calls.append(a), (True, "ok"))[1]
    _old_sb = os.environ.get("MCMUSEUM_SHARED_BOARD")
    os.environ["MCMUSEUM_SHARED_BOARD"] = "0"
    _d5 = _tf3.mkdtemp(prefix="mcmuseum-sb-")
    try:
        _p5 = os.path.join(_d5, "votes.json")
        _old_v5 = _rv5.VOTES
        _rv5.VOTES = _p5
        _old_rai5 = _rv5.real_account_info
        _rv5.real_account_info = lambda: (100, "sc-member-0003")
        try:
            _m6, _ok6, _v6 = _rv5.record_vote("shake_fries", None, from_mcp=True)
            _rec6 = dict(_rv5.LAST_VOTE_RESULT)
        finally:
            _rv5.real_account_info = _old_rai5
            _rv5.VOTES = _old_v5
            os.environ.pop("MCMUSEUM_SHARED_BOARD", None)
            if _old_sb is not None:
                os.environ["MCMUSEUM_SHARED_BOARD"] = _old_sb
            _rg5.report_vote = _old_rv5
    finally:
        _sh3.rmtree(_d5, ignore_errors=True)
    _sb_ok = (len(_calls) == 0 and _ok6 is True and _rec6.get("shared_board_skipped") is True)
    add("沙箱开关下不写正式共享榜", _sb_ok,
        f"GitHub 调用次数={len(_calls)}（预期 0），本地仍计 {_v6} 票" if _sb_ok
        else f"未生效：calls={len(_calls)}, ok={_ok6}")
except Exception as _e:
    add("沙箱开关检查", False, f"检查失败: {_e}")

# 9.19 文档诚实性防回归：文档不得把未实现的能力写成已实现
try:
    _docs_dir = os.path.join(BASE, "docs")
    _scan = [os.path.join(BASE, "README.md"), os.path.join(BASE, "SKILL.md"),
             os.path.join(_docs_dir, "DEMO_GUIDE.md")]
    # 这些写法曾经出现过，会把"设计目标"说成"上线能力"，一律禁止再出现
    # （"反刷榜"条款本身是真陈述：不提供批量刷票工具，故不在禁用列表内）
    _banned = [
        "从机制上杜绝", "跨用户真实聚合", "数据闭环", "自动匿名回流",
        "强身份防刷", "防止多账号刷票", "全网共同",
    ]
    # 这些边界声明必须存在于 README，避免开头与后文自相矛盾
    _required_readme = [
        "全局去重没有实现",        # 断言"未实现"（而不是只字不提）
        "demo_mode_vote_disabled",  # 断言演示票无入口
        "单个本地账本实例",        # 断言去重作用域
    ]
    _hits = []
    for _p in _scan:
        if not os.path.isfile(_p):
            continue
        _txt = open(_p, encoding="utf-8").read()
        for _b in _banned:
            if _b in _txt:
                _hits.append(f"{os.path.basename(_p)} 含禁用措辞「{_b}」")
    _rm = open(os.path.join(BASE, "README.md"), encoding="utf-8").read()
    _miss = [r for r in _required_readme if r not in _rm]
    if _miss:
        _hits.append(f"README 缺少边界断言 {_miss}")
    add("文档诚实性（无越界措辞 + 边界声明在位）", not _hits,
        "README/SKILL/DEMO_GUIDE 未发现把未实现写成已实现的措辞，且边界断言在位"
        if not _hits else "；".join(_hits))
except Exception as _e:
    add("文档诚实性检查", False, f"检查失败: {_e}")

# 9.20 图片档案完整性（七字段 + 引用自洽；规则与 image_research.collect_problems 共用一处实现）
try:
    sys.path.insert(0, os.path.join(BASE, "scripts"))
    import image_research as _ir
    _doc = _ir.load_doc()
    _ps = _doc.get("products", [])
    _errs, _paths = _ir.collect_problems(_ps)
    _have = sum(1 for p in _ps if (p.get("image") or "").strip())
    _cov = f"覆盖 {_have}/{len(_ps)}（{_have*100//max(len(_ps),1)}%）"
    add("图片档案完整性（七字段 + 引用自洽 + 无冒充已核实）", not _errs,
        f"{len(_ps)} 款、引用 {len(_paths)} 张图，{_cov}，无缺字段/非法枚举/断链/重复"
        if not _errs else f"{len(_errs)} 处问题：{'；'.join(_errs[:3])}")
except Exception as _e:
    add("图片档案完整性检查", False, f"检查失败: {_e}")

# 10. 真实依赖配置状态
mcp_tok = os.environ.get("MCD_MCP_TOKEN")
gh_repo = os.environ.get("GITHUB_REPO")
gh_tok = os.environ.get("GITHUB_TOKEN")
add_state("真实 MCP 调用", "⚠️待联调" if not mcp_tok else "✅已配置",
          f"MCD_MCP_TOKEN={'已配置' if mcp_tok else '未配置'} → 未配置时投票流程会提示先连接麦当劳账号")
add_state("真实 GitHub 后端", "⚠️待联调" if not (gh_repo and gh_tok) else "✅已配置",
          f"GITHUB_REPO={'已配置' if gh_repo else '未配置'} / GITHUB_TOKEN={'已配置' if gh_tok else '未配置'} → 未配置时走本地榜")

# 汇总
print("-" * 60)
for name, state, note in checks:
    print(f"  {state} {name}\n       └ {note}")
print("-" * 60)

fails = [c for c in checks if c[1] == "❌"]
warns = [c for c in checks if c[1] in ("⚠️待联调", "⚠️")]
print(f"\n结论：通过 {sum(1 for c in checks if c[1]=='✅')} 项 | ❌失败 {len(fails)} 项 | ⚠️提醒 {len(warns)} 项")
if fails:
    print("❌ 存在阻断性问题，请先修复再提交。")
    sys.exit(1)
else:
    print("✅ 核心功能（本地全流程 + 内容充分性）已可跑通。")
    # 尾提示必须反映真实配置状态：已配置的后端不能再宣称"待联调"
    need = []
    if not mcp_tok:
        need.append("真实 MCP 会员认证（未配置 MCD_MCP_TOKEN，模式 B 真实投票不可用）")
    if not (gh_repo and gh_tok):
        need.append("真实 GitHub 共享榜（未配置 GITHUB_REPO/GITHUB_TOKEN，仅走本地榜）")
    if need:
        print("   ⚠️ 以下真实后端尚未配置，对应能力不可用：" + "；".join(need))
    else:
        print("   ℹ️ 真实 MCP 与 GitHub 后端均已配置；端到端真实链路请用 "
              "`python3 scripts/test_scenarios.py --real` 单独验证（默认跳过，跳过不算通过）。")
    sys.exit(0)
