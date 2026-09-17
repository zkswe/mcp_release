# icons —— 图标资产库（vendor Tabler + 少量自绘，单色烘焙 PNG，任意分辨率）

> 解决的问题：**做 UI 时不该再为"图标风格/尺寸/两态"来回确认**。
> 本模块把 **Tabler Icons（MIT，v3.46.0）收录为唯一图标源**（203 个语义图标：
> 天气 / 开关选项 / 通用系统 / 智能家居设备 / 两轮车），加上**自绘的两轮车仪表一套**，
> 用**一条命令**渲染成任意分辨率的**单色 PNG**——像素尺寸严格等于请求值，
> 22px 不糊、56px 不细，两态（outline/filled）自动配对。
>
> 版本 **v0.3.0**（2026-09-17）｜形态：`components/` 规范里的**资产/工具型模块**（无 include/src）
> ｜v0.2.0（2026-09-16，转向 vendor）｜v0.1.0（自绘 86 图标 ios/material 双调性）已被取代
>
> **v0.3.0 变更（单归档 + 按需解）**：vendor 的 5777 个 SVG 散件收进一份归档
> `vendor/tabler-3.46.0.pack.tgz`（455,379 B，sha256 `a0ba69f2…1c95`），`out/` 生成物退出
> 版本库（已 gitignore）；**所有命令用法与输出不变**，读取层按需从归档解出用到的 SVG。

**规模**：语义图标 **203**（Tabler 198 + 自绘 5）→ 产物 **305** 张
（有 filled 变体的 vendor 图标出 `_off`/`_on` 两张，其余单张）
｜自绘矢量源 10 个｜vendor 引用 269 处｜旧工程名映射 **75** 条
｜入库体积：**48 文件 / 1.63 MB**（v0.2.0 为 6801 文件 / 6.30 MB）

**一句话取舍**：图形**不做任何修改**，只做「单色化 + 等比缩放」+「输出尺寸整数化」；
Tabler 的 `brand-*` 品牌 logo **已在 vendor 时排除**（376 个），不进本模块。

---

## 1. 这是什么 / 不是什么

**是**
- `vendor/tabler-3.46.0.pack.tgz`：Tabler Icons 3.46.0 的**单一归档**（outline 4754 +
  filled 1019 + `map.json`；MIT），由 `scripts/make_pack.py` 确定性生成（同一输入必得同一
  sha256）。归档外仍留 `index.json`（索引）/`LICENSE`（MIT 合规）/`VERSION.txt`（凭据）。
  读取层按需解出用到的 SVG → 缓存 `out/.icons-cache/`（已 gitignore）。
- `svg/`：**自绘**矢量源，只剩两轮车仪表一套（转向箭头/大灯/远光/定速巡航）——
  Tabler 风格不匹配（仪表要粗实箭头、带光束的车灯）。
- `scripts/gen_icons.py`：**唯一生成入口**。语义名 → 找源（磁盘散件/vendor 归档缓存/自绘）→
  8× 超采样光栅化 → 面积平均降采样 → α 整形 → 按 `--color` 烘焙纯色 PNG。
- `scripts/make_pack.py`：vendor 散件 → 归档（`--verify` 核对 sha256/条目；`--from-npm`
  可从上游 npm tarball 离线重建）。
- `catalog.json`：自动生成的语义清单（`scripts/gen_catalog.py`，**禁止手写**）。
- `out/`：**本机生成物，不入库**（已进 `.gitignore`），可现场重建（见下）。

**不是**
- **不是 iconfont**：设备端不装图标字体（FlyThings 没有 tint；22px 字体渲染会糊、无法像素对齐）。
- **不是运行时染色**：一张图一个颜色，换色 = 用 `--color` 重新生成（秒级）。
- **不改图形**：不重绘、不描边化、不"再设计"。只做单色化 + 等比缩放。

---

## 2. 快速开始

```bash
# ① 看有哪些图标（203 个：名字/分类/来源/状态）
#   数据源 = catalog.json / index.json / map.json，**不依赖任何 svg 散件**
python scripts/gen_icons.py --list
python scripts/gen_icons.py --list-vendor system     # 只看 vendor 语义名（可跟分类）
python scripts/gen_icons.py --list-tabler wifi       # Tabler 原生名全量 4754（子串过滤）
python scripts/gen_icons.py --pack-info              # 图标来源：归档/缓存/远端 状态

# ② 按**语义名**出图（不用记 tabler 文件名）——最常用
python scripts/gen_icons.py --vendor-name wifi --size 22 --color 255,255,255 --out out/22
python scripts/gen_icons.py --name weather.clear --size 56 --color 255,175,40 --out out/56

# ③ 直接渲染任意 SVG（vendor 里没收录的也能用）
python scripts/gen_icons.py --svg vendor/tabler/icons/rocket.svg --size 48 --out out/tmp

# ④ 批量：分类 / vendor / all
python scripts/gen_icons.py --set weather --size 22 --out out/22
python scripts/gen_icons.py --set vendor  --size 24 --out out/24
python scripts/gen_icons.py --all --size 56 --out out/56

# ④b Tabler 原生名 / 任意 SVG / 整目录 / vendor 批量
python scripts/gen_icons.py --vendor-name weather.sun --size 56 --out out/56  # 名字兜底：Tabler 原名也行
python scripts/gen_icons.py --tabler cloud-rain --size 22 --out out/22
python scripts/gen_icons.py --svg-dir vendor/tabler/icons --size 24 --out out/24   # 整目录（散件已收进归档 → 读层自动列名+按需解）
python scripts/gen_icons.py --vendor-set common --size 22 --out out/22        # 语义表全量
python scripts/gen_icons.py --vendor-set all --size 24 --out out/24           # Tabler 全量 4754

# ⑤ 非正方形（等比居中留白，绝不拉伸）：产出图严格 22×16
python scripts/gen_icons.py --name control.arrow-left --size 22x16 --out out/misc

# ⑥ contact sheet（审阅）
python scripts/gen_icons.py --sheet out/sheet_vendor_22.png --size 22 --set vendor

# ⑦ 质检（命名/尺寸/透明度/清单一致性/陈旧产物/全量可渲染）
python scripts/selfcheck.py
```

### 2.1 图标从哪来（按需加载）——v0.3.0 起

vendor 的 SVG **不再以散件形式入库**（原 5777 文件 / 3.95 MB → 1 个归档 455 KB）。
生成器把 catalog/map 里的**逻辑路径**（如 `vendor/tabler/icons/rocket.svg`）解析成真实文件，优先级：

| 顺序 | 来源 | 位置 / 开关 |
|---|---|---|
| ① | **本地缓存**（散件优先） | 默认 `out/.icons-cache/`（**已 gitignore**）；env `FLYTHINGS_ICONS_CACHE=<目录>` 覆盖 |
| ② | **pack 归档按下需解** | `vendor/tabler-3.46.0.pack.tgz`（tarfile 随机读，**只解这次用到的几个**，解出的写进 ①）；env `FLYTHINGS_ICONS_PACK=<路径>` 可换归档 |
| ③ | **远端 npm tarball**（**默认关闭**） | 按 `catalog.json` 的 `sources.vendor.url` 拉取 + sha256 校验后缓存；要显式 `--fetch-remote`（或 env `FLYTHINGS_ICONS_FETCH_REMOTE=1`）；单独跑 `--fetch-remote` = 预取缓存 |

- **归档**：`vendor/tabler-3.46.0.pack.tgz`｜**455,379 B（0.43 MB）**｜
  sha256 `a0ba69f224388e22790f04a0a157fb6207713511f7e308709a0166ebd8ec1c95`（条目 5774 = icons 4754 + icons-filled 1019 + map.json）
  ｜解压后 3.25 MB ｜确定性写入（mtime=0/uid=gid=0 → 可复现同一 sha256）
- **缓存位置**：`out/.icons-cache/`（env 可覆盖；卸载 MCP 时可直接删；不可写时自动退到系统临时目录）
- ⚠️ **不要再直接 `grep`/浏览单个 `.svg` 文件**（散件已不在仓库里）。要查图标就：
  `--list`（语义名）/ `--list-vendor <分类>` / `--list-tabler <子串>`（Tabler 原生名）/
  `--pack-info`（来源状态）/ 读 `catalog.json`（机器可读清单）；要看图就 `--sheet` 出 contact sheet。
- 归档里有 `map.json`（语义映射），**新增语义映射请改归档内的那份**：
  `python scripts/make_pack.py --from-npm <tarball> --map <改好的 map.json>`（或先解出 `/tmp` 改好再打）。
- 重建归档：`python scripts/make_pack.py`（从散件）｜核对：`python scripts/make_pack.py --verify vendor/tabler-3.46.0.pack.tgz`

**重建本机生成物**（`out/` 已不入库）：
```bash
python scripts/gen_icons.py --all --size 22 --out out/22      # 305 张
python scripts/gen_icons.py --all --size 24 --out out/24
python scripts/gen_icons.py --all --size 56 --out out/56
python scripts/gen_icons.py --sheet out/sheet_vendor_22.png --size 22 --set vendor
```

**进 FlyThings 工程 3 步**（可跑示例见 `example/`）：
1. 生成 PNG 到 `<项目>/app/resources/images/`（`--out` 直接指过去）；
2. json 引用：图片控件 `"backgroundPic": "images/ic_weather_cloudy_off.png"`，
   按钮 `"picTab": {"pic0": "images/ic_control_toggle-right_on.png"}`；
3. **控件 `position` 宽高 == 图片像素尺寸**（22px → `"width":22,"height":22`），否则被拉伸。

**小尺寸策略（实测）**：**≥22px 用 outline 即可**（本套用「半像素对齐线宽 + α 对比度整形 + 去雀斑」，
22px 中间值像素 ≤ 9.7%、边缘不发虚）；**≤20px 建议用 filled**（实心更清楚）。

---

## 3. 渲染与命名规范

### 3.1 网格与线宽
- 所有源都是 `viewBox="0 0 24 24"`（Tabler 原生 24 网格）；图形**不做变形**，只等比缩放。
- 线宽：**基准 = 根节点 `stroke-width`**（Tabler outline = 2），输出像素宽
  `px = max(1, round(基准 × size/24 × 2) / 2)`（**半像素对齐**，避免 4.08px 这种"半灰边"）。

  | 输出 | 2@24 的线宽（Tabler outline） |
  |---|---|
  | 16px | 1.5px |
  | 22px | 2.0px（不糊：整数像素） |
  | 24px | 2.0px（与上游一致） |
  | 32px | 2.5px |
  | 44px | 3.5px |
  | 56px | 4.5px |

- 抗锯齿：8× 超采样 → BOX 面积平均（=精确覆盖率）→ **α 对比度整形**（把 <0.40 / >0.60 的
  覆盖率推到 0/255，中间保留亚像素位置）+ 去雀斑。实测 22px 中间值像素 ≤ 9.7%、
  56px ≤ 2.8%（限值 15%），既干净又不发虚。

### 3.2 两态（off / on）
- **有 filled 变体的 vendor 图标**（79 个）：`off` = outline、`on` = filled，
  同尺寸可直接替换：`ic_wifi_off.png` ↔ `ic_wifi_on.png`（例：`ic_system_settings_off/_on`）。
- **无 filled 的图标**（66 个）：只出一张（如 `ic_system_wifi.png`）；需要强制拆两态时加
  `--state off|on`，会生成 `ic_system_wifi_off.png` / `_on.png`（图形相同）。
- **自绘两轮车图标**：`off` = 线框、`on` = 实心（+ 光束）；颜色差异用 `--color` 烘焙
  （旧工程里"白色箭头/绿色箭头"就是同一形状两次生成）。

### 3.3 compose（7 条组合图标）
天气里 Tabler 没有"太阳 + 云"这类组合，用 `map.json` 的 `compose` 表达：
`{tabler, dx, dy, scale}`×N，`dx/dy/scale` 都以 **24 网格为 1.0**（如 `dx=-0.16` → 左移 3.84 单位）。
渲染时**先各自栅格化再 alpha 合成**——描边不会互相穿插变脏（这也是它必须实现成"两张图叠"的原因）。
`on` 态优先取各部件的 filled 版本，缺 filled 的部件沿用 outline。
例：`ic_weather_partly-cloudy_off.png`（日+云 线框）/ `_on.png`（实心）。

### 3.4 命名
```
产物 PNG : ic_<分类>_<名字>[_<风格>][_off|_on].png      全小写中划线
矢量源   : svg/<分类>/<名字>[_<风格>][_off|_on].svg      （自绘）
           vendor/tabler/{icons,icons-filled}/<glyph>.svg（vendor；**逻辑路径**，
           散件已在 vendor/tabler-3.46.0.pack.tgz 里，按需解到 out/.icons-cache/）
分类     : weather / control / system / device / vehicle
```
`--name` / `--vendor-name` 都支持多种写法：`weather.clear`、`clear`、`sun`（tabler 名）、
`wx_clear`（旧工程名）、`ic_weather_clear_off.png`（产物文件名）。旧名映射 75 条见
`catalog.json` 的 `legacyMap`。

### 3.5 颜色
- `--color R,G,B`（默认 `255,255,255`）→ 产物 PNG 的 **RGB 全等于该颜色**，只有 alpha 变化；
  不做灰阶叠加/渐变/阴影/半透明蒙版。
- 建议色（`catalog.json` 的 `palette`）：白 `255,255,255`｜iOS 蓝 `0,122,255`
  ｜Material 蓝 `33,150,243`｜警示 `255,149,0`｜危险 `255,59,48`｜成功 `52,199,89`。
- 两态图标的 `on` 态如果有挖空（Tabler filled 的负空间），挖空处是**真透明**，露底图颜色。

---

## 4. 图标清单

> 机器可读清单：`catalog.json`（含中英 keywords、建议尺寸、别名、旧名映射、来源与许可）——
> **这是唯一权威清单**（当前 **203** 个：weather 30 / control 26 / system 112 / device 23 / vehicle 12），
> 由 `scripts/gen_catalog.py` 生成，要看全部用 `python scripts/gen_icons.py --list`。
> ⚠️ 下表是 v0.2.0 时期手写的**节选**（共 157 条，缺 system 里后加的 wifi-0/1/2、signal-1..5、
> cell-signal、电量分档、2G/3G/4G/5G/LTE 等），仅供人肉检索；**与 catalog.json 冲突时以 catalog.json 为准**。

### weather（天气）—— 30 个

| 名字 | 来源 | 状态 | 建议尺寸 | 产物文件名 | 说明 / 关键词 |
|---|---|---|---|---|---|
| `weather.clear` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_weather_clear_off.png`<br>`ic_weather_clear_on.png` | 晴｜晴、clear、sun |
| `weather.clear-high` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_weather_clear-high_off.png`<br>`ic_weather_clear-high_on.png` | 晴(强)｜晴、clear、high、sun、烈日 |
| `weather.sunrise` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_weather_sunrise_off.png`<br>`ic_weather_sunrise_on.png` | 日出｜日出、sunrise |
| `weather.sunset` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_weather_sunset_off.png`<br>`ic_weather_sunset_on.png` | 日落｜日落、sunset、傍晚 |
| `weather.cloudy` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_weather_cloudy_off.png`<br>`ic_weather_cloudy_on.png` | 多云/阴｜多云/阴、cloudy、cloud |
| `weather.cloud-fog` | Tabler | single | 16/20/22/24/32/44/56 | `ic_weather_cloud-fog.png` | 雾｜雾、cloud、fog、多云转雾 |
| `weather.mist` | Tabler | single | 16/20/22/24/32/44/56 | `ic_weather_mist.png` | 薄雾｜薄雾、mist |
| `weather.haze` | Tabler | single | 16/20/22/24/32/44/56 | `ic_weather_haze.png` | 霾｜霾、haze |
| `weather.haze-moon` | Tabler | single | 16/20/22/24/32/44/56 | `ic_weather_haze-moon.png` | 夜间霾｜夜间霾、haze、moon |
| `weather.rain` | Tabler | single | 16/20/22/24/32/44/56 | `ic_weather_rain.png` | 雨｜雨、rain、cloud |
| `weather.shower` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_weather_shower_off.png`<br>`ic_weather_shower_on.png` | 阵雨｜阵雨、shower、droplets |
| `weather.thunder` | Tabler | single | 16/20/22/24/32/44/56 | `ic_weather_thunder.png` | 雷｜雷、thunder、cloud、bolt |
| `weather.storm` | Tabler | single | 16/20/22/24/32/44/56 | `ic_weather_storm.png` | 暴风雨｜暴风雨、storm、cloud、狂风暴雨 |
| `weather.snow` | Tabler | single | 16/20/22/24/32/44/56 | `ic_weather_snow.png` | 雪｜雪、snow、cloud |
| `weather.snowflake` | Tabler | single | 16/20/22/24/32/44/56 | `ic_weather_snowflake.png` | 雪花｜雪花、snowflake、雪 |
| `weather.wind` | Tabler | single | 16/20/22/24/32/44/56 | `ic_weather_wind.png` | 风｜风、wind |
| `weather.moon` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_weather_moon_off.png`<br>`ic_weather_moon_on.png` | 月｜月、moon |
| `weather.moon-stars` | Tabler | single | 16/20/22/24/32/44/56 | `ic_weather_moon-stars.png` | 月+星｜月+星、moon、stars、星月 |
| `weather.umbrella` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_weather_umbrella_off.png`<br>`ic_weather_umbrella_on.png` | 雨伞｜雨伞、umbrella、带伞 |
| `weather.rainbow` | Tabler | single | 16/20/22/24/32/44/56 | `ic_weather_rainbow.png` | 彩虹｜彩虹、rainbow |
| `weather.droplet` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_weather_droplet_off.png`<br>`ic_weather_droplet_on.png` | 水滴｜水滴、droplet、湿度 |
| `weather.temp-sun` | Tabler | single | 16/20/22/24/32/44/56 | `ic_weather_temp-sun.png` | 高温｜高温、temp、sun、temperature、炎热 |
| `weather.temp-snow` | Tabler | single | 16/20/22/24/32/44/56 | `ic_weather_temp-snow.png` | 低温｜低温、temp、snow、temperature、寒冷 |
| `weather.partly-cloudy` | Tabler+组合 | off/on | 16/20/22/24/32/44/56 | `ic_weather_partly-cloudy_off.png`<br>`ic_weather_partly-cloudy_on.png` | 多云(晴间多云)= 太阳+云｜多云= 太阳+云、partly、cloudy |
| `weather.rain-sun` | Tabler+组合 | off/on | 16/20/22/24/32/44/56 | `ic_weather_rain-sun_off.png`<br>`ic_weather_rain-sun_on.png` | 太阳雨｜太阳雨、rain、sun |
| `weather.thunder-sun` | Tabler+组合 | off/on | 16/20/22/24/32/44/56 | `ic_weather_thunder-sun_off.png`<br>`ic_weather_thunder-sun_on.png` | 雷阵雨(晴)｜雷阵雨、thunder、sun |
| `weather.moon-cloud` | Tabler+组合 | off/on | 16/20/22/24/32/44/56 | `ic_weather_moon-cloud_off.png`<br>`ic_weather_moon-cloud_on.png` | 多云夜｜多云夜、moon、cloud |
| `weather.moon-rain` | Tabler+组合 | off/on | 16/20/22/24/32/44/56 | `ic_weather_moon-rain_off.png`<br>`ic_weather_moon-rain_on.png` | 雨夜｜雨夜、moon、rain |
| `weather.sleet` | Tabler+组合 | off/on | 16/20/22/24/32/44/56 | `ic_weather_sleet_off.png`<br>`ic_weather_sleet_on.png` | 雨夹雪｜雨夹雪、sleet |
| `weather.hail` | Tabler+组合 | off/on | 16/20/22/24/32/44/56 | `ic_weather_hail_off.png`<br>`ic_weather_hail_on.png` | 冰雹(近似)｜冰雹、hail |

### control（开关/选项）—— 26 个

| 名字 | 来源 | 状态 | 建议尺寸 | 产物文件名 | 说明 / 关键词 |
|---|---|---|---|---|---|
| `control.toggle-left` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_control_toggle-left_off.png`<br>`ic_control_toggle-left_on.png` | 开关-关｜开关-关、toggle、left、关闭 |
| `control.toggle-right` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_control_toggle-right_off.png`<br>`ic_control_toggle-right_on.png` | 开关-开｜开关-开、toggle、right、打开 |
| `control.switch-2` | Tabler | single | 16/20/22/24/32/44/56 | `ic_control_switch-2.png` | 拨动开关｜拨动开关、switch |
| `control.switch-3` | Tabler | single | 16/20/22/24/32/44/56 | `ic_control_switch-3.png` | 拨动开关-2｜拨动开关-2、switch、拨动开关 |
| `control.checkbox` | Tabler | single | 16/20/22/24/32/44/56 | `ic_control_checkbox.png` | 复选框｜复选框、checkbox、勾选框 |
| `control.square` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_control_square_off.png`<br>`ic_control_square_on.png` | 方框｜方框、square、未选 |
| `control.square-check` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_control_square-check_off.png`<br>`ic_control_square-check_on.png` | 勾选｜勾选、square、check、已勾选 |
| `control.circle` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_control_circle_off.png`<br>`ic_control_circle_on.png` | 圆｜圆、circle、未选 |
| `control.circle-check` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_control_circle-check_off.png`<br>`ic_control_circle-check_on.png` | 圆勾选｜圆勾选、circle、check、圆已选 |
| `control.circle-dot` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_control_circle-dot_off.png`<br>`ic_control_circle-dot_on.png` | 单选｜单选、circle、dot、圆点 |
| `control.selector` | Tabler | single | 16/20/22/24/32/44/56 | `ic_control_selector.png` | 选择器｜选择器、selector、下拉 |
| `control.chevron-up` | Tabler | single | 16/20/22/24/32/44/56 | `ic_control_chevron-up.png` | 上折角｜上折角、chevron、up |
| `control.chevron-down` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_control_chevron-down_off.png`<br>`ic_control_chevron-down_on.png` | 下折角｜下折角、chevron、down |
| `control.chevron-left` | Tabler | single | 16/20/22/24/32/44/56 | `ic_control_chevron-left.png` | 左折角｜左折角、chevron、left |
| `control.chevron-right` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_control_chevron-right_off.png`<br>`ic_control_chevron-right_on.png` | 右折角｜右折角、chevron、right |
| `control.arrow-up` | Tabler | single | 16/20/22/24/32/44/56 | `ic_control_arrow-up.png` | 上箭头｜上箭头、arrow、up |
| `control.arrow-down` | Tabler | single | 16/20/22/24/32/44/56 | `ic_control_arrow-down.png` | 下箭头｜下箭头、arrow、down |
| `control.arrow-left` | Tabler | single | 16/20/22/24/32/44/56 | `ic_control_arrow-left.png` | 左箭头｜左箭头、arrow、left |
| `control.arrow-right` | Tabler | single | 16/20/22/24/32/44/56 | `ic_control_arrow-right.png` | 右箭头｜右箭头、arrow、right |
| `control.check` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_control_check_off.png`<br>`ic_control_check_on.png` | 对勾｜对勾、check |
| `control.close` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_control_close_off.png`<br>`ic_control_close_on.png` | 关闭｜关闭、close、x |
| `control.plus` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_control_plus_off.png`<br>`ic_control_plus_on.png` | 加｜加、plus |
| `control.minus` | Tabler | single | 16/20/22/24/32/44/56 | `ic_control_minus.png` | 减｜减、minus |
| `control.sliders` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_control_sliders_off.png`<br>`ic_control_sliders_on.png` | 滑块｜滑块、sliders、adjustments、horizontal、调节 |
| `control.progress` | Tabler | single | 16/20/22/24/32/44/56 | `ic_control_progress.png` | 进度｜进度、progress |
| `control.loader` | Tabler | single | 16/20/22/24/32/44/56 | `ic_control_loader.png` | 加载｜加载、loader、载入 |

### system（通用系统）—— 66 个

| 名字 | 来源 | 状态 | 建议尺寸 | 产物文件名 | 说明 / 关键词 |
|---|---|---|---|---|---|
| `system.wifi` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_wifi.png` | WiFi｜WiFi、wifi、无线、无线网、联网 |
| `system.wifi-off` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_wifi-off.png` | WiFi 断开｜WiFi 断开、wifi、off、断网、无网络 |
| `system.bluetooth` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_bluetooth.png` | 蓝牙｜蓝牙、bluetooth、配对 |
| `system.bluetooth-conn` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_bluetooth-conn.png` | 蓝牙已连｜蓝牙已连、bluetooth、conn、connected |
| `system.battery` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_battery_off.png`<br>`ic_system_battery_on.png` | 电池｜电池、battery、电量 |
| `system.battery-1` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_battery-1_off.png`<br>`ic_system_battery-1_on.png` | 电池 1 格｜电池 1 格、battery |
| `system.battery-2` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_battery-2_off.png`<br>`ic_system_battery-2_on.png` | 电池 2 格｜电池 2 格、battery |
| `system.battery-3` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_battery-3_off.png`<br>`ic_system_battery-3_on.png` | 电池 3 格｜电池 3 格、battery |
| `system.battery-4` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_battery-4_off.png`<br>`ic_system_battery-4_on.png` | 电池满｜电池满、battery |
| `system.battery-charging` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_battery-charging.png` | 充电中｜充电中、battery、charging |
| `system.signal` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_signal.png` | 信号｜信号、signal、antenna、bars、格数 |
| `system.bell` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_bell_off.png`<br>`ic_system_bell_on.png` | 铃铛｜铃铛、bell、通知、提醒、消息 |
| `system.bell-off` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_bell-off.png` | 静音｜静音、bell、off、免打扰、消息免打扰 |
| `system.lock` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_lock_off.png`<br>`ic_system_lock_on.png` | 锁｜锁、lock、已锁、加密 |
| `system.lock-open` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_lock-open.png` | 解锁｜解锁、lock、open、开锁 |
| `system.search` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_search_off.png`<br>`ic_system_search_on.png` | 搜索｜搜索、search、查找 |
| `system.settings` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_settings_off.png`<br>`ic_system_settings_on.png` | 设置｜设置、settings、齿轮、配置 |
| `system.home` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_home_off.png`<br>`ic_system_home_on.png` | 主页｜主页、home、首页、家 |
| `system.more` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_more_off.png`<br>`ic_system_more_on.png` | 更多｜更多、more、dots、三点 |
| `system.more-vertical` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_more-vertical_off.png`<br>`ic_system_more-vertical_on.png` | 更多(竖)｜更多、more、vertical、dots、竖三点 |
| `system.star` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_star_off.png`<br>`ic_system_star_on.png` | 星标｜星标、star、收藏、评分 |
| `system.heart` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_heart_off.png`<br>`ic_system_heart_on.png` | 收藏｜收藏、heart、喜欢、点赞 |
| `system.power` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_power.png` | 电源｜电源、power、开机、关机 |
| `system.trash` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_trash_off.png`<br>`ic_system_trash_on.png` | 删除｜删除、trash、垃圾桶 |
| `system.pencil` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_pencil_off.png`<br>`ic_system_pencil_on.png` | 编辑｜编辑、pencil、铅笔、改名 |
| `system.share` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_share.png` | 分享｜分享、share、转发 |
| `system.refresh` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_refresh.png` | 刷新｜刷新、refresh、同步 |
| `system.volume` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_volume.png` | 音量｜音量、volume、声音 |
| `system.volume-off` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_volume-off.png` | 静音｜静音、volume、off、无声 |
| `system.play` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_play_off.png`<br>`ic_system_play_on.png` | 播放｜播放、play、player、开始 |
| `system.pause` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_pause_off.png`<br>`ic_system_pause_on.png` | 暂停｜暂停、pause、player |
| `system.microphone` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_microphone_off.png`<br>`ic_system_microphone_on.png` | 麦克风｜麦克风、microphone、语音、录音 |
| `system.camera` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_camera_off.png`<br>`ic_system_camera_on.png` | 相机｜相机、camera、拍照 |
| `system.user` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_user_off.png`<br>`ic_system_user_on.png` | 用户｜用户、user、个人、我的 |
| `system.users` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_users.png` | 多用户｜多用户、users、成员 |
| `system.mail` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_mail_off.png`<br>`ic_system_mail_on.png` | 邮件｜邮件、mail、邮箱 |
| `system.calendar` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_calendar_off.png`<br>`ic_system_calendar_on.png` | 日历｜日历、calendar、日期 |
| `system.clock` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_clock_off.png`<br>`ic_system_clock_on.png` | 时钟｜时钟、clock、时间 |
| `system.warning` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_warning_off.png`<br>`ic_system_warning_on.png` | 警告｜警告、warning、alert、triangle、告警 |
| `system.info` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_info_off.png`<br>`ic_system_info_on.png` | 信息｜信息、info、circle、说明 |
| `system.eye` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_eye_off.png`<br>`ic_system_eye_on.png` | 显示｜显示、eye、可见、预览 |
| `system.eye-off` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_eye-off.png` | 隐藏｜隐藏、eye、off、不可见 |
| `system.download` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_download_off.png`<br>`ic_system_download_on.png` | 下载｜下载、download |
| `system.upload` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_upload.png` | 上传｜上传、upload |
| `system.filter` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_filter_off.png`<br>`ic_system_filter_on.png` | 筛选｜筛选、filter、过滤 |
| `system.menu` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_menu_off.png`<br>`ic_system_menu_on.png` | 菜单｜菜单、menu |
| `system.grid` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_grid_off.png`<br>`ic_system_grid_on.png` | 网格｜网格、grid、layout、宫格 |
| `system.list` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_list_off.png`<br>`ic_system_list_on.png` | 列表｜列表、list |
| `system.map-pin` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_map-pin_off.png`<br>`ic_system_map-pin_on.png` | 定位｜定位、map、pin、位置、地点 |
| `system.navigation` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_navigation_off.png`<br>`ic_system_navigation_on.png` | 导航｜导航、navigation、指路 |
| `system.compass` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_compass_off.png`<br>`ic_system_compass_on.png` | 指南针｜指南针、compass、方向 |
| `system.gauge` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_gauge_off.png`<br>`ic_system_gauge_on.png` | 仪表｜仪表、gauge、速度、时速 |
| `system.shield` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_shield_off.png`<br>`ic_system_shield_on.png` | 防护｜防护、shield、安防 |
| `system.shield-check` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_shield-check_off.png`<br>`ic_system_shield-check_on.png` | 防护已启｜防护已启、shield、check、安防开启、已布防 |
| `system.alarm` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_alarm_off.png`<br>`ic_system_alarm_on.png` | 闹钟｜闹钟、alarm、提醒 |
| `system.bolt` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_bolt_off.png`<br>`ic_system_bolt_on.png` | 闪电｜闪电、bolt、快充、高压 |
| `system.flame` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_flame_off.png`<br>`ic_system_flame_on.png` | 火焰｜火焰、flame、燃气、点火 |
| `system.phone` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_phone_off.png`<br>`ic_system_phone_on.png` | 电话｜电话、phone、拨打 |
| `system.device-mobile` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_device-mobile_off.png`<br>`ic_system_device-mobile_on.png` | 手机｜手机、device、mobile、移动端 |
| `system.speaker` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_speaker.png` | 扬声器｜扬声器、speaker、speakerphone、外放 |
| `system.music` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_music.png` | 音乐｜音乐、music、歌曲 |
| `system.photo` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_photo_off.png`<br>`ic_system_photo_on.png` | 图片｜图片、photo、照片 |
| `system.video` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_system_video_off.png`<br>`ic_system_video_on.png` | 视频｜视频、video、录像 |
| `system.router` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_router.png` | 路由｜路由、router、网关 |
| `system.access-point` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_access-point.png` | 接入点｜接入点、access、point、热点、AP |
| `system.fingerprint` | Tabler | single | 16/20/22/24/32/44/56 | `ic_system_fingerprint.png` | 指纹｜指纹、fingerprint、生物识别 |

### device（智能家居设备）—— 23 个

| 名字 | 来源 | 状态 | 建议尺寸 | 产物文件名 | 说明 / 关键词 |
|---|---|---|---|---|---|
| `device.bulb` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_device_bulb_off.png`<br>`ic_device_bulb_on.png` | 灯(泡)｜灯、bulb、灯泡、照明、开灯 |
| `device.bulb-off` | Tabler | single | 16/20/22/24/32/44/56 | `ic_device_bulb-off.png` | 灯关｜灯关、bulb、off、关灯 |
| `device.lamp` | Tabler | single | 16/20/22/24/32/44/56 | `ic_device_lamp.png` | 台灯｜台灯、lamp、落地灯 |
| `device.air-conditioning` | Tabler | single | 16/20/22/24/32/44/56 | `ic_device_air-conditioning.png` | 空调｜空调、air、conditioning、制冷、冷气 |
| `device.windmill` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_device_windmill_off.png`<br>`ic_device_windmill_on.png` | 风扇/风机｜风扇/风机、windmill、风扇、风机、新风 |
| `device.tv` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_device_tv_off.png`<br>`ic_device_tv_on.png` | 电视｜电视、tv、device、电视机 |
| `device.cctv` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_device_cctv_off.png`<br>`ic_device_cctv_on.png` | 摄像头｜摄像头、cctv、device、监控、安防 |
| `device.device-speaker` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_device_device-speaker_off.png`<br>`ic_device_device-speaker_on.png` | 智能音箱｜智能音箱、device、speaker、音箱 |
| `device.plug` | Tabler | single | 16/20/22/24/32/44/56 | `ic_device_plug.png` | 插座｜插座、plug、通电、插头 |
| `device.plug-connected` | Tabler | single | 16/20/22/24/32/44/56 | `ic_device_plug-connected.png` | 插座已接｜插座已接、plug、connected、通电中 |
| `device.thermometer` | Tabler | single | 16/20/22/24/32/44/56 | `ic_device_thermometer.png` | 温度计｜温度计、thermometer、温控、温度 |
| `device.door` | Tabler | single | 16/20/22/24/32/44/56 | `ic_device_door.png` | 门｜门、door、门磁 |
| `device.window` | Tabler | single | 16/20/22/24/32/44/56 | `ic_device_window.png` | 窗｜窗、window、窗户 |
| `device.vacuum` | Tabler | single | 16/20/22/24/32/44/56 | `ic_device_vacuum.png` | 扫地机｜扫地机、vacuum、cleaner、扫地机器人、清洁 |
| `device.wash-machine` | Tabler | single | 16/20/22/24/32/44/56 | `ic_device_wash-machine.png` | 洗衣机｜洗衣机、wash、machine |
| `device.microwave` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_device_microwave_off.png`<br>`ic_device_microwave_on.png` | 微波炉｜微波炉、microwave |
| `device.fridge` | Tabler | single | 16/20/22/24/32/44/56 | `ic_device_fridge.png` | 冰箱｜冰箱、fridge |
| `device.bath` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_device_bath_off.png`<br>`ic_device_bath_on.png` | 卫浴｜卫浴、bath、浴缸、浴室、热水 |
| `device.sofa` | Tabler | single | 16/20/22/24/32/44/56 | `ic_device_sofa.png` | 沙发｜沙发、sofa |
| `device.bed` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_device_bed_off.png`<br>`ic_device_bed_on.png` | 床｜床、bed、卧室 |
| `device.solar-panel` | Tabler | single | 16/20/22/24/32/44/56 | `ic_device_solar-panel.png` | 太阳能｜太阳能、solar、panel、光伏 |
| `device.robot` | Tabler | single | 16/20/22/24/32/44/56 | `ic_device_robot.png` | 机器人｜机器人、robot |
| `device.fire-extinguisher` | Tabler | single | 16/20/22/24/32/44/56 | `ic_device_fire-extinguisher.png` | 灭火器｜灭火器、fire、extinguisher、消防 |

### vehicle（两轮车仪表）—— 12 个

| 名字 | 来源 | 状态 | 建议尺寸 | 产物文件名 | 说明 / 关键词 |
|---|---|---|---|---|---|
| `vehicle.scooter` | Tabler | single | 16/20/22/24/32/44/56 | `ic_vehicle_scooter.png` | 电动车｜电动车、scooter、electric、两轮车、踏板车 |
| `vehicle.motorbike` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_vehicle_motorbike_off.png`<br>`ic_vehicle_motorbike_on.png` | 摩托｜摩托、motorbike、摩托车 |
| `vehicle.steering-wheel` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_vehicle_steering-wheel_off.png`<br>`ic_vehicle_steering-wheel_on.png` | 方向盘｜方向盘、steering、wheel |
| `vehicle.engine` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_vehicle_engine_off.png`<br>`ic_vehicle_engine_on.png` | 引擎｜引擎、engine、发动机 |
| `vehicle.road` | Tabler | single | 16/20/22/24/32/44/56 | `ic_vehicle_road.png` | 道路｜道路、road、路面 |
| `vehicle.traffic-light` | Tabler | single | 16/20/22/24/32/44/56 | `ic_vehicle_traffic-light.png` | 红绿灯｜红绿灯、traffic、light、lights、交通灯 |
| `vehicle.car` | Tabler | off/on | 16/20/22/24/32/44/56 | `ic_vehicle_car_off.png`<br>`ic_vehicle_car_on.png` | 汽车｜汽车、car、轿车 |
| `vehicle.turn-left` | 自绘 | off/on | 22/24/32/44/56 | `ic_vehicle_turn-left_off.png`<br>`ic_vehicle_turn-left_on.png` | 两轮车仪表转向箭头（自绘：Tabler 的箭头是细线，仪表要粗实）｜两轮车仪表转向箭头、turn、left、左转、转向灯 |
| `vehicle.turn-right` | 自绘 | off/on | 22/24/32/44/56 | `ic_vehicle_turn-right_off.png`<br>`ic_vehicle_turn-right_on.png` | 同 turn-left，方向相反｜同 turn-left，方向相反、turn、right、右转、转向灯 |
| `vehicle.headlight` | 自绘 | off/on | 22/24/32/44/56 | `ic_vehicle_headlight_off.png`<br>`ic_vehicle_headlight_on.png` | 大灯（近光）：off 白描边 / on 实心 + 两道近光光束（对应旧版 ic_light_*_on 的琥珀色，用 --color 烘焙）｜大灯：off 白描边 / on 实心 + 两道近光光束、headlight、大灯、近光灯、车灯 |
| `vehicle.high-beam` | 自绘 | off/on | 22/24/32/44/56 | `ic_vehicle_high-beam_off.png`<br>`ic_vehicle_high-beam_on.png` | 远光：on 态光束多两道（与近光区分）｜远光：on 态光束多两道、high、beam、远光灯、远光 |
| `vehicle.cruise` | 自绘 | off/on | 22/24/32/44/56 | `ic_vehicle_cruise_off.png`<br>`ic_vehicle_cruise_on.png` | 定速巡航 = 闪电（旧版 ic_cruise_* 同构）｜定速巡航 = 闪电、cruise、定速巡航、巡航、定速 |

---

## 5. 接入 FlyThings 工程

**方式 A：生成到工程（推荐）**
```bash
python scripts/gen_icons.py --set system --size 22 --color 255,255,255 \
       --out /path/to/MyApp/app/resources/images
python scripts/gen_icons.py --name control.toggle-right --size 44 --color 52,199,89 \
       --out /path/to/MyApp/app/resources/images
```
**方式 B：拷现成产物** —— `out/22|24|56/*.png`（**本机生成、不入库**，首次用先按 §2.1 重建）
挑需要的拷（别整目录拷）。
**方式 C：深/浅主题两套** —— 同图标不同 `--color` 生成两次，工程里用不同目录区分。

布局 json 片段：
```json
{
  "textview__1": {
    "caption": "ImgWeather", "id": 50001, "touchable": false,
    "position": { "left": 40, "top": 26, "width": 56, "height": 56 },
    "backgroundPic": "images/ic_weather_partly-cloudy_on.png"
  },
  "button__2": {
    "caption": "BtnToggle", "id": 20001, "touchable": true,
    "position": { "left": 560, "top": 196, "width": 44, "height": 44 },
    "picTab": { "pic0": "images/ic_control_toggle-right_on.png" }, "text": ""
  }
}
```
`example/` 有能跑的最小例子（18 个控件，语义名 → 图标 → json → 校验 → 预览图）。

---

## 6. 质检（selfcheck）

```bash
python scripts/selfcheck.py                  # 递归检查 out/（标准产物目录）
python scripts/selfcheck.py --out out/22
python scripts/selfcheck.py --json
python scripts/selfcheck.py --skip-render    # 跳过全量渲染自检（快）
```

| 编号 | 断言 |
|---|---|
| A | 命名符合 `ic_<分类>_<名字>[_<风格>][_off\|_on].png` |
| B | 每个 PNG 的**像素尺寸严格等于**生成时请求的尺寸（读 `_manifest.json`） |
| C | α 只含 0/255 与少量抗锯齿中间值（中间值 ≤ 全图 15%）；**无孤立半透明噪点** |
| D | `catalog.json` ↔ `svg/` ↔ `vendor/` 三方对齐（引用的源都存在——vendor 线走归档/缓存解析；tags/sizes/source 齐全） |
| E | catalog 里每个 图标×风格×状态 都能渲染成功（22px+56px）且非空白（覆盖 ≥2%） |
| F | 同一目录内不允许多种尺寸混放 |
| I | out/ 下不允许出现 catalog 之外的陈旧 PNG（`demo/`、`_` 前缀目录豁免） |

实测（`--all` 生成 22/24/56 后）：


---

## 7. 数据来源与许可

| 来源 | 许可 | 说明 |
|---|---|---|
| Tabler Icons **3.46.0**（outline 4754 + filled 1019） | **MIT** | 全量镜像，打进 `vendor/tabler-3.46.0.pack.tgz`（sha256 `a0ba69f2…1c95`；`brand-*` 品牌 logo 376 个已排除）；`LICENSE` 留在归档外随资产分发；**图形未修改**，只做单色化 + 等比缩放。上游 tarball sha256 见 `catalog.json` 的 `sources.vendor` |
| 自绘（`svg/vehicle/*`） | 本项目 | 两轮车仪表一套（转向箭头/大灯/远光/定速巡航），无第三方版权 |
| 被取代的 v0.1.0 自绘集 | 本项目 | **v0.3.0 起已移出仓库**（原 `svg_retired/` 162 个 svg / 0.12 MB）：几何定义仍在 `scripts/author_svg.py`，实测 `python scripts/author_svg.py` 可逐字节重生（163 文件 sha256 全同），故不再占版本库 |

详见 `THIRD-PARTY.md`。

---

## 8. 限制 / 排错

**限制**
- 单色。彩色插画/品牌 logo 不在范围内（品牌 logo 也不允许进）。
- 只有 Tabler 收录的 152 个语义图标 + 自绘 5 个；要更多图标：往 `map.json` 加一条
  （`{name, category, tabler/"compose", outline, filled}`）→ 重跑 `gen_catalog.py` 即可。
- 非正方形只能"等比居中留白"（`--size 22x16`）；要贴边铺满得自己裁。
- Tabler 无 filled 的图标（66 个）没有"选中态"造型，只能靠颜色区分。

**排错**
| 现象 | 原因 / 处理 |
|---|---|
| 图标被拉伸 | 控件 `position` ≠ 图片像素尺寸；用 `--size` 重生成或改控件盒 |
| 找不到 `vendor/tabler/icons/*.svg` | v0.3.0 起散件已收进归档（**正常**）：`--pack-info` 看来源；要逐个看名用 `--list-tabler`；要用归档外的文件先 `--svg-dir`/`--svg`（读取层会自动按需解到 `out/.icons-cache/`） |
| `--vendor-name` 报「匹配到多个」 | 该词同时是别的图标别名；改用全名（如 `system.wifi-full`）或 `--list-vendor <分类>` 看候选 |
| 屏幕上空白/方块 | `backgroundPic` 路径写错（相对 `resources/`，写 `images/xxx.png`）；或没进包（重新 build） |
| 22px 发虚 | 检查控件盒是否 == 22（§3.1）；本套在 22px 用整数像素线宽 + α 整形修过 |
| 深浅主题色不对 | 颜色是烘焙的，浅色主题要 `--color 51,51,51` 再生成一套 |
| `--name` 找不到 | `--list` 看名字；旧工程名（`wx_*`/`ico_*`/`ic_left_*`）也能查；见 `legacyMap` |
| 想改图标样子 | vendor 图形**不改**（MIT 要求可改但没必要）：要么换语义名，要么把新图放
  `svg/` 并在 `author_svg.py` 里加一条自绘定义，再重跑 `gen_catalog.py` |

---

## 9. 加图标 / 改图标 / 重新生成

```
=== selfcheck: components/icons ===
  · catalog: 203 个图标 / 305 张产物 / 自绘矢量源 10（vendor 引用 269）
  · 图标来源：归档 tabler-3.46.0.pack.tgz（5774 条目 / 0.43 MB）｜缓存 out/.icons-cache（269 文件）｜磁盘散件 无
  · out\22: manifest 305 张（size=22x22, color=255,255,255）
  · ic_system_wifi-0.png 属合法极小图形（覆盖率 0.62%，白名单）
  · out\22: 305 张，最差中间值占比 9.7%（ic_device_wash-machine.png），覆盖率区间 0.6%~66.1%
  · out\24: manifest 305 张（size=24x24, color=255,255,255）
  · out\24: 305 张，最差中间值占比 9.0%（ic_system_settings_off.png），覆盖率区间 0.7%~68.8%
  · out\56: manifest 305 张（size=56x56, color=255,255,255）
  · out\56: 305 张，最差中间值占比 2.8%（ic_system_settings_off.png），覆盖率区间 0.5%~66.7%
  · 渲染自检：305 个 图标×风格×状态 × [22, 56]
--- PASS：915 张 PNG，0 失败，0 警告
```

> 实测（2026-09-17，v0.3.0）：`out/` 整目录删掉后按 §2.1 重建 → 305×3 张 PNG + 7 张 sheet
> 全部重生，selfcheck 915 张 0 失败；期间缓存从 0 长到 269 个文件（= 真正被用到的 SVG 数，
> 其余 5500+ 个 glyph **一个都没解出来**）。

---

## 10. 变更记录

| 版本 | 日期 | 内容 |
|---|---|---|
| **0.3.0** | 2026-09-17 | **单归档 + 按需解，离线优先（方案 A）**：①vendor 的 5777 个 SVG 散件（3.95 MB）→ **1 个归档** `vendor/tabler-3.46.0.pack.tgz`（455,379 B，sha256 `a0ba69f2…1c95`，确定性可复现），`map.json` 收进归档，`index.json`/`LICENSE`/`VERSION.txt` 留在归档外；②`gen_icons.py` 新增**图标来源解析**（① 缓存 `out/.icons-cache/` → ② 归档随机读按需解 → ③ 可选远端 npm 拉取，**默认关闭**，需 `--fetch-remote`）——`--vendor-name`/`--svg`/`--set`/`--sheet` 用法与输出不变；③新增 `--list-tabler`（Tabler 原生名全量）与 `--pack-info`（来源状态）；④`out/` 817 个生成物 `git rm --cached` + 进 `.gitignore`（现场可重建，实测 305×3 + 7 sheet 全重生）；⑤`svg_retired/` 163 文件移出仓库（`author_svg.py` 可逐字节重生）；⑥新增 `scripts/make_pack.py`（打归档 / `--verify` / `--from-npm` 离线重建）；⑦修 `--vendor-name wifi` 被 `system.wifi-full` 别名抢匹配（改为精确名优先）。**仓库内 `components/icons/`：6801 文件 / 6.30 MB → 48 文件 / 1.63 MB** |
| 0.2.0 | 2026-09-16 | **转向 vendor**：收录 Tabler Icons 3.46.0（MIT）152 个语义图标（含 7 条 compose 组合），自绘只保留两轮车仪表 5 个；渲染器补齐 Tabler 真实口径（根属性继承、`S/T` 指令、**nonzero 绕序挖孔**、跳过透明包围盒、`A` 弧转采样）；新增 `--vendor-name` / `--svg` / `--size WxH` / compose alpha 合成 / 两态自动配对；`catalog.json` 改为 `gen_catalog.py` 生成（禁止手写）；selfcheck 增加"陈旧产物"断言（I） |
| 0.1.0 | 2026-09-15 | 首版：自绘 86 图标（天气/开关选项/系统/设备）× ios+material，162 张产物。**已被 0.2.0 取代**，几何留档在 `svg_retired/` 与 `scripts/author_svg.py` |
