# 🖼️ 图片资源路径铁律（resources 相对路径）

> 2026-09-01 沛哥定规范，修复自动转图/生成图片放错目录导致**设备找不到图**的致命问题。
> 适用：写 json 布局引用图片、MCP 自动转图（CSS 效果）、generate_ui_assets 生成图标、手写逻辑 setBackgroundPic。

## 铁律（必须遵守）

1. **自动生成的图片一律放 `<项目>/resources/images/`**（AI 生图、emoji 渲染、线条兜底、CSS 效果自动转图都一样）
2. **json 布局引用图片路径写 `images/xxx.png` —— 相对 `resources/` 目录**，不带 `resources/` 前缀、不写绝对路径
3. 语义依据：设备端 `setBackgroundPic("bg.png")` 的相对路径就是相对于项目 resources 文件夹（官方 uicontrols/common_props.md）；json 的 backgroundPic / picTab.pic0 / picTab.pic1 同理
4. 图片放错位置（如 `ui/images/`）+ json 写 `images/xxx.png` = json 语义找 `resources/images/xxx.png` → **设备上显示空白**

## json 里怎么引用

```jsonc
// 普通控件背景图（textview/window 等）
"backgroundPic": "images/grad_card_0.png"

// 按钮两态图（normal + pressed，_p 后缀）
"picTab": {
  "pic0": "images/btn_normal.png",
  "pic1": "images/btn_pressed.png"
}
```

## MCP 各入口行为（v0.6.7+ 已统一）

| 入口 | 图片输出 | 返回 |
|------|---------|------|
| `flythings_generate_ui_assets` | `<项目>/resources/images/` | `path` = `images/xxx.png`（直接填 json）；`absolutePath` 备查 |
| `flythings_html_to_json`（CSS 效果自动转图：渐变 grad_*/阴影 shadow_*/gradshadow_*/emoji 图标/loading GIF） | output_json 在 `<项目>/ui/` 下时自动定位 `resources/images/`；其它位置回退 json 同目录 images/ 并 warning | 返回 `generatedAssets` 计数 + `assetDir` 实际目录 |
| 手动切图（设计稿切 PNG/.9.png） | 同样放 `<项目>/resources/images/` | json 引用 `images/xxx.png` |

## 各控件图片字段对照（易错点，2026-09-01 沛哥实战）

| 控件 | 图片字段 | 说明 |
|------|---------|------|
| button | `picTab{pic0,pic1,pic2}` | normal / pressed(_p) / selected 两到三态图 |
| slidewindow | `picTab{pic0,pic1}` | 图标两态图 |
| textview / window / 其它 | `backgroundPic` | 单背景图 |
| **pointer** | `backgroundPic`(表盘) + **`pointerPic`**(指针) | ⚠️ **没有 picTab**！指针图用 `pointerPic`，写成 picTab.pic0 IDE 识别不到；还有 `pointerSize`/`startAngle`/`rotateSpeed`/`clockwise`/`animatable` |

**Pointer 控件坐标三件套（PointerDemo/clockDemo 实测，缺了指针绕错圆心转）**：
- `rotationPoint` `{x,y}`：旋转点（控件内旋转圆心，表盘中心）
- `fixedPoint` `{x,y}`：指针固定点（指针图内的旋转支点，可超出图片范围实现游标效果）
- `pointerSize` `{width,height}`：指针图实际尺寸
- 时钟多指针：多个 Pointer 控件共用同一 position + rotationPoint，各自 pointerPic/pointerSize/fixedPoint；表盘图 backgroundPic 只需放一个控件上，其它留空 |
| qrcode | `codeStr` | 二维码内容是文本不是图 |
| checkbox | `pic2`/两态图 | 选中态图 |

## 常见坑

- 生成图片后**没写进 json**（只 warning 不生效）：检查控件是否被后处理覆盖、按钮是否应走 picTab
- `check_all` 有图片引用检查：json + logic.cc 引用的图片必须在 resources 下存在，交付前必跑
- 图片尺寸与控件尺寸不一致会拉伸变形：生成时按控件实际尺寸出图（图标 128 → 控件 128）
- 透明角图片（圆角卡片）按钮不要设 bgColorTab：会透出按钮底色而不是窗口背景
- 生成后检查四角透明：`img.getpixel((2,2))[3] == 0`
