/*
 * VinylWorker.cpp - 后台任务执行器实现
 */
#include "zk_vinyl_worker.h"

#include <deque>
#include <pthread.h>
#include <unistd.h>

#include <base/log.h>

namespace zk {

struct VinylWorker::Impl {
    std::deque<std::function<void()> > q;
    pthread_mutex_t mx;
    pthread_t tid;
    volatile bool quit;
    long long done;
    Impl() : tid(0), quit(false), done(0) {
        pthread_mutex_init(&mx, NULL);
    }
};

VinylWorker::VinylWorker() : mImpl(NULL) {
}

VinylWorker &VinylWorker::instance() {
    static VinylWorker sInst;
    return sInst;
}

void *VinylWorker::trampoline(void *user) {
    ((VinylWorker *) user)->loop();
    return NULL;
}

void VinylWorker::loop() {
    while (!mImpl->quit) {
        std::function<void()> fn;
        pthread_mutex_lock(&mImpl->mx);
        if (!mImpl->q.empty()) {
            fn = mImpl->q.front();
            mImpl->q.pop_front();
        }
        pthread_mutex_unlock(&mImpl->mx);
        if (!fn) {
            usleep(10 * 1000);
            continue;
        }
        fn();
        pthread_mutex_lock(&mImpl->mx);
        ++mImpl->done;
        pthread_mutex_unlock(&mImpl->mx);
    }
}

void VinylWorker::start() {
    if (mImpl != NULL) {
        return;
    }
    Impl *im = new Impl();
    mImpl = im;
    if (pthread_create(&im->tid, NULL, &VinylWorker::trampoline, this) != 0) {
        LOGE_TRACE("VinylWorker 线程创建失败");
        im->tid = 0;
    } else {
        LOGD_TRACE("VinylWorker started");
    }
}

void VinylWorker::post(const std::function<void()> &fn) {
    start();
    pthread_mutex_lock(&mImpl->mx);
    mImpl->q.push_back(fn);
    pthread_mutex_unlock(&mImpl->mx);
}

long long VinylWorker::doneCount() const {
    if (mImpl == NULL) {
        return 0;
    }
    pthread_mutex_lock(&((Impl *) mImpl)->mx);
    const long long d = mImpl->done;
    pthread_mutex_unlock(&((Impl *) mImpl)->mx);
    return d;
}

int VinylWorker::pendingCount() const {
    if (mImpl == NULL) {
        return 0;
    }
    pthread_mutex_lock(&((Impl *) mImpl)->mx);
    const int n = (int) mImpl->q.size();
    pthread_mutex_unlock(&((Impl *) mImpl)->mx);
    return n;
}

void VinylWorker::stop() {
    if (mImpl == NULL) {
        return;
    }
    mImpl->quit = true;
}

} /* namespace zk */
