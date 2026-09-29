# example · rapidjson 最小示例（可直接拷 · **未上机**）

480×480 页面 + 2 个按钮 + 1 个「自检 AUTO」：**纯计算，不联网**（解析一个演示报文 / 生成一段 JSON 并回读）。

> ⚠️ **验证状态（务必先读）**：本包是**纯头文件包**，且本仓**没有它的真机验证记录**
> （`../package.yaml` 是 `verified: null` / `status: unverified`，详见 `../platforms.md`）。
> 本示例的作用是：给出"**能编进工程 + 解析/生成语义正确**"的最小形态；
> **真机数据（耗时/内存/大报文表现）待补** —— 要标 ✅ 需上机跑一轮并留 logcat（tag = `rapidjson demo`）。

| 文件 | 用途 |
|---|---|
| `ui/main.json` | 页面：解析报文 / 生成 JSON / 自检 AUTO + 结果 textview。`cd ui && fui pack ./` |
| `src/logic/mainLogic.cc` | `jobParse()`（Parse + 逐级判类型取值 + 坏报文演示）、`jobBuild()`（StringBuffer + Writer + 回读闭环） |
| `mainActivity_button_tab.snippet.cpp` | **必须补**：activity 的 `sButtonCallbackTab` 注册（3 行） |
| `Manifest.xml` | 依赖：easyui / log / base-utility / rapidjson（**纯头文件：改完必须 `fun install` 让 include 路径进 CMake**） |

## 关键口径（照抄这几条）

```cpp
rapidjson::Document d;
if (d.Parse(payload).HasParseError()) {          // ① Parse 不抛异常：必须查错
    LOGD("parse error: %s offset=%u", rapidjson::GetParseError_En(d.GetParseError()), (unsigned) d.GetErrorOffset());
}
if (d.HasMember("name") && d["name"].IsString()) {   // ② 取值前必须判存在 + 判类型
    std::string name = d["name"].GetString();
}
rapidjson::StringBuffer sb;  rapidjson::Writer<rapidjson::StringBuffer> w(sb);
std::string out(sb.GetString(), sb.GetSize());        // ③ 用 (ptr,len)：JSON 允许内嵌 \0
```

- ⚠️ **纯头文件**：没有 `.a`/`.so`，**别去找 librapidjson**；改 Manifest 后仍要 `fun install`。
- ⚠️ **不判类型会崩**：debug 下 `RAPIDJSON_ASSERT` 直接 abort（release 下是垃圾值）。
- ⚠️ **带内嵌 `\0` 的二进制 payload** 用 `Parse(str, length)`（默认重载要求 `\0` 结尾）。
- ⚠️ **大报文别用 `Document`**（全量树），用 `Reader`（SAX）+ 自定义 handler 省内存。
- ⚠️ **1.1.0 是上游老版本（2016 年线）** → 与 master/新文档有行为差异，别照最新文档抄。
- ⚠️ **与 `base-json`/jsoncpp（`#include <json/json.h>`）不是一套库**，项目里选一套用。

## 三步跑起来

1. `ui/main.json` → 工程 `ui/`，`cd ui && fui pack ./`（出 `main.ftu`）
2. `src/logic/mainLogic.cc` 并进工程 logic；把 `mainActivity_button_tab.snippet.cpp` 的 3 行填进 `src/activity/mainActivity.cpp` 的 `sButtonCallbackTab[]`
3. `fun install && fun build -p z20` → 部署见 `../platforms.md`（`/tmp` 劫持 + 单次 `setprop ctl.restart zkswe`）

## 验证点

| 按钮 | 期望 |
|---|---|
| 解析报文 | `name=panel-108 brightness=37 online=1`；`relays 数组 3 项`（ch/on 逐项打印）；坏报文报 `ParseError=... offset=...` |
| 生成 JSON | 打印生成文本（约 100+ 字节）+ `回读 OK：relays=3 项` |
| AUTO | 两件事各跑一遍，结尾 `错误数=0` |

> 上表是**语义期望值**（本示例未上机）；把 `kPayload` 换成你项目里**真实收到的报文**再跑，才是有效验证。
