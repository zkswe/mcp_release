---
title: 互斥量/锁
---

## 互斥量/锁

当我们的程序里引入线程后，某些情况下又会引出其他问题。多线程编程中，常见的情况是A线程对一个变量赋值，然后B线程读这个值。

如果不对共享数据的操作加上保护，可能会出现数据不一致的问题。

## 如何使用互斥量

- 定义一个互斥量

```c++
static Mutex mutex1;
```

- 在需要加锁的地方，定义局部 Mutex::Autolock 类实例加锁。

```c++
Mutex::Autolock _l(mutex1);
```

结合A、B线程的例子：

```c++
#include <system/Thread.h>

struct Student {
 char name[24];
 int age;
 int number;
};

struct Student student = {0};
static Mutex mutext1;

class AThread: public Thread {
public:
 virtual bool threadLoop() {
 Mutex::Autolock _lock(mutext1);
 snprintf(student.name, sizeof(student.name), "xiaoming");
 student.age = 10;
 student.number = 20200101;
 return true;
 }
};

class BThread: public Thread {
public:
 virtual bool threadLoop() {
 Mutex::Autolock _lock(mutext1);
 struct Student s = student;
 LOGD("姓名：%s", s.name);
 LOGD("年龄：%d", s.age);
 LOGD("学号：%d", s.number);
 return true;
 }
};
```

使用互斥量后，使得被加锁的代码部分，能够互斥执行，且保证完整性。

项目中用到互斥量的例子，见源码 jni/uart/ProtocolParser.cpp。
