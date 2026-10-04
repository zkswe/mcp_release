---
title: 项目结构
---

## 项目结构

默认的项目，通常有 src 、 resources 、 ui 三个文件夹及一个Manifest.xml文件。

## ui 文件夹

展开 ui 文件夹，可以看到默认创建的 main.ftu 文件。
ftu 是UI文件的后缀名。
 每一个 ftu 文件对应一个应用界面。
 通常，一个应用包含多个界面，你可以按需在 ui 文件夹下创建多个 ftu 文件。
 添加新的 ftu 文件，可以参考 [如何新建FlyThings UI文件](./new_flythings_ui_file.html)。
 为了描述方便，在以后的教程中，统一将 ftu 文件称为 UI文件。
 你可以双击打开UI文件，对它进行编辑，可以即时预览效果。
 如何编辑 ，可以参考控件介绍相关说明。
 编辑结束后，必须主动编译一次 ([如何编译](./how_to_compile_flythings.html)），
注意
这里所说的编译不仅仅是编译源代码，还包括对 ui文件的预处理，以及生成模板代码等一系列操作，但是这些都是自动化的，你无需手动操作。编译这一动作背后的所有具体操作，请参考 [具体编译过程以及UI文件与源代码的对应关系](./ftu_and_source_relationships.html#ftu_and_source_relationships)，看完后，相信你会更容易理解，并且快速上手开发**

## resources 文件夹
该文件夹的所有内容会随着程序一起打包。 主要用来存放项目的各种资源文件，通常是一些图片。
 如果你有其他任何文件也可以添加到该文件夹。
 但是，设备自身存储空间有限，不建议将大文件存放到该目录，更推荐你将较大的资源文件存放到TF卡或者U盘等地方。
在代码中，可以获取resources目录下的某个文件的绝对路径。

```c++
#include <manager/ConfigManager.h>

std::string test_txt_path = CONFIGMANAGER->getResFilePath("test.txt");
std::string back_png_path = CONFIGMANAGER->getResFilePath("sub/back.png");
```

## src 文件夹
主要存放源码文件。

通常包含 activity 、logic 、uart 、Main.cpp

### activity 文件夹
自动生成的目录。
 每一个UI文件，在编译后，会生成相同前缀名的Activity类和Logic.cc文件。
 例如，ui文件夹下有一个 main.ftu，在编译后，会生成 mainActivity.h、mainActivity.cpp以及mainLogic.cc，
mainActivity生成在 activity 文件夹中，
mainLogic.cc生成在 logic 文件夹中。
注意
不要手动修改 activity 文件夹下自动生成的代码。

### logic 文件夹
每一个UI文件在编译后都会生成相对应前缀名的 Logic.cc 文件。
 按照设计思想，该界面的事件与控制，都应该体现在对应的Logic.cc文件中。

### uart 文件夹
该文件夹存放串口操作相关的代码，包括读写串口，协议解析等。 这只是基于linux串口接口，提供的一份简单实现，如果你有更好的方案，可以不使用它。

### Main.cpp
整个应用的入口代码，包括选择开机的界面以及一些初始化。

```c++
#include "entry/EasyUIContext.h"
#include "uart/UartContext.h"
#include "manager/ConfigManager.h"
#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

void onEasyUIInit(EasyUIContext *pContext) {
	// 初始化时打开串口， 如果不使用默认提供的串口代码，应该屏蔽这行
	UARTCONTEXT->openUart(CONFIGMANAGER->getUartName().c_str(), CONFIGMANAGER->getUartBaudRate());
}

void onEasyUIDeinit(EasyUIContext *pContext) {
	UARTCONTEXT->closeUart();
}

const char* onStartupApp(EasyUIContext *pContext) {
 //默认显示main界面，也就是 main.ftu
	return "mainActivity";
}

#ifdef __cplusplus
}
#endif /* __cplusplus */
```

## Manifest 文件
项目的清单文件。
 可以更改项目平台，增删依赖包等功能，是一个经常用到的文件。
 更详细的介绍 ，请参考 [Manifest章节](./manifest.html)
