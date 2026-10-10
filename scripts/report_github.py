#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦复活赛 · 后台真实统计（GitHub Issue 作为零服务器后端）

设计要点：
- 每个怀旧单品对应一个 GitHub Issue；每条「有效投票」由机器人**匿名**评论一条记录（仅含票种/增量/城市/日期，不含任何用户身份）。
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


def report_vote(product_id, vtype, value, city=None):
    """匿名上报一条有效投票到该单品对应的 GitHub Issue。返回 (ok, msg)。"""
    repo = os.environ.get("GITHUB_REPO")
    token = os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        return False, "未配置 GITHUB_REPO/GITHUB_TOKEN，跳过后台上报（本地演示模式）"
    m = _load_map()
    num = m.get(product_id)
    if not num:
        return False, f"单品 {product_id} 未绑定 Issue（请先运行 `python3 scripts/report_github.py setup`），跳过上报"
    url = f"{API}/repos/{repo}/issues/{num}/comments"
    # 匿名记录：仅含 票种/增量/城市/日期，不含任何用户身份
    body = f"vote {vtype} +{value} {city or '全国'} {datetime.date.today().isoformat()}"
    try:
        _req(url, "POST", {"body": body}, token)
    except RuntimeError as e:
        return False, f"后台上报失败: {e}"
    return True, "后台已匿名记录（GitHub Issue 真实日志，零服务器）"


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


def aggregate():
    """聚合所有单品 Issue 的匿名投票评论，返回 {product_id: total}；未配置则返回 {}。"""
    repo = os.environ.get("GITHUB_REPO")
    if not repo:
        return {}
    m = _load_map()
    token = os.environ.get("GITHUB_TOKEN")
    result = {}
    for pid, num in m.items():
        url = f"{API}/repos/{repo}/issues/{num}/comments?per_page=100"
        try:
            comments = _req(url, "GET", token=token)
        except RuntimeError:
            comments = []
        total = 0
        for c in comments:
            mm = re.search(r"^vote (\w+) \+(\d+)", (c.get("body") or ""))
            if mm:
                total += int(mm.group(2))
        result[pid] = total
    return result


def main():
    _load_env_file()
    ap = argparse.ArgumentParser(description="麦麦复活赛 · 后台真实统计（GitHub Issue 后端）")
    sub = ap.add_subparsers(dest="action")
    p_s = sub.add_parser("setup", help="为每个怀旧单品建 Issue 并写 issue_map.json（仅作者执行一次）")
    p_s.add_argument("--repo", default=None)
    sub.add_parser("aggregate", help="输出 GitHub 真实聚合榜（JSON）")
    args = ap.parse_args()
    if args.action == "setup":
        setup(args.repo)
    elif args.action == "aggregate":
        print(json.dumps(aggregate(), ensure_ascii=False, indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
