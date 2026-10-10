#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试用：打印 query-my-account 返回结构（值做脱敏，仅保留字段名与结构），
帮助定位"会员唯一标识 / 积分"在真实返回里的字段名。
不会泄露你的真实会员号或积分（字母数字一律打码为 X）。
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_client import McDonaldMCPClient
from revival import extract_member_id, extract_points, MEMBER_ID_KEYS


def mask_value(v):
    if isinstance(v, (int, float)):
        return "***" if v else v
    if isinstance(v, str):
        return "".join("X" if ch.isalnum() else ch for ch in v)[:200]
    return v


def mask_obj(o):
    if isinstance(o, dict):
        return {k: mask_obj(v) for k, v in o.items()}
    if isinstance(o, list):
        return [mask_obj(x) for x in o[:6]]
    return mask_value(o)


def main():
    if not os.environ.get("MCD_MCP_TOKEN"):
        print("❌ 未检测到 MCD_MCP_TOKEN，请先配置（.env 文件或 export）再运行本脚本。")
        return
    c = McDonaldMCPClient()
    c.initialize()
    out = c.call_tool("query-my-account", {})

    print("=== 返回结构（已脱敏，X=字母数字，* =数字）===")
    print(json.dumps(mask_obj(out), ensure_ascii=False, indent=2)[:3000])

    result = (out or {}).get("result", {})
    data = {}
    sc = result.get("structuredContent") if isinstance(result, dict) else None
    if isinstance(sc, dict):
        data = sc.get("data") or {}
    content = result.get("content", []) if isinstance(result, dict) else []
    raw_text = "\n".join(
        x.get("text", "") for x in content
        if isinstance(x, dict) and x.get("type") == "text"
    )

    print("\n=== 解析结果（用真实数据，非脱敏）===")
    print("候选会员字段名:", MEMBER_ID_KEYS)
    print("结构化解析  会员标识:", repr(extract_member_id(data)),
          "| 可用积分:", extract_points(data))
    print("文本兜底解析 会员标识:", repr(extract_member_id(raw_text)),
          "| 积分:", extract_points(raw_text))

    if extract_member_id(data):
        print("\n✅ 已成功从 structuredContent.data 解析出会员唯一标识，投票去重可用。")
    else:
        print("\n⚠️ 仍未解析到会员标识，请把上面『返回结构』整段发我继续排查。")


if __name__ == "__main__":
    main()
