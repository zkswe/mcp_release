# 📤 双仓库边界与发布流程约定（FlyThings MCP）

> 2026-09-09 沛哥定规。**默认开发维护内部版本（master）**；release 版**仅在沛哥确认需要推送时**按本文边界同步，测试验证后发布。

## 1. 仓库矩阵

| 仓库 | remote | 分支 | 定位 | 访问 |
|------|--------|------|------|------|
| 内部测试版 | `origin` = gitee.com/Kwolve/fly-things-os_-mcp.git | `master`（完整版） | 日常开发维护主战场，全量知识/工具/demo/内部史 | 私有（沛哥管理） |
| 公开发布版 | `release` = gitee.com/Kwolve/flythingsmcp_release.git | `master`（= 本地 `release-base` 裁剪分支） | 普通开发者：基础控件 + 通用机制 + hardware API + bin_tools + 模板 + 工具 | 公开 |

- 本地分支：`master`（内部全量）、`release-base`（发布裁剪，从 master 派生，force push 到 release/master）
- **版本号两边一致**（如 v0.27.13-open），内容 = 内部版公开裁剪集

## 2. 默认工作流（90% 的时间走这条）

1. 所有开发/知识更新**只改 `master`** → commit → `git push origin master`
2. **不主动同步 release**；只有沛哥说「发布 release / 推 release 版」才执行 §4 流程
3. 发布后 memory 记一笔（版本号 + 同步了什么）

## 3. 边界规范（release 保留 vs 剔除）

### ✅ 保留（公开基础，客户可拿）
| 内容 | 说明 |
|------|------|
| `knowledge/uicontrols/` | 基础控件 22 篇（字段/API/坑位）——核心资产 |
| `knowledge/devflow/` 通用篇 | 工程配置（package.properties/EasyUI.cfg）、自定义字库/控件、原型流程、代码骨架、部署场景 |
| `knowledge/hardware/` | **跨平台硬件 API**：usb-otg-switch（OTG/ADB/U盘 切换对照）、uvc-camera-generic（UVC 通用接入层） |
| `bin_tools/` | 调试工具（busybox/ui_test/mt_test，各平台 ELF）+ 配套 devflow 文档（busybox-debug-library/touch-inject-autotest） |
| `templates/` | 各平台 HelloWord 空模板（无深度知识） |
| MCP 工具全家桶 | 建工程/布局/预览/依赖/校验/i18n/测试（python 代码保留平台支持） |
| `models/` | bge-small-zh 开源向量模型（本地检索必需） |
| `rag_index.json` | 只索引 release 保留文档（重建：空目录技巧，勿把本地 wiki 编入） |

### ❌ 剔除（内部/方案/平台深度，绝不进 release）
| 内容 | 理由 |
|------|------|
| `knowledge/v85x/`（8 篇） | **V85X 完全不开放**（MPP/DVR/UVC/图层调试/录制卡格式化等 aw-dvr 私有媒体栈深度） |
| `knowledge/t113-car/`、esl、方案类 | 客户/专用方案（车载互联/仪表 CAN 等）不开放 |
| `demos/` | 参考工程依赖私有包（aw-dvr），不开放 |
| 私有/方案依赖包名 | package_catalog.json 剔除：aw-* / voip / tuyaoscxx / uvc-camera / lylink* / xunfei-aiui |
| devflow 内部规范 | kb-first-analysis（内部检索铁律）、gui-controls-gap（内部盘点） |
| CHANGELOG 完整内部迭代史 | release 不要带 CHANGELOG.md（自 v0.27.31 起冻结，内容不过发布；内部历史看 master git log） |
| kb_tools.py MCP_FEATURES | 精简为公开能力摘要（内部条目只在 master） |
| 内部工程名/路径 | CV201_PND/mark_cv201/UvcJpegTest/KlipperF133/xdv23/T113CarSystem_PND/guoxs/lib 等一律清除 |
| accessKey 真实值 | 一律全 0 占位 `0000000000000000000000000000000000000000`（真实 key 只在本机/内部 Manifest） |

### ⚠️ 边界说明
- hardware 跨平台对照表含 V85X 路径列 = API 一部分（沛哥 12:22 拍板 hardware 可开放）；但 V85X **绑定实现/私有媒体栈**表述为「未收录于公开版，以平台方 SDK 为准」
- bin_tools 含 v85x 平台 ELF = 通用调试工具（沛哥拍板 bin_tools 全开放）
- 保留文档中指向已删文档的引用必须同步清理（否则客户检索到死链/暴露文档名）

## 4. 发布流程（沛哥确认后执行）

```bash
# ① 从最新 master 派生/更新裁剪分支
git checkout master && git pull origin master
git checkout release-base        # 已存在则 git merge master（裁剪内容手动同步）
git checkout master -- <保留清单> # 或按 §3 增量同步

# ② 按 §3 剔除清单清理（git rm）+ 保留文档去工程化
# ③ 重建 release 索引（⚠️ 空目录技巧，勿编入本地 wiki 内部文档）
python rebuild_index_local.py <存在的空目录>   # → rag_index.json 只含保留 knowledge
# ④ 测试验证
python -c "import ast; ast.parse(open('kb_tools.py',encoding='utf-8').read())"  # 语法
#   可选：python mcp_server.py 冒烟 / rag 检索抽查
# ⑤ 干净性扫描（必须 0 命中）
#   词表：89afac(真实key) | aw-dvr | aw-mpp | voip | tuyaoscxx | uvc-camera | lylink
#         | CV201_PND | mark_cv201 | UvcJpegTest | xdv23 | T113CarSystem | KlipperF133
#         | guoxs/lib | DashBoard | LearningProject | temp_car | demos/ | knowledge/v85x
# ⑥ 提交 + force push（release/master 只接受 force 覆盖）
git add -A && git commit -m "release-base: <版本> 公开版同步（<摘要>）"
git push release release-base:master --force
# ⑦ 远端验证
git ls-remote release master          # head 一致
git ls-tree -r --name-only release/master | grep -E "knowledge/v85x|demos/|bin_tools|models"  # 结构符合 §3
# ⑧ memory 记录
```

## 5. 版本号与版本史

- 版本号递增只发生在 master：`kb_tools.py` MCP_VERSION + `MCP_FEATURES` 顶部新条 + `README.md` 版本号
- ⛔ **CHANGELOG.md 自 v0.27.31（2026-09-11）起冻结为历史归档**（沛哥：「changelog 不需要提交」）
  —— 不再追加新节、不进任何提交/发布；版本史唯一来源 = `MCP_FEATURES`（`compact=False` 取全量）+ `README.md`
- release 同步时：`kb_tools.py` 版本照 master（内容为裁剪版）；**CHANGELOG.md 不带**（历史留内部 git）
- 自检 `scripts/smoke.py` 已不再校验 CHANGELOG（避免代码与冻结档案脱节）

## 6. 常见坑（实战教训 2026-09-09）

1. release-base 上 git rm 目录可能残留 .gitignore 忽略的已跟踪文件（.vscode/ 等）→ 删完 `git ls-tree -r HEAD` 复核
2. edit 含 emoji 的文档用 read 先拿精确文本（?/✅/⚠️ 控制台会乱码显示导致 oldText 不匹配）
3. 发布前必扫真实 accessKey——open 库任何 Manifest/文档不得出现真实 key
4. demos/README.md 等规范文档只在 master（release 无 demos 目录）
