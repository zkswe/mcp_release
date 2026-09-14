# libzkble.a 构建信息（zk::ble 组件静态库）

构建时间：2026-09-14 13:02

| 平台 | 后端 | 依赖包（工程侧还需声明） | 导出符号 | 大小 | SHA256(前16) | 说明 |
|---|---|---|---|---|---|---|
| f133 | btstack | btstack 1.7.2 + easyui 2.9.0 | 30 | 417706 B | `1116B66C8726FBB3` | F133 RISC-V musl；中心侧 |
| v85x | btstack | btstack 1.7.2 + easyui 2.9.0 | 30 | 120384 B | `610FFE339569AE34` | V85X ARM musl；中心侧（本机注册表只有 btstack 1.7.2；包站 1.8.0 未本地安装，装了以后重跑本脚本即可） |
| z20 | gatt | gatt 1.0.0 | 30 | 183702 B | `305772356386E018` | Z20 ARM glibc；主从双角色（真机跑通） |
| z21 | gatt | gatt 1.0.0 | 30 | 183702 B | `305772356386E018` | Z21 ARM glibc；主从双角色（真机跑通） |

> 头文件：`include/zk/zk_ble.h`（唯一对外面，不含任何底层类型）。
> 链接：工程除本库外还要按平台声明底层包（btstack 后端 -> `btstack` + `easyui`；gatt 后端 -> `gatt 1.0.0`），
>       并保证与 libzkble.a 用**同一套工具链/libc**（f133=RISC-V musl、v85x=ARM musl、z20/z21=ARM glibc）。
> 源码不随本仓发布（私有维护）；本文件即"这个二进制是怎么来的"的凭据。
> 符号自检：`python components/ble/scripts/verify_lib_symbols.py`（核对每个平台的 .a 是否导出全部公开 API）。
