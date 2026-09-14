/*
 * zkble_backend.h —— 后端选择（内部头，不对外）
 *
 * 一个 API 面，两个后端实现文件（**同一平台只编一个**）：
 *   · src/zk_ble.cpp       → btstack 后端（F133 1.7.2 / V85X 1.8.0，串口 HCI + H5）
 *   · src/zk_ble_gatt.cpp  → gatt 后端（Z20/Z21/T113/T113EMMC，AIC USB + BlueZ 用户态 GATT）
 *
 * 判定顺序：
 *   1) 显式宏优先：-DZKBLE_BACKEND_GATT=1 或 -DZKBLE_BACKEND_BTSTACK=1（两个都传 → 编译期报错）
 *   2) 平台宏（fun build 实测会带 -D__PLATFORM_Z20__=1 / __PLATFORM_T113__ 这类）：
 *        Z20/Z21/T113/T113EMMC → gatt；F133/V85X → btstack
 *   3) include 路径探测（__has_include）：有 <btstack/btstack.h> → btstack（**已验证优先**）；
 *        否则有 <gatt/gatt-client.h> → gatt
 *   4) 都没有 → btstack（然后自然报"找不到 btstack/btstack.h"，比静默乱选好）
 *
 * 注意：V85X 同时有 btstack 与 gatt 两个包；本模块默认选 btstack（真机验证过）。
 *       要试 V85X 的 gatt 路线就显式 -DZKBLE_BACKEND_GATT=1。
 */
#pragma once

#if defined(ZKBLE_BACKEND_GATT) && defined(ZKBLE_BACKEND_BTSTACK)
#error "zkble: 只能选一个后端（ZKBLE_BACKEND_GATT 与 ZKBLE_BACKEND_BTSTACK 不能同时定义）"
#endif

#if !defined(ZKBLE_BACKEND_GATT) && !defined(ZKBLE_BACKEND_BTSTACK)
  #if defined(__PLATFORM_Z20__) || defined(__PLATFORM_Z21__) || \
      defined(__PLATFORM_T113__) || defined(__PLATFORM_T113EMMC__)
    #define ZKBLE_BACKEND_GATT 1
  #elif defined(__PLATFORM_F133__) || defined(__PLATFORM_V85X__)
    #define ZKBLE_BACKEND_BTSTACK 1
  #elif defined(__has_include)
    #if __has_include(<btstack/btstack.h>)
      #define ZKBLE_BACKEND_BTSTACK 1
    #elif __has_include(<gatt/gatt-client.h>)
      #define ZKBLE_BACKEND_GATT 1
    #else
      #define ZKBLE_BACKEND_BTSTACK 1
    #endif
  #else
    #define ZKBLE_BACKEND_BTSTACK 1
  #endif
#endif

// 统一成 0/1，方便下面两个后端文件各自设门
#if defined(ZKBLE_BACKEND_GATT)
  #define ZKBLE_IS_GATT 1
  #define ZKBLE_IS_BTSTACK 0
#else
  #define ZKBLE_IS_GATT 0
  #define ZKBLE_IS_BTSTACK 1
#endif
