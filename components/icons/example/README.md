# example —— 最小接入示例（可重复跑）

演示"**生成图标 → 放进 FlyThings 工程 resources\images → json 引用 images/ic_xxx.png**"这条链路，
并保证 **图片像素尺寸 == 控件 position**（zkgui 图片控件会拉伸不匹配的图）。

```
example/
├─ build_example.py            # 一键跑：生成图标 + 写 json + 校验尺寸 + 出预览图
├─ preview.png                 # 预览图（把 app/ui/main.json 里的图标按控件位置拼到背景上）
└─ app/                        # 一个最小 FlyThings 工程骨架（只含资源与布局）
   ├─ ui/main.json             # 布局：18 个控件，全部引用本模块生成的图标
   └─ resources/images/*.png   # 生成产物（18 张，尺寸 22/32/44/56）
```

## 跑一遍

```bash
cd <仓库>/tools/FlyThings_mcp_open/components/icons
python example/build_example.py          # 生成 + 写 json + 校验 + 出预览图
python example/build_example.py --check  # 只校验（图片存在 && 尺寸 == 控件盒）
```

输出（节选）：
```
[1/3] 生成图标 → app/resources/images/
  + ic_weather_partly-cloudy.png               56px
  + ic_system_wifi_ios.png                     22px
  + ic_control_toggle_ios_on.png               44px
[2/3] 写布局 → app/ui/main.json
校验图片尺寸与控件盒：
  OK  images/ic_weather_partly-cloudy.png            图 56x56  控件 56x56
  OK  images/ic_control_toggle_ios_on.png            图 44x44  控件 44x44
  --- PASS：0 处不一致
[3/3] 预览图 → example/preview.png
```

## 怎么接进真工程

1) **把图生成到工程里**（不要手工拷贝，换尺寸/换色重跑一次就好）：
```bash
python scripts/gen_icons.py --name ic_weather_cloudy.png --size 56 --color 255,255,255 \
       --out /path/to/MyApp/app/resources/images
# 或整类：
python scripts/gen_icons.py --set control --size 22 --color 255,255,255 \
       --out /path/to/MyApp/app/resources/images
```

2) **json 里引用**（两种控件写法，`example/app/ui/main.json` 是完整例子）：
```json
{
  "textview__1": {
    "caption": "ImgWeatherBig", "id": 50001, "touchable": false,
    "position": { "left": 40, "top": 28, "width": 56, "height": 56 },
    "backgroundPic": "images/ic_weather_partly-cloudy.png"
  },
  "button__2": {
    "caption": "BtnToggleOn", "id": 20001, "touchable": true,
    "position": { "left": 560, "top": 196, "width": 44, "height": 44 },
    "picTab": { "pic0": "images/ic_control_toggle_ios_on.png" },
    "text": ""
  }
}
```

3) **打包/运行**：
```bash
fui pack app/ui/main.json       # 或 flythings_fui_pack（设备实际加载 ftu）
fsc build -p F133 && fsc launch -p F133    # 或 flythings_build_ui_flow
```

## 两态切换要注意

`off`/`on` 是两张等尺寸的图，所以：
- 用 **button 的 `picTab`**（`pic0`/`pic1`）或代码里 `setPicture`/切图，
  不要用"改控件尺寸"来切换；
- 两张图的文件名只差后缀（`..._off.png` / `..._on.png`），替换时不会漏。

## 注意

- `example/app/` 只是**资源 + 布局**骨架，不是完整可编译工程（没有 Manifest/src）。
  要真编译：用 `flythings_create_project`（或 IDE 模板）建工程，再把 `ui/main.json`
  与 `resources/images/` 拷进去。
- 本示例故意用了 4 种尺寸（22/32/44/56）来演示"图 == 控件盒"；
  `selfcheck.py` 的"同目录不混尺寸"检查只针对 `out/`，不适用于工程 images 目录
  （工程里多种尺寸混放是正常的，只要每个控件盒与其图片一致）。
