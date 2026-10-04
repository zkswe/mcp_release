---
id: devflow-symptom-index
title: 现场症状索引（用户原话 → 机制/规范 → 权威文档，由 symptom_spec.json 派生）
category: devflow
status: review
confidence: manual
verified_at: 2026-10-04
stale_days: 180
origin: derived
source: 由 symptom_spec.json 派生（scripts/gen_symptom_doc.py）
needs_evidence: false
platforms: []
tags: [现场症状, 症状索引, 切一下才显示, 拖不动, 点了没反应, 界面文件乱码, 推上去没效果, 图标发糊, 图片有锯齿, client_id 互踢, 串口收不全, 半包重组, 第二次进页面空白, 改了没生效, 返回再进页面就不对, 改了数据界面没变]
evidence:
  - cmd: python scripts/gen_symptom_doc.py --check
    expect: rc=0（本页与 symptom_spec.json 一致）
---
# 现场症状索引（用户原话 → 机制 → 规范 → 权威文档）

> ⚠️ **本页是派生物，不要手改**（由 `symptom_spec.json` 派生，`--check` 进闸门）。
> 新增症状请改注册表：`symptom_spec.json`。
> 
> 用法：用户描述的是**症状**，本页把症状落到**机制与规范**，并给权威文档。
> 先按「能不能从设计端消灭」判断：能在判据/工具/模板层消灭的坑，不该只留记录。

## 切一下才显示 / 返回再进页面就不对 / 第二次进页面空白 / 改了数据界面没变

- **机制**：整屏 window 切换走的是重绘而不是重建；控件值在进入前写、或没触发重绘，画面就停在旧帧。
- **规范**：页面数据在 onUI_show() 里写，并显式触发重绘；不要只在构造/首次加载时写。
- **权威文档**：`knowledge/devflow/activity-code-skeleton.md`
- **怎么复验**：真机连续「进入 → 返回 → 再进入」，看 logcat 的 onUI_show 与画面是否一致（截图连抓两帧取第二张）。

## 拖不动 / 点了没反应 / 不跟手 / 一拖就卡死

- **机制**：触摸分发只发给 touchable=true 的控件；可交互控件若没显式打开触摸，事件根本不进回调。另有回调里做耗时活（滚动时逐行调用）会表现为卡死。
- **规范**：交互控件 json 必须显式 touchable=true；obtainListItemData_* 等高频回调里禁止耗时操作。
- **权威文档**：`knowledge/uicontrols/touch-events.md`
- **怎么复验**：真机注入点击/拖拽（bin_tools/<平台>/touch），看 logcat 是否收到对应回调。

## 界面文件打开是乱码 / 界面文件看不懂 / json 和 ftu 什么关系

- **机制**：设备加载的是 .ftu（fui pack 的编译产物）；.json 才是可读布局源。
- **规范**：改布局改 .json 再 pack；要读现有界面用 fui unpack 反解析成 json，不要直接编辑二进制。
- **权威文档**：`knowledge/devflow/ftu-json-pipeline.md`
- **怎么复验**：fui unpack <x.ftu> → 得到同名 json，字段可读。

## 推上去没效果 / 设备上还是旧的 / 改了像没改

- **机制**：推送成功 ≠ 设备在跑新版：同名旧程序/旧库仍可被加载（如 SD 上的 EasyUI.cfg 劫持、名字相同覆盖失败）。
- **规范**：推送后必须比对设备侧与本地产物（md5 或大小），staleOnDevice=true 即设备旧版，按升级/重推处理。
- **权威文档**：`knowledge/devflow/device-deploy-budget.md`
- **怎么复验**：走 build_ui_flow 的设备侧比对；或设备上直接量文件大小/时间戳。

## 图标发糊 / 图片有锯齿 / 图被拉长/变形 / 弧线毛边

- **机制**：引擎对「图 ≠ 控件盒」是拉伸不报错；二值 mask 当 α 用会把圆弧过渡压成硬阶梯。
- **规范**：自动生成切图尺寸必须严格等于控件盒（圆角/圆弧走超采样 + 面积平均），形状外真透明。
- **权威文档**：`knowledge/devflow/ui-layout-verify.md`
- **怎么复验**：python ui_tools/check_all.py <项目>（第 21/22/23 项：AA/倒角/底板）+ 真机截图比对。

## 两台设备互相顶掉 / client_id 互踢 / 刚连上就被断开

- **机制**：MQTT 服务端对同一 client_id 只保留一个会话，后来者会把先来者踢下线。
- **规范**：每台设备用唯一 client_id（含序列号等设备标识），不要用固定串或默认值。
- **权威文档**：`knowledge/devflow/mqtt-client-lifecycle.md`
- **怎么复验**：两台设备同时上线，看是否互相掉线；日志里看 CONNACK/断连原因。

## 串口收不全 / 半包怎么重组 / 报文粘包

- **机制**：串口是字节流：一帧可能被拆成多次中断、或多帧粘在一起。MCP 侧只对接「接进来之后」的约定（生命周期接线 / SProtocolData 共享变量 / listener 线程模型）。
- **规范**：帧的切分与校验归协议层（解析器）负责；业务回调只处理解析完的一帧，别在回调里自己拼半包。
- **权威文档**：`knowledge/devflow/uart-protocol-framework.md`
- **怎么复验**：发一条跨两次写入的帧，看 onProtocolDataUpdate 是否只被调用一次且数据完整。

