---
id: devflow-ui-asset-rules
title: UI 图片资源铁律与 PNG 抗锯齿管线
category: devflow
status: review
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: []
tags: [2026-09-19, 09-20 补, A1, A3, M5 落地, BOX, 面积平均, 逐像素覆盖率, 整像素描边带, 描边与填充混色, 按下态描边, 发丝线裁剪, 形状外不透明, 图标贴边, 没有透明像素, 切图缺倒角]
evidence: []
---
# UI 图片资源铁律与 PNG 抗锯齿管线

> 检索导引：生成图标/瓦片/按钮背景/卡片图 / 图片尺寸对不上 / 圆角四角发黑 / 按钮透背景 / 图片锯齿 / 1x 直画 / 大图缩小 / 走哪条路出图 / **滑块圆钮·开关药丸·圆形钮发锯齿 / thumb.size 与图对不上 / 超采样（SS）/ 某形状该用哪个出图函数**/ 浅色形状压浅底边缘有锯齿 / 选中条边界有毛边·阶梯 / 圆角不平滑 / 描边发脏 / 暗环 白点 脏边 / 低对比度边缘 / LANCZOS 振铃 / 重采样算子怎么选 / 抗锯齿审计（aliasing / 边缘阶梯 / 发毛）→ 本文（#8 / #10）。
> 2026-09-19/09-20 补（A1/A3/M5 落地）：缩回算子 `Image.BOX` / 面积平均 / 逐像素覆盖率 / 整像素描边带 / 描边与填充混色 / 按下态描边 / 发丝线裁剪 / **图片背景是黑的·应做成透明·烘了底色·页底色填进图 / 形状外不透明 / 图标贴边 / 没有透明像素 / 切图缺倒角 / 圆角缺失·直角·方角磁贴 / 圆角半径不对 / 四角不一致 / 倒角审计 / 标准侧 alpha 与 Lite 侧 RGB565+colorkey 差异**→ #11（透明底）/ #12（倒角）；门禁 = check_all 第 21/22/23 项（`aa_audit` / `corner_audit` / `alpha_bg_audit`）。
> 2026-09-27 补（现场反馈："多屏拼接几个图片倒角线变粗了，以前 MCP 修复过的"）：**倒角线变粗 / 描边比别的行厚 / 圆角发糊 / 弧线粗一档 / 描边发亮 / 角上一条亮带 / 与相邻行不一致 / 同一套图不一样厚 / 弧上 2px 实色带 / 同族图口径不一致 / 1.41px / 图标家族不一致 / 改宽只平移不重采样**→ #13。
> 用途：`flythings_generate_ui_assets` 的完整口径 + 全仓库通用的图片资源铁律（该工具 docstring 只保留要点，长尾与铁律细节在这里）。

## 1. 三级降级策略（任何环境都能出图）

| 级别 | 条件 | 效果 |
|------|------|------|
| ① AI 生图 | 配置了 `OPENAI_API_KEY` 且网络可达 | gpt-image-2 透明底，最精致 |
| ② 本地 emoji 渲染 | Windows `seguiemj.ttf` / Linux `NotoColorEmoji` | 卡通风（羊了个羊同款） |
| ③ 线条/几何兜底 | Pillow 画圆/方/星/心/对勾 | 无 AI、无 emoji 字体也能出 |

最终用户（客户）没有 AI 能力时自动降级，**无需任何外部依赖**。

## 2. 图片资源铁律（2026-08-29 羊了个羊实战，务必遵守）

1. **图片尺寸必须与「盒子」一致**（瓦片 76×76 控件 → 76×76 图；槽位 72×72 → 72×72 图）。
   **引擎行为先记清（2026-10-01 需求方口径）：图 != 盒时引擎「拉伸填充」，不报错**—— 所以这条是**质量纪律**
   （非整数缩放必糊/变形、正圆变椭圆），不是引擎贴不上；不要生成大图让控件缩放，也不要小图拉伸。
   **盒子有三种来源**（`verify_assets` / `check_all #11 #17` 都按这个口径核）：
   | 盒子 | 字段 | 说明 |
   |------|------|------|
   | 控件 position | `backgroundPic` / `picTab.picN` / `progressPic` / `secondaryProgressPic` / `thumbPic` | 主盒（默认） |
   | **`thumb.size`**| `thumb.normalPic` / `thumb.pressedPic`（SeekBar / CircleBar 滑块） | **自有尺寸**子盒，不是控件盒（v0.27.75 补） |
   | `iconPosition` / `textPosition` | 按钮/复选框的图标与文字、`textview` 的文字盒 | **子盒**（`{left,top,width,height}`，规格 `sharedTypes.iconBox`）：坐标**相对控件盒**；有图标的按键靠 `textPosition.left` 让开图标区，文字的 `alignment` 也相对该盒算 |
   ⚠️ **`textPosition` 实测有两种写法，只有一种是相对**（2026-10-05 实测 33 处）：**9 处落在控件盒内**（相对写法 —— 手写模板全属此类，是真口径）；**24 处按相对解释会整体越出控件盒**，那是把 `position` 逐字拷贝成绝对坐标（生成物/示例）。引擎对越界值的处置**未实测**，故离线渲染器照相对画 + 记账（`json2img --report` 报「按相对控件盒解释会越界」）；写新 json 一律给**不越界的相对值**，或干脆省掉该键（省 = 整控件盒）。
   ⚠️ **thumb 曾是核对盲区**（2026-09-16 案例）：`sk_thumb.png` 31×31 而 json 写 `thumb.size` 30×30，`check_all` 与 `verify_assets` 一路 PASS（两边都当「自有尺寸」跳过）→ 真机滑块圆钮与轨道对不上。现行口径：
   - **自动生成图**（`resources/images/`，铁律 #6/#9）thumb 图尺寸 != `thumb.size` → **FAIL**（`mismatch[]`）
   - **手绘 thumb**（`slider_/`、`navi/` 等）失配 → 仅 `stretched[]` 提示：官方基准工程 `SampleUI-New/ui/1024x600/testSlider.json` 本身就是 `slider_/jdt_ht.png` 35×34 配 `thumb.size` 33×35（引擎会拉伸），当 FAIL 会造假警报（基准工程零误报是校准目标）
   - 没写 `thumb.size` 或为 0 → 跳过核对 + 写 `skippedNoBox[]` / warning（不误报）
   - 编辑器（`ui_editor._preflight`）同口径：自动生成 thumb 失配给红标，手绘不报
2. **圆角卡片图四角必须真透明（alpha=0）**：渐变/填充底是整矩形画的，圆角只是描边轮廓，必须用圆角 mask 裁剪（`putalpha`）清掉弧线外角落；阴影模糊（`GaussianBlur`）会溢出到弧线外，最后整体再裁一次圆角清掉残影。
   - 通用函数 `gen_res.rounded_card()`（渐变 + 圆角 + 描边 + 高光）已内置裁剪；`gen_res.gen_gradient(..., radius=r)` 也已修复（radius>0 自动裁圆角）
3. **用透明角图片的按钮不要设 `bgColorTab`**：透明角会透出按钮底色而不是窗口背景；需要透背景的图片按钮（瓦片/槽位/图标钮）不放 `bgColorTab`；纯文字按钮才用底色。
4. **功能按钮尽量用图片按钮**：`picTab{pic0: normal, pic1: pressed（_p 后缀）}` 两态图。
5. **生成后必须检查四角 alpha**：`img.getpixel((2,2))[3] == 0` 才算合格。
6. **路径规范**（2026-09-01 需求方要求）：自动生成的图片一律放 `<项目>/resources/images/`；json 布局引用路径写 `images/xxx.png`（相对 resources 目录，与设备/ftu 加载一致）。返回的 `path` 字段就是 `images/xxx.png`，直接填 json 的 `backgroundPic` / `picTab.pic0` / `picTab.pic1`；**不要写绝对路径，也不要带 `resources/` 前缀**。
7. **PNG 生成管线铁律**（2026-09-08 需求方定规，方案 A 显式化）：AI/客户端需要图片时**禁止自写绘制代码 1x 直画、禁止用外部生图能力直出小图交付**（1x 二值 alpha 无抗锯齿、大图缩小边缘必锯齿）。
   **只走三条路**：CSS 效果交 `html2json` 自动转图（内置抗锯齿）/ 本工具（`flythings_generate_ui_assets`）生成 / `gen_res` 公开函数：`rounded_card` / `gen_gradient` / `gen_shadow_card` / `emoji_icon_ss` / `glyph_icon_ex` / `line_icon` / `frames_loading_gif` / **`rounded_rect_ss`（强曲率形状，见 #8）**（全部内置抗锯齿）。
   **PNG 防锯齿五要素**：尺寸 == 盒子（#1）/ **强曲率形状走 `rounded_rect_ss`（≥4x 超采样 + 面积平均 BOX，#8）**——⚠ **2026-09-19 落地**：缩回算子已从 LANCZOS 改成 `Image.BOX`（带直通 α 的边界**不得**用 LANCZOS，见 #8 末与 #10）/ `html2json` 的 CSS 效果出图**一律 SS（`ss=4`），不用选**（v0.27.76）/ 端点 round cap / 圆角四角 alpha=0 / 生成后跑 `check_all` 校验（#11 图片尺寸 + #17 产物核对 + 四角 alpha）。
完整规范见仓库 `ui_tools/HTML_SUBSET.md`「切图 / 图片资源铁律」#8 #9。

8. **★ 形状分类出图口径（FT-010 + v0.27.76，2026-09-16 定）**：按**调用方**分两条口径 —— **`html2json` 的 CSS 效果出图一律 SS**（2026-09-16 拍板：固定本地脚本工作，不额外耗 token，不再保留 1x+α 羽化那条路）；**手写调用**按曲率强度选。选错就是真机上肉眼可见的锯齿（经需求方反馈「滑块圆钮 / 开关有锯齿」的技术根因）。

   | 调用场景 | 用哪个 | 为什么 |
   |----------|--------|--------|
   | **`html2json` 自动出图**（渐变 / 圆角 / 阴影 / 阴影+渐变，`ss=4` 写死） | 不用选：内部一律 SS（`gen_gradient_stops` / `gen_shadow_card(..., ss=4)` / `ss_shape_mask`） | 药丸/正圆这类强曲率在设计稿里就那么写，脚本不可能知道形状意图；本地出图成本低 |
   | **手写调用 · 强曲率**：圆 / 圆钮 / 药丸 / 细圆条 / 小圆角条 / 圆角≈min(w,h)/2 | `gen_res.rounded_rect_ss(w, h, radius, fill, border=None, border_w=1, ss=4)` | ≥4x 超采样 + **面积平均（Image.BOX）**缩回 + alpha 预乘 |
   | **手写调用 · 大半径卡片圆角**（radius ≪ min(w,h)/2） | 继续用 `rounded_rect`（1x 直画 + α 高斯羽化 σ0.5，FT-008），**默认行为不变**| 它的 α≥128 轮廓与 1x 直画**逐像素一致**（FT-008 的修复目的：倒角宽度不漂），几何信息稳 |
   | **手写调用 · 其它带 `radius` 的函数**（`gen_gradient` / `gen_gradient_stops` / `rounded_card` / `gen_shadow_card` / `gen_btn9`） | 加 `ss=4` 即走 SS；**不传（`ss=0`）= 历史的 FT-008 口径**| 默认逐字节不变，老调用者不受影响 |

   **量化对比**（16x 超采样覆盖率当理想值；边界带 mean/p95，单位 /255；**2026-09-19 复测：真值与管线都改成 BOX 后的数字**；复现：构造同尺寸形状，取「理想 α ∈ (4,251)」的像素比 `|α_实测 − α_理想|`）：

   | 形状 | FT-008（`ss=0`） | `ss=4` | `ss=8` |
   |------|----------------|--------|--------|
   | 药丸 80×40 r20 | **39.6 / 102.0**| 7.7 / 25.0 | 1.9 / 5.0 |
   | 圆 30×30 r15 | **48.7 / 104.0**| 7.3 / 21.0 | 1.9 / 5.0 |
   | 圆钮 31×31 r15 | **47.7 / 100.0**| 7.8 / 20.0 | 3.6 / 12.0 |
   | 细圆条 200×8 r4 | **25.7 / 54.0**| 5.6 / 10.0 | 2.4 / 3.0 |
   | 大卡片 300×180 r16 | 48.3 / 158.0 | 10.7 / 26.0 | 2.3 / 6.0 |
   | 方角 64×24 r4 | 45.0 / 119.0 | 11.6 / 21.0 | 2.7 / 5.0 |

   → 强曲率误差是 FT-008 的 1/4~1/6；小尺寸强曲率可用 `ss=8`（mean <4、p95 ≤12）。设备端验证：案例 `projects/translate/lvgl-widgets-uiv1/`（Z21/F133/F136）的 SeekBar 圆钮 `sk_thumb` + 开关药丸 `sw_on/sw_off` + 细圆条 `sk_fill/sk_track`。

   ⚠️ **自画合成层的调用方**（自己叠阴影/高光/渐变）：用**公开**的 `gen_res.ss_shape_mask(w, h, radius, ss=4)`（L 模式覆盖率）配合 `ImageChops.multiply(layer.getchannel('A'), mask)` —— **只缩 alpha**；千万别 `paste(color_layer, mask)`（会把 RGB 一起按 mask 缩小 → 边界发黑 = 暗边 halo）。（html2json 的「渐变+阴影」分支就是这套写法。）

9. **尺寸核对机制**（谁在什么时候核）：出图脚本自检 → `check_all`/`flythings_verify_assets` 全量核对 → 像素验收。`verify_assets` 只**报**不**修**：`missing`（缺图）/`mismatch`（盒子不等）= FAIL；`stretched`（手绘图被引擎拉伸）/`skippedNoBox`（盒子未知）只提示。改图为**重新出图**，不要手改 json 去迁就旧图（盒子是设计真相）。

10. **★ 缩回算子铁律 + 低对比度边缘（2026-09-19 需求方真机反馈入规：选中条边界有锯齿）现象/根因**：浅色选中条（`#F2F3FF`）压浅底（`#F3F3F3`）时，左右圆角 8× 放大下有肉眼可见锯齿 + 一圈断续暗边，而当时审计工具（只看 alpha 硬台阶）**一条都没报**。两条根因：① **重采样算子选错**—— 超采样后缩回用 `LANCZOS` → **负瓣（Gibbs 振铃）**：硬边上预乘色被推出 `[0, α·C]`，反预乘后 RGB 越界，欠冲 clip 成近黑（α 仍 8~56/255）= **暗边**、过冲 clip 成纯白 = **白点**（实测 200×36 r18 药丸 8× SS：偏离填充色 >6 的半透明像素 **88 个**+ 不透明纯白杂点 **28 个**）；② **低对比度边缘无归一化判据**—— `#F2F3FF` vs `#F3F3F3` **B 通道仅差 12 级、亮度差 ~1.4**→ 亮度/灰度阈值与亮度梯度算子全是噪声（连"边在哪"都定位不到）。

   **铁律**
   1. 凡 **浅色/低对比度的圆角、描边、斜线**→ **必须超采样渲染（≥4×，强曲率/浅色压浅色建议 8~16×）+ 面积平均（AREA/BOX）下采样**；
   2. **带直通 α 的边界禁止 LANCZOS/BICUBIC/BILINEAR**（负瓣 → 暗边/白点）；只有整幅不透明（无 α 边界）的插值类缩放可以用 LANCZOS；
   3. 多色（描边+填充）分层时：**2026-09-19 起改用「整像素描边带」**（不按覆盖率混合描边↔填充）—— `gen_res.coverage_ring` / `bordered_cov`：描边像素 = 「被描边环触达（A外>0）且未被内形状完整覆盖（A内<255）」的**整像素**，整体上描边色；其余上填充色；α = A外。旧写法 `Cpm = border_c·max(0,A外−A内) + fill_c·A内` 在**圆角对角线**上会出 1~4px 混色带（描边环只有 0.707px 厚）→ `dirty`/`speck` WARN。代价：圆角处描边视觉厚度 ~1.41px（直线段仍 1px），与设备端 1px 描边光栅化一致。
   4. **按下态描边必须跟随按下色**：`gen_res.gen_btn9(border=None)` 已改（旧口径按下态沿用常态填充色当描边 → 角上「旧色×新色」混色）；描边色与填充色相同时退化为单色区（最干净）。
   5. **发丝线（1px 通栏线）**：轴对齐线保持 **1x 直画**（不要超采样）；但**只能画在形状「全覆盖（α==255）」的列/行段上**——越过圆角弧的线头会与弧边部分透明像素相邻 → 被判 `dirty`。
   6. **审计必须用「逐通道最大差 + 按该处对比度归一化」的阶梯/残差判据**（`tools/qa/aa_audit.py` v2：`resid_bad` = 边界像素到「外侧底色↔内侧形色」连线的 Chebyshev 残差 > max(5, 0.6×对比度)；`hard_diag` = 斜/弧边界成片的 1px 硬阶跃），跑 `--fail` 期望真缺陷 0 张；**已接进 `check_all` 第 21 项**（扫 `resources/images/**`，真缺陷 = FAIL，WARN/EXEMPT 逐条打理由；`.9.png` marker 环用审计内置豁免）。
   7. 真机复核用 **8× 最近邻**放大看边界（平滑放大/缩放会直接抹掉这类缺陷）。

   **复核命令**：`python tools/qa/aa_audit.py <工程>/resources/images --fail`（口径/豁免见 `workspace/tools/qa/README.md`；完整生图规范 `workspace/references/kb/image-gen-standard.md` §1.2/§1.3/§1.4/§1.5）。

   **已落地（2026-09-19，v0.27.96-open）**：`gen_res._ss_down`/`_ss_mask` + 全链路 14 处带 α 缩回点已改 `Image.BOX`；描边/发丝线/按下态三条口径已改出图。实测：案例 19 张 `.9.png` 的 WARN 从 **18 张（dirty 172 / speck 176）**→ **11 张（dirty 0 / speck 0，余下全是切点区 `hard_diag`：同一几何在 ss=16/64/256 下同值 = 几何固有）**。
   **尚存误报（待定，见 `workspace/tools/qa/README.md` §3）**：① 多色位图字形（emoji）的 `resid_bad`（换 LANCZOS 也一样 → M3 两区模型的局限）；② 高对比 1px 描边压深色填充时 `hard_diag` 占比可到 100%（需三区制剖面模型）。

11. **★ 形状类资产必须真透明底（标准侧支持 PNG alpha，禁烘底色）**（2026-09-20 需求方入规：「**控件里面图片背景是黑色的，应该做成透明的，这个设计不符合 flyThings OS 平台的能力**」）：
    - **必须 RGBA 真透明（形状外 α=0）**：图标 / 磁贴 / 环形 / 指针 / 开关滑块 / 图形装饰 / 圆角卡片底 / 药丸（track·fill·seg·sw）/ 圆钮 / 表盘；
    - **不要求透明区（「形状外没有外面」，登记理由豁免）**：满幅底图・渐变壁纸・照片内容图・全屏遮罩・**1px 通栏线**（发丝线轴对齐）・软阴影翼；
    - **禁止**把页面底色/黑底烘进图当透明 —— 那是 **Lite（MCU）侧 RGB565 + colorkey**的做法（无 α 混合，见 `knowledge/mcu/*` 与 `workspace/references/kb/lite-input-pipeline.md`），**两套口径不能混**（MEMORY 铁律 #17：两侧严格隔离）；把 Lite 做法带到标准侧 = 整图没有透明像素 → 拦。
    - 图标类还要求**四周 ≥1px 透明**（不贴死图边）。
    - **判定/门禁**（数字与几何都有出处，禁拍脑袋）：`ui_tools/alpha_bg_audit.py` —— 整图 `min(α) ≥ 250` = `no_alpha`、内切/图标族角块不透明率 ≥0.5 = `corner_opaque`、最外 1px 环不透明率 ≥0.25（或任一边 ≥0.9）= `edge_bleed` → **FAIL**；**已接进 `check_all` 第 23 项**。分类登记表 `ui_tools/asset_audit_rules.json`。

12. **★ 矩形/卡片/磁贴/药丸必须有倒角（半径按 DESIGN.md 圆角令牌；禁直角）**（2026-09-20 需求方入规：「**主界面大量图片依旧存在切图缺倒角问题，这个问题三番五次提出来过的。必须给我从设计标准和拦截上处理好**」）：
    - **半径令牌出处**= 工程 `<项目>/DESIGN.md` 的「圆角令牌」表（磁贴 squircle `n=5,r=30`、9-patch 卡片 14、面板 24、缩略图 16/12、药丸 = `min(w,h)/2`、圆/环 = `min(w,h)/2`）；`ui_tools/asset_audit_rules.json` 是机读副本（改令牌要同步改它）。
    - **几何判据（可复算）**：沿圆角所在边界行/列量「边起跑距离」`d` = 从角点起第一个 α≥128 的像素位置；半径 r 满足 `d = r - sqrt(r - 0.25)` → 反解 `r_est = (0.5+sqrt(d))**2+0.25`。**直角残留 = `d ≤ 1`**（α 铺到角点）。
    - **判定**：`r_est < 0.5×令牌` 或直角残留或四角极差 >4px 且 min/max <0.5 → **FAIL**；`< 0.8×令牌` → WARN。工具 `ui_tools/corner_audit.py`，**已接进 `check_all` 第 22 项**。
    - **反例（必须记住）**：**把不透明图形 `alpha_composite` 到圆角底图上 = 把下层圆角抹平**（`over` 的 α = `src_α + dst_α(1-src_α)`，`src_α=255` 处 α 恒为 1）。实测：主屏 `tile_photos.png`/`tile_place.png` 底边图形铺满 → 底部两角 `d=0`（r_est 0.5px）、上两角 `d=25`（r_est 30.5px）→ 真机就是两个「方角磁贴」。**修法（推荐 ①）**：① 渐变底 + 图形都画在 `size×SS` 画布，最后一次套形状遮罩、只缩回一次（同一轮廓一次成图，整图只有一条抗锯齿边）；② 内容先按形状 α 裁剪 → composite → 最后 `putalpha(形状 α)`（轮廓只由遮罩决定）。
    - **出图验收命令**：`python ui_tools/corner_audit.py <工程>/resources/images --fail` + `python ui_tools/alpha_bg_audit.py <工程>/resources/images --fail`（证据图：`<name>.corner.png` 四角 8× 放大 + 违例角红框；`<name>.alpha.png` 违例角块/边环标红）。回归样本 `tools/qa/samples/` + `python tools/qa/run_samples.py`。真实口径文档：`workspace/references/kb/image-gen-standard.md` **§7（透明底与圆角）**。

13. **★ 倒角/描边「变粗」与同族一致性（2026-09-27 需求方入规）**

    > 症状检索词：**倒角线变粗 / 描边比别的行厚 / 圆角发糊 / 弧线粗一档 / 描边发亮 / 角上一条亮带 / 与相邻行不一致 / 同一套图不一样厚 / 弧上 2px 实色带 / 同族图口径不一致 / 图标家族不一致**。

    **现场原话**：「**新做的 UI 切图多屏拼接里面几个图片的倒角线变粗了，这个问题以前 MCP 应该修复过的。你再检查下 MCP 如果说明不够明显就修改。**」

    **现场实测**（同族 452 宽行底图，脚本量 45° 弧上同色连续段）：`srow452x50.png`（素面，`r=12`，设置页多数行底）= 无描边 / **1px**；`srow452x38.png` = 有 1px / ~1px；`srow452x46.png` = 有 1px（`#31313A`）/ **~2px**；`af_btn216x48.png` = 有 1px（`#31313A`）/ **~2px**。

    **症状 → 根因 → 修法 → 拦截（一条链）**

    | 症状 | 根因（三选一） | 修法 | 拦截/自检 |
    |---|---|---|---|
    | 倒角线变粗 / 与相邻行不一致 | **同族图混了两种口径**：一部分带 1px 描边、一部分素面 | **同族同口径**：要么全带描边、要么全不带；半径也统一到同一令牌值（例 452 行底统一 `r=12`） | 闸门抓不到（见下）；出图时同族同函数 + 人眼 8× 最近邻复核 |
    | 弧线粗一档（直线段正常 1px） | **整像素描边带的弧上代价**（#10 铁律 3）：`coverage_ring` 整像素指派 → 弧上视觉厚度 **~1.41px**（对角投影 √2）——**已知代价，不是 bug**| 把「1px 描边 + 填充」改走 `gen_res.bordered_cov(w,h,r,fill,border)`；**不要描边**就 `gen_res.rounded_rect_cov(w,h,r,fill)`；**不要**混用 | `corner_audit --arc-only --fail` |
    | 圆角整体变宽 1px / 发虚 | **取整偏移 / 重采样**（FT-008）：超采样缩回带像素网格取整偏移；或用了 LANCZOS/BICUBIC/BILINEAR | 缩回算子 = `Image.BOX`（面积平均）；带直通 α 的边界**禁**负瓣算子（#8/#10） | `aa_audit --fail`（dirty/speck） |
    | 弧上一圈硬阶梯 / 描边边缘发脏 | **把二值 mask（`coverage_ring`）当 α 层**| `coverage_ring` 只用来**指派颜色**；α 必须走覆盖率（`coverage_mask` / `ring_cov_alpha` / `card9_alpha`） | `corner_audit --arc-only --fail`（#25） |

    **唯一的正确画法（照抄）**：形状（含圆角）一律 **≥4× 超采样 + `AREA/BOX` 面积平均**缩回，α = 覆盖率；要描边 → `gen_res.bordered_cov(...)`（整像素描边带 + 覆盖率 α）；不要描边 → `gen_res.rounded_rect_cov(...)`；**禁**二值 mask 当 α 层 / 手写亚像素混色 `Cpm = 描边·(A外−A内) + 填充·A内`；半透明描边（9-patch 卡片）α = 覆盖率 × 设计 α。

    **一致性要求（这条才是「变粗」的真正解药）**：**同一族（同一页 / 同一视觉层的一组行底、按钮底）必须同一口径**—— 都有 1px 描边 或 都没有，**半径也必须是同一个令牌值**；描边只用在**独立形态**（对话卡片 / 独立按钮）上，**不要把带描边的和素面的混在一条竖向列表里**。可复算判据：**弧上同色实色带 > 1.5px = 「粗一档」**（沿 45° 对角线量连续段）。

    **自检命令（0 token，有退出码）**
    ```bash
    python ui_tools/corner_audit.py <工程>/resources/images --arc-only --fail  # #25 弧线过渡硬阶跃
    python ui_tools/corner_audit.py <工程>/resources/images --fail            # #22 倒角几何
    python tools/qa/aa_audit.py     <工程>/resources/images --fail            # #21 脏边/暗边/白点
    python ui_tools/check_all.py <工程>                                  # 21/22/23/25 一起跑
    ```

    ❗ **闸门盲区（必须知道）**：#21 量脏边/残差、#25 量「覆盖率是否真的从 0 渐变到满值」—— **两者都抓不到「弧上 2px 的描边观感」和「同族图口径不一致」**（本案 5 张图上述审计全 PASS）。所以这一条靠**出图时同族同口径**保证 + **人眼 8× 最近邻**复核。

    ❗ **图标/小件家族一致性**：同一页同族图标要**像素级同款**。改宽度（例：箭头统一成 `26×20`，原图 20×20）时**只平移、零重采样**（canvas 加宽 + `paste` 原图），**禁**`resize` / 重绘 —— 缩放会让小图标发糊、笔画粗细漂移。真实口径文档：`workspace/references/kb/image-gen-standard.md` **§1.6 + §1.7**。

## 3. 入参与返回

`assets` 为 JSON 数组字符串，每项：

```json
{"name": "icon_ok.png", "size": 128,
 "prompt": "cute white cartoon sheep, game icon",
 "emoji": "🐑",
 "color": "#42C9FF", "kind": "check"}
```

- `prompt`：有则优先 AI 生图；`emoji`：AI 失败后用它；`color` / `kind`：线条兜底参数（`kind` 可选 `check/charging/wifi/alert/circle/square/star/heart`）；`name` 必填（自动补 `.png`）
- 返回每项实际生成方式（`method: ai/emoji/line`）

## 4. 生成后必做

跑 `flythings_verify_assets`（或 `check_all` 第 17 项）：引用存在 + **自动生成图尺寸严格 == 盒子**（盒子 = 控件 position，**以及 thumb 自有尺寸子盒 `thumb.size`**；`missing` / `mismatch` = FAIL；手绘图被引擎拉伸记 `stretched` 仅提示；盒子未知记 `skippedNoBox` 并写 warning）。第 11 项用同一份判定（含 thumb 子盒）。

若项目有 `<项目>/DESIGN.md`（新项目第一版视觉应当有）：`check_all` **第 18 项设计令牌漂移检测**会自动核对 json 里的颜色/字号是否都落在 DESIGN.md 令牌内。口径：
- 令牌外的色值/字号 = **FAIL**（漂移；结构值 0 / -1 / 16777215 例外）
- 无 `<项目>/DESIGN.md` 或令牌表未填全 → **NOTE 跳过**（兼容存量工程）
- 单点例外在 DESIGN.md 写一行 `漂移豁免: #RRGGBB 18` 留痕（比改代码好溯源）
- 间距梯度外的纵向间距 → **WARN**（对齐/芯距可能正常，人工确认）

形状类资产额外两道门禁（2026-09-20 M5 起）：

| 项 | 工具 | 判什么 | 免/降 |
|----|------|--------|------|
| **#22 缺倒角**| `ui_tools/corner_audit.py` | 直角残留（`d≤1`）/ `r_est < 0.5×` 圆角令牌 / 四角不一致 → FAIL | `< 0.8×令牌` = WARN；图标・内切族不适用；满幅族 EXEMPT |
| **#23 透明底**| `ui_tools/alpha_bg_audit.py` | 整图无透明像素（`min α ≥ 250`）/ 内切・图标族角区不透明 / 图标贴边 → FAIL | 满幅族（底图・照片・遮罩・1px 线・软阴影）登记豁免 |

两项共用分类登记表 `ui_tools/asset_audit_rules.json`（kind / 圆角令牌 / 豁免理由）——**缺它工具直接报错退出**（不允许缺省拍脑袋）；回归样本 `tools/qa/samples/`（正例 + 反例，`python tools/qa/run_samples.py`）。

## 5. 相关

- HTML 原型侧的效果转图与属性写法 → `knowledge/devflow/html-subset-quickref.md`
- 控件层图片字段语义 → `knowledge/uicontrols/button-fields.md`、`knowledge/uicontrols/circlebar-fields.md`
- 产物核对/编辑器预检/像素验收流程 → `knowledge/devflow/ui-layout-verify.md`（§3 预检口径与本文 §2 铁律 #1/#8 一致）
- 像素级渲染坑（半透明图贴纯色底发脏、圆角四角发黑、listview 黑块）→ `knowledge/devflow/pixel-analysis-ai.md`
