---
title: C++基础知识
---

这一章节主要针对没有C++基础的同学开设的，主要讲解一下我们系统中常用C++语法及常用类。

## 类
提到C++就不得不先提一下类，也不要想得太复杂，把它当C语言中的结构体来理解就可以了。

```c++
// C
struct Position {
 int left;
 int top;
 int width;
 int height;
};

// C++
class Position {
public:
 int left;
 int top;
 int width;
 int height;
};
```

类里可以直接定义函数，C语言中的结构体是定义函数指针。在我们框架中常用的例子：

```c++
// 设置文本内容
mTextView1Ptr->setText("Hello");
```

## 常用类

### string类
string类就是对字符串进行了一些封装，并提供了大量函数。只需要知道一个函数：c_str()

```c++
// 输入框回调接口
static void onEditTextChanged_Edittext1(const std::string &text) {
 const char *pStr = text.c_str();
}
```

## 格式化输出函数snprintf

### 函数原型

```c++
int snprintf(char* dest_str, size_t size, const char* format, ...);
```

### 格式化参数
- %d 十进制有符号整数
- %u 十进制无符号整数
- %f 浮点数
- %s 字符串
- %c 单个字符
- %x, %X 无符号以十六进制表示的整数

### 例子

```c++
char buf[64] = {0};
snprintf(buf, sizeof(buf), "%d", 314);
snprintf(buf, sizeof(buf), "%05d", 314); // 前面补0
snprintf(buf, sizeof(buf), "%f", 3.14);
snprintf(buf, sizeof(buf), "%06.3f", 3.14); // 6字符宽度，3位小数
```
