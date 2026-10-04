---
title: 文件读写
---

如果你熟悉标准C语言的文件读写，可以按照标准C语言的方式读写文件。或者使用base-utility依赖包中提供的函数。

在项目下的Manifest.xml中，添加依赖包 base-utility。

```c++
#include <base/base.h>
```

## 写文件

```c++
const char* filename = "/mnt/extsd/123.txt";
const char* str = "0123456789";
base::writeFile(filename, str);
base::writeFile(filename, str, strlen(str));
sync(); //写文件结束后调用该函数，确保写入完整
```

## 追加文件

```c++
const char* filename = "/mnt/extsd/123.txt";
base::appendFile(filename, "abcd", 4);
base::appendFile(filename, "abcd");
sync();
```

## 读文件

```c++
const char* filename = "/mnt/extsd/123.txt";
std::string content = base::readFile(filename);
```

警告：base::readFile函数将读取文件的所有内容到内存中，如果文件过大，内存可能不足。
