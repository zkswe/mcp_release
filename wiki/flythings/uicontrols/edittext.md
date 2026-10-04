---
title: 编辑/输入框
---

## 编辑/输入框

## 我需要数字键盘， 我需要用户手动输入中文，怎么办？

## 如何添加编辑/输入框
如果需要数字及中文输入，利用现有的编辑/输入框控件就可以快速实现。具体操作步骤如下：

- 双击打开main.ftu文件
- 在右侧控件集合中找到编辑/输入框控件
- 鼠标左键点击编辑/输入框控件不放，然后将其拖拽到任意位置，松开左键，就能看到自动编辑/输入框的控件。
- 在右侧属性中，根据需要选择 文本类型， 如果你需要输入中文，那就将 文本类型 选择为 全文本， 并且在 项目属性 中开启拼音输入法。
- 当下载运行到机器上，点击编辑/输入框控件，会自动打开一个系统内置输入法或者数字键盘，这样就可以输入文字或数字了。

默认的编辑/输入框为白色，你可以在右侧的属性表里自定义外观样式。其中关于编辑/输入框的相关属性有如下几个：

- 是否为密码框输入 如果选择是，当模拟键盘输入时，正在键入的字符会显示为指定的密码字符，否则无变化
- 密码字符 如果是否为密码输入选择是，正在键入的字符会显示为指定的密码字符，否则无变化
- 文本类型 该属性有两个选项，分别是 全文本 表示可以输入中英文及数字，不受限制。
- 仅数字 表示只能输入数字，其他受限。

- 提示文本 当模拟键盘中内容为空时，会自动显示提示文本。
- 提示文本颜色 当模拟键盘中内容为空时，会自动显示提示文本，该文本颜色为指定的颜色。

## 如何得到模拟键盘的输入内容？
当成功创建了编辑/输入框，选择 编译FlyThings ，会自动生成它的关联函数，
 打开工程目录下的jni/logic/****Logic.cc文件(****表示UI文件名 )，找到自动生成的函数
 （XXXX表示控件ID名）[了解更多控件的关联函数](./relation_function.html)

```c++
static void onEditTextChanged_XXXX(const std::string &text) {
 //LOGD("当前输入的内容为 %s \n", text.c_str());
}
```

当模拟键盘输入内容结束后，系统会自动调用该函数，参数text就是当前模拟键盘上的完整字符串。
std::string 是c++语言类型的字符串。还可以通过如下语句，得到C语言形式的字符串指针。

```c++
const char* str = text.c_str();
```

## 如何将字符串转为数字？
编辑框的关联函数中，我们只能得到字符串，所以，当我们输入数字时，需要自行将数字字符串转为数字。

- atoi函数可以将字符串转为对应的数字，比如 "212" 可以转为整形 213 如果遇到非法字符，会造成转换失败或者中断解析。例如：atoi("213abc"); 返回 213，atoi("abc"); 返回 0

```c++
static void onEditTextChanged_EditText1(const std::string &text) {
 int number = atoi(text.c_str());
 LOGD("字符串转为数字 = %d", number);
}
```

- atof函数可以将字符串转为对应的浮点数，比如 "3.14" 可以转为浮点数 3.14 如果遇到非法字符，会造成转换失败或者中断解析。

```c++
static void onEditTextChanged_EditText1(const std::string &text) {
 // atof函数可以将字符串转为对应的浮点数，比如 "3.14" 可以转为整形 3.14
 //如果参数不规范，会造成转换失败，统一返回 数字 0
 double f = atof(text.c_str());
 LOGD("字符串转为浮点数 = %f", f);
}
```

## 如何自定义输入法？
除了使用默认的输入法外，我们还可以自定义输入法，[样例代码包](./demo_download.html#demo_download)中提供了演示例子ImeDemo工程。
 目前仅支持数字和字母输入的定制，带有中文输入法的界面无法自定义。
输入法界面与普通界面的实现有些区别：

- 普通界面是继承Activity实现的，输入法需要继承IMEBaseApp；
- 另外注册的方式也不一样，普通界面注册方式：REGISTER_ACTIVITY(****Activity);，输入法界面注册方式：REGISTER_SYSAPP(APP_TYPE_SYS_IME, ****Activity);(****表示UI文件名 )
这些区别ImeDemo工程中已经做好了修改，只需移植到自己工程即可：

- 将ui目录下UserIme.ftu文件拷贝到自己工程ui目录下；
- 将activity目录下UserImeActivity.h和UserImeActivity.cpp文件拷贝到自己工程activity目录下；
- 将logic目录下UserImeLogic.cc文件拷贝到自己工程logic目录下；
之后的操作与普通界面编程一致，在UserImeLogic.cc中编写逻辑；

## 如何主动打开键盘？
通常使用编辑框控件，用户点击编辑框后，系统将打开键盘，得到用户的输入。
 如果不使用编辑框，也可以主动打开键盘，或者隐藏键盘，参考如下代码

- 引入头文件

```c++
#include "IMEContext.h"
```

- 实现 IIMETextUpdateListener

```c++
namespace { //匿名命名空间

class IMETextUpdateListener: public IMEContext::IIMETextUpdateListener {
public:
 virtual void onIMETextUpdate(const std::string &text) {
 LOGD("输入内容是 %s", text.c_str());
 //显示到TextView3
 mTextView3Ptr->setText(text);

 //保存输入的内容,方便列表获得内容显示
 last_input_content = text;
 //强制列表刷新
 mListView1Ptr->refreshListView();
 }

};

//定义实例
static IMETextUpdateListener ime_text_update_listener;
}
```

- 主动打开输入法

```c++
static bool onButtonClick_Button1(ZKButton *pButton) {
 static IMEContext::SIMETextInfo info;
 info.imeTextType = IMEContext::E_IME_TEXT_TYPE_NUMBER; //数字键盘
 info.isPassword = false; //非密码
 info.text = ""; //默认内容为空

 //showIME调用参数有平台差异
#if 0 // 适用于Z11S,Z6,Z6s,A33平台
 EASYUICONTEXT->showIME(info, &ime_text_update_listener);
#endif

#if 1 // 适用于H500S,Z20,Z21,Z261,T113等平台
 EASYUICONTEXT->showIME(&info, &ime_text_update_listener);
#endif
 return false;
}
```

- 也可以主动隐藏键盘

```c++
EASYUICONTEXT->hideIME();
```

- 还可以检查当前输入法是否已经显示

```c++
EASYUICONTEXT->isIMEShow();
```
