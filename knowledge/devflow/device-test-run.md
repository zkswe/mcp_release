---
id: devflow-device-test-run
title: 多设备并行测试跑批 + 机读报告（`flythings_test_run`）
category: devflow
status: verified
confidence: offline
verified_at: 2026-09-29
machine_verified_at: "2026-09-29 20:45:46"
stale_days: 180
origin: total
source: 2026-09-29 front-matter 迁移（P1：先显式登记"待补可执行判据"）
needs_evidence: false
platforms: []
tags: [JUnit 报告, 像素基线, 基线回归, 首次怎么建基线, 比不到基线是过还是没过, 多设备并行, 测试用例 JSON 怎么写, touch 注入怎么批量跑]
evidence:
  - {kind: offline, cmd: python -m unittest tests.test_baseline_testrun -q, expect_rc: 0, expect_contains: OK, ran_at: "2026-09-29 20:45:46", output_sha256: d4b1f449069ce6930e5a978720fcfa60d80d94054422a007e02051dd6b0b67df}
---
# 多设备并行测试跑批 + 机读报告（`flythings_test_run`）

> **检索导引**：自动化测试怎么跑 / 验收怎么批量做 / 多台设备一起跑用例 / 测试报告能进 CI 吗 /
> JUnit 报告 / 像素基线 / 基线回归 / 首次怎么建基线 / 比不到基线是过还是没过 /
> 报告里 no-baseline 什么意思 / 多设备并行 / 测试用例 JSON 怎么写 /
> touch 注入怎么批量跑 / touch / ui_test（兼容老屏）与 test_run 区别 / test_run 与 gen_ui_test 区别

---

## 0. 一句话

`flythings_gen_ui_test` **生成**用例（从 ui/*.json 自动出脚本），
`flythings_test_run` **执行**用例（多设备并行 + 机器可判 + 出报告）。
写业务断言、要回归、要进 CI → 用 `test_run`。

---

## 1. 用例（plan）schema

`plan` 传 JSON 文本或 `.json` 文件路径：

```json
{
  "name": "主界面巡检",
  "steps": [
    {"name": "唤醒", "action": "tap", "x": 240, "y": 240, "wait": 800,
     "shot": "home_awake"},
    {"name": "进设置", "action": "tap", "x": 120, "y": 620, "wait": 1200,
     "shot": "settings", "expectLog": ["onClick"]},
    {"name": "翻页", "action": "swipe", "from": [240, 700], "to": [240, 200],
     "duration": 300, "wait": 500},
    {"name": "自检日志", "action": "log", "lines": 300,
     "expectNoLog": ["FATAL", "segfault", "Assertion failed"]}
  ]
}
```

| 字段 | 作用 |
|------|------|
| `action` | `tap` / `long` / `swipe` / `wait` / `monkey` / `run` / `shot` / `log` |
| `shot` | 截图并存到这个 key（缺省 `shot_<序号>`）；**有 project_root 时会做基线对比** |
| `expectLog` / `expectNoLog` | 日志断言（`logcat -d -t N -s zkgui`）：必须出现 / 必须不出现 |
| `wait` | 动作后等待毫秒（注入类动作才生效） |
| `x` `y` `ms` `from` `to` `duration` `count` `script` `lines` `tag` | 各 action 的专属参数 |
| `timeout` | 单步命令超时秒（缺省 90） |

**判据（不静默）**：注入命令 rc != 0 → `error`；日志断言不过 → `fail`；
截图与基线有差异 → `fail`；**没有基线可比 → `no-baseline`（不算通过，进 warnings）**。

---

## 2. 首次流程（建基线 → 卡回归）

```bash
# ① 先跑一轮把「当前已知good」的状态存成基线（同时产出报告）
flythings_test_run(plan=..., devices="192.168.x.x:5555", project_root="<工程>", baseline="save")
# ② 之后每次改完 UI 跑同一份用例做回归
flythings_test_run(plan=..., devices="all", project_root="<工程>", baseline="compare")
# ③ 确认某次改动就是要的新样子 → 显式刷基线
flythings_ui_visual(action="baseline", project_root="<工程>", mode="update", image_a="<新截图>")
```

- `baseline="auto"`（默认）：能比就比，比不到记 `no-baseline` 并进 warnings。
- `baseline="compare"`（**严格模式**）：明确要回归就**不该缺基线**——缺基线仍报 `no-baseline` 状态，
  但报告里按 **failure** 算（`auto` 才算 skipped）。首次务必先 `save`。
- `baseline="off"`：不做像素判定（只要注入 + 日志断言时用）。
- **每步可单独放宽容差**：step 里写 `"allowRegions": N`（活页面如时钟/温度会自己变，
  实测同一个单台 save→compare 也会因状态文字变化报 1 处差异，给 1~2 的宽容差即可）；
  plan 级 `"allowRegions": N` 作为整份用例的默认，函数参数 `allow_regions` 为最后兵。
- **多台设备自动按设备区分 key**（`per_device_keys="auto"`，缺省）：`shot="panel"` + 两台设备
  → 实际 key `panel@108` / `panel@71`（避免「两台本来就不在同一页」被当成回归差异），
  设备名与回退目录都会写进该设备的 `notes`；想故意跨机共用一把 key 就传 `per_device_keys="off"`。
- 基线库存 `<工程>/ui_baseline/`：`baseline.json`（索引 + 容差档案）+ `<key>.png` + `_diff/<key>.diff.png`。
- **key 必须稳定**（同一页面同一状态永远用同一个 key）；key 变了等于绕过基线。
- 分辨率改了 → `size-mismatch`：**别拿旧基线硬比**，确认新尺寸后 `mode=update` 刷基线。

---

## 3. 报告（机器可读）

| 文件 | 内容 |
|------|------|
| `<out>/report.json` | plan / summary（设备数·步骤数·pass·fail·error·noBaseline·耗时）/ 逐设备逐步骤明细 / warnings |
| `<out>/report.xml` | **JUnit**：`<testsuite>` per 设备… 实际为 `testsuite` 含全部 testcase（`classname=serial`，`name=<action> / <步骤名>`）；`<failure>` / `<error>` / `<skipped>`（no-baseline） |
| `<out>/<serial>/shots/*.png` | 每步截图（取证 + 基线载体） |
| `<out>/<serial>/logcat.txt` | 该设备 `logcat -d -s zkgui` 末 400 行 |

接 CI：`report.xml` 直接喂 JUnit 解析器；退出码看 `success`（有 fail/error/no-baseline 即 false）。

---

## 4. 多设备并行

- `devices="auto"`：**只有恰好 1 台在线才自动选**；多台在线时明确拒绝并给出在线清单（沿用本仓「多设备不猜」口径，防推错设备）。
- `devices="all"`：所有在线设备各跑一遍（用例相同 → 验证一致性/兼容性）。
- `devices="<IP>:5555,<IP>:5555"`：指定若干台；裸 IP 会自动补 `:5555`。
- `parallel`（缺省 4）：并发度，取 `min(parallel, 设备数)`。
- 平台：显式 `platform=` 优先；否则按设备型号查 `device_models.json`（查不到 → 明确报错要求显式传，不猜）。
- 注入工具：自动推 `bin_tools/<平台>/touch` 到 `/data/touch`（**touch 自动扫节点+判协议，不传 eventNo**）。

**并发注意**（硬约束）：

0. **跨设备不要共用同一个基线 key**（真源：`op_spec.json` 的 `flythings_test_run.rules`）（真机实测（2026-09-29））：两台 Z20 用同一 key `panel`
   跑同一用例，一台 pass、一台 fail（32 处差异）——因为**两台设备本来就不在同一页/同一内容**。
   基线是「**某台设备某个状态**该长什么样」，多机一致性验收请用**带设备标识的 key**
   （如 `panel@108`）或分设备建基线库；否则会把“两台机器内容不同”误报成回归。
1. 多台设备**同时**跑同一份用例，屏幕会各自被点——确认没有别人在用这些板子再开。
2. 每台设备各推一份 `/data/touch`（同名文件，互不干扰）。
3. 抓屏/注入都走各自 `-s <serial>`，不会串台；但 **adb 服务端是单点**，`parallel` 别开太大（>4 台时建议分批）。
4. 设备重启类用例（`setprop ctl.restart zkswe`）**不要多台同时做**——会集中占用宿主 adb 与网络。

---

## 5. 坑

| 现象 | 原因 / 处置 |
|------|-------------|
| 单台 save→compare 也报 1~2 处差异 | 页面上有**自己在变的内容**（时钟/温度/动画）：给 step 加 `"allowRegions": 1~2`，或裁到稳定区域，或改日志断言 |
| 全部步骤 `no-baseline` | 还没建基线：先 `baseline="save"` 跑一轮 |
| `size-mismatch` | 工程分辨率变了：确认新尺寸后 `mode=update` |
| 抓屏步骤 `error` 且 hint 提「双缓冲/pan」 | 抓到上一帧：注入前先 `tap` 唤醒重绘，或对同一步抓两次（见 `knowledge/devflow/device-screenshot.md`） |
| 日志断言老不过 | `tag` 不是 `zkgui`，或 `lines` 太小（业务日志被刷屏挤掉缓冲） |
| 注入 `error` 且提 `No space left on device` | 设备 `/data` 写满（Z20 常见）：工具自动退到 `/tmp`→`/mnt/extsd`；三个都放不下就只能先腾空间 |
| 注入 `error` | 设备无 root/权限（`chmod 777` 失败）、平台 ELF 不匹配、触摸节点被占用 |
| 报告里同一设备两条 `testsuite` | 不存在；是按 testcase 逐条列——不要按「用例数 = testsuite 数」读 |

---

## 6. 相关

- 单步工具（人工试）：`knowledge/devflow/touch-inject-autotest.md`（`touch tap/swipe/long/monkey/run/record/play`）
- 像素判据与容差：`knowledge/devflow/ui-asset-rules.md`、`knowledge/devflow/ui-layout-verify.md`
- 整机快照 / 缺陷单：`knowledge/devflow/selfcheck-and-bugreport.md`
- 依赖包真机验证套路：`knowledge/devflow/package-verify-playbook.md`
