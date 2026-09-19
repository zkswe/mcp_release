# 设备部署体积与内存预算（小内存设备必看）

> 实测来源：Z21（`Zkswe_SSD21X_SPINOR`）2026-09-16 —— 曾因部署体积把设备搞到 OOM 反复重启，表现像「WiFi 坏了」。
> 适用：**内存 ≤ 64MB 的真机**（Z20/Z21 这类 SigmaStar 板子尤甚）。
> 检索词：部署体积 / 内存预算 / OOM 杀 zkgui / 设备重启 / 整板掉网 / 温和终止 / kill -TERM / kill -9 / 重启应用进程。

## 1. 先量三个数

```bash
adb shell "free; df -h /tmp; /tmp/busybox du -sk /tmp/* | sort -n"
```

Z21 实测：`Mem total 36072 kB`（**36MB**）；`/tmp` = **tmpfs 13.6MB**（tmpfs 占的是 RAM，不是磁盘！）。

## 2. 铁律：`fun launch` 的产物全部落在 /tmp（= 吃内存）

一次 `fun launch` 至少推：`/tmp/lib/libzkgui.so` + `/tmp/font/font.ttf` + `/tmp/ui/main.ftu` + `/tmp/EasyUI.cfg`。
**字库是最大头**（思源黑体常用字 872KB，全量版 7.5MB / 多语言 10.7MB）——加上 tmpfs 里已有的调试工具（busybox 1.9MB 等），
很容易把可用内存压到几百 KB → **OOM killer 杀 `zkgui` → 设备重启**。

**症状对照**：内核日志出现
`Out of memory: Kill process <pid> (zkgui_ui) score ... ` + `oom_reaper: reaped process ...`，
重启后 `/tmp` 全空（连 `EasyUI.cfg` 都没了）→ UI 回到出厂页（看起来"程序没生效"）。

## 3. 处置顺序（按性价比）

1. **清 tmpfs 垃圾**：重复的 busybox、旧工程的 `ui/images`、`ui/fonts`、用不到的 `.ftu`。
2. **字库按工程实际用字裁剪**（最有效，872KB → 数十 KB）：
   ```bash
   python tools/ui_tools/font_subset_by_project.py <项目根> \
       [--src tools/FlyThings_mcp_open/components/fonts/fonts/zkswe-hans-full.ttf]
   ```
   - 默认源 = `zkswe-hans-common.ttf`（GB2312 一级字）→ **只含一级字**，像「阈」这种二级字会缺字形（界面少一笔）。
   - 需要覆盖更多字（如「阈」）时用 `--src` 指到 `zkswe-hans-full.ttf`（7.4MB 源，产出仍只有几十 KB）。
   - ⚠️ **改完 UI 文案要重跑**：新增的字若不在字库里会**静默缺字**（例如按钮「系统 WiFi 设置」少了个「系」）。
3. 部署完复量：`free` 里 `available` 应回到 **10MB+**（Z21 清理后 17MB）。
4. 长期方案：`update.img` 固化（程序进只读分区），不再吃 tmpfs。

## 4. 两条部署侧坑

- `adb push` **不带执行位** → 推完必须 `chmod 777 /tmp/xxx`（否则 `can't execute: Permission denied`）。
- 设备**重启会清空 /tmp**（含 `EasyUI.cfg`）→ 必须用 `fun launch` **整套**重新部署；
  **只 push 单个文件会跑出厂 UI**（缺 `EasyUI.cfg` 时 zkgui 走默认资源路径，现象是"我的界面没出现"）。
- `fun launch` 偶发 `FATAL read tcp 127.0.0.1:5037 i/o timeout` / `device offline`：重连（`adb connect <ip>:5555`）后重试即可，
  压测类程序反复断电 WiFi 时网络 adb 必然抖。

## 5. 重启应用进程：温和终止优先（`kill -TERM` → 必要时才 `kill -KILL`）

**口径（2026-09-17，钟工；⚠️ 因果未定，不当作已证实结论）**：

- 现场疑似复现两类「整板掉网」：① 多次 `kill -9 zkgui` 之后；② deploy 脚本里的 `adb reboot` 之后。
  **两条现象互相矛盾，因果关系未确证**（可能都是网络 adb / tmpfs / 供电抖动导致的偶发）。
- 据此只做一个**无害的防御性改动**：重启应用进程一律 **`kill -TERM` 优先** —— 给 zkgui 一个正常收尾的机会
  （关 fb / disp 图层 / 套接字），轮询等它退出（**约 3 秒**），仍活着才回退 `kill -KILL`。
  行为等价（init 都会自动 respawn），不多花时间；日志要把「用了哪条、是否回退」打出来（可取证）。
- 实现（单一来源）：MCP 侧 `adb_tools.restart_app(adb, serial, name='zkgui')`；
 案例侧 `deploy_z21.py` 同姿势（原组件示例 `components/ui_v1/WheelPicker/example/tools/deploy.py` 随该自绘包 2026-09-19 一并移除）。
- **遇到掉网怎么处理**：按**现场断电重启**处理（先看设备电源/网线/WiFi，再 `adb connect`），
  **不要**据此得出「kill -9 会掉网」或「reboot 会掉网」的结论，也不要拿它当改代码的依据。
- 另：`adb reboot` 后 /tmp 是空的（tmpfs）→ 必须**整套重推**（见 §2/§4），且重启后要等网络 adb 重新上线。
