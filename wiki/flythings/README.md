# FlyThings OS 开发文档 Wiki

> 来源：https://developer.flythings.cn/zh-hans/
> 抓取时间：2026-05-31
> 共计：112 个文档页面，17 个章节

---

## 目录

### 📖 关于
- [关于我们](about/README.md) — 公司介绍、产品理念、系统架构

### 🔧 安装
- [下载安装](install/download.md) — IDE 下载、Z11S旧版、Linux工具链
- [初次使用](install/first_use.md) — IDE 环境初识
- [界面概览](install/ide_overview.md) — 开发工具布局

### 🏗 开发流程
- [入门须知](devflow/getting_started.md) — 新手快速上手指南
- [新建项目](devflow/new_project.md) — 项目创建向导
- [项目结构](devflow/project_structure.md) — src/ui/resources/Manifest.xml
- [编译项目](devflow/compile.md) — 编译流程
- [新建UI文件](devflow/new_ui_file.md) — ftu 文件创建
- [运行项目](devflow/run_project.md) — 下载调试
- [UI文件与生成代码关系](devflow/ftu_source_relation.md) — 编译原理、Logic.cc 生成
- [控件命名规则](devflow/naming_rules.md) — 指针变量名 ↔ ID 规则
- [关联函数讲解](devflow/callback_functions.md) — 按键/编辑框/滑块/列表回调
- [编辑器技巧](devflow/editor_tips.md) — 常用操作
- [导入项目](devflow/import_project.md) — 导入现有工程

### 📦 Manifest
- [Manifest 介绍](manifest/manifest_intro.md) — 配置文件概述
- [切换平台](manifest/switch_platform.md) — 平台切换操作
- [添加依赖包](manifest/add_package.md) — 依赖管理
- [添加本地库](manifest/add_local_lib.md) — 本地库配置
- [制作静态库/动态库](manifest/make_lib.md)

### 🎨 UI控件
- [通用属性](uicontrols/common_props.md) — ID/位置/背景色/背景图/显示隐藏/状态/蜂鸣器
- [文本 TextView](uicontrols/textview.md)
- [按键 Button](uicontrols/button.md)
- [复选框 CheckBox](uicontrols/checkbox.md)
- [单选组 RadioGroup](uicontrols/radiogroup.md)
- [滑块 SeekBar](uicontrols/seekbar.md)
- [指针/仪表 Pointer](uicontrols/pointer.md)
- [列表 ListView](uicontrols/listview.md)
- [波形图 Diagram](uicontrols/diagram.md)
- [圆形进度条 CircleBar](uicontrols/circlebar.md)
- [二维码 QRCode](uicontrols/qrcode.md)
- [视频 VideoView](uicontrols/video.md)
- [编辑框 EditText](uicontrols/edittext.md)
- [窗口容器 Window](uicontrols/window.md)
- [翻页窗口 PageWindow](uicontrols/pagewindow.md)
- [滚动窗口 ScrollWindow](uicontrols/scrollwindow.md)
- [滑动窗口 SlideWindow](uicontrols/slidewindow.md)
- [画布 Painter](uicontrols/painter.md)
- [动图 ImageAnim](uicontrols/imageanim.md)
- [摄像头 CameraView](uicontrols/camera.md)
- [数字时钟 DigitalClock](uicontrols/digital_clock.md)

### 🔄 界面交互
- [启动界面](interaction/launch_screen.md) — 开机首屏
- [打开/关闭界面](interaction/open_close.md)
- [界面活动周期](interaction/activity_lifecycle.md) — onCreate/onResume/onPause
- [系统内置界面](interaction/internal_screens.md)
- [系统应用](interaction/system_apps.md)

### ⏱ 定时器
- [定时器](timer/timer.md) — 基本使用
- [手动注册/停止定时器](timer/register_stop.md)

### 🔌 串口通讯
- [Linux串口编程](serial/linux_serial.md)
- [串口简介](serial/intro.md) — 通讯模型（屏作为主机端）
- [通讯框架讲解](serial/framework.md) — ProtocolParser/协议解析
- [通讯案例实战](serial/example.md)
- [串口配置](serial/configuration.md)
- [多串口配置](serial/multiuart.md)

### 🌐 网络控制
- [Wi-Fi设置](network/wifi.md)
- [以太网设置](network/ethernet.md)
- [4G设置](network/4g.md)
- [热点设置](network/hotspot.md)

### 🎵 多媒体
- [视频播放](multimedia/video.md)
- [音频播放](multimedia/audio.md)

### ⚙️ 系统操作
- [数据存储](system/data_storage.md) — 文件/SharedPreference
- [模拟EEPROM](system/virtual_eeprom.md)
- [屏幕背光操作](system/brightness.md)
- [系统时间](system/system_time.md) — 设置/获取/NTP同步
- [设备唯一ID](system/device_id.md)
- [TF卡/U盘](system/tf_usb.md)
- [插拔TF卡监听](system/tf_mount_listener.md)
- [GPIO操作](system/gpio.md)
- [SPI操作](system/spi.md)
- [I2C操作](system/i2c.md)
- [ADC操作](system/adc.md)
- [PWM操作](system/pwm.md)
- [截屏](system/screenshot.md)
- [重启系统](system/reboot.md)
- [内存和CPU信息](system/mem_cpu.md)
- [CAN总线](system/can_bus.md)

### 🌍 多国语言
- [i18n 多国语言翻译](i18n/i18n.md)

### 🔤 字体
- [设置字体](font/font_setting.md)
- [裁剪字体](font/font_cut.md)

### 📲 升级与调试
- [ADB调试](upgrade/adb_debug.md) — ADB IP配置/下载
- [查看打印日志](upgrade/logcat.md) — logcat 使用
- [从TF卡启动程序](upgrade/boot_from_sd.md)
- [升级开机LOGO](upgrade/update_logo.md)
- [制作升级镜像文件](upgrade/make_image.md) — update.img
- [自动升级](upgrade/auto_upgrade.md)
- [制作刷机卡](upgrade/sd_boot.md)
- [远程升级](upgrade/remote_update.md)
- [批量升级软件](upgrade/mass_update.md)
- [USB刷机](upgrade/usb_flash.md)
- [代码样例下载](upgrade/demo_download.md) — 各平台各分辨率样例

### 💻 Linux标准编程
- [C++基础](linux_std/cpp_basics.md)
- [文件读写](linux_std/file_io.md)
- [Socket编程](linux_std/socket.md)
- [HTTP](linux_std/http.md)
- [Sqlite](linux_std/sqlite.md)
- [MQTT](linux_std/mqtt.md)
- [MODBUS](linux_std/modbus.md)
- [编码转换](linux_std/encoding.md)
- [JSON](linux_std/json.md)
- [线程](linux_std/thread.md)
- [互斥量](linux_std/mutex.md)

### 🔩 硬件使用
- [Z210核心板使用](hardware/z210_core_board.md)
- [Sigmastar UI授权](hardware/authorization.md)

### 📎 附录
- [触摸校准](appendix/touch_calibration.md)
- [硬件使用说明](appendix/hardware_guide.md)
- [常见问题 FAQ](appendix/faq.md)
- [安装ADB驱动](appendix/adb_driver.md)
- [产品规格型号说明](appendix/product_spec.md)
- [核心模组使用教程](appendix/core_module.md)
- [脚本工具使用说明](appendix/scripts.md)
- [自动化测试](appendix/monkey_test.md)
- [虚拟触摸](appendix/virtual_touch.md)

---

> 📌 **提示**：做 FlyThings UI 项目时，可直接查阅 `wiki/flythings/` 下对应章节的 markdown 文件。
> 技术问题反馈时，可快速定位到 `appendix/faq.md` 或各控件对应文档。
