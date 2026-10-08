# rapidjson —— RapidJSON 1.1.0（纯头文件 JSON 库）

**没有 lib，不用找 `librapidjson`**：`include/` 里 36 个头，声明了就能用。Z20 上一般由 `base-json 3.1.0`
依赖引入（`base::JSONObject` 的底座），也可单独声明后直接 `#include <rapidjson/document.h>`；Z20 在跑的写法见 `projects/SmartPanel_HA/src/network/LocalLink.cpp`。

**怎么用**
1. Manifest：`<package id="rapidjson" version="1.1.0"/>`（或走 base-json 间接引入）→ `fsc install`
   （**改完 Manifest 必须跑**，否则 include 路径不进 CMake）→ `fsc build -p z20`。
2. 关键 API：解析 `rapidjson::Document d; d.Parse(json.c_str())` → **必须** `HasParseError()` →
   `IsObject()/HasMember()/IsString()` 判定后再 `d["k"].GetString()/GetInt()/GetBool()`；生成
   `rapidjson::StringBuffer sb; Writer<rapidjson::StringBuffer> w(sb);` → `StartObject/Key/String/EndObject`
   → `std::string(sb.GetString(), sb.GetSize())`。
3. 类型断言会 abort、与 easyui 的 jsoncpp 是两套、跨平台可用性（只有 Z20）→ `package.yaml`。

⚠️ 未实测（`verified: null`）：实读头文件 + Z20 真实工程用法交叉验证写成。
