# tools/adb/ —— 随包 PC 端 adb（Android Debug Bridge）

> 让客户**不必另外安装 Android SDK / platform-tools** 就能连设备（USB 或网络 adb）。
> 与 `bin_tools/` 的区别：`bin_tools/<平台>/` 里是**设备端** ELF（push 到设备上跑），
> 这里是**PC 端**可执行程序（在电脑上跑）。

## 内容（只带这三件，别的不进包）

| 文件 | 大小 | 说明 |
|------|------|------|
| `adb.exe` | 5,941,760 B | Windows 主程序 |
| `AdbWinApi.dll` | 97,792 B | Windows adb 依赖库（USB 通信） |
| `AdbWinUsbApi.dll` | 62,976 B | Windows adb 依赖库（WinUSB 后端） |

合计 ≈ 6.1 MB。**不带**：`vdisp_capture.exe`（厂家抓屏小工具，与本包无关）、
`adb1DB4.tmp`（临时残留）、`双击查看日志.bat`（本机快捷方式 —— 带绝对路径，且隐私门禁会拦）。

## 来源与版本

- 来源：FlyThings IDE 自带的 `sdk/platform-tools/adb/`（与 `fun` / `fui` 同源发布链；`fsc.exe` 由 IDE 工具链分发，不随本包）。
- 实测版本（随包入库时用本目录的 adb 亲自跑）：

```
$ tools/adb/adb.exe version
Android Debug Bridge version 1.0.41
Version 31.0.3-7562133
```

## 怎么被用到（单一入口 `adb_tools.py`）

仓库根 `adb_tools.py` 是**唯一**知道 adb 在哪的地方，解析优先级：

1. 环境变量 `ADB`（兼容 `FLYTHINGS_ADB`、旧名 `ADB_PATH`）—— 显式指定永远优先；
2. **本目录** `tools/adb/adb.exe`（非 Windows 用 `tools/adb/adb`）；
3. `PATH` 里的 `adb`。

调用方（都走 `adb_tools.resolve_adb()`，不再各写一份）：

- `project_tools.py`：`build_ui_flow` 的设备探测（`adb devices -l` + `getprop ro.product.model`）、
  设备侧 ftu/so 比对（`staleOnDevice`）、`fsc launch -s <serial>` 的选机；
- `ui_tools/device_screenshot.py`：抓屏链路的 adb 定位；
- `i18n_tools.py`：`i18n_to_json` 的 adb push；
- `components/fonts/scripts/device_font_check.py`、案例侧 deploy 脚本（`projects/**/deploy*.py`）。

排查一条命令：

```
python adb_tools.py            # 打印解析来源 + 版本 + 设备列表（型号↔平台匹配）
python adb_tools.py devices    # 只列设备
```

设备型号 → 平台的对照表在仓库根 `device_models.json`（只放型号字符串，不放内网地址）。

## 注意（现场经验）

- **USB 接入还要 ADB 驱动**：本目录给的是 adb 程序本身；Windows 上「设备管理器里带叹号的未知设备」
  = 缺 USB 驱动，需要装厂家驱动或用 Zadig/WinUSB 指定 Android ADB Interface。装完
  `tools/adb/adb.exe kill-server && tools/adb/adb.exe devices` 再试。
- **host server 版本冲突**：adb 客户端会拉起/复用 `127.0.0.1:5037` 上的 host server。
  若本机已有别的 adb（IDE 自带、其它平台的 platform-tools）在跑，可能出现
  `adb server version doesn't match this client` → adb 会杀掉旧 server 重起（正常，一次即可）。
  设备 `offline`/看不到时先 `kill-server` 再 `devices`（比拔插有效）。
- **`fun` 不走这里的 adb**：`fsc launch` 用自带的 Go adb 客户端直连 `127.0.0.1:5037`。
  所以本目录给的是 **MCP 侧探测/比对/抓屏/i18n 推送**用的 adb；两者共用同一个 host server。
- 不要在设备上跑 `adb reboot` 做验证 —— 整机板子重启后可能掉网（现场踩过）。
