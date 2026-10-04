---
title: 涂鸦厨电/云食谱专项（Z20 + tuyaoscxx）
---

# 涂鸦厨电专项：Z20 + tuyaoscxx（TuyaOS）

> ⚠️ **专项文档**：仅当用户问题涉及 **涂鸦 / TuyaOS / 涂鸦食谱 / 在线食谱 / 云食谱 / 智能厨电上云 / 配网绑定（二维码）** 等场景时才关联本文。
> 常规 UI 布局、控件、工程创建等问题**不要**引用本文，避免干扰常规客户需求。
> 适用平台：**Z20**（Manifest `platform="Z20"`）。

## 方案概述
- Z20 平台原生支持涂鸦云：配网（二维码激活）、DP 点上报/下发、云食谱、收藏评分、OTA 等能力全在 **`tuyaoscxx`** 包里，客户无需直接碰 TuyaOS C SDK
- 参考工程：`Z20_TuyaCaiPu`（涂鸦厨电，**双区烹饪**：左/右灶独立控制）
- 配套：`TuyaDataPointCodeGen`（DP 点 JSON → 头文件自动生成）、`lib-tuyaos`（TuyaOS SDK 使用参考）

## 依赖（Manifest.xml）
```xml
<manifest platform="Z20">
  <dependencies enableOnPlatforms="Z20">
    <package id="easyui" version="3.0.0"/>
    <package id="log" version="0.0.0"/>
    <package id="zkhardware" version="0.0.0"/>
    <package id="zknet" version="0.0.0"/>
    <package id="tuyaoscxx" version="最新版"/>   <!-- 涂鸦核心包 -->
    <package id="base-utility" version="10.3.0"/>
    <package id="base-json" version="3.0.0"/>
  </dependencies>
</manifest>
```
- `tuyaoscxx` 仅 Z20 平台有，新工程拉最新版
- 内部头文件：`tuyacxx/tuya_os.h`、`tuya/tuya_cloud_types.h`、`tuya/tuya_iot_internal_api.h`、`tuya/ty_cJSON.h`

## 工程结构（src/）
| 目录/文件 | 职责 |
|-----------|------|
| `core/TuYaInit.h/.cpp` | 涂鸦初始化（Configuration + 5 个 listener）+ 状态管理单例 |
| `core/BurnTuYa.h/.cpp` | 烧录涂鸦账号（读写 UUID/Key） |
| `core/TuYaCallBack.h/.cpp` | DP 回调分发（AddCallback/delCallback/UpdateCallback） |
| `core/tuya_data_manager.hpp/.cpp` | DataManager 单例（`#define TUYA`），DP 缓存 + 上报封装 |
| `core/tuya_data_point.h/.cpp` | DP 点枚举 + 上报函数（TuyaDataPointCodeGen 生成） |
| `core/tuya_atop_interface.h/.cpp` | ATOP 云接口（食谱/收藏/评分/banner/自定义食谱） |
| `core/tuya_recipe_struct.h` | 食谱数据结构 |
| `logic/mainLogic.cc` | 配网状态机 UI + DP 下发回调处理 |
| `logic/CloudRecipeLogic.cc` | 云食谱页逻辑（ATOP 调用示例） |

## 初始化流程
```cpp
void TuYa::InItTuYa() {
  tuya::Configuration conf;
  conf.version = "1.0.0";
  conf.pid = PID;                        // 产品 ID（涂鸦后台申请）
  conf.uuid = BURNTUYAD->RetUuid();      // 设备授权 UUID（烧录/测试）
  conf.authkey = BURNTUYAD->RetKey();    // 设备授权 Key
  conf.database_dir = "/data/";
  conf.log_level = TAL_LOG_LEVEL_ERR;
  conf.data_point_change_listener = onDataPointChange;  // DP 下发回调
  conf.activate_listener = onActivate;                 // 激活（返回配网 URL）
  conf.network_state_listener = onNetworkChange;       // 网络状态
  conf.reset_listener = onReset;                       // 重置
  conf.status_change_listener = onCloudStatusChange;   // 云端状态
  tuya::TuyaOS::instance().init(conf);
}
```
- **启动条件**：WiFi 已连接才初始化（线程轮询 `WIFIMANAGER->isConnected()`，500ms）
- 网络设备：`setenv("TUYA_NET_DEV", "wlan0", 1)`（可选 wlan1/eth0/eth1）
- **测试授权**：可用 `#define TUYATEST` 内置测试 UUID/AUTHKEY，正式版读烧录授权码
- 设备重置：`tuya::TuyaOS::instance().reset()` + `setprop ctl.restart zkswe` 重启涂鸦应用

## 配网状态机（TuYaStatic）
| 状态 | 含义 | UI |
|------|------|-----|
| 0 | 重置 | 显示二维码（绑定窗） |
| 1 | 激活 | 显示二维码（绑定窗） |
| 2 | 第一次使用 | 显示二维码（绑定窗） |
| 3 | 正常 | 主界面（解绑窗） |
| 4 | 蓝牙激活/绑定完成 | WiFi 窗 |

- 二维码：`mDeviceQRPtr->loadQRCode(TUYAINIT->RetURL().c_str())`
- 网络回调：`GB_STAT_LAN_UNCONN/LAN_CONN/CLOUD_CONN`，云连接后上报初始状态
- 天气（可选）：`tuya::TuyaOS::instance().getWeather(&weather)`

## DP 点体系（产品能力核心）
`DataPointID` 枚举（涂鸦后台定义，工具自动生成）：
```cpp
DP_SWITCH = 1,  DP_STATUS = 6,  DP_MULTISTEP = 13,  DP_FAULT = 14,
DP_CLOUD_RECIPE_ID = 22,  DP_COOKING_HISTORY_ID = 23,  DP_POWER_CONSUMPTION = 101,
DP_POWER_LEFT = 102,  DP_STATUS_LEFT = 103,  DP_RUNTIME_TOTAL = 104,
DP_RUNTIME_TOTAL_RESET = 105,  DP_CHILD_LOCK = 106,  DP_POWER_RIGHT = 107,
DP_TIME_LEFT = 108,  DP_TIME_RIGHT = 109,  DP_REMAIN_LEFT = 110,  DP_REMAIN_RIGHT = 111,
DP_STATUS_RIGHT = 112,  DP_ESTIMATED_LEFT = 113,  DP_ESTIMATED_RIGHT = 114,  DP_RECIPE_ZONE = 115,
```
**双区烹饪**：左右灶独立 功率/状态/时间/剩余时间/预估温度，`DP_RECIPE_ZONE` 切区（LEFT=0/RIGHT=1）。
状态枚举：`STANDBY/APPOINTMENT/COOKING/DONE`；左/右状态：`STANDBY/DONE/OFF/RECIPE/BASIC/PAUSED`。

### 上报（设备→云）
```cpp
TUYA.setSwitch(on);                  // 开关
TUYA.setChildLock(on);               // 童锁
TUYA.setRuntimeTotalReset(on);       // 复位累计时间
TUYA.setEstimatedLeft(progress);     // 预估温度左
TUYA.setPowerLeft(10);               // 功率左 0~10
TUYA.setStatusLeft(2);               // 状态左
TUYA.setCloudRecipeId(data, len);    // 云食谱 ID
TUYA.setCookingHistoryId(data, len); // 烹饪历史 ID
TUYA.setMultistep(data, len);        // 多步骤执行
TUYA.setFault(code);                 // 故障告警
```
### 下发（云→设备，onDataPointChange 回调）
```cpp
static bool TuYaData(const tuya::DataPoint& dp) {
  switch (dp.id) {
    case tuya::DP_SWITCH:  mSwitchPtr->setSelected(dp.data.cast<bool>()); break;
    case tuya::DP_CLOUD_RECIPE_ID: ... // App 一键烹饪
    case tuya::DP_RECIPE_ZONE: zoneInit(zone); break;
  }
}
// 注册：TUYACALLBACK->AddCallback(TuYaData);  注销：delCallback
```
- 数据类型：`dp.data.cast<int>/float/bool/std::string`
- 回调里刷新 UI，耗时逻辑别放回调里

## ATOP 云接口（云食谱/内容运营）
```cpp
int getMenuCategoryList1(lang, list);          // 食谱一级分类
int getMenuCategoryList2(lang, list);          // 食谱分类（含二级）
int getPagedRecipes(lang, result, page, size); // 分页食谱（size 最大 500）
int getRecipeDetail(lang, menuId, out);        // 食谱详情
int getCustomRecipeList(...);                  // C 端自定义食谱列表
int upsertCustomRecipe(recipe, out_id);        // 增/改自定义食谱
int deleteCustomRecipe(recipe_id);             // 删自定义食谱
int getUserStarredRecipeList(...);             // 用户收藏列表
int addRecipeCollection(id) / cancelRecipeCollection(id);  // 收藏/取消
int isStarRecipe(id, isStar);                  // 是否已收藏
int RecipeStarCount(lang, count);              // 收藏数量
int addRecipeScore(recipe_id, score);          // 评分
int getBannerList(bizType, lang, result);      // banner(1)/推荐设备(2)
int getAllCookbookLanguages(result);           // 食谱语言
int getDeviceMenuQueryModelList(result);       // 搜索模型
int getMinMaxCookTime(...);                    // 烹饪时间范围
int getDeviceMenuSyncList(lang, result);       // 设备菜单同步列表
int syncRecipeDetails(lang, menuIds, details); // 批量同步食谱详情
```
- 语言参数：`"cn" / "en" / "zh-CN"` 等
- 食谱结构体：`RecipeCategory(2)`（多语言）、`PagedRecipe`（主图/口味/难度/时间/份数/收藏）、`RecipeDetail`（图文步骤）、`CustomRecipeInfo`（自定义：主图/步骤/烹饪参数 dpCode+dpValue）

## 铁律
1. **tuyaoscxx 仅 Z20 平台**；**专项能力，常规项目不引入**
2. **必须 WiFi 已连接才 init**；网络设备名必须 setenv 指定（TUYA_NET_DEV）
3. **授权三件套**：PID（产品）+ UUID + AUTHKEY（涂鸦后台申请），测试用 TUYATEST 宏，正式读烧录
4. DP 回调刷新 UI，**不做耗时操作**；多步骤/云食谱 ID 是字符串 DP，注意长度
5. **重置流程**：`TuyaOS::reset()` + `setprop ctl.restart zkswe`（重启涂鸦服务，非整机 reboot）
6. 云食谱 ATOP 调用**要等云连接**（GB_STAT_CLOUD_CONN）后再拉数据
7. DP 头文件用 `TuyaDataPointCodeGen` 工具生成，改 DP 定义后重新生成，勿手改
8. 双区产品注意 `DP_RECIPE_ZONE` 切区同步 UI 窗口显隐
