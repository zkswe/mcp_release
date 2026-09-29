/****** mp_transfer 最小接线示例（设备端） ******
 *
 * 目标：把「小程序发现设备 → 收文件落盘 → 回 ACK/OK」这条链路接进一个 FlyThings/EasyUI 工程。
 *
 * 文件（照 README「怎么用」复制进工程）：
 *   src/mp_transfer/broadcast_task.{h,cpp}       UDP 广播任务（内部自动加 zkswe: 前缀）
 *   src/mp_transfer/tcp_receive.{h,cpp}          TCP 接收核心（包头解析/落盘/ACK/OK）
 *   src/mp_transfer/runtime_coordinator.h        服务启停（retain/release）
 *   src/system/transfer_type_and_data.h          接收结果结构 TransferFileInfo
 *
 * ⚠️ 本文件是**接线示例**（最小可跑形态），不是本仓已上机的产物：
 *    组件形态在本仓没有设备侧验证记录（见 ../platforms.md §0）。
 *
 * 依赖替换点（README「怎么用」第 2 条）：
 *   base::Task / 日志宏 / defer  → 换项目自己的后台线程与 RAII；
 *   MP_PATH                      → 换自己可写的目录（**末尾带 `/`**）；
 *   媒体解析/缓存（FileParseManager 等）→ 可整段删掉，不影响传输与落盘。
 */

#include <stdio.h>
#include <string>
#include <vector>

/* 工程里改成实际路径 */
#include "mp_transfer/runtime_coordinator.h"
#include "mp_transfer/tcp_receive.h"
#include "system/transfer_type_and_data.h"

/* ------------------------------------------------------------------ *
 * 1) 起/停：谁需要这个能力谁 retain，不用了 release（owner 集合，最后一个释放才真正停）
 * ------------------------------------------------------------------ */
static const char *kOwner = "my-project";
static const char *kDeviceName = "My Frame";      /* 小程序看到的名字；空 → 广播用 "Frame" */

static void startMpTransfer() {
	MpTransferRuntimeCoordinator::instance().retain(kOwner, kDeviceName);
	/* 之后：设备每 ≈2s 向 255.255.255.255:8899 发 "zkswe:My Frame"，并监听 TCP 9000 */
}

static void stopMpTransfer() {
	MpTransferRuntimeCoordinator::instance().release(kOwner);
}

/* ------------------------------------------------------------------ *
 * 2) 收文件通知：注册 listener，拿到落盘结果（路径/名字/类别/大小）
 *    ⚠️ 回调在接收线程上跑 → 只置标志位/入队列，别直接动 UI 控件
 * ------------------------------------------------------------------ */
class MyMpListener : public TcpReceiveTask::TcpReceiveListener {
public:
	void onScanFinished(const std::vector<TransferFileInfo> &fileList) {
		printf("[mp] 已缓存文件 %d 个\n", (int) fileList.size());
	}

	void onFileAdded(const TransferFileInfo &info) {
		/* info.path / info.name / info.category(PHOTO|VIDEO|...)/ info.size */
		printf("[mp] 收到文件: %s (%llu B, category=%d)\n",
				info.path.c_str(), (unsigned long long) info.size, (int) info.category);
		/* 这里改成项目自己的"新文件到了"处理：刷新列表 / 入播放队列 / 发通知 */
	}

	void onTcpStateChanged(int state) {
		printf("[mp] TCP 状态变化: %d（isClientConnected=%d）\n", state,
				TcpReceiveTask::instance().isClientConnected() ? 1 : 0);
	}
};

static MyMpListener sListener;

static void registerListener() {
	TcpReceiveTask::instance().addListener(&sListener);
}

static void unregisterListener() {
	TcpReceiveTask::instance().removeListener(&sListener);
}

/* ------------------------------------------------------------------ *
 * 3) 想调接收参数：在 start 之前改 TcpReceiveParams（收不到想改分块/超时/上限时用）
 * ------------------------------------------------------------------ */
static void tuneParams() {
	TcpReceiveParams p;
	p.listen_port = 9000;                       /* 端口固定 9000（小程序侧写死） */
	p.socket_timeout_ms = 2000;                 /* 连接 socket 收发超时，别改太大（协议就是这么定的） */
	p.max_file_size = 500 * 1024 * 1024;        /* 协议上限 500 MiB */
	p.packet_size = 32 * 1024;                  /* 分块 32 KiB —— 改了两端要一起改 */
	(void) p;                                   /* 本示例保持默认；要改就在 TcpReceiveTask::start(p) 传进去 */
}

/* ------------------------------------------------------------------ *
 * 4) 典型用法（放进合适的生命周期里调用）
 * ------------------------------------------------------------------ */
void mp_transfer_example_main() {
	registerListener();
	startMpTransfer();

	/* …应用运行，小程序随时发现并传文件；onFileAdded 里拿结果… */

	stopMpTransfer();
	unregisterListener();
}

/* ------------------------------------------------------------------ *
 * 5) PC 侧联调（不接设备先验协议链路）——纯标准库，Python ≥3.9
 *
 *   py .\src\python\receiver.py --name PythonFrame --output .\received
 *   # 多网卡/VPN： --bind <本机IP> --broadcast <子网广播地址> --verbose
 *
 *   期望：手机小程序能发现 "PythonFrame" 并传图；收到的文件长度与发送端一致。
 * ------------------------------------------------------------------ */
