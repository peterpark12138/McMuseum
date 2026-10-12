#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦复活赛 · 后台真实统计（GitHub Issue 作为零服务器后端）

设计要点：
- 每个怀旧单品对应一个 GitHub Issue；每条「有效投票」由机器人**匿名**评论一条记录
  （仅含票种/增量/省份/日期/幂等 rid，不含任何用户身份）。
- 真实全民榜 = 聚合所有单品 Issue 的匿名投票评论。
- 投票资格与「强身份去重」由 revival.py 在本地完成：仅麦当劳会员账号可投票，以会员唯一标识（会员号 / openid / 卡号等）为去重主键，每会员每单品仅一次。
- 本后端只负责把「已通过麦当劳会员校验的一票」匿名归档，做到「真实跨用户统计 + 防刷 + 零门槛（无需 GitHub 账号）」三者兼得。

环境变量：
- GITHUB_REPO : owner/repo（本参赛仓库，必须 Public，符合赛事要求）
- GITHUB_TOKEN: 机器人/作者 token（仅用于写 Issue 评论与读聚合，不对外）

数据文件：
- data/issue_map.json : { 单品id: issue_number }（由 setup 生成，可提交，不含敏感信息）
"""
import os
import re
import json
import time
import uuid
import datetime
import argparse
import urllib.request
import urllib.error

try:
    from mcp_client import _load_env_file
except Exception:  # noqa: BLE001
    def _load_env_file():
        pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCTS = os.path.join(BASE, "data", "nostalgic_products.json")
ISSUE_MAP = os.path.join(BASE, "data", "issue_map.json")
API = "https://api.github.com"

# 合法票种白名单：只认「已通过麦当劳会员校验」的票(mcp) 与 幂等补报(backfill)。
# 任何其他票种（如未来的 guest/anon/未验证票）一律不计入共享榜，防止未验证票混入。
VOTE_TYPES = ("mcp", "backfill")
MAX_DELTA = 1000          # 单条评论的票数上限，防异常数据污染榜单
_RID_RE = re.compile(r"\brid=([0-9a-f]{8,32})\b")


def _req(url, method="GET", data=None, token=None):
    """极简 GitHub API 请求（无第三方依赖）。"""
    token = token or os.environ.get("GITHUB_TOKEN")
    req = urllib.request.Request(url)
    req.method = method
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "mcrevival-bot")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    body = None
    if data is not None:
        req.add_header("Content-Type", "application/json")
        body = json.dumps(data).encode("utf-8")
    try:
        with urllib.request.urlopen(req, data=body, timeout=15) as r:
            txt = r.read().decode("utf-8")
            return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GitHub API {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"GitHub API 网络错误: {e}")


def _load_products():
    with open(PRODUCTS, encoding="utf-8") as f:
        return json.load(f)["products"]


def _load_map():
    if os.path.exists(ISSUE_MAP):
        with open(ISSUE_MAP, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_map(m):
    with open(ISSUE_MAP, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)


def _has_rid(comments_url_base, rid, token=None):
    """回查某条 rid 的评论是否已存在（POST 成功但响应丢失时的防重复提交）。"""
    try:
        cs = _fetch_all_comments(comments_url_base, token, max_pages=10)
    except RuntimeError:
        return False      # 读不到就不敢断言"已提交"，交给调用方保守重试
    for c in cs:
        mm = _RID_RE.search(c.get("body") or "")
        if mm and mm.group(1) == rid:
            return True
    return False


def _post_comment(url, body, token, verify_url_base, retries=1):
    """幂等地提交一条评论。返回 (ok, msg)。

    GitHub 评论接口没有幂等键，网络超时会造成「其实写成功了但以为失败」，
    直接重试就会重复计票。这里的做法：正文带唯一 rid；失败后先回查该 rid
    是否已在评论里，已存在即视为成功（绝不重复写），否则退避重试。
    4xx（鉴权/限流/参数错误）不重试——重试也不会成功，且不会"半成功"。
    """
    rid = uuid.uuid4().hex[:12]
    full = f"{body} rid={rid}"
    last = ""
    for attempt in range(retries + 1):
        try:
            _req(url, "POST", {"body": full}, token)
            return True, "已匿名记录"
        except RuntimeError as e:
            last = str(e)
            if re.search(r"GitHub API 4\d\d", last):
                return False, last          # 4xx：不重试
            if _has_rid(verify_url_base, rid, token):
                return True, "已匿名记录（首次提交响应丢失，回查确认已写入）"
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    return False, last or "提交失败（原因未知）"


def report_vote(product_id, vtype, value, province=None):
    """匿名上报一条有效投票到该单品对应的 GitHub Issue。返回 (ok, msg)。

    只上报「已在本地通过麦当劳会员身份校验」的票；票种必须是 VOTE_TYPES 之一，
    否则即便写进去聚合时也会被丢弃（双保险，防止未验证票混入共享榜）。
    """
    repo = os.environ.get("GITHUB_REPO")
    token = os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        return False, "未配置 GITHUB_REPO/GITHUB_TOKEN，跳过后台上报（本地演示模式）"
    if vtype not in VOTE_TYPES:
        return False, f"票种 {vtype} 不在共享榜白名单内，拒绝上报"
    try:
        value = int(value)
    except (TypeError, ValueError):
        return False, f"票数 {value} 非法，拒绝上报"
    if value <= 0 or value > MAX_DELTA:
        return False, f"票数 {value} 超出合法范围（1~{MAX_DELTA}），拒绝上报"
    m = _load_map()
    num = m.get(product_id)
    if not num:
        return False, f"单品 {product_id} 未绑定 Issue（请先运行 `python3 scripts/report_github.py setup`），跳过上报"
    url = f"{API}/repos/{repo}/issues/{num}/comments"
    # 匿名记录：仅含 票种/增量/省份/日期，不含任何用户身份
    body = f"vote {vtype} +{value} {province or '全国'} {datetime.date.today().isoformat()}"
    ok, msg = _post_comment(url, body, token, url)
    if ok:
        return True, "后台已匿名记录（GitHub Issue 真实日志，零服务器）"
    return False, f"后台上报失败: {msg}"


def setup(repo=None):
    """为每个怀旧单品建一个 Issue，并把 issue_number 写入 issue_map.json。仅作者执行一次。

    具备幂等恢复：
    - 每成功建一个 Issue 立即存盘，中途出错不丢进度；
    - 若仓库已有带 `revival` 标签的同名 Issue（标题含 product_id），自动复用，不重复创建。
    """
    repo = repo or os.environ.get("GITHUB_REPO")
    token = os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        print("需要设置 GITHUB_REPO(owner/repo) 与 GITHUB_TOKEN 才能建 Issue。")
        return
    products = _load_products()
    m = _load_map()
    # 幂等恢复：从仓库现有 revival Issue 反查 product_id（标题格式 [复活赛] 名称（product_id））
    if len(m) < len(products):
        try:
            issues = _req(f"{API}/repos/{repo}/issues?labels=revival&state=all&per_page=100",
                          "GET", token=token)
            for it in issues:
                title = it.get("title", "")
                # 标题格式 [复活赛] 名称（可能含括号昵称）（product_id）；取【最后一个】括号才是 product_id
                ids = re.findall(r"[（(]([\w-]+)[）)]", title)
                pid = ids[-1] if ids else None
                if pid and pid not in m:
                    m[pid] = it.get("number")
                    print(f"  复用已有 Issue #{it.get('number')} <- {title}")
            _save_map(m)
        except RuntimeError as e:
            print(f"  读取已有 Issue 失败（不影响新建）: {e}")
    for p in products:
        if p["id"] in m:
            continue
        title = f"[复活赛] {p['name']}（{p['id']}）"
        body = (
            f"为怀旧单品「{p['name']}」开设的复活赛投票 Issue。\n\n"
            f"- 时代：{p['era']}\n- 故事：{p['story']}\n\n"
            f"本 Issue 的评论为**匿名投票日志**，由麦麦复活赛机器人自动写入；"
            f"真实票数聚合见项目 `README.md` 与 `ranking --from-github` 命令。"
            f"投票需在 WorkBuddy 内连接麦当劳会员账号参与（按会员唯一标识强身份去重），无需 GitHub 账号。"
        )
        try:
            r = _req(f"{API}/repos/{repo}/issues", "POST",
                     {"title": title, "body": body, "labels": ["revival"]}, token)
            m[p["id"]] = r.get("number")
            _save_map(m)  # 每成功一个立即存盘，避免中途崩溃丢失进度
            print(f"  已建 Issue #{r.get('number')} <- {p['name']}")
        except RuntimeError as e:
            print(f"  建 Issue 失败 {p['name']}: {e}（继续下一个）")
            continue
    print("data/issue_map.json 已更新。")


def _bot_login(token=None):
    """信任锚点：确定「哪些评论可信」。

    投票评论由机器人（持有 GITHUB_TOKEN 的账号）以自身身份发布，因此只统计
    机器人自身发布的评论，可彻底杜绝他人在 Issue 下伪造 `vote ...` 刷票。

    优先级：
      1. 显式 GITHUB_BOT_LOGIN（推荐，最明确）；
      2. 有 token 时调用 /user 拿到「真实写评论的身份」（比猜 owner 更准确：若
         机器人 token 不是仓库 owner，按 owner 过滤会把所有真实票过滤掉 = 漏票）；
      3. 无 token 的只读公开部署：由 GITHUB_REPO 的 owner 推断。
    都拿不到则返回 None —— 此时**不信任任何作者**，聚合结果必须为空（见 _tally_comments）。
    """
    repo = os.environ.get("GITHUB_REPO") or ""
    key = (os.environ.get("GITHUB_BOT_LOGIN") or "", bool(token), repo)
    if key in _BOT_CACHE:
        return _BOT_CACHE[key]
    login = (os.environ.get("GITHUB_BOT_LOGIN") or "").strip() or None
    if not login and token:
        try:
            u = _req(f"{API}/user", "GET", token=token)
            login = u.get("login") or None
        except RuntimeError:
            login = None
    if not login:
        owner = repo.split("/")[0].strip() if "/" in repo else ""
        login = owner or None
    _BOT_CACHE[key] = login
    return login


_BOT_CACHE = {}


def _tally_comments(comments, bot_login):
    """纯函数：从一个 Issue 的评论列表中，仅统计【机器人自身】发布的合法投票评论。

    返回 (total, {province: votes})。不触网，便于自检与单测。
    评论正文格式：vote <票种> +<增量> <省份|全国> <日期> rid=<幂等标记>

    安全约束（缺一不可）：
      - bot_login 为空 => 一条都不统计（否则任何人的 `vote ...` 都能刷榜）；
      - 作者必须是机器人本人；
      - 票种必须在 VOTE_TYPES 白名单内（mcp = 已过会员校验；backfill = 幂等补报）；
      - 增量必须是 1~MAX_DELTA 的正整数。
    """
    if not bot_login:
        return 0, {}                      # 没有信任锚点 => 不承认任何票
    total = 0
    pt = {}
    pat = re.compile(r"^vote (\w+) \+(\d+)(?:\s+(\S+))?")
    for c in comments:
        if (c.get("user") or {}).get("login") != bot_login:
            continue
        body = (c.get("body") or "").strip()
        mm = pat.match(body)
        if not mm:
            continue
        if mm.group(1) not in VOTE_TYPES:
            continue                      # 非白名票种 = 未验证票，丢弃
        try:
            val = int(mm.group(2))
        except (TypeError, ValueError):
            continue
        if val <= 0 or val > MAX_DELTA:
            continue
        prov = mm.group(3) or "全国"
        total += val
        if prov != "全国":
            pt[prov] = pt.get(prov, 0) + val
    return total, pt


def _fetch_all_comments(url_base, token=None, max_pages=50):
    """拉取一个 Issue 的全部评论（自动翻页，每页 100，防止超 100 条评论丢票）。

    GET URL 附带随机 uuid 参数（cache-buster），避免中间代理缓存旧响应导致
    「刚发的评论读不到」进而破坏 backfill 幂等性。
    """
    out = []
    page = 1
    while page <= max_pages:
        sep = "&" if "?" in url_base else "?"
        url = f"{url_base}{sep}per_page=100&page={page}&_={uuid.uuid4().hex}"
        comments = _req(url, "GET", token=token)
        if not isinstance(comments, list) or not comments:
            break
        out.extend(comments)
        if len(comments) < 100:
            break
        page += 1
    return out


def _plan_backfill(local_votes, gh):
    """纯函数：计算「本地已计票但尚未回流 GitHub」的差额，返回待补报评论计划。

    返回 [(product_id, delta, province)]，province 为省份名或「全国」。
    幂等：补报后 GitHub 聚合值上升，再次计算差额为 0，不会重复补报。
    """
    lt = (local_votes or {}).get("totals", {}) or {}
    lpt = (local_votes or {}).get("province_totals", {}) or {}
    gt = (gh or {}).get("totals", {}) or {}
    gpt = (gh or {}).get("province_totals", {}) or {}
    plan = []
    for pid, n in lt.items():
        delta = n - gt.get(pid, 0)
        if delta <= 0:
            continue
        prov_sum = 0
        for prov, pv in lpt.items():
            d = (pv or {}).get(pid, 0) - ((gpt.get(prov) or {}).get(pid, 0))
            if d > 0:
                plan.append((pid, d, prov))
                prov_sum += d
        rest = delta - prov_sum
        if rest > 0:
            plan.append((pid, rest, "全国"))
    return plan


def backfill():
    """把本地 votes.json 中尚未回流 GitHub 的票，匿名补报到对应 Issue（幂等，可重复执行）。"""
    repo = os.environ.get("GITHUB_REPO")
    token = os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        print("需要 GITHUB_REPO/GITHUB_TOKEN 才能补报。")
        return
    votes_path = os.path.join(BASE, "data", "votes.json")
    local = {}
    if os.path.exists(votes_path):
        with open(votes_path, encoding="utf-8") as f:
            local = json.load(f)
    gh = aggregate()
    plan = _plan_backfill(local, gh)
    if not plan:
        print("✅ 本地与 GitHub 共享榜已一致，无需补报。")
        return
    m = _load_map()
    today = datetime.date.today().isoformat()
    done = 0
    for pid, delta, prov in plan:
        num = m.get(pid)
        if not num:
            print(f"  ⚠️ {pid} 未绑定 Issue，跳过")
            continue
        body = f"vote backfill +{delta} {prov} {today}"
        url = f"{API}/repos/{repo}/issues/{num}/comments"
        ok, msg = _post_comment(url, body, token, url)
        if ok:
            done += 1
            print(f"  ✅ 已补报 {pid} +{delta}（{prov}）-> Issue #{num}")
        else:
            print(f"  ⚠️ 补报 {pid} 失败: {msg}")
    print(f"补报完成：{done}/{len(plan)} 条。")


def aggregate():
    """聚合所有单品 Issue 的匿名投票评论，返回真实可信的跨用户复活榜。

    信任模型：只统计机器人自身发布的投票评论（见 _bot_login / _tally_comments），
    他人无法伪造刷票。

    性能与限流：使用仓库级列表接口（GET /repos/{repo}/issues/comments）一次拉取
    全部 Issue 评论，按 issue_url 归属到单品——整个聚合仅需个位数 API 调用
    （每 100 条评论一页），远优于逐 Issue 请求的 51 次调用（会撞未认证 60 次/小时限流）。

    返回：
        {
          "totals": {product_id: 总票数},
          "province_totals": {省份: {product_id: 票数}},
        }
    未配置 GITHUB_REPO 时返回全空结构（不影响本地/前端运行）。
    """
    repo = os.environ.get("GITHUB_REPO")
    if not repo:
        return {"totals": {}, "province_totals": {}}
    m = _load_map()
    token = os.environ.get("GITHUB_TOKEN")
    bot = _bot_login(token)
    result = {"totals": {}, "province_totals": {}}
    # 初始化所有单品为 0，保证榜完整
    for pid in m:
        result["totals"][pid] = 0
    # 仓库级评论列表 -> 按 issue 编号分组
    num2pid = {num: pid for pid, num in m.items()}
    try:
        all_comments = _fetch_all_comments(f"{API}/repos/{repo}/issues/comments", token)
    except RuntimeError:
        result["_github_ok"] = False  # 网络失败标记：调用方（如 serve.py）不应缓存全 0 结果
        return result
    result["_github_ok"] = True
    by_issue = {}
    for c in all_comments:
        issue_url = c.get("issue_url") or ""
        mm = re.search(r"/issues/(\d+)$", issue_url)
        if not mm:
            continue
        pid = num2pid.get(int(mm.group(1)))
        if pid:
            by_issue.setdefault(pid, []).append(c)
    for pid, comments in by_issue.items():
        total, pt = _tally_comments(comments, bot)
        result["totals"][pid] = total
        for prov, v in pt.items():
            result["province_totals"].setdefault(prov, {})
            result["province_totals"][prov][pid] = result["province_totals"][prov].get(pid, 0) + v
    return result


def main():
    _load_env_file()
    ap = argparse.ArgumentParser(description="麦麦复活赛 · 后台真实统计（GitHub Issue 后端）")
    sub = ap.add_subparsers(dest="action")
    p_s = sub.add_parser("setup", help="为每个怀旧单品建 Issue 并写 issue_map.json（仅作者执行一次）")
    p_s.add_argument("--repo", default=None)
    sub.add_parser("aggregate", help="输出 GitHub 真实聚合榜（JSON）")
    sub.add_parser("backfill", help="把本地已计票但未回流 GitHub 的票匿名补报（幂等）")
    args = ap.parse_args()
    if args.action == "setup":
        setup(args.repo)
    elif args.action == "aggregate":
        print(json.dumps(aggregate(), ensure_ascii=False, indent=2))
    elif args.action == "backfill":
        backfill()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
