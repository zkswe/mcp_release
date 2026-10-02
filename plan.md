# AI 需要采用当前MCP的开发FlyThings的根因
1. FlyThings UI文件ftu(json 压缩文件AI不认识解析不了)，需要这个来配合AI生成以及理解他是什么样子的
2. FlyThings APP 的框架有一个libeasyui在底层，有自己的生命周期以及自己控件的API，也就是wiki里面的知识
3. FlyThings OS基于Linux构建，文件系统不开源，配套硬件有固定的分区和打包img以及升级安装的方法。就是fun pack的动作。这个也是专属知识；
4. FlyThings 也提供了嵌入式硬件相关的标准化硬件API 比如IIC，SPI，GPIO，ADC,PWM等接口能力，这个是专有知识
5. FlyThings 也为多媒体音视频播放，录音提供了标准化的API。解决嵌入式多媒体不同硬件不同的差异问题。
6. FlyThigns 提供了一些组件包让AI开发更加便捷。
7. 在训练过程中，AI也在components目录下生成了一下可以复用的lib库或者样例代码组件让后期的AI开发起来更加快速以此来达到更便捷高效的开发


#  FlyThings AI MCP目标是解决：
1. 让AI开发FlyThings 应用的时候不管是UI还是业务功能逻辑甚至是通讯协议对接调试都是跟开发网页前端或者Android APP一样。无限接近AI原生能力
2. 让开发者在移植第三方软件或者功能的时候更加高效
3. 让开发者在FlyThings 上面做代码修改，UI替代更加方便。

# FlyThings UI基础框架
1. ftu(json)为UI的layout文件
2. activity或者是.fsc下的文件为系统基于ftu生成的基础关联代码。用户逻辑代码落到logic目录下，实现和真实业务功能关联
3. acitivity 有自己的生命周期
4. libeasyui 是FlyThings UI引擎以及界面框架。有activity生命周期，有2D图形加速，有视频UI图层叠加能力。