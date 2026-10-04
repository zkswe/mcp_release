---
title: 动图
---

可以在屏幕中显示GIF文件。暂时只支持Z20、Z21、T113、T113STDCXX、T113EMMC、Z261、V85X这几个平台。

## 如何使用
首先在UI文件中创建一个 动图 控件，再设置 动图 属性中的动图文件和循环次数，如果动图需要不断的循环显示，循环次数设置为小于等于0，动图实际显示的大小会根据动图控件设置的大小缩放。

## 代码操作

```c++
/**
 * @brief 播放
 */
void play(const std::string &file);

/**
 * @brief 停止播放
 */
void stop();

/**
 * @brief 暂停播放
 */
void pause();

/**
 * @brief 恢复播放
 */
void resume();

/**
 * @brief 设置循环次数
 * @param count <=0 持续循环播放, >0 播放count次后停止播放
 */
void setLoopCount(int count);

/**
 * @brief 获取图像宽度
 */
int getImageWidth() const;

/**
 * @brief 获取图像高度
 */
int getImageHeight() const;
```

## 样例代码
具体动图控件的使用，参考[样例代码](./demo_download.html#demo_download)中的ImageAnimDemo项目。
