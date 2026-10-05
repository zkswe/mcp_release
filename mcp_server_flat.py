# -*- coding: utf-8 -*-
"""MCP server (stdio) — **flat 模式**：47 个 op 各自注册为独立工具（无分发器）。

给哪类客户端用：Trae / Cursor / Claude Desktop 这类**需要每个工具独立 schema**、
或者你不会（也不想）配置工具白名单的场景——它们能直接在工具面板里看到 `flythings_knowledge_search`
`flythings_build_ui_flow` 等 47 个工具，参数提示由 schema 提供。

代价：44 份 schema 常驻上下文（约 1 万 token/session）。想省 token 就用默认入口
`mcp_server.py`（只暴露 1 个 `flythings_kb`，op="list" 取目录）。

配置（`.mcp.json`）：
```json
{"mcpServers": {"flythings-kb-flat": {
  "command": "python", "args": ["<路径>/mcp_server_flat.py"]}}}
```
也支持环境变量开关：`FLYTHINGS_MCP_MODE=flat python mcp_server.py`（等价）。

参数为对象（dict）时可直接传：flat 模式下每个工具就是普通函数，客户端按 schema 传参即可。

⚠️ **平台定位（判平台能力前必读）**：FlyThings OS 是**基于 Linux 的操作系统**（内核 + 自研系统框架 +
自研 GUI 交互系统），判平台能力**向 Linux buildroot/OpenWrt 看齐**，**不是**单片机/RTOS/ESP32 式板级 SDK；
GUI 库是自研 **EasyUI**（产品名 FlyThings UI，设备侧产物 `zkgui`/`libzkgui.so`），与 **LVGL 是对标竞争**的
两套独立 GUI 库（❌ 不要写「FlyThings 用的是 LVGL」）。长文：`knowledge/devflow/flythings-os-positioning.md`
（同一文案也经 MCP `instructions` 下发，见下）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp.server.fastmcp import FastMCP
import kb_tools
import mcp_extras

# 平台定位随 MCP initialize instructions 下发（与默认入口同一文案来源 = kb_tools.PLATFORM_POSITIONING）。
# flat 模式没有分发器 docstring 这个常驻面，不补的话用 42 个独立工具的人看不到定位。
try:
    mcp = FastMCP("flythings-kb-flat", instructions=kb_tools.positioning_instructions())
except Exception:
    mcp = FastMCP("flythings-kb-flat")
REGISTERED = kb_tools.register_all(mcp)     # 42 个独立工具（不含 flythings_kb 分发器）
mcp_extras.register(mcp)                    # resources + prompts（与默认入口同一实现）


def main():
    """console_scripts / 直接运行入口。"""
    mcp.run()


if __name__ == '__main__':
    main()
