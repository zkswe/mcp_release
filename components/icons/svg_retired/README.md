# svg_retired —— v0.1.0 自绘图标（留档，不参与主线）

这里放的是 **v0.1.0（2026-09-15）自绘的 162 个矢量图标**：
天气 24 / 开关选项 17 / 通用系统 29 / 智能家居设备 16 × ios(线框)+material(实心)。

**为什么留在这里**：v0.2.0（2026-09-16）改成"**收录 vendor（Tabler Icons，MIT）+ 只自绘两轮车仪表**"，
这四类语义图标由 Tabler 承担，于是自绘版退出主线。几何定义仍在 `scripts/author_svg.py`
（可复现，能重新生成这些 svg），只是不再进 `svg/`、不进 `catalog.json`。

**它们不影响任何流程**：
- `gen_catalog.py` 不读这里（清单只来自 `vendor/tabler/map.json` + `author_svg.active_icons()`）；
- `selfcheck.py` 只校验 `svg/`（D 项），不校验 `svg_retired/`；
- 要彻底清理：`rm -rf svg_retired/`（几何还在 `author_svg.py` 里，随时可再生成）。

**什么时候还会用到**：
- 想回退到"自绘 + ios/material 双调性"那套时（把 `author_svg.ACTIVE_CATEGORIES` 放开即可）；
- 天气类需要"与 `projects/inSightOS3` 旧版 `wx_*.png` 像素级一致"的场合
  （这套是按已量产画法 1:1 复刻的，Tabler 版只是同语义不同造型）。
