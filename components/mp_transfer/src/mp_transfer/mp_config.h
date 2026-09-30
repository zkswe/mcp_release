/*
 * mp_config.h —— mp_transfer 编译期配置（组件自带默认值，工程侧可覆盖）
 *
 *  MP_PATH     落盘目录，**必须带末尾 '/'**。
 *              默认 "/mnt/sdnand/album/"；改这里，或编译时 -DMP_PATH=\"/your/dir/\" 覆盖。
 *              ⚠️ 与业务侧配置（如 zk::album 的 Config::save_dir）必须一致。
 *
 *  媒体解析（宽高 / 时长 / 照片-视频分类）：
 *    · 默认**不解析** —— 组件只填 path / name / size / last_modified，category = UNKNOWN
 *      （只收不解析，不影响传输与落盘；业务要列表/计数够用）。
 *    · 要真解析，两种方式（二选一）：
 *        ① 编译加 -DMP_TRANSFER_HAVE_FILE_PARSER=1，并把工程里
 *           "mtp_monitor/file_parse_manager.h" 放进 include 路径（原工程就是这么用的）；
 *        ② 在工程里提供 **强符号** TransferFileInfo mp_parse_file(const std::string&)
 *           （覆盖本组件里那个 __attribute__((weak)) 默认实现）。
 */

#ifndef MP_TRANSFER_MP_CONFIG_H_
#define MP_TRANSFER_MP_CONFIG_H_

#ifndef MP_PATH
#define MP_PATH "/mnt/sdnand/album/"
#endif

#include <string>
#include "system/transfer_type_and_data.h"

/* 解析钩子：组件内给弱符号默认实现；工程可用强符号覆盖 */
TransferFileInfo mp_parse_file(const std::string& path);

#endif /* MP_TRANSFER_MP_CONFIG_H_ */
