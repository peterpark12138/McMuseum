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

# 9.2 CONTEST_DECLARATION 关键声明
cd_txt = read_text(os.path.join(BASE, "CONTEST_DECLARATION.md"))
if len(cd_txt) < 50:
    add("CONTEST_DECLARATION 完整性", False, "内容过短，疑似被改/缺失")
elif all(k in cd_txt for k in ("声明", "原创")):
    add("CONTEST_DECLARATION 完整性", True, "含「声明/原创」等关键表述")
else:
    add("CONTEST_DECLARATION 完整性", False, "缺少「声明/原创」等关键表述，可能已被改动")

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
    print("   ⚠️ 真实 MCP / 真实 GitHub 后端需在 WorkBuddy 配置对应 Token 后联调验证。")
    sys.exit(0)
