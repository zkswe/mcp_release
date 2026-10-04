---
title: 切换平台
---

## 切换平台
双击Manifest.xml，开始修改项目配置。
通常，不同的平台表示不同的芯片。
 项目平台与设备保持一致，才能正常运行。
 在项目平台下拉框中，可以直接切换项目平台，更改后，记得按Ctrl-S 保存。

开发工具会根据当前平台生成对应的宏定义，代码中，可以通过宏定义，判断当前平台。

```c++
#if __PLATFORM_Z6S__
// Z6S平台
#elif __PLATFORM_A33NOR__
// A33NOR 平台
#elif __PLATFORM_Z21__
//Z21平台
#elif __PLATFORM_Z20__
//Z20平台
#elif __PLATFORM_Z261__
//Z261平台
#elif __PLATFORM_T113__
//T113平台
#elif __PLATFORM_T113EMMC__
//T113EMMC平台
#elif __PLATFORM_V85X__
//V85X平台
#endif
```

当你的项目需要在多个平台上运行时，建议你根据宏进行条件编译，这样你只需在多个平台上维护一份代码。
