#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
探测「自动识别省份」是否可用（脱敏输出，绝不打印地址原文 / Token）。

用途：
- 确认麦当劳 MCP 是否暴露了「地址类」工具；
- 确认能否从中解析出省份（仅省级，用于分省统计）。

用法：
    python scripts/detect_province.py

输出仅含：工具名列表 + 命中的工具 + 识别到的省份。
不会输出任何详细地址、门牌、联系方式等敏感信息。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import revival  # noqa: E402


def main():
    try:
        from mcp_client import McDonaldMCPClient
    except Exception as e:  # noqa: BLE001
        print(f"❌ 无法导入 mcp_client：{e}")
        return

    try:
        c = McDonaldMCPClient()
        c.initialize()
    except Exception as e:  # noqa: BLE001
        print(f"❌ MCP 连接/初始化失败：{e}")
        print("   请确认 MCD_MCP_TOKEN 已配置（写入 .env 或 export）且有效。")
        return

    tools = c.list_tools()
    print("=== MCP 暴露的工具 ===")
    if not tools:
        print("  （未获取到工具列表，服务端可能不支持 tools/list）")
    for t in tools:
        print(f"  - {t}")

    addr_tools = revival.address_read_tools(tools)
    skipped = [t for t in tools
               if "address" in str(t).lower() and t not in addr_tools]
    print("\n=== 地址类工具（仅只读，写操作已排除）===")
    if skipped:
        print(f"  已跳过写操作工具（绝不调用）：{', '.join(skipped)}")
    if not addr_tools:
        print("  未发现只读地址工具 → 无法自动识别省份（将降级为「全国」）")
    else:
        for t in addr_tools:
            print(f"  尝试调用：{t}")
            try:
                resp = c.call_tool(t, {})
                import json
                p = revival.find_province_in_text(json.dumps(resp, ensure_ascii=False))
                # 只回显省份，不打印任何地址原文
                print(f"    → 识别到省份：{p or '（未识别）'}")
            except Exception as e:  # noqa: BLE001
                print(f"    → 调用失败：{str(e)[:120]}")

    p = revival.auto_detect_province()
    print("\n=== 最终自动识别结果 ===")
    print(f"  省份：{p or '（未识别，将计入「全国」）'}")


if __name__ == "__main__":
    main()
