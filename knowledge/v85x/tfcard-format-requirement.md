---
id: v85x-tfcard-format-requirement
title: 💾 V85X TF 录制卡格式化要求（FAT32 + 64KB 簇 + OEM=zkswe，不满足会被弹窗要求重格）
category: v85x
status: verified
confidence: manual
verified_at: 2026-09-29
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: true
platforms: [V85X]
tags: []
evidence: []
---
# 💾 V85X TF 录制卡格式化要求（FAT32 + 64KB 簇 + OEM=zkswe，不满足会被弹窗要求重格）

> 2026-09-09 沉淀（V85X DVR 录制产品实测）。适用：**V85X**（V853/V553 等）带 TF 卡录像/存储的产品。
> ⚠️ 仅 V85X 平台生效；T113/F133/Z20 无此机制。
> **检索导引**：问「录制卡/SD 卡/TF 卡 格式化、文件系统不符合要求、要不要格式化、exFAT/NTFS 不识别、簇大小、DVR 录不了像」→ 本篇。

## 0. 一句话

**V85X 录制 TF 卡有专属格式要求：FAT32 + 64KB 簇 + OEM 标识 "zkswe"**。
设备插卡后校验簇大小，**不是 64KB（65536 字节）就弹「SD卡文件系统不符合要求 是否格式化？」**；挂载失败会自动强制重格。
**普通电脑格式化的 FAT32（簇 ≤32KB）/ exFAT / NTFS 一律判不符**——这是"录不了像/一直提示格式化"的头号原因。

## 1. 格式规格（设备内写死）

| 项 | 值 | 来源 |
|------|------|------|
| 文件系统 | FAT32 | 命令 `-F 32`（exFAT/NTFS 不识别） |
| 块大小 | 65536 B = 64KB | `-b 65536` |
| 每簇扇区 | 128（512B×128 = 64KB 簇） | `-c 128`（覆盖 `-b` 折算值） |
| OEM 标识 | `zkswe` | `-O zkswe` |
| 校验口径 | statfs `f_bsize == 65536` | 挂载后检测 |

- 格式化器 = 移植的 `newfs_msdos`（设备端工具，命令前端名 `zkrecovery`，入口 `newfs_msdos_main()`），调用形如：
  `zkrecovery -F 32 -O zkswe -c 128 -b 65536 <块设备>`
- 64KB 簇原因推测：录像连续大文件写入，大簇减少 FAT 碎片与寻址开销（代码无注释，不必纠结，检测写死 65536）

## 2. 设备行为（谁触发格式化/校验）

| 场景 | 行为 |
|------|------|
| 卡已挂载且读写测试通过 | 直接用，不动 |
| 卡挂载失败 | umount → 重试挂载 5 次（间隔 1s）→ 仍失败 → **自动强制重格**成上述规格 → 再挂载 |
| 卡挂上但簇不对（电脑格式化过） | 弹窗「SD卡文件系统不符合要求 是否格式化？」（文案 `invalid_tfcard`），确认后格 |
| 卡插入后一直 CHECKING | 3 秒未挂载成功 → 弹同样的格式化确认框 |
| 手动格式化入口 | 设置页「格式化存储卡」按钮 / 系统服务收到存储格式化指令 |

**统一格式化流程**（代码侧 `formatTfcardProcess(record, onSuccess)`）：
停录像 `Recorder::stop()` → umount → `format_fat32fs(块设备)` → `checkAndMount` 重新挂载 → 提示「格式化完成」→ `record=true` 时自动恢复录像。
⚠️ 格式化 = **清空整卡**（含锁定的 SOS/紧急片段）。

**常规定义**（按产品硬件可不同，双介质产品用探针二选一）：
- TF 卡块设备：`/dev/block/mmcblk0`（纯 TF 变体）/ 内置 EMMC 分区 `mmcblk0p1`
- 挂载点：`/mnt/extsd`（TF）/ `/mnt/storage`（EMMC）
- 目录约定：照片 `/photo`、录像 `/video`（如 `/mnt/extsd/video/Rear/`）

## 3. 关键实现骨架（供移植/对照）

```cpp
// 格式化（FAT32 + 64KB 簇 + OEM=zkswe）
void format_fat32fs(const char* block) {
  const char* args[] = {"zkrecovery", "-F", "32", "-O", "zkswe",
                        "-c", "128", "-b", "65536", block};
  newfs_msdos_main(10, args);   // 移植版入口
}

// 挂载 + 自动重格 + 校验
void checkAndMount(block, mount_point) {
  if (已挂载 && 读写测试通过) return;          // 直接可用
  umount(mount_point);
  for (i = 0; i < 5; ++i) {                    // 重试 5 次
    if (mount_vfat(block, mount_point) 成功 && 读写测试通过) return;
    usleep(1s);
  }
  format_fat32fs(block);                        // 仍失败 → 强制重格
  mount_vfat(block, mount_point);               // 重格后再挂
}

// 簇校验（插卡/挂载成功后调用）
int getBlockSize(mount_point) { return statfs(mount_point).f_bsize; }
//   != 65536  → 弹「SD卡文件系统不符合要求 是否格式化？」
```

## 4. ⚠️ 要点 / 排障
1. **设备上录不了像，先怀疑卡被电脑格过**（簇不对/exFAT/NTFS）；用设备自身「格式化存储卡」最稳
2. 量产/测试装机前直接用设备格式化，别用电脑格
3. 文件系统工具链（newfs_msdos）是 V85X 平台 DVR 配套的一部分，随设备系统提供，应用层只调命令/接口
4. 双介质产品（EMMC + TF）：挂载与 USB 存储暴露共用同一介质探针（EMMC 存在 → EMMC 分区，否则 → TF 卡），见 `v85x/usb-gadget-storage.md`

## 5. 参考
- `v85x/dvr-recorder-guide.md`（DVR 录制功能开发 Playbook，存储章节引用本篇）
- `v85x/usb-gadget-storage.md`（EMMC/TF 双介质挂载与 USB 暴露）
- `devflow/package-properties-easyui-cfg.md`（EasyUI.cfg 配置机制，与格式化无关但同为工程级坑位）
