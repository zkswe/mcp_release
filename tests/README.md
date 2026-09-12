# tests/ — 契约用例（离线，零真机依赖）

> 为什么有：35+ 个 op 此前**没有任何契约测试**，参数写错、envelope 变形、清单漂移、
> 破坏性默认值被人改回去，都只能等用户在真机上撞到（见 `reports/flythings-mcp-review-2026-09-11.md` §3.5）。

## 跑法

```bash
python -m unittest discover -s tests -q     # 全部（约 2 秒）
python scripts/ci.sh                        # CI 前置：compileall + 用例 + 一致性 + 冒烟
python scripts/check_consistency.py --with-tests
```

依赖：只用标准库 + 仓库已有依赖（Pillow 缺失时图像相关用例自动 skip）。**不连真机**。
当前规模：**122 项**（1 项按环境 skip）。

## 用例分布

| 文件 | 钉住什么 |
|------|----------|
| `test_dispatch_contract.py` | op 清单（分发器 = manifest = kb_tools.OP_NAMES）、未知 op 候选、`BAD_ARGS`/`BAD_PARAMS`（参数写错必须回正确签名）、每个非真机 op 空参调用必须回可解析 envelope、**工具面三模式**（默认只 1 个分发器 / `all` 兼容 / `flat` 与 `mcp_server_flat.py` 均 32 个）、`get_version` compact 不膨胀、manifest 新鲜度 |
| `test_search_quality.py` | 检索：中文**字级 bigram** 切词（整段中文不得成为一个 token）、kb_tools 与 rag_search 共用同一套切词、8 条真实问法 BM25 top-3 命中、hits 带 `source`、返回体带 `retrieval`/`degraded`/`quality`、未收录与低置信必须带检索边界提醒、`k` 上限夹紧 |
| `test_platform_matrix.py` | 平台唯一来源：模板/bin_tools 目录真实存在、别名归一、未知平台报错且列出全部支持项、默认平台有效 |
| `test_layout_flow.py` | fui pack 确定性 + affectedFiles；**edit_ftu 默认不覆盖原 ftu**（原文件字节不变、留 .bak、产 `.edited.ftu`）；`flythings_ui_visual(action="edit_apply")` dry_run 不写盘 / 默认不 pack / 写盘留 .bak |
| `test_asset_pipeline.py` | html2json **黄金样例**（渐变/圆角/阴影/emoji/loading 必须真出图且 PNG 尺寸 == 控件盒 = v0.27.30 三连 bug 防回归）；已自动转图的效果不许再喊「请切图」；`verify_assets`：分层 `ui/<res>/*.json` 必须扫到、自动生成图尺寸不符 = FAIL、手绘图被拉伸 = 仅提示、缺图 = FAIL、0 页必须 warning |
| `test_ui_visual_merge.py` | ui-visual 三合一（`flythings_ui_visual(action)`）：action="list" 参数目录、未知 action / 缺必填参数 = BAD_PARAMS、editor/edit_apply/diff 三路路由、别家 action 的参数必须回 `visualNote`（不静默忽略）、三个旧名回 OP_RENAMED 且 hint 带该用哪个 action |
| `test_toolchain_capability.py` | `fui unpack` 能力声明与实际一致（声称能用必须真解出 json；声称不能用必须真解不出）、json→ftu→json 往返语义等价、无 unpack 且缺 json 源时 edit_ftu 必须明确报错 |

> 工具 docstring 有字数预算（单 op ≤ 900 字符、全体 ≤ 12,000）——由 `scripts/check_consistency.py` 卡；
> 长尾细节请写进 `knowledge/`（可检索），别塞回 docstring。

## 约定

- 临时工程一律建在系统临时目录（`_util.project()`），用例结束清理，不污染仓库。
- 夹具优先复用 `ui_tools/examples/`（`effects_test.html` = CSS 效果黄金样例、`main.json` = 布局样例）。
- 新增 op / 改平台 / 改破坏性默认值时，**先补用例再改代码**（这些契约正是事故留下的钉子）。
