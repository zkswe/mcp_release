---
title: 制作静态库或动态库
---

## 制作静态库或动态库
双击打开Manifest.xml，切换到源文件视角，可以直接编辑文件，按规则添加target标签，可以制作静态链接库或动态链接库。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xml>
<manifest platform="Z21">
	<dependencies>
 <package id="easyui" version="0.0.0" />
 <package id="log" version="0.0.0" />
 <package id="zkhardware" version="0.0.0" />
 <package id="zknet" version="0.0.0" />
	</dependencies>

	<targets>
 <!-- 生成libfoo1.a 静态链接库 -->
 <target id="foo1" type="staticLibrary">
 <header filter="src/foo/hello.h" />
 <!-- subdirectory 可指定目标子目录 -->
 <header filter="src/foo/hello.h" subdirectory="foo"/>
 <source filter="src/foo/hello.cpp" />
 </target>

 <!-- 生成libfoo2.so 动态链接库 -->
 <target id="foo2" type="sharedLibrary">
 <header filter="src/foo/hello.h" />
 <source filter="src/foo/hello.cpp" />
 </target>
	</targets>

</manifest>
```

target的id属性表示库名称，type表示库的类型， staticLibrary 表示静态链接库， sharedLibrary 表示动态链接库。
header元素 用于指定需要随库提供的头文件，filter属性表示文件的路径，支持通配符。
source元素 用于指定需要编译成库的源文件，filter属性表示文件的路径，支持通配符。
 可以根据情况，添加多个 header 及 source 元素。
编译项目后，静态链接库和动态链接库将生成到 Release目录下。
