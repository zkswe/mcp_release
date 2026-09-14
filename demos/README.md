# 📦 Demos — 验证全功能的参考工程库（带着走，AI 快速参考避免踩坑反复 try）

> 定位（2026-09-09 沛哥定调）：**做一批验证全功能的 demo 案例带着走**——每个 demo = 一个**已真机验证可编译可运行**的功能闭环（代码 + xml + json + README），
> 供外部开发者/AI 同步 MCP 后**照抄改改就能跑**，避免从零拼装反复 try 浪费 token 和时间。
> 配套：`knowledge/` 文档讲"为什么/怎么调"（原理+坑），`demos/` 给"现成能跑的"（实现）。

## 📋 现有案例

| Demo | 平台 | 功能闭环 | 状态 | 配套知识 |
|------|------|---------|------|---------|
| `dvr-uvc-recorder-v85x` | V85X | UVC 摄像头 探测/预览/拍照/录像/停止/回放 + 图层释放 + 竖屏旋转 | ✅ 真机全链路验证 | `knowledge/v85x/dvr-recorder-guide.md` |
| `h264-player-v85x` | V85X | 硬件 H264 解码（bin 工具）：env + dlopen 加载库 + `init_ex` 缩放解码 + 解码回调 + Annex-B 按 AU 喂帧 + 内存采样 | ✅ 真机解码验收（V851 640×480）+ 编译通过 | `knowledge/v85x/h264-player-usage.md` |

## 🆕 新增 demo 的规范（照此执行，保证质量与可维护）

1. **命名**：`<功能>-<形态>-<平台>`（如 `dvr-uvc-recorder-v85x`、`esl-html-f133`）；平台不同名放同目录
2. **必备文件**：
   - `Manifest.xml`：真实平台依赖；⚠️ **accessKey 私有包一律全 0 占位发布**（`accessKey="0000000000000000000000000000000000000000"`，40 位全 0），README 说明向平台方获取后替换，**真实 key 禁止进公开仓库**
   - `ui/*.json` + 编译产物 ftu 齐（json 是源，README 写明改布局需 fui pack）
   - `src/`：业务代码只写 `logic/`；`activity/` 目录由构建自动生成不手改
   - `package.properties`：工程级配置（旋转/字库等）写清楚用途
   - `README.md`：三件套——①三步跑起来（含 accessKey/依赖/编译部署）②功能与预期/验证点表 ③关键坑位清单（代码里修过的坑，注明别回退）
3. **必须真机/真编译验证过**才能进库：README 标注验证状态（✅ 真机全链路 / ✅ 编译通过未上机），未验证的标 ⚠️
4. **红线**：
   - 不提交编译产物/工具链：`.fun/`、`fun.exe`、`fui.exe`、`.vscode/`、`.fun-lock.json`、`.deps.lock`（体积红线，源码级交付）
   - 不体现内部工程/客户名（知识库定规：open 版去工程化）
   - 不留半成品（每个 demo 是一个跑得通的闭环，宁缺毋滥）
5. **知识联动**：每个 demo 在配套 knowledge 文档头部加"同仓 demos/xxx 参考工程"指引，AI 检索知识时能找到实现
6. **登记**：本表加一行 + `MCP_FEATURES` 加一条摘要（CHANGELOG 已冻结，不再记）

## 🔍 AI/开发者使用方式

- 先 `flythings_search` 查知识（`knowledge/`）拿原理与坑 → 再翻 `demos/<案例>/` 照抄实现 → 改功能 → `fun build`/`launch` 验证
- demo 目录在 MCP 检索范围外（代码不是文档），靠 knowledge 文档导引进 demo 路径
