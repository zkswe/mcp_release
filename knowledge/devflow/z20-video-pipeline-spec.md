---
id: devflow-z20-video-pipeline-spec
title: Z20 视频链路规格（素材编码 → 解码 → 上屏）—— H.264 去 B 帧与块状花屏硬约束
category: devflow
status: review
confidence: manual
verified_at: 2026-10-01
stale_days: 180
origin: partial
source: 2026-10-01 由 workspace references/kb/z20-video-pipeline-spec.md（229 行，含需求方新增「H.264 必须去 B 帧」要素）+ split_wall.py / README 与既有 kb 条目交叉核对后入库；未能取证的条目只标注不引数字
needs_evidence: true
platforms: [Z20]
tags: [视频链路, 去B帧, 块状花屏, MI VDEC, 通道属性, H264, H265不支持, 素材编码, 播放判据, 拼墙起播]
evidence:
  - "去 B 帧来历：tools/video_wall/split_wall.py L68-L79、tools/video_wall/README.md L179-L184 与 L215（Z20 编码建议表 B 帧 0）；判据 has_b_frames==0 见 memory/2026-09-29.md L6"
  - "块状花屏与通道属性：references/kb/z20-mi-vdec-channel-attrs.md §1（块度 1.53~1.81→1.08~1.17）、§2（固化于 libmi-module.a 成员 h264_player.o）、§5、§7（厂商实建值 524288/1/INPLACE）"
  - "素材与通道一致正反证：temp/h265_probe/REPORT.md §4.2（A 用例 chn0 H264 480 480 2097152 能播；B 用例 HEVC 报错 0 帧）"
  - "H.265 交付不支持：temp/h265_probe/REPORT.md §2.1/§2.2/§2.4/§5/§6.3；原文 temp/h265_probe/evidence/probe2_h265.txt"
  - "播放侧判据：references/kb/video-wall-sync.md §9.5（bind mi_vdec chn1）、§10.1（GOP 内丢包→P 帧花屏）、§12.7（dropGop==0、块度 1.07/1.00）"
---

# Z20 视频链路规格（素材编码 → 解码 → 上屏）

> 适用平台：**Z20**（SigmaStar 方案）。本条目是 MCP 侧速查；完整规格（含逐条出处、现象→根因→做法→判据、未取证清单 8 条）见工作区 `references/kb/z20-video-pipeline-spec.md`。
> 同源：`knowledge/devflow/video-wall-sync.md`（起播/相位）、`knowledge/devflow/device-screenshot.md`（抓帧）、`knowledge/hardware/*`（分区与现场）。
> 相关工具：`tools/video_wall/split_wall.py`（切段，已含 `bf=0`）、`tools/video_wall/README.md`（Z20 编码参数建议表）。

## 0. 硬约束速查（照做即可）

| # | 环节 | 约束 | 不做的后果 | 判据 / 怎么发现 |
|---|------|------|-----------|----------------|
| 1 | 编码 | **H.264 必须去 B 帧：`-bf 0`**| **卡顿**一类问题（2026-10-01 口径）；解码顺序 ≠ 显示顺序，seek/起播也不准 | `has_b_frames=0`（`ffprobe`）；`split_wall.py` 默认 `bf: 0` |
| 2 | 解码 | **素材属性必须与 MI VDEC 通道属性一致**（分辨率/编码/帧内存） | **块状花屏**（块度 1.53~1.81 → 修后 1.08~1.17） | 抓帧算块度；`/proc` 看通道实建值 |
| 3 | 解码 | 通道属性**固化在预编译 `libmi-module.a` 的 `h264_player.o`**| 改错地方 = 白跑（源码移植不覆盖固化值） | `nm`/`objdump` 核对；改完必须 `/proc` 自证 |
| 4 | 编码 | `yuv420p`（硬件只吃 420）、分辨率/帧率**不超屏**、`-fps_mode cfr`、`+faststart`、段内首帧 IDR | 不播 / 起播慢 / 拼接处卡 | `ffprobe` + 真机起播时间 |
| 5 | 编码 | 码率给足（拼墙建议 CRF20 或 2~4 Mbps；本工程 baseline `-crf 21 -maxrate 1500k -bufsize 3000k`） | 细节糊 / 卡顿 | 真机对比 |
| 6 | 编码 | 音频 AAC 160k / 44.1k / 2ch | 无声/爆音 | `ffprobe` |
| 7 | 编码 | **H.265/HEVC 不要用**：Z20 硬件 VDEC 有 HEVC 能力，但**依赖包内 0 个解码器、无 HEVC parser/BSF**，播放核也未打通 → **交付不支持**| 直接不播（`0xa008200f`，0 帧） | `TOTAL decoders=0`；`Codec 'hevc' ... not supported` |
| 8 | 播放 | **GOP 内不能丢包**（丢一片 = P 帧花屏一片）；长稳看 `dropGop=0`、块度 ≈1.0 | 花屏 / 逐渐劣化 | 播放日志 + 抓帧块度 |

## 1. 标准素材编码命令（baseline）

```bash
ffmpeg -i in.mp4 \
  -c:v libx264 -profile:v high -pix_fmt yuv420p -crf 21 \
  -maxrate 1500k -bufsize 3000k -fps_mode cfr \
  -bf 0 \
  -c:a aac -b:a 160k -ar 44100 -ac 2 -movflags +faststart \
  out.mp4
```

- **`-bf 0` 是本规格的第一条硬约束**（新增）：B 帧让解码顺序 ≠ 显示顺序 → 卡顿/seek 不准。
- 同族参数（非强制）：`-refs 1`；`-g` 与切段对齐（拼墙按段切、段内首帧 IDR）。
- 拼墙切段不要手搓：`tools/video_wall/split_wall.py` 已内建 `bf=0`、段一致 fps、首帧 IDR。
- 平台隔离：F133（refs16 + bf≥4 会 HANG）与 V85X（`ZKMEDIA_H264_VBVSIZE`）口径不同，**另见各自条目**，不要套到 Z20。

## 2. 调试与验收口径

- **块状花屏**：抓帧 → 算块度（正常 1.0~1.2，异常 1.5+）；先查"素材属性 vs 通道属性"，再查固化属性。
- **卡顿**：先查素材有没有 B 帧（`has_b_frames`），再查码率/GOP 丢包，再看是否 800×1280 这类大尺寸同步渲染叠加。
- **拼墙/多屏**：相位与整边界起播、`dropGop=0`、通道归属（拼墙播放器在 `chn1`；Z20 屏保 zkmedia 走 FFmpeg 软解、**不建通道**）。

## 3. 未取证（如实标注，勿当结论用）

1. **B 帧在 Z20 上"具体走哪条路径卡"没有 A/B 量化**（目前依据 = 需求方口径 + 切段工具设计前提 `bf=0`，缺 `-bf 0` vs `-bf 3` 真机对照）。
2. B 帧/参考帧与 `max_dec_frame_buffering`/DPB 的关系未测。
3. Z20 H265 通道真机能否解出画面（只到"SDK/驱动/内核具备"）。
4. 码率硬门槛未做阶梯实测；素材分辨率 ≠ 屏时的通道缩放行为未实测。
