# 📋 Datasheet — 芯片平台规格书

存放各芯片平台的规格书（Datasheet）、产品简介、硬件参考手册等文档。

## 目录结构

### 🧠 主控芯片

| 子目录 | 芯片/平台 | 架构 | 文件数 |
|--------|----------|------|--------|
| `f133/` | 全志 F133/F135/F136/F102MX | RISC-V C906 | 4 |
| `f101/` | 全志 F101 | RISC-V | 3 |
| `t113/` | 全志 T113-S3/T113-I | ARM Cortex-A7 | 5 |
| `v85x/` | 全志 V553/V851S/V851S3/V853 | ARM Cortex-A7 | 4 |
| `ssd20x/` | SigmaStar SSD202D/SSD212/SSD2353 | ARM Cortex-A7 | 4 |
| `ssd210/` | SigmaStar SSD210（含核心板） | ARM Cortex-A7 | 4 |
| `mcu/` | FR800x MCU 系列 | MCU | 3 |
| `board/` | 整板/整机规格（串口屏、广告机、86盒等） | — | 9 |

### 文件清单

#### f133/ — F133/F135/F136/F102MX（RISC-V C906）
| 文件 | 说明 |
|------|------|
| `F133 brief_V1.4.pdf` | F133 产品简介 |
| `F135_Brief_V0.90.pdf` | F135 产品简介 |
| `F135_Datasheet_V0.90.pdf` | F135 数据手册 |
| `F136_Datasheet_V0.90.pdf` | F136 数据手册 |
| `F102MX_Datasheet_V0.11_Draft_Version.pdf` | F102MX 数据手册（草案） |

#### f101/ — F101（Allwinner RISC-V）
| 文件 | 说明 |
|------|------|
| `F101_Brief_V0.12_Draft_Version.pdf` | F101 产品简介 |
| `F101_Datasheet_V0.10_Draft_Version.pdf` | F101 数据手册 |
| `F101_User Manual_V0.11_Draft_Version.pdf` | F101 用户手册 |

#### t113/ — T113-S3/T113-I（ARM Cortex-A7）
| 文件 | 说明 |
|------|------|
| `T113-i brief-V1.1.pdf` | T113-I 产品简介 |
| `T113-I核芯模组规格书V1.0-20250521.pdf` | T113-I 核心模组规格书 |
| `T113-S3_Brief.pdf` | T113-S3 产品简介 |
| `T113-S3核芯模组规格书V1.3-20230315.pdf` | T113-S3 核心模组规格书 |
| `T113开发板规格简介V2.0-20231220.pdf` | T113 开发板规格简介 |

#### v85x/ — V553/V851S/V851S3/V853（ARM Cortex-A7）
| 文件 | 说明 |
|------|------|
| `V553 Brief_CN_V1.00.pdf` | V553 产品简介 |
| `V851S_Brief_CN_V1.1.pdf` | V851S 产品简介 |
| `V851S3_Brief_CN_V1.2.pdf` | V851S3 产品简介 |
| `V853 Brief_CN_V1.7.pdf` | V853 产品简介 |

#### ssd20x/ — SigmaStar SSD202D/SSD212/SSD2353（ARM Cortex-A7）
| 文件 | 说明 |
|------|------|
| `SSD202D_Datasheet_V0.4.pdf` | SSD202D 数据手册 |
| `SSD202D_DS_V05.pdf` | SSD202D 数据手册 v0.5 |
| `SSD212_DS_V05.pdf` | SSD212 数据手册 |
| `SSD2353_PB.pdf` | SSD2353 产品简介 |

#### ssd210/ — SigmaStar SSD210（ARM Cortex-A7）
| 文件 | 说明 |
|------|------|
| `SSD210_pb_v01_中科世为.pdf` | SSD210 产品简介 |
| `SWC-2A SSD210 双核A7核心板规格书.pdf` | SSD210 核心板规格书 |
| `SWC-2A SSD210底板+4.58寸屏幕.pdf` | SSD210 底板+4.58"屏 |
| `SWC-2A SSD210底板+屏幕 .pdf` | SSD210 底板+屏幕 |

#### mcu/ — FR800x MCU
| 文件 | 说明 |
|------|------|
| `FR8000 Specification V1.1.4.pdf` | FR8000 规格书 v1.1.4 |
| `FR8000 Specification V1.1.5.pdf` | FR8000 规格书 v1.1.5 |
| `FR8000 SDK 用户手册 V1.1.pdf` | FR8000 SDK 用户手册 |

#### board/ — 整板/整机
| 文件 | 说明 |
|------|------|
| `SW80480070D-CK系列型.pdf` | 屏幕规格 |
| `ZK-113M广告机主板规格简介V2.1.pdf` | ZK-113M 广告机主板 |
| `深圳市中科世为公版Z21平台7寸串口屏RE辐射测试.pdf` | Z21 串口屏辐射测试 |
| `深圳市中科世为公版Z21平台7寸串口屏规格书简介.pdf` | Z21 串口屏规格书 |
| `MCU双屏使用说明书V2.0.pdf` | MCU 双屏使用说明 |
| `SV50PD核心板规格书V3.0-20210813.pdf` | SV50PD 核心板 |
| `SW10600070D_C(sv50pd).pdf` | SV50PD 相关规格 |
| `86盒系列/` | 深圳中科世为科技4寸86盒系列规格书等 |

---

## 文档命名规范

```
<芯片型号>_<文档类型>_<版本>.pdf
```

文档类型：`Datasheet`（数据手册）、`Brief`（产品简介）、`User Manual`（用户手册）

## 用途说明

这些规格书可用于：
- **项目选型** — 对比各芯片平台的能力（主频、内存、编码能力等）
- **硬件评估** — 确认 PCBA 接口、电源、尺寸是否匹配
- **性能参考** — 了解编码/解码/显示等能力上限

*最后更新：2026-06-29，共 36 个文件*
