/* =====================================================================
 * zk_wall_internal.h —— components/wall_sync 内部共享（**不对外发布**，不放进 include/）
 *
 * 只做三件事：
 *   ① 把「日志钩子 / 墙钟钩子 / 组内时钟跟随钩子」收在一处（业务可随时换）；
 *   ② 给实现文件一个统一的日志宏（ZWLOG）；
 *   ③ 放几个两边都要用的小工具（读文件、JSON 取值）。
 * 目的：让 src 下各实现文件里**看不到任何项目私有依赖**（无 StoragePreferences / 无 Log.h /
 * 无 TimeHelper / 无 ClockManager）—— 那些都由业务在构造配置时注入。
 * ===================================================================== */
#ifndef ZK_WALL_INTERNAL_H
#define ZK_WALL_INTERNAL_H

#include "zk/zk_wall.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

namespace zk {
namespace wall {
namespace internal {

/** 组件内的全局钩子（Sync::start()/Player::configure() 写入） */
struct Hooks {
    LogFn logFn;
    void* logUser;
    NowMsFn nowFn;
    void* nowUser;
    ClockFollowFn clockFollowFn;
    void* clockFollowUser;
    Hooks() : logFn(NULL), logUser(NULL), nowFn(NULL), nowUser(NULL),
              clockFollowFn(NULL), clockFollowUser(NULL) {}
};

Hooks& hooks();

/** 打一条日志（钩子没设就丢，避免设备上乱刷 stdout）。 */
void log(int level, const char* fmt, ...);

/** 墙钟毫秒：钩子优先；否则 clock_gettime(CLOCK_REALTIME)（毫秒分辨率）。
 *  两条路都拿不到可信值时返回 <=0（调用方必须当"未校时"处理）。 */
long long nowMsRaw();

/** 读整个文件到 std::string（playlist.json 只有几 KB；上限 4MB 防呆）。 */
bool readFileAll(const std::string& path, std::string* out);

} /* namespace internal */
} /* namespace wall */
} /* namespace zk */

/** 组件统一日志宏（水平与真源一致：DEBUG 心跳 / INFO 状态变化 / WARN 异常可继续 / ERROR 要处置） */
#define ZWLOG(level, ...) ::zk::wall::internal::log((level), __VA_ARGS__)

#endif /* ZK_WALL_INTERNAL_H */
