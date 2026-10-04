---
title: 音频播放
---

创建 ZKMediaPlayer对象，类型为 ZKMediaPlayer::E_MEDIA_TYPE_AUDIO

```c++
static ZKMediaPlayer sPlayer(ZKMediaPlayer::E_MEDIA_TYPE_AUDIO);
```

注册消息监听

```c++
// 消息监听接口如下
class PlayerMessageListener : public ZKMediaPlayer::IPlayerMessageListener {
public:
 virtual void onPlayerMessage(ZKMediaPlayer *pMediaPlayer, int msg, void *pMsgData) {
 switch (msg) {
 case ZKMediaPlayer::E_MSGTYPE_ERROR_INVALID_FILEPATH:
 case ZKMediaPlayer::E_MSGTYPE_ERROR_MEDIA_ERROR:
 // 出错消息
 break;

 case ZKMediaPlayer::E_MSGTYPE_PLAY_STARTED:
 // 开始播放消息
 break;

 case ZKMediaPlayer::E_MSGTYPE_PLAY_COMPLETED:
 // 播放结束消息
 break;
 }
 }
};
static PlayerMessageListener sPlayerMessageListener;

// 注册消息监听
sPlayer.setPlayerMessageListener(&sPlayerMessageListener);
```

操作接口说明

```c++
sPlayer.play("/mnt/extsd/music/test.mp3"); // 播放指定路径的文件
sPlayer.pause(); // 暂停播放
sPlayer.resume(); // 恢复播放
sPlayer.seekTo(int msec); // 跳转到msec时间播放， msec 单位: ms
sPlayer.stop(); // 停止播放
sPlayer.isPlaying(); // 是否播放中，返回bool型

sPlayer.getDuration(); // 获取当前播放歌曲的总时间
sPlayer.getCurrentPosition(); // 获取当前播放歌曲的当前播放时间点

// Z6、Z11、A33平台设置音量接口为2个参数
sPlayer.setVolume(0.5, 0.5); // 设置媒体音量，音量范围：0.0 ~ 1.0
// H500S、Z20、Z21及之后的平台设置音量接口为1个参数
sPlayer.setVolume(0.5); // 设置媒体音量，音量范围：0.0 ~ 1.0
```

> **注意**：播放的音频文件不能过短，时间过短可能导致无法正常播放。

完整代码见[样例代码](./demo_download.html#demo_download.md) 控件样例里的 MusicDemo 工程
