# QRCode 二维码控件 JSON 字段规范

> 检索导引：问「二维码控件怎么用 / loadQRCode 传什么内容 / 设备 SN·MAC·蓝牙名展示绑定 / codeStr 是不是运行时内容 / 码太密扫不出」→ 本文。
> 2026-09-07 git.com 全库学习 + basedemo/QRCodeDemo-New 实测（PriceTag 价签 / 设备配网绑定场景）。

## 核心铁律

1. **二维码内容是代码动态生成**：`loadQRCode(const char* str)` 传**字符串内容**（实测价签传 JSON：`{"SN":"xxx"}`），控件自动渲染二维码。json 里的 `codeStr` 只是 IDE 预览占位。
2. **典型场景 = 设备绑定/配网信息展示**：设备 SN/蓝牙名/MAC 等拼 JSON → loadQRCode；内容随数据变化反复调用即可（PriceTag mainLogic.cc 实测）。
3. 白色背景 + 深色码默认；内容越长码越密，控件尺寸要留够（实测 216×177 能容较长 URL）。

## JSON 字段表（ftu 实测校准）

| 字段 | 类型/取值 | 说明 |
|------|----------|------|
| `caption` | string | 控件名 |
| `id` | int | 控件 id（实测 **92001** 段） |
| `codeStr` | string | IDE 预览用二维码内容（运行期由 loadQRCode 覆盖） |
| `padding` | int | 码内边距（实测 1） |
| `backgroundColor` | int | 背景色（16777215=白） |
| `touchable`/`visible`/`position` | | 通用（通常不可触摸） |

## 代码操作

```cpp
// 生成内容二维码（PriceTag 实测：SN 转十六进制串后拼 JSON）
mDeviceQRCodePtr->loadQRCode(std::string("{\"SN\":\"" + UiLayout::GetDeviceID() + "\"}").c_str());
// 或输入框实时生成（QRCodeDemo）
mQrcode1Ptr->loadQRCode(text.c_str());
```

## 样例代码
QRCodeDemo-New（EditText 输入即生成）；PriceTag（价签 SN 码 + 广告位绑定动态码）；KaiduZ9S wifiLogic.cc（配网二维码）；Z20_HaiNaiDe 菜谱工程。
