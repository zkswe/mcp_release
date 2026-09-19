# UI 图片资源铁律与 PNG 抗锯齿管线

> 检索导引：生成图标/瓦片/按钮背景/卡片图 / 图片尺寸对不上 / 圆角四角发黑 / 按钮透背景 /
> 图片锯齿 / 1x 直画 / 大图缩小 / 走哪条路出图 / **滑块圆钮·开关药丸·圆形钮发锯齿 /
> thumb.size 与图对不上 / 超采样（SS）/ 某形状该用哪个出图函数** 时命中。
> 2026-09-19 补：**浅色形状压浅底边缘有锯齿 / 选中条边界有毛边/阶梯 / 圆角不平滑 / 描边发脏 /
> 暗环 白点 脏边 / 低对比度边缘 / LANCZOS 振铃 / 重采样算子怎么选 / 抗锯齿审计
> （aliasing / 边缘阶梯 / 边缘发毛 / 不平滑）** 也命中本文件（见 §2 铁律 #8 与 #10）。
> 2026-09-19 再补（A1/A3 落地）：**缩回算子 Image.BOX / 面积平均 / 逐像素覆盖率 / 整像素描边带 /
> 描边与填充混色 / 按下态描边 / 发丝线裁剪 / check_all 第 21 项 / aa_audit --fail / 出图核抗锯齿**
> 同属本文件 #8/#10。
> 用途：`flythings_generate_ui_assets` 的完整口径 + 全仓库通用的图片资源铁律
> （该工具 docstring 只保留要点，长尾与铁律细节在这里）。

## 1. 三级降级策略（任何环境都能出图）

| 级别 | 条件 | 效果 |
|------|------|------|
| ① AI 生图 | 配置了 `OPENAI_API_KEY` 且网络可达 | gpt-image-2 透明底，最精致 |
| ② 本地 emoji 渲染 | Windows `seguiemj.ttf` / Linux `NotoColorEmoji` | 卡通风（羊了个羊同款） |
| ③ 线条/几何兜底 | Pillow 画圆/方/星/心/对勾 | 无 AI、无 emoji 字体也能出 |

最终用户（客户）没有 AI 能力时自动降级，**无需任何外部依赖**。

## 2. 图片资源铁律（2026-08-29 羊了个羊实战，务必遵守）

1. **图片尺寸必须与「盒子」一致**（瓦片 76×76 控件 → 76×76 图；槽位 72×72 → 72×72 图）。
   不要生成大图让控件缩放，也不要小图拉伸。
   **盒子有三种来源**（`verify_assets` / `check_all #11 #17` 都按这个口径核）：
   | 盒子 | 字段 | 说明 |
   |------|------|------|
   | 控件 position | `backgroundPic` / `picTab.picN` / `progressPic` / `secondaryProgressPic` / `thumbPic` | 主盒（默认） |
   | **`thumb.size`** | `thumb.normalPic` / `thumb.pressedPic`（SeekBar / CircleBar 滑块） | **自有尺寸**子盒，不是控件盒（v0.27.75 补） |
   | `iconPosition` / `textPosition` | — | 是**位置**不是盒子（无 width/height），不参与 |
   ⚠️ **thumb 曾是核对盲区**（2026-09-16 案例实测）：`sk_thumb.png` 31×31 而 json 写
   `thumb.size` 30×30，`check_all` 与 `verify_assets` 一路 PASS（两边都把它当「自有尺寸」跳过了）
   → 真机上滑块圆钮与轨道对不上。现行口径：
   - **自动生成图**（`resources/images/`，铁律 #6/#9）thumb 图尺寸 != `thumb.size` → **FAIL**（`mismatch[]`）
   - **手绘 thumb**（`slider_/`、`navi/` 等）失配 → 仅 `stretched[]` 提示：官方基准工程
     `SampleUI-New/ui/1024x600/testSlider.json` 本身就是 `slider_/jdt_ht.png` 35×34 配
     `thumb.size` 33×35（引擎会拉伸），把它当 FAIL 会制造假警报（基准工程零误报是校准目标）
   - 没写 `thumb.size` 或为 0 → 跳过核对 + 写 `skippedNoBox[]` / warning（不误报）
   - 编辑器（`ui_editor._preflight`）同口径：自动生成 thumb 失配给红标，手绘不报
2. **圆角卡片图四角必须真透明（alpha=0）**：渐变/填充底是整矩形画的，圆角只是描边轮廓，
   必须用圆角 mask 裁剪（`putalpha`）清掉弧线外角落；阴影模糊（`GaussianBlur`）会溢出到弧线外，
   最后整体再裁一次圆角清掉残影。
   - 通用函数 `gen_res.rounded_card()`（渐变 + 圆角 + 描边 + 高光）已内置裁剪
   - `gen_res.gen_gradient(..., radius=r)` 也已修复（radius>0 自动裁圆角）
3. **用透明角图片的按钮不要设 `bgColorTab`**：透明角会透出按钮底色而不是窗口背景；
   需要透背景的图片按钮（瓦片/槽位/图标钮）不放 `bgColorTab`；纯文字按钮才用底色。
4. **功能按钮尽量用图片按钮**：`picTab{pic0: normal, pic1: pressed（_p 后缀）}` 两态图。
5. **生成后必须检查四角 alpha**：`img.getpixel((2,2))[3] == 0` 才算合格。
6. **路径规范**（2026-09-01 沛哥要求）：自动生成的图片一律放 `<项目>/resources/images/`；
   json 布局引用路径写 `images/xxx.png`（相对 resources 目录，与设备/ftu 加载一致）。
   返回的 `path` 字段就是 `images/xxx.png`，直接填 json 的 `backgroundPic` / `picTab.pic0` /
   `picTab.pic1`；**不要写绝对路径，也不要带 `resources/` 前缀**。
7. **PNG 生成管线铁律**（2026-09-08 沛哥定规，方案 A 显式化）：AI/客户端需要图片时
   **禁止自写绘制代码 1x 直画、禁止用外部生图能力直出小图交付**
   （1x 二值 alpha 无抗锯齿、大图缩小边缘必锯齿）。

   **只走三条路**：
   - CSS 效果交 `html2json` 自动转图（内置抗锯齿）
   - 本工具（`flythings_generate_ui_assets`）生成
   - `gen_res` 公开函数：`rounded_card` / `gen_gradient` / `gen_shadow_card` / `emoji_icon_ss` /
     `glyph_icon_ex` / `line_icon` / `frames_loading_gif` / **`rounded_rect_ss`（强曲率形状，见 #8）**
     （全部内置抗锯齿）

   **PNG 防锯齿五要素**：尺寸 == 盒子（#1）/ **强曲率形状走 `rounded_rect_ss`（≥4x 超采样 + 面积平均 BOX，#8）**
   ——⚠ **2026-09-19 落地**：缩回算子已从 LANCZOS 改成 `Image.BOX`（带直通 α 的边界**不得**用 LANCZOS），
   见 #8 末尾「缩回算子铁律」与 #10。
   `html2json` 的 CSS 效果出图**一律 SS（`ss=4`），不用选**（v0.27.76）/
   端点 round cap / 圆角四角 alpha=0 / 生成后跑 `check_all` 校验（#11 图片尺寸 + #17 产物核对 + 四角 alpha）。

   完整规范见仓库 `ui_tools/HTML_SUBSET.md`「切图 / 图片资源铁律」#8 #9。

8. **★ 形状分类出图口径（FT-010 + v0.27.76，2026-09-16 定）**：按**调用方**分两条口径 ——
   **`html2json` 的 CSS 效果出图一律 SS**（钟工 2026-09-16 拍板：固定本地脚本工作，不额外耗 token，
   不再保留 1x+α 羽化那条路）；**手写调用**按曲率强度选。选错就是真机上肉眼可见的锯齿
   （钟工反馈「滑块圆钮 / 开关有锯齿」的技术根因）。

   | 调用场景 | 用哪个 | 为什么 |
   |----------|--------|--------|
   | **`html2json` 自动出图**（渐变 / 圆角 / 阴影 / 阴影+渐变，`ss=4` 写死） | 不用选：内部一律 SS（`gen_gradient_stops` / `gen_shadow_card(..., ss=4)` / `ss_shape_mask`） | 药丸/正圆这类强曲率在设计稿里就那么写，脚本不可能知道形状意图；本地出图成本低 |
   | **手写调用 · 强曲率**：圆 / 圆钮 / 药丸 / 细圆条 / 小圆角条 / 圆角≈min(w,h)/2 | `gen_res.rounded_rect_ss(w, h, radius, fill, border=None, border_w=1, ss=4)` | ≥4x 超采样 + **面积平均（Image.BOX）**缩回 + alpha 预乘；边界平均误差 5.6~11.6/255 |
   | **手写调用 · 大半径卡片圆角**（radius ≪ min(w,h)/2） | 继续用 `rounded_rect`（1x 直画 + α 高斯羽化 σ0.5，FT-008），**默认行为不变** | 它的 α≥128 轮廓与 1x 直画**逐像素一致**（FT-008 的修复目的：倒角宽度不漂），几何信息稳 |
   | **手写调用 · 其它带 `radius` 的函数**（`gen_gradient` / `gen_gradient_stops` / `rounded_card` / `gen_shadow_card` / `gen_btn9`） | 加 `ss=4` 即走 SS；**不传（`ss=0`）= 历史的 FT-008 口径** | 默认逐字节不变，老调用者不受影响 |

   **量化对比**（16x 超采样覆盖率当理想值；边界带 mean/p95，单位 /255；本机 Pillow 12.2.0
   / numpy 2.5.1；复现：构造同尺寸形状，取「理想 α ∈ (4,251)」的像素比 `|α_实测 − α_理想|`；
   **2026-09-19 复测：真值与管线都改成 BOX 后的数字**，脚本 `temp/a1_remeasure.py`）：

   | 形状 | FT-008（`ss=0`） | `ss=4` | `ss=8` |
   |------|----------------|--------|--------|
   | 药丸 80×40 r20 | **39.6 / 102.0** | 7.7 / 25.0 | 1.9 / 5.0 |
   | 圆 30×30 r15 | **48.7 / 104.0** | 7.3 / 21.0 | 1.9 / 5.0 |
   | 圆钮 31×31 r15 | **47.7 / 100.0** | 7.8 / 20.0 | 3.6 / 12.0 |
   | 细圆条 200×8 r4 | **25.7 / 54.0** | 5.6 / 10.0 | 2.4 / 3.0 |
   | 大卡片 300×180 r16 | 48.3 / 158.0 | 10.7 / 26.0 | 2.3 / 6.0 |
   | 方角 64×24 r4 | 45.0 / 119.0 | 11.6 / 21.0 | 2.7 / 5.0 |

   → 强曲率误差是 FT-008 的 1/4~1/6；小尺寸强曲率可用 `ss=8`（mean <4、p95 ≤12）。
   （改前 LANCZOS 口径旧数字（真值也用 LANCZOS）仅作历史对照：药丸 35.4/97.9 → ss4 5.3/22.7；
   真值换成 BOX 后差距拉大，尤其细圆条：ss4 从 11.7 降到 5.6。）

   **`html2json` 出图同样口径的实测**（v0.27.76，脚本 `temp/html2json_ss/measure.py`，
   理想值 = 同算法 16x；mean/p95，阴影片看 α 最大偏差）：
   药丸渐变 80×40 35.4/97.9 → **5.3/22.8**；正圆渐变 48×48（`50%`）31.7/74.0 → **4.0/8.0**；
   大圆角渐变卡 120×80 r16 43.9/153.0 → **10.0/22.0**；阴影片 140×60 α-max 170 → **20**；
   阴影药丸 80×40 α-max 125 → **23**。暗边回归：渐变边界像素 RGB 与「同列内部基准」偏差 ≤ 4/255。

   **为什么手写的大半径卡片仍保留 FT-008**：2026-09-01 沛哥反馈「超采样会引入像素网格
   取整偏移 → 圆角倒角视觉变宽 1px」（FT-008 注释原文）；钟工 2026-09-16 只把 **html2json 自动出图**
   全切 SS，`rounded_rect` 默认（FT-008）与各函数 `ss=0` 路径逐字节不变
   （2026-09-16 实测：5 形状 × 「改动前代码复刻」输出比对全同）。

   设备端验证：案例 `projects/translate/lvgl-widgets-uiv1/`（Z21/F133/F136）的 SeekBar 圆钮
   `sk_thumb` + 开关药丸 `sw_on/sw_off` + 细圆条 `sk_fill/sk_track`。

   ⚠️ **自画合成层的调用方**（自己叠阴影/高光/渐变）：用**公开**的 `gen_res.ss_shape_mask(w, h,
   radius, ss=4)`（L 模式覆盖率）配合 `ImageChops.multiply(layer.getchannel('A'), mask)` ——
   **只缩 alpha**；千万别 `paste(color_layer, mask)`（会把 RGB 一起按 mask 缩小 → 边界发黑 = 暗边 halo）。
   （html2json 的「渐变+阴影」分支就是这套写法。）

9. **尺寸核对机制**（谁在什么时候核）：出图脚本自检 → `check_all`/`flythings_verify_assets`
   全量核对 → 像素验收。`verify_assets` 只**报**不**修**：`missing`（缺图）/`mismatch`（盒子不等）
   = FAIL；`stretched`（手绘图被引擎拉伸）/`skippedNoBox`（盒子未知）只提示。改图为**重新出图**，
   不要手改 json 去迁就旧图（盒子是设计真相）。

10. **★ 缩回算子铁律 + 低对比度边缘（2026-09-19 钟工真机反馈入规：选中条边界有锯齿）**

   **现象**：浅色选中条（`#F2F3FF`）压浅底（`#F3F3F3`）时，左右圆角在 8× 放大下有肉眼可见的
   毂齿 + 一圈断续暗边；而当时的审计工具（只看 alpha 硬台阶）**一条都没报**。

   **根因（两条，都很容易重复犯）**
   - **重采样算子选错**：超采样后缩回用 `LANCZOS` → **负瓣（Gibbs 振铃）**。在「透明 ↔ 实色」
     硬边上预乘色 `Cpm` 被推出 `[0, α·C]` → 反预乘后 RGB 越界：欠冲被 clip 成近黑（α 仍 8~56/255）
     = **暗边**；过冲 clip 成纯白 = **白点**。实测（200×36 r18 药丸，8× SS）：部分透明像素里
     RGB 偏离填充色 >6 的有 **88 个**（如 `(116,116,119,α=56)`）+ 不透明纯白杂点 **28 个**。
   - **低对比度边缘没有归一化判据**：`#F2F3FF` vs `#F3F3F3` **只有 B 通道差 12 级，亮度差仅 ~1.4**
     → 任何亮度/灰度阈值或亮度梯度算子都是噪声（连“边在哪”都定位不到）。

   **铁律**
   1. 凡 **浅色/低对比度的圆角、描边、斜线** → **必须超采样渲染（≥4×，强曲率/浅色压浅色建议 8~16×）
      + 面积平均（AREA/BOX）下采样**；
   2. **带直通 α 的边界禁止 LANCZOS/BICUBIC/BILINEAR**（负瓣 → 暗边/白点）；只有整幅不透明
      （无 α 边界）的插值类缩放可以用 LANCZOS；
   3. 多色（描边+填充）分层时：**2026-09-19 起改用「整像素描边带」**（不按覆盖率混合描边↔填充）——
      `gen_res.coverage_ring` / `bordered_cov`：描边像素 = 「被描边环触达（A外>0）且未被内形状
      完整覆盖（A内<255）」的**整像素**，整体上描边色；其余上填充色；α = A外。
      旧写法 `Cpm = border_c·max(0,A外−A内) + fill_c·A内` 在**圆角对角线**上会出 1~4px 混色带
      （描边环只有 0.707px 厚）→ `dirty`/`speck` WARN。代价：圆角处描边视觉厚度 ~1.41px
      （直线段仍 1px），与设备端 1px 描边光栅化一致。
   4. **按下态描边必须跟随按下色**：`gen_res.gen_btn9(border=None)` 已改（旧口径按下态沿用常态
      填充色当描边 → 角上「旧色×新色」混色）；描边色与填充色相同时退化为单色区（最干净）。
   5. **发丝线（1px 通栏线）**：轴对齐线保持 **1x 直画**（不要超采样）；但**只能画在形状
      「全覆盖（α==255）」的列/行段上**——越过圆角弧的线头会与弧边部分透明像素相邻 → 被判 `dirty`。
   6. **审计必须用「逐通道最大差 + 按该处对比度归一化」的阶梯/残差判据**
      （`tools/qa/aa_audit.py` v2：`resid_bad` = 边界像素到「外侧底色↔内侧形色」连线的 Chebyshev
      残差 > max(5, 0.6×对比度)；`hard_diag` = 斜/弧边界成片的 1px 硬阶跃），跑 `--fail` 期望
      真缺陷 0 张；**已接进 `check_all` 第 21 项**（扫 `resources/images/**`，真缺陷 = FAIL，
      WARN/EXEMPT 逐条打理由；`.9.png` marker 环用审计内置豁免）。
   7. 真机复核用 **8× 最近邻**放大看边界（平滑放大/缩放会直接抹掉这类缺陷）。

   **复核命令**：`python tools/qa/aa_audit.py <工程>/resources/images --fail`（口径/豁免见
   `tools/qa/README.md`；完整生图规范 `references/kb/image-gen-standard.md` §1.2/§1.3/§1.4/§1.5）。

   **已落地（2026-09-19，v0.27.96-open）**：`gen_res._ss_down`/`_ss_mask` + 全链路 14 处带 α 缩回点
   已改 `Image.BOX`；描边/发丝线/按下态三条口径已改出图（不登记白名单）。实测：
   案例 19 张 `.9.png` 的 WARN 从 **18 张（dirty 172 / speck 176）** → **11 张（dirty 0 / speck 0，
   余下全是切点区 `hard_diag`：同一几何在 ss=16/64/256 下同值 = 几何固有）**。

   **尚存误报（待定，见 `tools/qa/README.md` §3）**：① 多色位图字形（emoji）的 `resid_bad`
   （换 LANCZOS 也一样 → M3 两区模型的局限）；② 高对比 1px 描边压深色填充时 `hard_diag` 占比
   可到 100%（需三区制剖面模型）。

## 3. 入参与返回

`assets` 为 JSON 数组字符串，每项：

```json
{"name": "icon_ok.png", "size": 128,
 "prompt": "cute white cartoon sheep, game icon",
 "emoji": "🐑",
 "color": "#42C9FF", "kind": "check"}
```

- `prompt`：有则优先 AI 生图
- `emoji`：AI 失败后用它
- `color` / `kind`：线条兜底参数；`kind` 可选 `check/charging/wifi/alert/circle/square/star/heart`
- `name` 必填（自动补 `.png`）
- 返回每项实际生成方式（`method: ai/emoji/line`）

## 4. 生成后必做

跑 `flythings_verify_assets`（或 `check_all` 第 17 项）：引用存在 + **自动生成图尺寸严格 == 盒子**
（盒子 = 控件 position，**以及 thumb 自有尺寸子盒 `thumb.size`**；`missing` / `mismatch` = FAIL；
手绘图被引擎拉伸记 `stretched` 仅提示；盒子未知记 `skippedNoBox` 并写 warning）。
第 11 项用同一份判定（含 thumb 子盒）。

若项目有 `DESIGN.md`（新项目第一版视觉应当有）：`check_all` **第 18 项设计令牌漂移检测** 会自动核对
json 里的颜色/字号是否都落在 DESIGN.md 令牌内。口径：
- 令牌外的色值/字号 = **FAIL**（漂移；结构值 0 / -1 / 16777215 例外）
- 无 `DESIGN.md` 或令牌表未填全 → **NOTE 跳过**（兼容存量工程）
- 单点例外在 DESIGN.md 写一行 `漂移豁免: #RRGGBB 18` 留痕（比改代码好溯源）
- 间距梯度外的纵向间距 → **WARN**（对齐/芯距可能正常，人工确认）

## 5. 相关

- HTML 原型侧的效果转图与属性写法 → `html-subset-quickref.md`
- 控件层图片字段语义 → `uicontrols/button-fields.md`、`uicontrols/circlebar-fields.md`
- 产物核对/编辑器预检/像素验收流程 → `ui-layout-verify.md`（§3 预检口径与本文 §2 铁律 #1/#8 一致）
- 像素级渲染坑（半透明图贴纯色底发脏、圆角四角发黑、listview 黑块）→ `pixel-analysis-ai.md`
