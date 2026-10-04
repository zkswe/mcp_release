---
id: devflow-device-storage-full-fallback
title: 设备 /data 写满导致注入工具推不上去（落点 /data → /tmp → /mnt/extsd 回退）
category: devflow
status: verified
confidence: real-device
verified_at: 2026-09-29
machine_verified_at: "2026-09-29 20:45:45"
stale_days: 180
origin: total
source: 2026-09-29 真机实测（两台 Z20 并行跑测试跑批时 push /data/touch 失败）
needs_evidence: false
platforms: [Z20]
tags: [touch 起不来, 设备存储写满, 部署工具放哪, tmp 能不能放工具, 注入失败怎么办]
evidence:
  - {kind: offline, cmd: python -m unittest tests.test_baseline_testrun.TestTouchFallback -q, expect_rc: 0, expect_contains: OK, ran_at: "2026-09-29 20:45:45", output_sha256: 2a50b4749107e50e3993c9a59df48e8d8cebd81e26a286e83bb83d7fe81b2d90}
---
# 设备 /data 写满导致注入工具推不上去（落点回退）

> **检索导引**：push 到 /data 失败 / remote No space left on device / 注入工具推不上去 /
> touch 起不来 / 设备存储写满 / 部署工具放哪 / /tmp 能不能放工具 / 注入失败怎么办
> 口语别名（用户就这么说）：touch 起不来 / touch 注入起不来 / 触摸工具起不来 / 推上去放哪 / /data 满了还能放哪 / 注入工具起不来 / 触摸没反应是不是工具没推上去 / 端口注入失败。

## 现象

`adb push <工具> /data/touch` 报：

```
adb: error: failed to copy '<...>\touch' to '/data/touch': remote No space left on device
```

**2026-09-29 实测**：两台 Z20 并行跑 `flythings_test_run` 时**双双**撞上（`/data` 已满）；
工具若直接报错退出，整批用例就全废。

## 处置（已内建）

注入工具（`bin_tools/<平台>/touch`）落点**逐级回退**：

```
/data  →  /tmp  →  /mnt/extsd
```

- 任一成功即用，并把「用了哪个目录 + 前面为什么失败」写进该设备的 `notes`（可自证）。
- 三个都放不下 → 明确报错：带上最后一次的真实报错 + `hint`（先腾空间，或手动推到 `/tmp`），
  **不静默失败**。
- `/tmp` 是 tmpfs：重启即清，属正常（每次跑批都会重推，代价 ~0.3s）。

## 判据（可复算）

```bash
python -m unittest tests.test_baseline_testrun.TestTouchFallback -q
```

钉住两件事：① `/data` 失败必须回退 `/tmp` 且 `notes` 里有回退记录；
② 三条路径全失败必须返回错误 + `hint`（不许静默返回 None 当成功）。

## 相关

- 测试跑批：`knowledge/devflow/device-test-run.md`
- 部署纪律：`knowledge/devflow/device-deploy-budget.md`
