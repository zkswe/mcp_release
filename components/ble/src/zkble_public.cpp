/*
 * zkble_public.cpp —— 门面公共 API 的实现（**后端无关，两个后端共用，必须一起编译**）
 *
 * 为什么单独一个 TU，而不是在 zkble_common.h 里 inline：
 *   应用只 include 公开头 `zk/zk_ble.h`（看不到定义），inline 函数只会在"被使用的 TU"里发射符号
 *   → 应用 TU 里有调用、没有定义 → 链接期 undefined reference。
 *   （这是子代理做链接验证时暴露出来的真问题，2026-09-14 修。）
 *
 * 编译清单（组件引入工程时这几个 .cpp 都要进构建）：
 *   btstack 后端： src/zk_ble.cpp      + src/zkble_public.cpp
 *   gatt   后端： src/zk_ble_gatt.cpp + src/zkble_public.cpp
 * （后端二选一由 src/zkble_backend.h 判定；zkble_public.cpp 两边都要。）
 */
#include "zkble_common.h"

namespace zk {
namespace ble {

std::string version() { return std::string(ZKBLE_VERSION); }

void setLogHook(LogHook hook) { internal::logHookRef() = hook; }

void onAdapterStateChange(OnAdapterStateChange cb) { internal::cbAdapterRef() = cb; }
void onDeviceFound(OnDeviceFound cb) { internal::cbDeviceRef() = cb; }
void onConnectionChange(OnConnectionChange cb) { internal::cbConnRef() = cb; }
void onValueChange(OnValueChange cb) { internal::cbValueRef() = cb; }
void onWriteRequest(OnWriteRequest cb) { internal::cbWriteRef() = cb; }

void offAll() {
    internal::cbAdapterRef() = NULL;
    internal::cbDeviceRef() = NULL;
    internal::cbConnRef() = NULL;
    internal::cbValueRef() = NULL;
    internal::cbWriteRef() = NULL;
}

}  // namespace ble
}  // namespace zk
