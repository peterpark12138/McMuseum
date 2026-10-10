#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦当劳 MCP 真实调用客户端（Streamable HTTP，仅读取）
- 读取环境变量 MCD_MCP_TOKEN
- 实现 MCP 握手：initialize -> notifications/initialized -> tools/call
- 提供 get_my_points() / get_meals() 便捷方法
- 明确只做读取（query-my-account / query-meals），不执行任何下单/扣减操作

用途：证明本作品「真实使用麦当劳 MCP 能力」，并为本作品的用餐积分票、在售对比提供真实数据底座。
"""
import os
import json
import urllib.request
import urllib.error

MCP_URL = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2024-11-05"


def _load_env_file():
    """从项目根目录 .env 读取环境变量（不覆盖已存在的系统环境变量）。

    这样用户无需在终端手动 export，把 token 写进 .env 文件即可，
    .env 已被 .gitignore 排除，不会误提交。
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(root, ".env")
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v
    except FileNotFoundError:
        pass


class McDonaldMCPClient:
    def __init__(self, token=None):
        _load_env_file()
        self.token = token or os.environ.get("MCD_MCP_TOKEN")
        if not self.token:
            raise RuntimeError("缺少 MCD_MCP_TOKEN，请先 export MCD_MCP_TOKEN=你的Token")
        self._id = 0
        self._session = None

    def _post(self, payload, notify=False):
        self._id += 1
        payload.setdefault("jsonrpc", "2.0")
        if not notify:
            payload["id"] = self._id
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(MCP_URL, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
        if self._session:
            req.add_header("Mcp-Session-Id", self._session)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if "Mcp-Session-Id" in resp.headers:
                    self._session = resp.headers["Mcp-Session-Id"]
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:300]
            raise RuntimeError(f"MCP HTTP 错误 {e.code}: {detail}")
        return self._parse(body)

    @staticmethod
    def _parse(body):
        body = (body or "").strip()
        if not body:
            return None
        if "data:" in body or body.startswith("event:"):
            for line in body.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    chunk = line[len("data:"):].strip()
                    if chunk:
                        try:
                            return json.loads(chunk)
                        except json.JSONDecodeError:
                            continue
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None

    def initialize(self):
        resp = self._post({
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "mcrevival", "version": "1.0.0"},
            },
        })
        try:
            self._post({"method": "notifications/initialized"}, notify=True)
        except Exception:
            pass
        return resp

    def list_tools(self):
        """列出 MCP 服务端暴露的工具名（用于自适应发现地址/门店类工具）。失败返回 []。"""
        try:
            resp = self._post({"method": "tools/list", "params": {}})
            tools = (resp or {}).get("result", {}).get("tools", [])
            return [t.get("name") for t in tools if t.get("name")]
        except Exception:
            return []

    def call_tool(self, name, arguments=None):
        return self._post({
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        })

    def get_my_points(self):
        """读取会员积分余额（仅读取，不扣减）"""
        return self._extract_text(self.call_tool("query-my-account", {}))

    def get_meals(self):
        """读取当前在售菜单"""
        return self._extract_text(self.call_tool("query-meals", {}))

    @staticmethod
    def _extract_text(resp):
        if not resp:
            return None
        result = resp.get("result")
        if not result:
            return resp
        content = result.get("content", [])
        texts = [c.get("text") for c in content if c.get("type") == "text"]
        return "\n".join(texts) if texts else result


def main():
    import argparse
    ap = argparse.ArgumentParser(description="麦当劳 MCP 真实调用客户端（只读）")
    ap.add_argument("--tool", default="query-my-account", help="要调用的工具名")
    ap.add_argument("--args", default="{}", help="工具参数 JSON")
    args = ap.parse_args()
    client = McDonaldMCPClient()
    client.initialize()
    out = client.call_tool(args.tool, json.loads(args.args))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
