# UI 图片资源铁律与 PNG 抗锯齿管线

> 检索导引：生成图标/瓦片/按钮背景/卡片图 / 图片尺寸对不上 / 圆角四角发黑 / 按钮透背景 /
> 图片锯齿 / 1x 直画 / 大图缩小 / 走哪条路出图 时命中。
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

1. **图片尺寸必须与 json 控件尺寸一致**（瓦片 76×76 控件 → 76×76 图；槽位 72×72 → 72×72 图）。
   不要生成大图让控件缩放，也不要小图拉伸。
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
     `glyph_icon_ex` / `line_icon` / `frames_loading_gif`（全部内置抗锯齿）

   **PNG 防锯齿五要素**：尺寸 == 控件 position / ≥4x 超采样 + LANCZOS 缩回或 α 羽化（sigma≈0.5）/
   端点 round cap / 圆角四角 alpha=0 / 生成后跑 `check_all` 校验（#11 图片尺寸 + 四角 alpha）。

   完整规范见仓库 `ui_tools/HTML_SUBSET.md`「切图 / 图片资源铁律」#8 #9。

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

跑 `flythings_verify_assets`（或 `check_all` 第 17 项）：引用存在 + **自动生成图尺寸严格 == 控件 position**
（`missing` / `mismatch` = FAIL；手绘图被引擎拉伸记 `stretched` 仅提示）。

## 5. 相关

- HTML 原型侧的效果转图与属性写法 → `html-subset-quickref.md`
- 控件层图片字段语义 → `uicontrols/button-fields.md`、`uicontrols/image-path-rule.md`
- 像素级渲染坑（半透明图贴纯色底发脏、圆角四角发黑、listview 黑块）→ `pixel-analysis-ai.md`
