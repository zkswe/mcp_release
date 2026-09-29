/****** activity 侧：sButtonCallbackTab 按键注册片段（照抄进 src/activity/mainActivity.cpp） ******
 *  漏了这一步 = 按钮点了没反应（无日志、无结果）。
 *  ID_MAIN_<Caption> 由构建生成在 .fun/<平台>/generated/ui_main.h。
 */
static S_ButtonCallback sButtonCallbackTab[] = {
    ID_MAIN_ButtonWifiOn, onButtonClick_ButtonWifiOn,
    ID_MAIN_ButtonWifiOff, onButtonClick_ButtonWifiOff,
    ID_MAIN_ButtonScan, onButtonClick_ButtonScan,
    ID_MAIN_ButtonConnect, onButtonClick_ButtonConnect,
    ID_MAIN_ButtonDisconnect, onButtonClick_ButtonDisconnect,
    ID_MAIN_ButtonNetInfo, onButtonClick_ButtonNetInfo,
    ID_MAIN_ButtonNetUtils, onButtonClick_ButtonNetUtils,
    ID_MAIN_ButtonSoftAp, onButtonClick_ButtonSoftAp,
    ID_MAIN_ButtonChannel, onButtonClick_ButtonChannel,
    ID_MAIN_ButtonAuto, onButtonClick_ButtonAuto,
};
