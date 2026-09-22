/*
 * VinylWorker.hpp - 极简后台任务执行器（CloudMusic-F133）
 *
 * 为什么需要：设备侧所有网络调用（搜索/歌单/歌词/封面）都是同步阻塞的（最长 8s），
 * **绝不能放在 UI 线程**（会把整页卡住）。这里给一个单线程串行执行器：
 *   · post(fn)：把任务丢进队列，由后台线程按序执行；
 *   · 任务体自己负责「把结果写进 static 变量 + 加锁 + 递增版本号」，
 *     UI 定时器看到版本号变化再刷新控件（标准的生产者/消费者分工）。
 * 只用标准库（pthread + std::function），不依赖任何三方包。
 */
#ifndef _ZK_VINYL_WORKER_H_
#define _ZK_VINYL_WORKER_H_

#include <functional>

namespace zk {

class VinylWorker {
public:
    static VinylWorker &instance();

    /** 起后台线程（幂等） */
    void start();
    /** 投递任务（FIFO 串行执行） */
    void post(const std::function<void()> &fn);
    /** 已执行任务数（诊断） */
    long long doneCount() const;
    int pendingCount() const;
    void stop();

private:
    VinylWorker();
    VinylWorker(const VinylWorker &);
    VinylWorker &operator=(const VinylWorker &);

    static void *trampoline(void *user);
    void loop();

    struct Impl;
    Impl *mImpl;
};

} /* namespace zk */

#endif /* _ZK_VINYL_WORKER_H_ */
