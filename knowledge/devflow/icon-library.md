# 🎨 UI 图标库（Tabler, MIT）— 权威规则

> 检索导引：问「图标哪来 / 图标风格不统一 / 有没有语义名 / 图标库许可合规 / 小尺寸图标发糊 / 按控件盒尺寸出图」→ 本文；抗锯齿与透明底铁律见 `devflow/ui-asset-rules.md`。
> 2026-09-16 沛哥定规：**UI 图标不再"每个项目现画、现切"**。统一用随 MCP 发布的图标库
> `components/icons/`：矢量源存在 MCP 里，按控件盒尺寸一条命令烘成 PNG。
> 起因：AI 生成的界面切图风格/比例反复不一致，每次都要人工回来确认 → 风格统一这件事必须由工具保证，不能靠"每次画一遍"。

---

## 0. 一句话

**图标的矢量源在 MCP（Tabler MIT 全量 + 自绘兜底），生成时按控件尺寸 + 指定颜色烘成 PNG。**
风格统一是"库自带"的，业务侧只需要报**语义名**，不需要描述外观。

---

## 1. 选型结论（别再纠结，这是定论）

| 候选 | 许可 | 结论 |
|---|---|---|
| Apple **SF Symbols** | Apple 专属：**禁止再分发**，且限定 Apple 生态 UI | ❌ 不进 MCP/发布包（随包分发有法律风险）。只作观感参照 |
| Google **Material Symbols** | Apache-2.0，可分发 | 🟡 可用，但笔画偏"谷歌"、拐角偏方，且没提供成对两态 |
| **Tabler Icons** | **MIT**（可商用可再分发） | ✅ **选定**。24×24 网格 + 2px 圆头圆角线框 → 观感最接近 iOS；5900+ 图标；**每图带 `-filled` 成对变体 = 现成 on/off 两态**；天气/家居长尾齐全 |

- vendor 时**排除 376 个 `brand-*`**（Google/Apple/各家厂商 logo，商标风险，不进发布包）
- 收录量：`icons/` **4754** outline + `icons-filled/` **1019** filled（解压 3.25 MB → 单归档
  `vendor/tabler-3.46.0.pack.tgz` 455 KB，sha256 `a0ba69f2…1c95`）

---

## 2. 用法（生成器是唯一入口）

```bash
# ① 语义名（推荐）：AI/业务只报语义名（203 个语义名，含 wifi/信号/电量分档）
python components/icons/scripts/gen_icons.py --vendor-name weather.sun --size 56 --color 255,175,40 \
       --out <项目>/resources/images
# ② 非正方形（开关/胶囊这类按控件盒出图）
python components/icons/scripts/gen_icons.py --vendor-name control.toggle-left --size 73x34 --color 30,91,46 \
       --out <项目>/resources/images
# ③ 自绘兜底线（Tabler 没有的语义，如两轮车仪表图标）
python components/icons/scripts/gen_icons.py --name weather.hail --size 32 --color 255,255,255 \
       --out <项目>/resources/images

# 名字兜底：Tabler 原生名也能直接传（不必等语义表收录）
python components/icons/scripts/gen_icons.py --tabler antenna-bars-3 --size 22 --out <项目>/resources/images
# 检索：列出可用语义名（可跟分类过滤）
python components/icons/scripts/gen_icons.py --list-vendor system
# 批量：语义表全量 / Tabler 全量 4754
python components/icons/scripts/gen_icons.py --vendor-set common --size 22 --out out/22
```

- 输出命名：`ic_<分类>_<语义名>[_off|_on].png`
- 目录清单：`components/icons/catalog.json`（每条含中英 tags、`source`、是否有 filled）
- 两态规则：**有 filled → `_on` 用 filled、`_off` 用 outline**；没有 filled 的语义只出 outline（例外清单见模块 README）
- **矢量源在归档里，不在散件里**（v0.3.0 起）：vendor 的 5777 个 SVG 打包成
  `components/icons/vendor/tabler-3.46.0.pack.tgz`（455 KB），生成时**按需解出用到的几个**
  到 `components/icons/out/.icons-cache/`。所以：
  - **不要再去 `grep`/浏览 `vendor/tabler/icons/*.svg`**（已不存在）；
  - 查名字用 `--list` / `--list-vendor <分类>` / `--list-tabler <子串>`，或读 `catalog.json`；
  - 查来源/缓存状态用 `--pack-info`；默认**完全离线**，不拉网。
- 设备/产品包只带烘好的 PNG；归档不进设备（见模块 `platforms.md` §3）。

---

## 3. 铁律呼应（违反会被 check_all / verify_assets 判 FAIL）

1. **图的像素尺寸必须严格等于控件 position**（引擎会拉伸变形）——生成器已保证，别手改尺寸
2. **颜色是烘焙进 PNG 的**：FlyThings **没有运行时 tint API**，不能"一张图换色" → 换色就重新生成
3. 图片一律放 `<项目>/resources/images/`，json 里引用写 `images/xxx.png`（不带 `resources/` 前缀、不写绝对路径）
4. **设备字库不放图标**（设备字库是裁剪字库）→ 图标一律 PNG，文本只用汉字 + ASCII + 基础符号
5. **两态切换**：json 用 `picTab{off,on}`（`data-pic0`/`data-pic2`），代码用 `setSelected(bool)` 切状态

---

## 4. 小尺寸策略（实测，2026-09-17 抗锯齿去量化后重测）

Tabler 的线宽是 2px@24 网格；缩到 **22px 时只剩 ~1.83px**。本套生成器用
「**半像素对齐线宽 + 8× 超采样真实覆盖率 + 只清极弱孤立噪点**」处理——即
alpha = BOX 面积平均出来的**真实覆盖率**（不做 α 对比度整形），边缘灰度完整（22px 中位
30 级、56px 中位 42 级），既不硬阶梯也不糊：

| 控件尺寸 | 用法 |
|---|---|
| **≥ 22px** | outline 即可（真实覆盖率抗锯齿，22px 不发虚、无硬阶梯） |
| **≤ 20px** | 建议 filled（实心），密集图形（toggle/bell/bulb）更清楚 |
| ≤ 16px | 未纳入默认清单，需要时 `--size 16` 自行确认 |

> ⚙️ **老口径已降为 opt-in**：v0.3.1 前默认的「α 对比度整形（<0.40/>0.60 推 0/255）」会把
> 小尺寸边缘灰度**量化成个位数级**（48px bell 只有 9 级 → 肉眼硬阶梯，这是 2026-09-17 修的 bug）。
> 确实需要"近二值"时用 `python components/icons/scripts/gen_icons.py --snap ...`。
>
> ⚠️ 重要：设备端**不能靠字体渲染图标**（FlyThings 无 tint，小字号字形糊、像素对不齐）→ 图标一律烘 PNG。
> 纪律复核：`python components/icons/scripts/selfcheck.py`（命名/尺寸严格/透明度【C 条：上限随尺寸】/
> 抗锯齿保真【C2 条：对拍 16× 理想覆盖率】/ 清单一致性/全量可渲染）。

---

## 5. 合规（发布包必须满足）

- `components/icons/vendor/tabler/LICENSE` **必须随发布产物分发**（MIT 唯一义务 = 保留版权与许可声明）
- 我们**只做「单色化 + 等比缩放」，图形路径一字未改**（不构成衍生作品）
- **不收录品牌 logo**；对外说明写明"图标来自 Tabler Icons（MIT）"
- 登记与排除清单见 `components/icons/THIRD-PARTY.md`（含版本 3.46.0 / npm tarball sha256 / 收录范围）

---

## 6. 常见坑

| 现象 | 原因 / 正解 |
|---|---|
| 想"运行时把图标换成另一个颜色" | 做不到（无 tint）；重新生成一张烘焙好颜色的图 |
| 直接往工程里塞 SVG | FlyThings 不渲染 SVG → 必须烘成 PNG |
| 图比控件盒大/小 | 引擎会拉伸 → 按控件盒尺寸生成（`--size WxH`） |
| 图标糊成一团 | 控件 ≤20px 却用了 outline → 换 filled（本套 ≥22px outline 已按真实覆盖率抗锯齿，不发虚） |
| 图标边缘有硬阶梯 | 有人重开了 `--snap`（α 对比度整形，把边缘量化） → 去掉 `--snap` 重新生成 |
| 语义名写错/写中文描述 | 生成器按 `catalog.json` 的语义名解析，报错会提示相近候选 |
| 想用 SF Symbols 那一套 | 许可禁止再分发；观感需求用 Tabler + 少量自绘满足 |
| 找不到 `vendor/tabler/icons/xxx.svg` | v0.3.0 起散件已收进 `vendor/tabler-3.46.0.pack.tgz`（**正常，不是损坏**）：生成器会自动按需解到 `out/.icons-cache/`；要看清单用 `--list-tabler`，要看状态用 `--pack-info` |

---

## 7. 相关文件

- 模块（随 MCP 发布）：`components/icons/`（`README.md` 用法 / `platforms.md` 平台与硬规则 / `THIRD-PARTY.md` 合规 / `catalog.json` 清单）
- 资产：`components/icons/vendor/tabler-3.46.0.pack.tgz`（Tabler 3.46.0，MIT，单归档按需解）
  + `components/icons/svg/`（自绘兜底）+ `vendor/tabler/{LICENSE,index.json,VERSION.txt}`（归档外）
- 配套规范：`knowledge/devflow/ui-asset-rules.md`（图片路径与尺寸铁律）、`knowledge/devflow/design.md`（字库限制）
