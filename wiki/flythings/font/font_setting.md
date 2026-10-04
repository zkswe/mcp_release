---
title: 设置字体
---

## 设置单字体
FlyThings系统默认打包的字体是思源黑体字体，我们可以查看项目属性：

字体选项默认勾上，编译生成的升级文件就会打包工具安装目录下相应平台font目录下的fzcircle.ttf字体库。该字体库即为思源黑体字体库，我们做了些裁剪，改名为fzcircle.ttf。

如果我们想使用其他字体库，只需去除默认选项，导入新的字体库即可（注意，这里字体库仅支持ttf格式）。

- Z6S、A33平台：系统内置有fzcircle.ttf字体库，目的是为了加快开机速度。如果有字体缺失，需要定制一个扩展字体库。导入的字体库名称不叫fzcircle.ttf即可。
- Z11S平台：系统没有内置字体库，直接使用工具打包出来的字体库。
- Z20、Z21、H500S、T113及后续平台：系统内置有fzcircle.ttf字体库，导入其他字体库后完全使用该字体库，命名没有限制。

## 设置多字体

- 在项目属性中，将字体设置为默认。
- 在项目目录下新建package.properties文件，并添加内容：enable.font.location = true
- 在项目下新建font文件夹，将字体文件拷贝到font文件夹中。
- 在代码中，调用控件的setFontFamily函数，分别指定字体。

```c++
static void onUI_init(){
 mTextView1Ptr->setText("HELLO");
 mTextView1Ptr->setFontFamily("a");//以文件名作为参数

 mTextView2Ptr->setText("HELLO");
 mTextView2Ptr->setFontFamily("b");//以文件名作为参数
}
```

注意：
- setFontFamily函数的参数是文件名（不包含.ttf后缀），而不是字体名。
- 请确认使用的easyui依赖包版本为2.2.0或更高。
- 当有多个字体时，按文件名ASCII码排序，排序最靠前的文件作为默认字体。
- 当控件没有明确设置字体时，会使用默认字体。

### 参考源码
- gitee https://gitee.com/oszksw/example-multi-font
