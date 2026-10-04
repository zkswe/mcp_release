---
title: 线程
---

系统支持pthread线程，如果你了解pthread接口，也可以用posix接口实现线程。另外，我们还提供一个对pthread的封装类。

## 线程的使用

- 引入头文件，继承Thread类，实现virtual bool threadLoop()函数。

```c++
#include <system/Thread.h>

class MyThread: public Thread {
public:
 virtual bool readyToRun() {
 LOGD("Thread 已经创建完成");
 return true;
 }

 virtual bool threadLoop() {
 LOGD("线程循环函数");
 if (exitPending()) {
 return false;
 }
 loop_count += 1;
 mTextView2Ptr->setText(loop_count);
 usleep(1000 * 500);
 return true;
 }
};
```

- 实例化线程对象

```c++
static MyThread my_thread;
```

- 启动线程

```c++
my_thread.run("this is thread name");
```

- 停止线程
  - requestExitAndWait()：请求退出线程并等待完成
  - requestExit()：请求退出线程，立即返回

```c++
my_thread.requestExitAndWait();
my_thread.requestExit();
```

- 判断线程是否还在运行

```c++
if (my_thread.isRunning()) {
 mTextView4Ptr->setText("正在运行");
} else {
 mTextView4Ptr->setText("已停止");
}
```

注意：禁止在threadLoop函数中调用requestExitAndWait和requestExit函数，可能造成死锁。

## 样例代码
见[样例代码](./demo_download.html#demo_download)中的ThreadDemo工程
