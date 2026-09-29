# rapidjson / evidence

**本目录是空的（只有这份说明）——因为本包没有真机证据，不是漏放。**

## 为什么没有证据文件

- `rapidjson` 是**纯头文件包**（`libs: []`，无 `.a`/`.so`），`package.yaml` 里 **`verified: null` / `status: unverified`**。
- 本仓**没有在真机上单独验证过它**：`package.yaml` 的事实来源是「实读包头签名」+「既有工程 `projects/SmartPanel_HA` 在用（`LocalLink.cpp` 直接 include）」，
  后者是**既有项目痕迹**，不是本仓的验证记录 → 不能算已验证。
- 按仓库口径（`packages/README.md`：**没测的写「未验证」不骗**），这里**不放伪造的 logcat**。

## 怎么把它补成有证据

1. 用 `packages/rapidjson/example/` 建最小工程（`fun install && fun build -p z20`）；
2. `/tmp` 劫持部署（命令见 `../platforms.md` 的「复现方式」），用**真实报文**跑：`Document::Parse` → 类型判定取值 → `Writer` 生成 → 回读；
3. 把 logcat 原文存成 `evidence/rapidjson_<日期>.txt`（tag = `rapidjson demo`），并同步更新 `../platforms.md` 的表格与 `package.yaml` 的 `verified_*`。

## 相关条目

- 平台结论（全部「未验证」+ 需要什么条件）：`../platforms.md`
- 最小示例（可直接抄，**未上机**）：`../example/README.md`
- 包事实（头/API/gotchas）：`../package.yaml`、`../README.md`
